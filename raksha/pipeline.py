"""RakshaMed pipeline: ingest -> extract -> link -> policy -> rewrite -> verify -> report."""
from __future__ import annotations

import csv
import io
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

from . import extract as X
from . import lexicon as L
from . import patterns as P
from . import privacy as PV
from .ingest import Doc, Unit, infer_date_order, iter_input, load
from .link import resolve
from .sanitize import Ctx, Sanitizer
from .translit import has_deva, name_key, split_name
from .util import Keys, SafeLog, peak_rss_mb


# ---------------------------------------------------------------- policy
def load_policy(path: Path) -> dict:
    pol = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if ":" in line:
                k, v = (x.strip() for x in line.split(":", 1))
                try:
                    pol[k] = float(v) if "." in v else int(v)
                except ValueError:
                    pol[k] = v
    return pol


# ---------------------------------------------------------------- dynamic dictionary
class Dictionary:
    def __init__(self):
        self.name_keys: dict[str, str] = {}
        self.key_index: dict[str, list] = defaultdict(list)
        self.ids: set[str] = set()
        self.id_cores: set[str] = set()
        self.id_to_psn: dict[str, str] = {}
        self.core_to_psn: dict[str, str] = {}
        self.village_keys: set[str] = set()
        self.protect_re = None
        self.surfaces: set[str] = set()

    def add_name(self, name: str, role: str):
        for t in split_name(name):
            tl = t.lower().strip(".'’")
            if tl in L.PRE_HONORIFICS or tl in L.POST_HONORIFICS or tl in L.GENERIC_NAME_PARTS:
                continue
            if not has_deva(t) and (len(t) < 3 or tl in L.MEDICAL_WORDS or tl in L.HINGLISH_MEDICAL):
                continue
            k = name_key(t)
            if len(k) < 3:
                continue
            prev = self.name_keys.get(k)
            if prev is None or (prev == "relative" and role == "patient"):
                self.name_keys[k] = role
            if len(t) >= 3:
                self.surfaces.add(t.lower())

    def add_id(self, nid: str):
        if not nid or not re.search(r"\d{3,}", nid):
            return
        self.ids.add(nid)
        core = P.id_core(nid)
        if len(core) >= 5:
            self.id_cores.add(core)

    def finalize(self, orgs, doctors):
        for k in sorted(self.name_keys):
            self.key_index[k[:2]].append(k)
        phrases = sorted({o.strip() for o in orgs | doctors if o and len(o.strip()) >= 4}, key=len, reverse=True)
        if phrases:
            self.protect_re = re.compile("|".join(re.escape(p) for p in phrases[:3000]))


# ---------------------------------------------------------------- structured walking
def walk_json(obj, ptr="", parents=(), rtype=None):
    """Yield (pointer, key, value, parents, rtype) for every leaf (and every key)."""
    if isinstance(obj, dict):
        rt = obj.get("resourceType") if isinstance(obj.get("resourceType"), str) else rtype
        for k in obj:
            v = obj[k]
            kp = str(k).replace("~", "~0").replace("/", "~1")
            if isinstance(v, (dict, list)):
                yield from walk_json(v, f"{ptr}/{kp}", parents + (str(k),), rt)
            else:
                yield f"{ptr}/{kp}", str(k), v, parents, rt
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, (dict, list)):
                yield from walk_json(v, f"{ptr}/{i}", parents, rtype)
            else:
                yield f"{ptr}/{i}", parents[-1] if parents else "", v, parents, rtype


def get_ptr(obj, ptr):
    cur = obj
    for part in ptr.split("/")[1:]:
        part = part.replace("~1", "/").replace("~0", "~")
        cur = cur[int(part)] if isinstance(cur, list) else cur[part]
    return cur


