"""StegnoZ pipeline: ingest -> extract -> link -> policy -> rewrite -> verify -> report."""
from __future__ import annotations

import base64
import csv
import hashlib
import math
import io
import json
import re
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

from . import extract as X
from . import lexicon as L
from . import patterns as P
from . import privacy as PV
from .fhir import FHIR, UnsafeFHIR, pointer_key
from .ingest import Doc, Unit, infer_date_order, iter_input, load
from .link import resolve
from .sanitize import ASHA_RE, DOC_RE, EPONYM_RE, ORG_RE, WARD_RE, Ctx, Sanitizer
from .staging import EncryptedStaging
from .translit import has_deva, name_key, split_name
from .util import Keys, SafeLog, peak_rss_mb


# ---------------------------------------------------------------- policy
def load_policy(path: Path) -> dict:
    limits = {
        "k_target": (int, 1, math.inf),
        "population_factor": (float, 1, 1),
        "max_singling_out": (float, 0, 1),
        "rare_dx_max_patients": (int, 0, math.inf),
        "date_shift_min_days": (int, 1, 365),
        "date_shift_max_days": (int, 1, 365),
        "link_threshold": (float, -math.inf, math.inf),
    }
    policy = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        key, sep, raw = line.partition(":")
        key = key.strip()
        if not sep or key not in limits or key in policy:
            raise ValueError("invalid policy key")
        convert, lo, hi = limits[key]
        value = convert(raw.strip())
        if not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError("invalid policy value")
        policy[key] = value
    if policy.get("date_shift_min_days", 21) > policy.get("date_shift_max_days", 180):
        raise ValueError("inverted shift range")
    return policy


# ---------------------------------------------------------------- dynamic dictionary
class Dictionary:
    def __init__(self):
        self.name_keys: dict[str, str] = {}
        self.key_index: dict[str, list] = defaultdict(list)
        self.ids: set[str] = set()
        self.id_cores: set[str] = set()
        self.id_to_psn: dict[str, str] = {}
        self.core_to_psn: dict[str, str] = {}
        self.village_keys: set = set()
        self.place_keys: set = set()
        self.protect_re = None
        self.phrases: set[str] = set()
        self.core_re = None
        self.phrase_re = None

    def add_name(self, name: str, role: str):
        tokens = split_name(name)
        if len(tokens) >= 2 or (len(tokens) == 1 and len(tokens[0]) >= 4 and
                                tokens[0].casefold() not in L.MEDICAL_WORDS | L.COMMON_EN | L.GENERIC_NAME_PARTS):
            self.phrases.add(" ".join(tokens).casefold())
        for t in tokens:
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

    def add_id(self, nid: str, core: str = ""):
        if not nid or not re.search(r"\d{3,}", nid):
            return
        self.ids.add(nid)
        if len(core) >= 5:
            self.id_cores.add(core)

    def add_village(self, v: str):
        toks = tuple(name_key(t) for t in split_name(v) if name_key(t))
        if toks and sum(len(t) for t in toks) >= 4:
            self.village_keys.add(toks)
            self.phrases.add(v.casefold())

    def finalize(self, orgs, doctors):
        for k in sorted(self.name_keys):
            self.key_index[k[:2]].append(k)
        if self.phrases:
            escaped = [re.escape(term) for term in sorted(self.phrases, key=lambda term: (-len(term), term))]
            self.phrase_re = re.compile(r"(?<!\w)(?:" + "|".join(escaped) + r")(?!\w)", re.I)
        cores = sorted(c for c in self.id_cores if len(c) >= 6)
        if cores:
            self.core_re = re.compile(r"(?<!\d)(?:" + "|".join(map(re.escape, cores)) + r")(?!\d)")
        phrases = sorted({o.strip() for o in orgs | doctors if o and len(o.strip()) >= 4}, key=lambda p: (-len(p), p))
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
                yield f"{ptr}/{kp}", str(k), v, parents, rt, obj
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, (dict, list)):
                yield from walk_json(v, f"{ptr}/{i}", parents, rtype)
            else:
                yield f"{ptr}/{i}", parents[-1] if parents else "", v, parents, rtype, None


_EXT_HINTS = [(re.compile(r"(?i)name|mother|father|spouse|relative|guardian|kin|husband|wife"), "relative"),
              (re.compile(r"(?i)phone|mobile|contact|telecom"), "phone"),
              (re.compile(r"(?i)aadha?a?r|uid"), "aadhaar"), (re.compile(r"(?i)abha|health-?id"), "abha"),
              (re.compile(r"(?i)birth|dob"), "dob"), (re.compile(r"(?i)address|village|locality"), "address")]


def ext_kind(container) -> str | None:
    """FHIR extensions / key-value pairs carry their meaning in a sibling 'url'/'key'/'label'."""
    if not isinstance(container, dict):
        return None
    hint = container.get("url") or container.get("key") or container.get("label") or container.get("field")
    if not isinstance(hint, str):
        return None
    for rx, kind in _EXT_HINTS:
        if rx.search(hint.rsplit("/", 1)[-1]):
            return kind
    return None


def get_ptr(obj, ptr):
    cur = obj
    for part in ptr.split("/")[1:]:
        part = part.replace("~1", "/").replace("~0", "~")
        cur = cur[int(part)] if isinstance(cur, list) else cur[part]
    return cur


_QI_CHANGES = {"AGE", "DOB", "[VILLAGE]", "[PIN]", "[ADDRESS]", "LOCATION", "DATE"}


class Pipeline:
    def __init__(self, inp: Path, out: Path, secret: str, policy: dict, strict_risk=True):
        self.inp, self.out = inp, out
        self.keys = Keys(secret)
        self.policy = policy
        self.strict_risk = strict_risk
        self.risk_blocked = False
        self.staging = EncryptedStaging()
        self.fhir = {}
        self.header_attrs = {}
        self.date_votes = defaultdict(Counter)
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
                    with p.open("rb") as source:
                        d.sha = hashlib.file_digest(source, "sha256").hexdigest()
                except Exception:
                    pass
            if d.text:
                order = infer_date_order(d.text)
                if order:
                    d.date_order = order
                    self.date_votes[self._file_family(d)][order] += 1
                else:
                    d.date_order = ""
            self._release_input(d)
            self.docs.append(d)
        self.log.stage(f"ingested {len(self.docs)} files")

    @staticmethod
    def _release_input(doc):
        doc.text = doc.rows = doc.obj = None

    def _restore_input(self, doc):
        restored = load(self.inp / doc.rel, doc.rel)
        if restored.status == "quarantined" or restored.sha != doc.sha:
            raise ValueError("input changed during run")
        doc.text, doc.rows, doc.obj = restored.text, restored.rows, restored.obj

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
                self._restore_input(d)
                self._extract_doc(d)
            except Exception as e:  # noqa: BLE001
                d.status, d.reason = "quarantined", "unsafe_fhir" if isinstance(e, UnsafeFHIR) else "parse_error:" + type(e).__name__
                for u in d.units:
                    u.attrs = X.new_attrs()
                    u.attrs["dx"] = set()
            finally:
                self._release_input(d)
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
            for c in a["cores"]:
                if len(c) >= 5:
                    self.D.id_cores.add(c)
            for v in a["villages"]:
                self.D.add_village(v)
            for v in a["tehsils"] + a["districts"]:
                self.D.place_keys.add(tuple(name_key(t) for t in split_name(v) if name_key(t)))
        for headers in self.header_attrs.values():
            for name in headers["names"]:
                self.D.add_name(name, "patient")
            for identifier in headers["ids"]:
                self.D.add_id(identifier)
        for u in self.units:
            a = u.attrs
            for c in sorted(a["cand_ids"]):
                if c in self.D.ids:
                    a["ids"].add(c)
                    a["cores"].add(a["cand_cores"].get(c, ""))
            u.has_identity = bool(a["names"] or any(a[k] for k in ("ids", "aadhaar", "abha", "phones", "emails", "pans", "insurance")))
            u.bearing |= bool(u.has_identity or a["dob"] or a["ages"] or a["dx"] or a["pins"]
                              or a["gender"] or a["relatives"] or a["event_dates"])
        self.D.finalize(self.orgs, self.doctors)
        self.log.stage(f"extracted {len(self.units)} records")

    def _extract_doc(self, d: Doc):
        d.date_order = d.date_order or self._family_order(d) or "dmy"
        if d.fmt == "csv":
            ncol = len(d.header)
            cols = [[r[i] if i < len(r) else "" for r in d.rows] for i in range(ncol)]
            kinds = [X.classify_column(h, c) for h, c in zip(d.header, cols)]
            self.col_kinds[d.rel] = kinds
            d.date_orders = [infer_date_order("\n".join(col), h) or d.date_order for h, col in zip(d.header, cols)]
            headers = X.new_attrs()
            self.header_attrs[d.rel] = headers
            for header in d.header:
                X.extract_text(headers, header, d.date_order)
            for ri, row in enumerate(d.rows):
                u = self._new_unit(d, f"row:{ri}")
                u.bearing = any(cell.strip() for cell in row)
                name_parts = []
                for ci, cell in enumerate(row):
                    kind = kinds[ci] if ci < ncol else None
                    hdr = d.header[ci] if ci < ncol else ""
                    if kind == "maybe_name" and X.looks_like_person(cell):
                        kind = "name"
                    elif kind == "maybe_relative" and X.looks_like_person(cell):
                        kind = "relative"
                    if kind == "name":
                        if cell.strip():
                            name_parts.append(cell.strip())
                        continue
                    if kind in ("doctor", "org"):
                        if kind == "org" and cell.strip():
                            u.attrs["source"].add(cell.strip().casefold())
                        self.doctors.add(cell.strip()) if kind == "doctor" else self.orgs.add(cell.strip())
                        continue
                    if kind == "date" and "dob" in hdr.lower():
                        kind = "dob"
                    if kind:
                        X.add_value(u.attrs, kind, cell, d.date_orders[ci])
                    else:
                        X.extract_text(u.attrs, cell, d.date_order)
                    self._dx(u, cell)
                if name_parts:
                    X.add_value(u.attrs, "name", " ".join(name_parts), d.date_order)
                # File-level identity is only attributable when the file contains one row.
                if len(d.rows) == 1:
                    for kind in ("names", "ids", "cores"):
                        if not u.attrs[kind]:
                            u.attrs[kind] = headers[kind].copy()
        elif d.fmt in ("json", "fhir"):
            plan = FHIR(d.obj, self.keys, d.sha) if d.fmt == "fhir" else None
            if plan is not None:
                self.fhir[d.rel] = plan
            if plan and len(plan.patients) != 1:
                ptrs = sorted(plan.patients)
            else:
                ptrs = d.record_ptrs or [""]
            for ptr in ptrs:
                u = self._new_unit(d, ptr if ptr else "doc")
                u.bearing = bool(plan or ptr)
                sub = get_ptr(d.obj, ptr) if ptr else d.obj
                base_parents = tuple(p.replace("~1", "/").replace("~0", "~") for p in ptr.split("/")[1:] if not p.isdigit())
                name_groups = defaultdict(list)
                for p, k, v, parents, rt, cont in walk_json(sub, ptr, base_parents):
                    if plan and p in plan.values:
                        continue
                    kind = self._json_kind(k, parents, rt if plan else None)
                    if k.startswith("value") or k in ("val", "data"):
                        kind = ext_kind(cont) or kind
                    if isinstance(v, str):
                        self._dx(u, v)
                    if kind == "org":
                        if isinstance(v, str):
                            self.orgs.add(v)
                            if k.lower() == "name":
                                u.attrs["source"].add(v.casefold())
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
                    if kind in ("maybe_name", "maybe_relative") and isinstance(v, str) and X.looks_like_person(v):
                        X.add_value(u.attrs, "relative" if kind == "maybe_relative" else "name", v)
                        continue
                    if kind == "base64" and isinstance(v, str):
                        dec = self._b64_text(v)
                        if dec:
                            X.extract_text(u.attrs, dec, d.date_order)
                        continue
                    if kind == "clinical":
                        u.bearing = True
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
                if plan:
                    scope = ptr if ptr else next(iter(plan.patients), None)
                    for namespace, identifier in plan.identifiers.get(scope, ()):
                        normalized = P.id_norm(identifier)
                        if normalized:
                            u.attrs["ids"].add(normalized)
                            u.attrs["id_scopes"].setdefault(normalized, set()).add(namespace.casefold())
        else:
            u = self._new_unit(d, "doc")
            X.extract_text(u.attrs, d.text, d.date_order)
            for m in re.finditer(r"(?:Consultant|Doctor|Ref(?:erred)?\s*by)\s*[:\-]\s*(Dr\.?\s*[A-Z][a-zA-Z.]+(?:\s[A-Z][a-zA-Z]+){0,3})", d.text):
                self.doctors.add(m.group(1))
            self._dx(u, d.text)
            u.bearing = bool(u.attrs["names"] or u.attrs["event_dates"] or u.attrs["dx"])
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
            return dec if all(c.isprintable() or c in "\r\n\t" for c in dec) else None
        except Exception:
            return None

    @staticmethod
    def _file_family(doc):
        return re.split(r"[_\-]", doc.rel.rsplit("/", 1)[-1].lower(), maxsplit=1)[0]

    def _family_order(self, doc):
        votes = self.date_votes[self._file_family(doc)]
        return min(votes, key=lambda order: (-votes[order], order)) if votes else None

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
        self.groups = groups
        used = {}
        self.cluster_of = {}
        def evidence(members):
            units = [self.units[i] for i in members]
            for kind in ("aadhaar", "abha", "pans", "ids", "emails", "phones", "insurance", "names"):
                values = set()
                for unit in units:
                    attrs = unit.attrs
                    for value in attrs[kind]:
                        if kind == "ids":
                            scopes = attrs["id_scopes"].get(value) or attrs["source"] or {""}
                            values.update(f"{scope}:{value}" for scope in scopes)
                        else:
                            values.add(value.casefold())
                if values:
                    return json.dumps([kind, min(values)], ensure_ascii=False)
            raise ValueError("identity cluster without evidence")

        anchors = {cluster: evidence(members) for cluster, members in groups.items()}
        frequency = Counter(anchors.values())
        for c in sorted(groups, key=lambda c: (anchors[c], min(self.units[i].loc for i in groups[c]), c)):
            canon = anchors[c]
            if frequency[canon] > 1:
                # Distinct unresolved clusters with the same evidence must stay separate.
                canon += "|" + min(self.unit_doc[i].sha + "#" + self.units[i].loc for i in groups[c])
            psn = self.keys.pseudonym(canon)
            n = 0
            while psn in used:
                n += 1
                psn = self.keys.pseudonym(canon + f"#{n}", length=7)
            if n:
                canon += f"#{n}"
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
            for core in u.attrs["cores"]:
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
    def choose(self, verified_dir):
        initial = [(d.status, d.reason) for d in self.docs]
        expected_files = None

        def evaluate(node):
            nonlocal expected_files
            self.policy_result = {"base": node, "overrides": {}}
            self.entities.clear()
            for d, (status, reason) in zip(self.docs, initial):
                d.status, d.reason = status, reason
                d.verified_path = d.out_bytes = d.out_rel = None
                for u in d.units:
                    u.embedded = u.generalized = False
                    u.out_loc = None
            self.rewrite(verified_dir)
            files = {d.rel for d in self.docs if d.status == "sanitized"}
            if expected_files is None:
                expected_files = files
            exposure = self._exposure_stats()
            return {"risk": exposure["singling_out_risk"],
                    "risk_floor": exposure["preserved_facts_risk_floor"],
                    "patients": exposure["patients"], "valid": files == expected_files}

        chosen = PV.choose_policy(evaluate, self.policy)
        # Rebuild the selected candidate so counters, locators and bytes all agree.
        final = evaluate(chosen["base"])
        if not final["valid"] or final["risk"] != chosen["selected_risk"]:
            raise ValueError("candidate changed during policy search")
        self.policy_result = chosen
        self.log.stage("release policy selected")

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
    def rewrite(self, verified_dir=None):
        self.verification = Counter()
        for index, d in enumerate(self.docs):
            if d.status == "quarantined":
                continue
            try:
                self._restore_input(d)
                stats = {}
                if d.fmt == "csv":
                    d.out_bytes = self._rw_csv(d, stats)
                elif d.fmt in ("json", "fhir"):
                    d.out_bytes = self._rw_json(d, stats)
                else:
                    d.out_bytes = self._rw_text(d, stats)
                d.out_rel = self._rename(d)
                d.status = "sanitized"
                if verified_dir is not None:
                    self.verify([d])
                    if d.status == "sanitized":
                        d.verified_path = verified_dir / str(index)
                        self.staging.write(d.verified_path, d.out_bytes)
                        d.out_bytes = None
                if d.status == "sanitized":
                    for k, v in stats.items():
                        if not k.startswith("_"):
                            self.entities[k] += v
                d.stats = stats
            except Exception as e:  # noqa: BLE001
                reason = "unsafe_fhir" if isinstance(e, UnsafeFHIR) else "rewrite_error:" + type(e).__name__
                d.status, d.reason, d.out_bytes = "quarantined", reason, None
            finally:
                self._release_input(d)
        self.log.stage("rewritten and verified" if verified_dir is not None else "rewritten")

    def _rw_csv(self, d: Doc, stats) -> bytes:
        kinds = self.col_kinds[d.rel]
        hctx = self.ctx_for(None, d, stats)
        header = [self.san.scrub(h, hctx, "header") for h in d.header]
        rows = []
        for ri, row in enumerate(d.rows):
            u = d.units[ri]
            ctx = self.ctx_for(u, d, stats)
            before = stats.copy()
            new = []
            for ci, cell in enumerate(row):
                kind = kinds[ci] if ci < len(kinds) else None
                if kind == "maybe_name":
                    kind = "name" if X.looks_like_person(cell) else None
                if kind == "date" and "dob" in (d.header[ci] if ci < len(d.header) else "").lower():
                    kind = "dob"
                if kind in ("date", "dob"):
                    ctx.order = d.date_orders[ci]
                else:
                    ctx.order = d.date_order
                new.append(self.san.value(kind, cell, ctx, ctx.order) if kind else self.san.scrub(cell, ctx))
            u.generalized = any(ctx.stats.get(key, 0) > before.get(key, 0) for key in _QI_CHANGES)
            new = ["" if x is None else str(x) for x in new]
            rows.append(new)
        for u, source, row in zip(d.units, d.rows, rows):
            if u.psn and not any(u.psn in cell for cell in row):
                for i, (kind, original) in enumerate(zip(kinds, source)):
                    if kind in {"phone", "email", "abha", "abha_addr", "aadhaar", "mrn", "insurance", "pan"} and original.strip():
                        row[i] = u.psn
                        break
            u.embedded = bool(u.psn and any(u.psn in cell for cell in row))
        buf = io.StringIO(newline="")
        w = csv.writer(buf, delimiter=d.delimiter, lineterminator=d.lineterm, quoting=csv.QUOTE_MINIMAL)
        w.writerow(header)
        w.writerows(rows)
        return buf.getvalue().encode("utf-8")

    def _rw_json(self, d: Doc, stats) -> bytes:
        unit_at = {u.loc: u for u in d.units}
        doc_unit = unit_at.get("doc")
        base_ctx = self.ctx_for(doc_unit, d, stats)
        plan = self.fhir.get(d.rel)
        if plan and base_ctx.shift is None:
            base_ctx.shift = self.keys.shift_days(
                "FHIR dates:" + d.sha, int(self.policy.get("date_shift_min_days", 21)),
                int(self.policy.get("date_shift_max_days", 180)),
            )
        contexts = {u.loc: self.ctx_for(u, d, {}) for u in d.units}

        def tr(o, ptr, out_ptr, parents, rtype, ctx):
            if ptr in unit_at and ptr != "doc":
                ctx = contexts[ptr]
                unit_at[ptr].out_loc = out_ptr
            elif plan and ptr in plan.owners and plan.owners[ptr] in contexts:
                ctx = contexts[plan.owners[ptr]]
            if isinstance(o, dict):
                rt = o.get("resourceType") if isinstance(o.get("resourceType"), str) else rtype
                new = {}
                attachment = bool(plan and ("attachment" in parents or "presentedForm" in parents or rt == "Binary"))
                for k, v in o.items():
                    path = f"{ptr}/{pointer_key(k)}"
                    nk = k
                    if not plan:
                        view = k.replace("_", " ")
                        clean = self.san.scrub(view, ctx, "key")
                        if clean != view:
                            nk = clean
                        elif (isinstance(v, (dict, list)) and view.casefold() in L.GIVEN_NAMES
                              and self._json_kind(k, parents, None) is None):
                            nk = "[NAME]"
                    while nk in new:
                        nk += "_"
                    if plan and path in plan.values:
                        new[nk] = plan.values[path]
                    elif attachment and k in {"hash", "size"} and "data" in o:
                        continue
                    elif attachment and k == "url":
                        raise UnsafeFHIR("unsupported external attachment")
                    elif attachment and k == "data":
                        if not isinstance(v, str):
                            raise UnsafeFHIR("invalid attachment")
                        raw = self._b64_text("".join(v.split()))
                        mime = o.get("contentType", "text/plain")
                        if raw is None or not isinstance(mime, str) or not mime.startswith("text/"):
                            raise UnsafeFHIR("unsupported attachment")
                        new[nk] = base64.b64encode(self.san.scrub(raw, ctx).encode("utf-8")).decode("ascii")
                    elif isinstance(v, (dict, list)):
                        new[nk] = tr(v, path, f"{out_ptr}/{pointer_key(nk)}", parents + (str(k),), rt, ctx)
                    else:
                        kind = self._json_kind(k, parents, rt if plan else None)
                        if k.startswith("value") or k in ("val", "data"):
                            kind = ext_kind(o) or kind
                        if plan and (k in {"resourceType", "system", "code", "status", "contentType", "url", "type"}
                                     and kind is None):
                            new[nk] = v
                            continue
                        value = self._leaf(kind, v, ctx, d)
                        if plan and kind in {"date", "dob"} and isinstance(value, str) and "[DATE]" in value:
                            if k != "birthDate":
                                raise UnsafeFHIR("unrepresentable date")
                            continue
                        if plan and k == "birthDate" and value == "[DOB]":
                            continue
                        new[nk] = value
                if plan and ptr in plan.patients and d.obj.get("resourceType") == "Bundle" and ctx.psn:
                    new["id"] = ctx.psn
                return new
            if isinstance(o, list):
                out = []
                for i, v in enumerate(o):
                    if isinstance(v, (dict, list)):
                        out.append(tr(v, f"{ptr}/{i}", f"{out_ptr}/{i}", parents, rtype, ctx))
                    else:
                        kind = self._json_kind(parents[-1], parents[:-1], rtype if plan else None) if parents else None
                        out.append(self._leaf(kind, v, ctx, d))
                return out
            return self._leaf(None, o, ctx, d)

        new = tr(d.obj, "", "", (), None, base_ctx)
        for u in d.units:
            if u.out_loc and u.out_loc != u.loc:
                # The organizer requires the original locator. It cannot be published if it contains PII.
                raise ValueError("sensitive record locator")
            ctx = base_ctx if u is doc_unit else contexts[u.loc]
            u.generalized = any(ctx.stats.get(key) for key in _QI_CHANGES)
            exported = new if u is doc_unit else get_ptr(new, u.out_loc or u.loc)
            u.embedded = bool(u.psn and u.psn in json.dumps(exported, ensure_ascii=False))
            if ctx.stats is not stats:
                for key, value in ctx.stats.items():
                    stats[key] = stats.get(key, 0) + value
        return (json.dumps(new, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")

    @staticmethod
    def _json_kind(key, parents, rtype):
        kind = X.classify_key(key, parents, rtype)
        normalized = re.sub(r"([a-z])([A-Z])", r"\1 \2", key).replace("_", " ")
        if rtype and key.lower() in {"start", "end", "effectivedatetime", "issued", "authoredon", "recordeddate", "lastupdated"}:
            return "date"
        if kind is None and (X._KEEP_HEADERS.fullmatch(normalized) or
                             (rtype and ("valueQuantity" in parents or key == "valueInteger"))):
            return "clinical"
        return kind

    def _leaf(self, kind, v, ctx, d):
        if kind == "maybe_name":
            kind = "name" if isinstance(v, str) and X.looks_like_person(v) else None
        if kind == "maybe_relative":
            kind = "relative" if isinstance(v, str) and X.looks_like_person(v) else None
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
        if u is not None:
            u.generalized = any(stats.get(key) for key in _QI_CHANGES)
        if u is not None and u.psn and u.psn not in out:
            out = f"Patient: {u.psn}\n" + out
        if u is not None:
            u.embedded = bool(u.psn and u.psn in out)
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
            unsafe_ext = bool(ext and self.san.scrub(ext, ctx, "filename") != ext)
            if risky or unsafe_ext:
                stem = ("record" if i == len(parts) - 1 else "folder") + "_" + self.keys.tag(
                    "/".join(parts[:i + 1]), 12
                )
                if unsafe_ext or ext and not re.fullmatch(r"[A-Za-z0-9]{1,8}", ext):
                    ext = {"fhir": "json", "text": "txt"}.get(d.fmt, d.fmt) or "txt"
            new_parts.append(stem + (dot + ext if dot else ""))
        return "/".join(new_parts)

    # ------------------------------------------------------------ pass 5: verify (self-correcting firewall)
    def verify(self, documents=None):
        fixes = quarantined = 0
        for d in self.docs if documents is None else documents:
            if d.status != "sanitized" or d.out_bytes is None:
                continue
            def scan(text):
                nonlocal fixes
                hits = self._residual(text)
                fixes += len(hits)
                spans = [(1, start, end, "[REDACTED]") for start, end in hits]
                return self.san._apply(text, spans)

            def check_json(value, parents=(), rtype=None):
                if isinstance(value, dict):
                    rt = value.get("resourceType", rtype)
                    for key, item in value.items():
                        kind = self._json_kind(key, parents, rt)
                        if isinstance(item, (list, dict)):
                            check_json(item, parents + (key,), rt)
                        elif isinstance(item, str) and kind not in {"doctor", "org", "clinical", "district", "tehsil", "state"}:
                            if d.fmt == "fhir" and key in {"reference", "fullUrl", "id", "system", "url", "data", "contentType", "code", "resourceType"}:
                                continue
                            value[key] = scan(item)
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if isinstance(item, str):
                            value[i] = scan(item)
                        else:
                            check_json(item, parents, rtype)

            try:
                text = d.out_bytes.decode("utf-8")
                if d.fmt in ("json", "fhir"):
                    obj = json.loads(text)
                    check_json(obj)
                    if d.fmt == "fhir":
                        FHIR(obj, self.keys, d.sha)
                    text = json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
                elif d.fmt == "csv":
                    source = io.StringIO(text, newline="")
                    target = io.StringIO(newline="")
                    writer = csv.writer(target, delimiter=d.delimiter, lineterminator=d.lineterm)
                    kinds = self.col_kinds[d.rel]
                    for i, row in enumerate(csv.reader(source, delimiter=d.delimiter, strict=True)):
                        writer.writerow([cell if i and kind in {"clinical", "doctor", "org", "district", "tehsil", "state"}
                                         else scan(cell) for kind, cell in zip(kinds, row)])
                    text = target.getvalue()
                else:
                    text = scan(text)
                d.out_bytes = text.encode("utf-8")
            except (ValueError, csv.Error):
                d.status, d.reason, d.out_bytes = "quarantined", "verification_error", None
                quarantined += 1
        if documents is not None:
            self.verification.update({"residual_fixes": fixes, "residual_quarantined": quarantined})
        else:
            self.diag["verification"] = {"residual_fixes": fixes, "residual_quarantined": quarantined}
            self.log.stage("verified")

    def _residual(self, text):
        hits = []
        protected = [m.span() for regex in (DOC_RE, ORG_RE, WARD_RE, ASHA_RE, EPONYM_RE, self.D.protect_re)
                     if regex for m in regex.finditer(text)]
        from .extract import aadhaar_candidate
        for regex, valid in (
            (self.D.phrase_re, lambda m: tuple(name_key(w) for w in split_name(m.group())) not in self.D.place_keys),
            (P.AADHAAR, lambda m: aadhaar_candidate(text, m)),
            (P.PHONE, lambda m: not P.phone_guard(text, *m.span())),
            (P.EMAIL, lambda m: True),
            (P.PAN, lambda m: True),
            (P.ABHA_NUM, lambda m: True),
            (self.D.core_re, lambda m: not P.phone_guard(text, *m.span())),
        ):
            if regex:
                for m in regex.finditer(text):
                    start, end = m.span()
                    if valid(m) and not any(start < right and end > left for left, right in protected):
                        hits.append((start, end))
        return hits

    # ------------------------------------------------------------ outputs
    def write(self, t0: float):
        san = self.out / "sanitized"
        san.mkdir(parents=True, exist_ok=True)
        files = []
        records = []
        used_paths = set()
        for d in self.docs:
            if d.status == "sanitized":
                rel = d.out_rel or d.rel
                while rel.lower() in used_paths:
                    stem, dot, ext = rel.rpartition(".")
                    rel = f"{stem}_{self.keys.tag(rel)[:4]}.{ext}" if dot else rel + "_"
                used_paths.add(rel.lower())
                d.out_rel = rel
                p = san / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                if d.verified_path:
                    p.write_bytes(self.staging.read(d.verified_path))
                else:
                    p.write_bytes(d.out_bytes)
                e = {"input_sha256": d.sha, "output": f"sanitized/{rel}", "status": "sanitized"}
                if rel != d.rel:
                    e["renamed"] = True
                files.append(e)
                if d.fmt == "fhir" and len(d.units) != 1:
                    records.append({"file": f"sanitized/{rel}", "loc": "doc", "patient": None})
                else:
                    for u in d.units:
                        if not u.bearing:
                            continue
                        patient = u.psn if u.embedded else None
                        r = {"file": f"sanitized/{rel}", "loc": u.loc, "patient": patient}
                        if u.generalized:
                            r["status"] = "generalized"
                        records.append(r)
            else:
                files.append({"input_sha256": d.sha, "output": None, "status": d.status,
                              "reason": d.reason or "unsupported_format"})
        with open(self.out / "records.jsonl", "w", encoding="utf-8", newline="\n") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
        sanitized_docs = [d for d in self.docs if d.status == "sanitized"]
        n_records = sum(len(d.units) for d in sanitized_docs)
        cluster_counts = Counter(r["patient"] for r in records if r["patient"])
        linked = sum(size for size in cluster_counts.values() if size > 1)
        gen = sum(1 for d in sanitized_docs for u in d.units if u.generalized)
        quarantine = [d for d in self.docs if d.status == "quarantined"]
        q_records = sum(len(d.units) for d in quarantine)
        suppressed = [d for d in self.docs if d.status == "suppressed"]
        report = {
            "schema": "raksha-report/1",
            "files": files,
            "counts": {
                "files_total": len(self.docs),
                "files_sanitized": len(sanitized_docs),
                "files_quarantined": len(quarantine),
                "files_suppressed": len(suppressed),
                "records_processed": n_records,
                "identifiers_detected": int(sum(v for k, v in self.entities.items())),
                "records_linked": linked,
                "records_generalized": gen,
                "records_suppressed": sum(len(d.units) for d in suppressed),
                "records_quarantined": q_records,
            },
            "entities": {k: int(v) for k, v in sorted(self.entities.items())},
            "timing": {"seconds": round(time.time() - t0, 2)},
            "resources": {"peak_rss_mb": peak_rss_mb()},
            "privacy": {"target_met": self.policy_result["target_met"], "strict_blocked": self.risk_blocked},
        }
        (self.out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        audit = {
            "schema": "stegnoz-audit/1",
            "policy": {k: v for k, v in self.policy_result.items() if k != "overrides"},
            "linkage": self.diag.get("linkage"),
            "verification": self.diag.get("verification"),
            "quarantine_reasons": dict(sorted(Counter(d.reason for d in self.docs if d.status == "quarantined").items())),
            "exposure": self.exposure,
        }
        (self.out / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return report

    def _release_signatures(self):
        """Collect matched facts from the verified output, including unresolved records."""
        profiles = defaultdict(set)
        simple = {"age", "age_sex", "gender", "tehsil", "district", "pin", "village", "address"}

        def collect(profile, kind, value, order):
            if not isinstance(value, (str, int, float)) or isinstance(value, bool):
                return
            text = str(value).strip().casefold()
            if not text or text in {"0", "[pin]", "[location]", "[village]", "[address]"}:
                return
            if kind in simple:
                profile.add((kind, text))
            if kind in {"diagnosis", "clinical"}:
                if kind == "diagnosis":
                    profile.add(("diagnosis", text))
                for code in P.ICD.findall(text.upper()):
                    profile.add(("diagnosis_code", code))
            if kind in {None, "date", "free"}:
                for pattern in X.FULL_DATE_PATTERNS:
                    for match in pattern.finditer(text):
                        date = X.parse_any_date(match.group(), order)
                        if date:
                            year, week, _ = date.isocalendar()
                            profile.add(("event_week", f"{year}-{week:02}"))
            if kind in {None, "free"}:
                for match in re.finditer(r"(?i)\b(?:age|umar)\s*[: -]*\d{1,3}(?:-\d{1,3}|\+)|[1-9]\d{2}\*\*\*", text):
                    profile.add(("text_qi", match.group()))
                for code in P.ICD.findall(text.upper()):
                    profile.add(("diagnosis_code", code))

        for d in self.docs:
            if d.status != "sanitized":
                continue
            text = self.staging.read(d.verified_path).decode("utf-8") if d.verified_path else d.out_bytes.decode("utf-8")
            rows = obj = None
            if d.fmt == "csv":
                rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=d.delimiter))[1:]
            elif d.fmt in {"json", "fhir"}:
                obj = json.loads(text)
            for u in d.units:
                if not u.bearing:
                    continue
                group = u.psn if u.embedded else (d.rel, u.loc)
                profile = profiles[group]
                profile.update(("source", source) for source in u.attrs["source"])
                if rows is not None:
                    for i, (key, kind, value) in enumerate(zip(d.header, self.col_kinds[d.rel], rows[int(u.loc[4:])])):
                        collect(profile, "diagnosis" if key.strip().casefold() in {"diagnosis", "dx"} else kind,
                                value, d.date_orders[i])
                elif obj is not None:
                    if d.fmt == "fhir" and u.loc != "doc":
                        plan = self.fhir[d.rel]
                        sections = [get_ptr(obj, path) for path, owner in plan.owners.items() if owner == u.loc]
                    else:
                        sections = [obj if u.loc == "doc" else get_ptr(obj, u.out_loc or u.loc)]
                    for section in sections:
                        for _, key, value, parents, rt, _ in walk_json(section):
                            kind = self._json_kind(key, parents, rt)
                            collect(profile, "diagnosis" if key.casefold() in {"diagnosis", "dx"} else kind,
                                    value, d.date_order)
                else:
                    collect(profile, None, text, d.date_order)
        return profiles

    def _exposure_stats(self):
        profiles = self._release_signatures()
        signatures = [frozenset(facts) for facts in profiles.values()]
        classes = Counter(signatures)
        buckets = Counter()
        cluster_sizes = Counter()
        for signature in signatures:
            k = classes[signature]
            bucket = "1" if k == 1 else "2-4" if k < 5 else "5-9" if k < 10 else "10+"
            buckets[bucket] += 1
        sizes = Counter(u.psn for u, d in zip(self.units, self.unit_doc)
                        if d.status == "sanitized" and u.bearing and u.embedded and u.psn)
        for size in sizes.values():
            cluster_sizes["1" if size == 1 else "2-3" if size <= 3 else "4-6" if size <= 6 else "7+"] += 1
        unresolved = sum(isinstance(key, tuple) for key in profiles)
        k_target = int(self.policy.get("k_target", 5))
        risk = sum(classes[signature] < k_target for signature in signatures) / max(1, len(profiles))
        # These facts cannot change under the age/location/PIN candidate lattice.
        # Their small classes are a lower bound, not an estimate of attacker success.
        preserved = [frozenset((kind, value) for kind, value in signature
                              if kind in {"diagnosis_code", "event_week", "source"})
                     for signature in signatures]
        preserved_classes = Counter(preserved)
        risk_floor = sum(preserved_classes[s] < k_target for s in preserved) / max(1, len(profiles))
        return {
            "patients": len(profiles),
            "k_anonymity": {k: buckets[k] for k in ("1", "2-4", "5-9", "10+")},
            "cluster_sizes": {k: cluster_sizes[k] for k in ("1", "2-3", "4-6", "7+")},
            "unlinked_records": unresolved,
            "singling_out_risk": risk,
            "preserved_facts_risk_floor": risk_floor,
            "k_target": k_target,
        }

    def run(self):
        t0 = time.time()
        self.ingest()
        self.extract()
        self.link()
        self.out.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".verified-", dir=self.out) as spool:
            self.choose(Path(spool))
            self.diag["verification"] = dict(self.verification)
            self.exposure = self._exposure_stats()
            target = float(self.policy.get("max_singling_out", 0.05))
            self.policy_result["risk_target"] = target
            self.policy_result["target_met"] = self.exposure["singling_out_risk"] <= target
            if self.strict_risk and not self.policy_result["target_met"]:
                self.risk_blocked = True
                for doc in self.docs:
                    if doc.status == "sanitized":
                        doc.status, doc.reason = "suppressed", "risk_target_exceeded"
            return self.write(t0)