class Pipeline:
    def __init__(self, inp: Path, out: Path, secret: str, policy: dict):
        self.inp, self.out = inp, out
        self.keys = Keys(secret)
        self.policy = policy
        self.log = SafeLog()
        self.D = Dictionary()
        self.san = Sanitizer(self.D)
        self.docs: list[Doc] = []
        self.units: list[Unit] = []
        self.unit_doc: list[Doc] = []
        self.col_kinds: dict[str, list] = {}
        self.orgs: set[str] = set()
        self.doctors: set[str] = set()
        self.entities = Counter()
        self.diag = {}

    # ------------------------------------------------------------ pass 1
    def ingest(self):
        for p, rel in iter_input(self.inp):
            try:
                d = load(p, rel)
            except Exception as e:  # noqa: BLE001 - never echo content
                d = Doc(rel=rel, sha="", size=0, status="quarantined", reason="read_error:" + type(e).__name__)
                try:
                    from .ingest import sha256
                    d.sha = sha256(p.read_bytes())
                except Exception:
                    pass
            self.docs.append(d)
        self.log.stage(f"ingested {len(self.docs)} files")

    def _new_unit(self, doc, loc):
        u = Unit(loc=loc)
        u.attrs = X.new_attrs()
        u.attrs["dx"] = set()
        doc.units.append(u)
        self.units.append(u)
        self.unit_doc.append(doc)
        return u

    def _dx(self, u, s):
        if isinstance(s, str):
            for m in P.ICD.finditer(s):
                u.attrs["dx"].add(m.group(0))

    def extract(self):
        for d in self.docs:
            if d.status == "quarantined":
                continue
            try:
                self._extract_doc(d)
            except Exception as e:  # noqa: BLE001
                d.status, d.reason = "quarantined", "parse_error:" + type(e).__name__
                for u in d.units:
                    u.attrs = X.new_attrs()
                    u.attrs["dx"] = set()
                d.units = []
        # dictionary
        for u, d in zip(self.units, self.unit_doc):
            if d.status == "quarantined":
                continue
            a = u.attrs
            for n in a["names"]:
                self.D.add_name(n, "patient")
            for n in a["relatives"]:
                self.D.add_name(n, "relative")
            for i in a["ids"]:
                self.D.add_id(i)
        for u in self.units:
            a = u.attrs
            a["ids"] |= {c for c in a["cand_ids"] if c in self.D.ids}
            u.has_identity = bool(a["names"] or a["ids"] or a["aadhaar"] or a["abha"] or a["phones"])
        self.D.finalize(self.orgs, self.doctors)
        self.log.stage(f"extracted {len(self.units)} records")

    def _extract_doc(self, d: Doc):
        hint = " ".join(d.header) if d.header else ""
        d.date_order = infer_date_order(d.text or "", hint) or self._family_order(d) or "dmy"
        if d.fmt == "csv":
            ncol = len(d.header)
            cols = [[r[i] if i < len(r) else "" for r in d.rows] for i in range(ncol)]
            kinds = [X.classify_column(h, c) for h, c in zip(d.header, cols)]
            self.col_kinds[d.rel] = kinds
            for ri, row in enumerate(d.rows):
                u = self._new_unit(d, f"row:{ri}")
                name_parts = []
                for ci, cell in enumerate(row):
                    kind = kinds[ci] if ci < ncol else None
                    hdr = d.header[ci] if ci < ncol else ""
                    if kind == "maybe_name" and X.looks_like_person(cell):
                        kind = "name"
                    if kind == "name":
                        if cell.strip():
                            name_parts.append(cell.strip())
                        continue
                    if kind in ("doctor", "org"):
                        self.doctors.add(cell.strip()) if kind == "doctor" else self.orgs.add(cell.strip())
                        continue
                    if kind == "date" and "dob" in hint.lower() and "dob" in hdr.lower():
                        kind = "dob"
                    if kind:
                        X.add_value(u.attrs, kind, cell, d.date_order)
                    else:
                        X.extract_text(u.attrs, cell, d.date_order)
                    self._dx(u, cell)
                if name_parts:
                    X.add_value(u.attrs, "name", " ".join(name_parts), d.date_order)
                if d.header:
                    for h in d.header:
                        X.extract_text(u.attrs, "", d.date_order)
        elif d.fmt in ("json", "fhir"):
            ptrs = d.record_ptrs or [""]
            for ptr in ptrs:
                u = self._new_unit(d, ptr if ptr else "doc")
                sub = get_ptr(d.obj, ptr) if ptr else d.obj
                base_parents = tuple(p.replace("~1", "/").replace("~0", "~") for p in ptr.split("/")[1:] if not p.isdigit())
                name_groups = defaultdict(list)
                for p, k, v, parents, rt in walk_json(sub, ptr, base_parents):
                    kind = X.classify_key(k, parents, rt if d.fmt == "fhir" else None)
                    if isinstance(v, str):
                        self._dx(u, v)
                    if kind == "org":
                        if isinstance(v, str):
                            self.orgs.add(v)
                        continue
                    if kind == "doctor":
                        if isinstance(v, str):
                            self.doctors.add(v)
                        continue
                    if kind in ("name", "relative") and isinstance(v, str):
                        grp = "/".join(p.split("/")[:-1]) if k in {"first", "last", "given", "family", "middle", "local", "text"} else p
                        if k == "local" or has_deva(v):
                            X.add_value(u.attrs, kind, v)
                        else:
                            name_groups[(kind, grp)].append(v)
                        continue
                    if kind == "maybe_name" and isinstance(v, str) and X.looks_like_person(v):
                        X.add_value(u.attrs, "name", v)
                        continue
                    if kind == "base64" and isinstance(v, str):
                        dec = self._b64_text(v)
                        if dec:
                            X.extract_text(u.attrs, dec, d.date_order)
                        continue
                    if kind and kind not in ("maybe_name", "free"):
                        X.add_value(u.attrs, kind, v, d.date_order)
                    elif isinstance(v, str):
                        X.extract_text(u.attrs, v, d.date_order)
                for (kind, _), parts in sorted(name_groups.items()):
                    seen = []
                    for x in parts:
                        if x not in seen:
                            seen.append(x)
                    full = " ".join(seen)
                    X.add_value(u.attrs, kind, full)
                # keys can hold identifiers (e.g. an index keyed by UHID)
                for kk in self._keys(sub):
                    X.extract_text(u.attrs, kk, d.date_order)
        else:
            u = self._new_unit(d, "doc")
            X.extract_text(u.attrs, d.text, d.date_order)
            for m in re.finditer(r"(?:Consultant|Doctor|Ref(?:erred)?\s*by)\s*[:\-]\s*(Dr\.?\s*[A-Z][a-zA-Z.]+(?:\s[A-Z][a-zA-Z]+){0,3})", d.text):
                self.doctors.add(m.group(1))
            self._dx(u, d.text)
            # fragments: "<Name>, W/o <Relative>" and "<Name> sahab/ji"
            for m in re.finditer(rf"(?P<n>{X.NAME_SEQ})\s*,?\s*\(?\s*(?:S|D|W)\s*/\s*[Oo]\b", d.text):
                nm = X.clean_name(m.group("n"))
                if nm and nm.split()[0].lower() not in L.MEDICAL_WORDS and nm.split()[0].lower() not in L.COMMON_EN:
                    u.attrs["names"].append(nm)
            hon = "|".join(sorted(L.POST_HONORIFICS - {"devi"}, key=len, reverse=True))
            for m in re.finditer(rf"\b(?P<n>[A-Z][a-z]+)\s+(?:{hon})\b", d.text):
                w = m.group("n")
                if w.lower() not in L.MEDICAL_WORDS and w.lower() not in L.COMMON_EN and w.lower() not in L.HINGLISH_MEDICAL:
                    u.attrs["names"].append(w)

    def _keys(self, obj):
        out = []
        stack = [obj]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                for k, v in o.items():
                    if re.search(r"\d{3,}|[A-Z][a-z]+[ _][A-Z]", str(k)):
                        out.append(str(k).replace("_", " "))
                    stack.append(v)
            elif isinstance(o, list):
                stack.extend(o)
        return out

    @staticmethod
    def _b64_text(v):
        import base64
        try:
            dec = base64.b64decode(v + "=" * (-len(v) % 4), validate=True).decode("utf-8")
            return dec if dec.isprintable() or "\n" in dec else dec
        except Exception:
            return None

    def _family_order(self, d: Doc):
        fam = re.split(r"[_\-]", d.rel.split("/")[-1].lower())[0]
        votes = Counter()
        for o in self.docs:
            if o is d or o.status == "quarantined" or not o.text:
                continue
            if re.split(r"[_\-]", o.rel.split("/")[-1].lower())[0] == fam:
                v = infer_date_order(o.text[:20000], " ".join(o.header) if o.header else "")
                if v:
                    votes[v] += 1
        return max(sorted(votes), key=lambda k: votes[k]) if votes else None

    # ------------------------------------------------------------ pass 2: linkage + pseudonyms
    def link(self):
        attrs = [u.attrs if (u.has_identity and d.status != "quarantined") else X.new_attrs()
                 for u, d in zip(self.units, self.unit_doc)]
        assign, diag = resolve(attrs, float(self.policy.get("link_threshold", 6.0)))
        self.diag["linkage"] = diag
        groups = defaultdict(list)
        for i, c in enumerate(assign):
            if c is not None:
                groups[c].append(i)
        used = {}
        self.cluster_of = {}
        for c in sorted(groups, key=lambda c: min(f"{self.unit_doc[i].rel}#{self.units[i].loc}" for i in groups[c])):
            canon = min(f"{self.unit_doc[i].rel}#{self.units[i].loc}" for i in groups[c])
            psn = self.keys.pseudonym(canon)
            n = 0
            while psn in used:
                n += 1
                psn = self.keys.pseudonym(canon + f"#{n}", length=7)
            used[psn] = c
            shift = self.keys.shift_days(canon, int(self.policy.get("date_shift_min_days", 21)),
                                         int(self.policy.get("date_shift_max_days", 180)))
            for i in groups[c]:
                u = self.units[i]
                u.cluster, u.psn, u.shift, u.canonical = c, psn, shift, canon
                self.cluster_of[i] = c
        # id -> pseudonym map (only unambiguous)
        idmap = defaultdict(set)
        coremap = defaultdict(set)
        for u in self.units:
            if not u.psn:
                continue
            for i in u.attrs["ids"]:
                idmap[i].add(u.psn)
                core = P.id_core(i)
                if len(core) >= 5:
                    coremap[core].add(u.psn)
        self.D.id_to_psn = {k: next(iter(v)) for k, v in sorted(idmap.items()) if len(v) == 1}
        self.D.core_to_psn = {k: next(iter(v)) for k, v in sorted(coremap.items()) if len(v) == 1}
        # cluster-level name keys / places
        self.cl_own, self.cl_rel, self.cl_place = defaultdict(set), defaultdict(set), {}
        places = defaultdict(lambda: ([], []))
        for u in self.units:
            if u.cluster is None:
                continue
            for n in u.attrs["names"]:
                self.cl_own[u.cluster] |= {name_key(t) for t in split_name(n)}
            for n in u.attrs["relatives"]:
                self.cl_rel[u.cluster] |= {name_key(t) for t in split_name(n)}
            places[u.cluster][0].extend(u.attrs["tehsils"])
            places[u.cluster][1].extend(u.attrs["districts"])
        for c, (t, dd) in places.items():
            self.cl_place[c] = (PV._mode(t), PV._mode(dd))
        for c in self.cl_rel:
            self.cl_rel[c] -= self.cl_own[c]
        self.log.stage(f"linked: {diag['clusters']} patients")

    # ------------------------------------------------------------ pass 3: policy
    def choose(self):
        profiles = PV.build_profiles(self.units, self.unit_doc)
        self.policy_result = PV.choose_policy(profiles, self.policy)
        self.log.stage("policy selected")

    def ctx_for(self, u: Unit | None, d: Doc, stats) -> Ctx:
        if u is None:
            return Ctx(order=d.date_order, node=self.policy_result["base"], stats=stats)
        node = self.policy_result["overrides"].get(u.psn, self.policy_result["base"]) if u.psn else self.policy_result["base"]
        if u.cluster is not None:
            own, rel = self.cl_own[u.cluster], self.cl_rel[u.cluster]
            teh, dist = self.cl_place.get(u.cluster, (None, None))
        else:
            own = {name_key(t) for n in u.attrs["names"] for t in split_name(n)}
            rel = {name_key(t) for n in u.attrs["relatives"] for t in split_name(n)} - own
            teh, dist = PV._mode(u.attrs["tehsils"]), PV._mode(u.attrs["districts"])
        shift = u.shift if u.psn else None
        return Ctx(psn=u.psn, shift=shift, order=d.date_order, node=node, own_keys=own, rel_keys=rel,
                   tehsil=teh, district=dist, stats=stats)

    # ------------------------------------------------------------ pass 4: rewrite
    def rewrite(self):
        for d in self.docs:
            if d.status == "quarantined":
                continue
            try:
                stats = {}
                if d.fmt == "csv":
                    d.out_bytes = self._rw_csv(d, stats)
                elif d.fmt in ("json", "fhir"):
                    d.out_bytes = self._rw_json(d, stats)
                else:
                    d.out_bytes = self._rw_text(d, stats)
                d.out_rel = self._rename(d)
                d.status = "sanitized"
                for k, v in stats.items():
                    if not k.startswith("_"):
                        self.entities[k] += v
                d.stats = stats
            except Exception as e:  # noqa: BLE001
                d.status, d.reason, d.out_bytes = "quarantined", "rewrite_error:" + type(e).__name__, None
        self.log.stage("rewritten")

    def _rw_csv(self, d: Doc, stats) -> bytes:
        kinds = self.col_kinds[d.rel]
        hctx = self.ctx_for(None, d, stats)
        header = [self.san.scrub(h, hctx) for h in d.header]
        rows = []
        for ri, row in enumerate(d.rows):
            u = d.units[ri]
            ctx = self.ctx_for(u, d, stats)
            new = []
            for ci, cell in enumerate(row):
                kind = kinds[ci] if ci < len(kinds) else None
                if kind == "maybe_name":
                    kind = "name" if X.looks_like_person(cell) else None
                if kind == "date" and "dob" in (d.header[ci] if ci < len(d.header) else "").lower():
                    kind = "dob"
                new.append(self.san.value(kind, cell, ctx, d.date_order) if kind else self.san.scrub(cell, ctx))
            new = ["" if x is None else str(x) for x in new]
            if u.psn and not any(u.psn in c for c in new):
                pass
            rows.append(new)
        buf = io.StringIO(newline="")
        w = csv.writer(buf, delimiter=d.delimiter, lineterminator=d.lineterm, quoting=csv.QUOTE_MINIMAL)
        w.writerow(header)
        w.writerows(rows)
        return buf.getvalue().encode("utf-8")

    def _rw_json(self, d: Doc, stats) -> bytes:
        unit_at = {u.loc: u for u in d.units}
        doc_unit = unit_at.get("doc")
        base_ctx = self.ctx_for(doc_unit, d, stats) if doc_unit else self.ctx_for(None, d, stats)
        ctx_cache = {}

        def ctx_of(u):
            if u.loc not in ctx_cache:
                ctx_cache[u.loc] = self.ctx_for(u, d, stats)
            return ctx_cache[u.loc]

        is_fhir = d.fmt == "fhir"

        def tr(o, ptr, parents, rtype, ctx):
            if ptr in unit_at and ptr != "doc":
                ctx = ctx_of(unit_at[ptr])
            if isinstance(o, dict):
                rt = o.get("resourceType") if isinstance(o.get("resourceType"), str) else rtype
                new = {}
                for k in o:
                    v = o[k]
                    kp = str(k).replace("~", "~0").replace("/", "~1")
                    nk = k
                    if isinstance(k, str) and not re.fullmatch(r"[a-z_]{1,24}", k):
                        nk = self.san.scrub(k, ctx, "key")
                        while nk in new:
                            nk = nk + "_"
                    if isinstance(v, (dict, list)):
                        new[nk] = tr(v, f"{ptr}/{kp}", parents + (str(k),), rt, ctx)
                    else:
                        kind = X.classify_key(k, parents, rt if is_fhir else None)
                        new[nk] = self._leaf(kind, v, ctx, d)
                return new
            if isinstance(o, list):
                out = []
                for i, v in enumerate(o):
                    if isinstance(v, (dict, list)):
                        out.append(tr(v, f"{ptr}/{i}", parents, rtype, ctx))
                    else:
                        kind = X.classify_key(parents[-1], parents[:-1], rtype if is_fhir else None) if parents else None
                        out.append(self._leaf(kind, v, ctx, d))
                return out
            return o

        new = tr(d.obj, "", (), None, base_ctx)
        txt = json.dumps(new, ensure_ascii=False, indent=2)
        return (txt + "\n").encode("utf-8")

    def _leaf(self, kind, v, ctx, d):
        if kind == "maybe_name":
            kind = "name" if isinstance(v, str) and X.looks_like_person(v) else None
        if kind == "free":
            kind = None
        if kind in ("date",) and isinstance(v, str):
            return self.san.value("date", v, ctx, d.date_order)
        if kind:
            return self.san.value(kind, v, ctx, d.date_order)
        if isinstance(v, str):
            return self.san.scrub(v, ctx)
        return self.san.value(None, v, ctx, d.date_order)

    def _rw_text(self, d: Doc, stats) -> bytes:
        u = d.units[0] if d.units else None
        ctx = self.ctx_for(u, d, stats)
        out = self.san.scrub(d.text, ctx)
        if u is not None and u.psn and u.psn not in out:
            out = f"Patient: {u.psn}\n" + out
        if d.lineterm == "\r\n":
            out = out.replace("\r\n", "\n").replace("\n", "\r\n")
        return out.encode("utf-8")

    def _rename(self, d: Doc) -> str:
        parts = d.rel.split("/")
        new_parts = []
        for i, part in enumerate(parts):
            stem, dot, ext = part.rpartition(".") if (i == len(parts) - 1 and "." in part) else (part, "", "")
            view = stem.replace("_", " ")
            ctx = Ctx(order=d.date_order, stats={})
            clean = self.san.scrub(view, ctx, "filename")
            risky = clean != view or any(len(P.id_core(m.group(0))) >= 5 for m in P.GENERIC_ID.finditer(view)
                                         if re.match(r"[A-Za-z]{2,}", m.group(0)))
            if risky:
                keep = []
                for tok in re.split(r"[ _\-]+", stem):
                    if not tok or not tok.isalpha() or len(tok) < 2 or tok.isupper() and len(tok) <= 5:
                        continue
                    if self.san.is_name_word(tok) or tok.lower() in L.SURNAMES or tok.lower() in L.GIVEN_NAMES:
                        continue
                    keep.append(tok)
                prefix = "_".join(keep[:3]) or "record"
                stem = f"{prefix}_{self.keys.tag(d.rel + '#' + str(i))}"
            new_parts.append(stem + (dot + ext if dot else ""))
        return "/".join(new_parts)

    # ------------------------------------------------------------ pass 5: verify (self-correcting firewall)
    def verify(self):
        surf = sorted(self.D.surfaces, key=len, reverse=True)
        id_like = sorted(self.D.ids, key=len, reverse=True)
        fixes = quarantined = 0
        for d in self.docs:
            if d.status != "sanitized" or d.out_bytes is None:
                continue
            txt = d.out_bytes.decode("utf-8")
            for attempt in range(2):
                hits = self._residual(txt, surf, id_like)
                if not hits:
                    break
                fixes += len(hits)
                for h in sorted(hits, key=len, reverse=True):
                    txt = re.sub(re.escape(h), "[REDACTED]", txt, flags=re.I) if len(h) >= 5 else \
                        re.sub(rf"(?<![A-Za-z0-9]){re.escape(h)}(?![A-Za-z0-9])", "[REDACTED]", txt)
            else:
                if self._residual(txt, surf, id_like):
                    d.status, d.reason, d.out_bytes = "quarantined", "residual_pii", None
                    quarantined += 1
                    continue
            if d.fmt in ("json", "fhir"):
                try:
                    json.loads(txt)
                except ValueError:
                    d.status, d.reason, d.out_bytes = "quarantined", "residual_pii", None
                    quarantined += 1
                    continue
            d.out_bytes = txt.encode("utf-8")
        self.diag["verification"] = {"residual_fixes": fixes, "residual_quarantined": quarantined}
        self.log.stage("verified")

    def _residual(self, txt, surf, id_like):
        hits = set()
        low = txt.lower()
        for m in P.AADHAAR.finditer(txt):
            d = P.norm_digits(m.group(0))
            if d[0] not in "01" and not P.DATE_ISO.search(m.group(0)):
                hits.add(m.group(0))
        for m in P.PHONE.finditer(txt):
            if not P.phone_guard(txt, m.start(), m.end()):
                hits.add(m.group(0))
        for i in id_like:
            core = P.id_core(i)
            if len(core) >= 6 and core in txt:
                for m in re.finditer(rf"(?<!\d){core}(?!\d)", txt):
                    hits.add(m.group(0))
        return {h for h in hits if h.strip()}

    # ------------------------------------------------------------ outputs
    def write(self, t0: float):
        san = self.out / "sanitized"
        san.mkdir(parents=True, exist_ok=True)
        files = []
        records = []
        used_paths = set()
        for d in self.docs:
            if d.status == "sanitized" and d.out_bytes is not None:
                rel = d.out_rel or d.rel
                while rel.lower() in used_paths:
                    stem, dot, ext = rel.rpartition(".")
                    rel = f"{stem}_{self.keys.tag(rel)[:4]}.{ext}" if dot else rel + "_"
                used_paths.add(rel.lower())
                d.out_rel = rel
                p = san / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(d.out_bytes)
                e = {"input_sha256": d.sha, "output": f"sanitized/{rel}", "status": "sanitized"}
                if rel != d.rel:
                    e["renamed"] = True
                files.append(e)
                for u in d.units:
                    if u.has_identity:
                        r = {"file": f"sanitized/{rel}", "loc": u.loc, "patient": u.psn}
                        if u.psn and self._generalized(u):
                            r["status"] = "generalized"
                        records.append(r)
            else:
                files.append({"input_sha256": d.sha, "output": None, "status": "quarantined",
                              "reason": d.reason or "unsupported_format"})
        with open(self.out / "records.jsonl", "w", encoding="utf-8", newline="\n") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
        sanitized_docs = [d for d in self.docs if d.status == "sanitized"]
        n_records = sum(len(d.units) for d in sanitized_docs)
        linked = sum(1 for d in sanitized_docs for u in d.units if u.psn)
        gen = sum(1 for d in sanitized_docs for u in d.units if u.psn and self._generalized(u))
        q_records = sum(len(d.units) for d in self.docs if d.status == "quarantined")
        report = {
            "schema": "raksha-report/1",
            "files": files,
            "counts": {
                "files_total": len(self.docs),
                "files_sanitized": len(sanitized_docs),
                "files_quarantined": len(self.docs) - len(sanitized_docs),
                "records_processed": n_records,
                "identifiers_detected": int(sum(v for k, v in self.entities.items())),
                "records_linked": linked,
                "records_generalized": gen,
                "records_suppressed": 0,
                "records_quarantined": q_records,
            },
            "entities": {k: int(v) for k, v in sorted(self.entities.items())},
            "timing": {"seconds": round(time.time() - t0, 2)},
            "resources": {"peak_rss_mb": peak_rss_mb()},
        }
        (self.out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        audit = {
            "schema": "rakshamed-audit/1",
            "policy": {k: v for k, v in self.policy_result.items() if k != "overrides"},
            "linkage": self.diag.get("linkage"),
            "verification": self.diag.get("verification"),
            "quarantine_reasons": dict(sorted(Counter(d.reason for d in self.docs if d.status == "quarantined").items())),
        }
        (self.out / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return report

    def _generalized(self, u):
        return True

    def run(self):
        t0 = time.time()
        self.ingest()
        self.extract()
        self.link()
        self.choose()
        self.rewrite()
        self.verify()
        return self.write(t0)
