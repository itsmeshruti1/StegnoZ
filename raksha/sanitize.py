"""Detection + rewriting (passes 3/4).

Free text is processed as a set of candidate spans with priorities:
  protected (doctor names, hospitals/labs, wards, eponyms, ASHA)  >  strong identifiers  >
  address blocks  >  labelled / kinship / honorific names  >  dates & ages  >  dictionary names  >
  context names (capitalised spans next to phones or cue words: catches canaries in no list).
Accepted spans never overlap; protected spans are kept verbatim.

Hidden channels (base64, hex, \\uXXXX, HTML entities, %-encoding, zero-width characters,
homoglyphs) are decoded before detection; base64/hex payloads are re-encoded after cleaning so
attachments stay valid.
"""
from __future__ import annotations

import base64
import binascii
import html
import re
import unicodedata
from urllib.parse import unquote

from . import lexicon as L
from . import patterns as P
from . import privacy as PV
from .extract import (DISTRICT_RE, KIN_RE, NAME_LABEL_RE, NAME_SEQ, TEHSIL_RE, VILLAGE_RE, clean_name,
                      has_deva, looks_like_person)
from .translit import jaro_winkler, name_key
from .util import _HOMO, _ZW

WORD_RE = re.compile(r"[A-Za-z]+|[\u0900-\u0963\u0971-\u097F]+")
SAFE_WORDS = {w.lower() for w in (L.MEDICAL_WORDS | L.HINGLISH_MEDICAL | L.COMMON_EN)}
_ORG_SUFFIX = r"(?:Hospital|Hospitals|Diagnostics|Diagnostic|Pathology|Path\s+Lab|Labs?|Clinic|Centre|Center|Trust|Medical\s+College|Nursing\s+Home|Dispensary|PHC|CHC|Health\s+Centre|Polyclinic|Imaging|Scans?|Pharmacy|Medicals?)"
ORG_RE = re.compile(rf"(?:[A-Z][A-Za-z]+\s+){{1,4}}{_ORG_SUFFIX}\b|\b{_ORG_SUFFIX}\s*,\s*[A-Z][a-z]+")
DOC_RE = re.compile(r"(?:\b(?:Dr|DR|Doctor|Prof)\.?\s*|डॉ\.?\s*|डा\.\s*)(?:[A-Z][a-zA-Z'’]*\.?\s?){1,4}|(?:\b(?:Dr|DR|Doctor)\.?\s*|डॉ\.?\s*)[\u0900-\u097F]+(?:\s[\u0900-\u097F]+){0,2}")
WARD_RE = re.compile(r"\b(?:Ward|WARD)\s*(?:No\.?\s*)?\d+\s*\([A-Za-z ]+\)|\b(?:ICU|NICU|PICU|CCU|OT|Emergency|Casualty)\b")
ASHA_RE = re.compile(r"\bASHA\b(?:\s+(?:worker|didi|karyakarta|sahayogini|bahu|sevika))?|\b[Aa]sha\s+(?:worker|karyakarta|sahayogini|sevika)\b|आशा\s+(?:कार्यकर्ता|बहू|दीदी)")
EPONYM_RE = re.compile(r"\b(?:" + "|".join(sorted({re.escape(e.rstrip("'’s")) for e in L.EPONYMS}, key=len, reverse=True)) + r")(?:'s|’s|')?\s+(?:disease|syndrome|palsy|sign|test|fracture|ulcer|sarcoma|tumou?r|lymphoma|phenomenon|criteria|score|scale|triad|operation|procedure|repair|anomaly|tetralogy)\b", re.I)
POST_HON_RE = re.compile(r"(?P<n>(?:[A-Z][a-z]+|[\u0900-\u097F]+)(?:\s(?:[A-Z][a-z]+|[\u0900-\u097F]+))?)\s+(?P<h>" + "|".join(sorted(map(re.escape, L.POST_HONORIFICS - {"devi"}), key=len, reverse=True)) + r")\b(?!\s*[:])")
PRE_HON_RE = re.compile(r"\b(?:Mr|Mrs|Ms|Smt|Shri|Sri|Kumari|Km|Mst|Master|Baby)\.?\s+(?P<n>" + NAME_SEQ + ")")
BEFORE_KIN_RE = re.compile(rf"(?P<n>{NAME_SEQ})\s*,?\s*(?:\(?\s*)(?:S|D|W|C|B)\s*/\s*[Oo]\b")
KIN_LABEL_RE = re.compile(rf"(?i:attendant|guardian|father(?:'s)?\s*name|husband(?:'s)?\s*name|mother(?:'s)?\s*name|relative|next\s+of\s+kin|nok|informant|care\s+of|spouse)\s*[:\-–]\s*(?:(?i:Mr|Mrs|Smt|Shri)\.?\s+)?(?P<n>{NAME_SEQ})")
CUE_RE = re.compile(rf"(?i:called\s+by|raised\s+by|witnessed\s+by|signed\s+by|brought\s+by|accompanied\s+by|informed\s+by|visitor|caller|contact\s+person|consent\s+(?:given|signed)\s+by|attended\s+by)\s*[:\-–]?\s*(?P<n>{NAME_SEQ})")
CAP_SEQ_RE = re.compile(r"(?<![A-Za-z])(?:[A-Z][a-z'’]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-z'’]+|[A-Z]{2,})){1,2}(?![A-Za-z])")
ADDRESS_LINE_RE = re.compile(r"(?P<lab>(?i:address|addr|residence|res\.|pata)(?:\s*\([^)\n]{0,30}\))?\s*[:\-]\s*|पता\s*[:\-]\s*)(?P<v>[^\n]+)")
HOUSE_RE = re.compile(r"(?i:\b(?:H\.?\s*No|House(?:\s+No)?|Makan(?:\s+No)?|Flat(?:\s+No)?|Plot(?:\s+No)?|Qtr(?:\s+No)?|Door\s+No)\.?\s*[:\-]?\s*\d+[A-Za-z]?(?:/\d+)?)|मकान\s*नं\.?\s*[0-9\u0966-\u096F]+")
LOCALITY_RE = re.compile(r"\b(?:Mohalla|Mohallah|Mohala|Colony|Basti|Nagar|Sector|Gali|Lane)\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})|\b(?:[A-Z][a-z]+\s+){1,2}(?:Colony|Basti|Bazar|Bazaar|Nagar|Mohalla)\b|मोहल्ला\s+[\u0900-\u097F]+(?:\s[\u0900-\u097F]+)?")
LANDMARK_RE = re.compile(r"\b(?:near|opp\.?|opposite|behind|beside|next\s+to)\s+(?:the\s+)?(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})|[\u0900-\u097F]+(?:\s[\u0900-\u097F]+){0,2}\s+(?:के\s+पीछे|के\s+पास|के\s+सामने)")
B64_RE = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{20,}={0,2}(?![A-Za-z0-9+/=])")
HEX_RE = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}){12,}(?![0-9A-Fa-f])")
BIGNUM_RE = re.compile(r"(?<![\d.])\d{9,}(?![\d.])")


def _clean_view(text: str) -> str:
    """Decode disguises that would hide PII from detection."""
    t = text
    if "\\u" in t:
        t = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), t)
    if "&#" in t or "&amp;" in t or "&lt;" in t:
        t = re.sub(r"&#x?[0-9a-fA-F]+;|&[a-zA-Z]{2,8};", lambda m: html.unescape(m.group(0)), t)
    if re.search(r"%[0-9A-Fa-f]{2}%[0-9A-Fa-f]{2}", t):
        t = re.sub(r"(?:%[0-9A-Fa-f]{2})+", lambda m: unquote(m.group(0)), t)
    t = t.translate(_ZW)
    if any(ord(c) > 0x36F and ord(c) < 0x4FF for c in t):
        t = t.translate(_HOMO)
    return unicodedata.normalize("NFC", t)


class Ctx:
    """Per-record rewriting context."""
    __slots__ = ("psn", "shift", "order", "age_w", "loc", "pin", "own_keys", "rel_keys", "tehsil", "district",
                 "ref_year", "stats")

    def __init__(self, psn=None, shift=None, order="dmy", node=(5, "tehsil", "prefix3"), own_keys=(),
                 rel_keys=(), tehsil=None, district=None, ref_year=2026, stats=None):
        self.psn, self.shift, self.order = psn, shift, order
        self.age_w, self.loc, self.pin = node
        self.own_keys, self.rel_keys = set(own_keys), set(rel_keys)
        self.tehsil, self.district = tehsil, district
        self.ref_year = ref_year
        self.stats = stats if stats is not None else {}


class Sanitizer:
    def __init__(self, dictionary):
        self.D = dictionary   # see pipeline.Dictionary

    # ------------------------------------------------------------ helpers
    def _count(self, ctx, kind, n=1):
        ctx.stats[kind] = ctx.stats.get(kind, 0) + n

    def patient_token(self, ctx):
        return ctx.psn or "[PATIENT]"

    def is_name_word(self, w: str, strict: bool = True) -> str | None:
        """Return the role ('patient'|'relative'|'name') if the word is a known name token."""
        k = name_key(w)
        if len(k) < 3:
            return None
        role = self.D.name_keys.get(k)
        if role is None and len(k) >= 5:
            for cand in self.D.key_index.get(k[:2], ()):
                if abs(len(cand) - len(k)) <= 1 and jaro_winkler(k, cand) >= 0.94:
                    role = self.D.name_keys[cand]
                    break
        return role

    # ------------------------------------------------------------ free text
    def scrub(self, text: str, ctx: Ctx, kind: str | None = None) -> str:
        if not text or not isinstance(text, str):
            return text
        text = _clean_view(text)
        text = self._hidden_payloads(text, ctx)
        spans = []  # (priority, start, end, replacement or None for protected)

        def add(pr, s, e, rep):
            if e > s:
                spans.append((pr, s, e, rep))

        # protected clinical / organisational spans
        for rx in (DOC_RE, ORG_RE, WARD_RE, ASHA_RE, EPONYM_RE):
            for m in rx.finditer(text):
                add(100, m.start(), m.end(), None)
        for m in self.D.protect_re.finditer(text) if self.D.protect_re else ():
            add(100, m.start(), m.end(), None)
        for m in P.FREQ.finditer(text):
            add(100, m.start(), m.end(), None)
        for m in P.BP.finditer(text):
            if not P.DATE_NUM.match(text, m.start()):
                add(99, m.start(), m.end(), None)

        # strong identifiers
        for rx, tag in ((P.EMAIL, "[EMAIL]"), (P.ABHA_ADDR, "[ABHA]"), (P.ABHA_NUM, "[ABHA]"), (P.PAN, "[PAN]"),
                        (P.AADHAAR_MASKED, "[AADHAAR]"), (P.PHONE_MASKED, "[PHONE]"), (P.INSURANCE, "[INSURANCE-ID]")):
            for m in rx.finditer(text):
                add(95, m.start(), m.end(), tag)
                self._count(ctx, tag)
        for m in P.AADHAAR.finditer(text):
            d = P.norm_digits(m.group(0))
            if d[0] not in "01":
                add(94, m.start(), m.end(), "[AADHAAR]")
                self._count(ctx, "[AADHAAR]")
        for m in P.PHONE.finditer(text):
            if P.phone_guard(text, m.start(), m.end()):
                continue
            add(93, m.start(), m.end(), "[PHONE]")
            self._count(ctx, "[PHONE]")
        for m in P.GENERIC_ID.finditer(text):
            tok = m.group(0)
            nid = P.id_norm(tok)
            core = P.id_core(tok)
            psn = self.D.id_to_psn.get(nid) or (self.D.core_to_psn.get(core) if len(core) >= 5 else None)
            known = nid in self.D.ids or (len(core) >= 5 and core in self.D.id_cores)
            if known or psn:
                add(92, m.start(), m.end(), psn or (ctx.psn if nid in ctx.stats.get("_own_ids", ()) else None) or "[ID]")
                self._count(ctx, "[ID]")
        for m in re.finditer(r"(?<![\d])\d{5,}(?![\d])", text):
            core = m.group(0)
            if core in self.D.id_cores and (len(core) >= 6 or re.search(r"[A-Za-z_\-/]$", text[max(0, m.start() - 1):m.start()])):
                add(91, m.start(), m.end(), self.D.core_to_psn.get(core) or "[ID]")
                self._count(ctx, "[ID]")
        from .extract import ID_LABEL_RE
        for m in ID_LABEL_RE.finditer(text):
            v = m.group("id")
            if re.search(r"\d{3,}", v):
                nid = P.id_norm(v)
                add(92, m.start("id"), m.end("id"), self.D.id_to_psn.get(nid) or ctx.psn or "[ID]")
                self._count(ctx, "[ID]")
        for m in BIGNUM_RE.finditer(text):
            add(90, m.start(), m.end(), "[NUMBER]")

        # address blocks
        for m in ADDRESS_LINE_RE.finditer(text):
            add(85, m.start("v"), m.end("v"), self.scrub_address(m.group("v"), ctx))
            self._count(ctx, "[ADDRESS]")
        for rx, tag in ((HOUSE_RE, "[HOUSE]"), (LOCALITY_RE, "[LOCALITY]"), (LANDMARK_RE, "[LANDMARK]")):
            for m in rx.finditer(text):
                if rx is LOCALITY_RE and self._is_safe_phrase(m.group(0)):
                    continue
                if rx is LANDMARK_RE and not self._addressy(text, m.start()):
                    continue
                add(84, m.start(), m.end(), tag)
                self._count(ctx, tag)
        for m in VILLAGE_RE.finditer(text):
            add(84, m.start("v"), m.end("v"), self.village_out(ctx))
            self._count(ctx, "[VILLAGE]")
        for m in re.finditer(r"(?<![\d])([1-9]\d{5})(?![\d])", text):
            if re.search(r"(?i)(pin|pincode|zip|distt?\.?|district|जिला|ज़िला|tehsil)[^\n]{0,30}$", text[max(0, m.start() - 40):m.start()]) \
                    or re.search(r"(?i)pin", text[max(0, m.start() - 12):m.start()]) or text[max(0, m.start() - 3):m.start()].strip() == "-":
                add(84, m.start(), m.end(), PV.pin_out(m.group(1), ctx.pin))
                self._count(ctx, "[PIN]")

        # labelled / contextual names
        for rx, role in ((NAME_LABEL_RE, "patient"), (PRE_HON_RE, "patient"), (KIN_RE, "relative"),
                         (KIN_LABEL_RE, "relative"), (CUE_RE, "other")):
            for m in rx.finditer(text):
                s, e = m.start("n"), m.end("n")
                nm = clean_name(m.group("n"))
                if not nm:
                    continue
                if rx is KIN_RE and m.group("rel").lower().replace(" ", "").startswith("c/o") and \
                        nm.split()[0].lower() in SAFE_WORDS:
                    continue
                if nm.split()[0].lower() in SAFE_WORDS and not self.is_name_word(nm.split()[0]):
                    continue
                e = s + len(m.group("n")[:m.group("n").find(nm.split()[-1]) + len(nm.split()[-1])]) if nm.split()[-1] in m.group("n") else e
                add(80, s, e, self._name_rep(role, nm, ctx))
        for m in BEFORE_KIN_RE.finditer(text):
            nm = clean_name(m.group("n"))
            if nm and not (nm.split()[0].lower() in SAFE_WORDS and not self.is_name_word(nm.split()[0])):
                add(79, m.start("n"), m.start("n") + len(m.group("n").rstrip()), self._name_rep("patient", nm, ctx))
        for m in POST_HON_RE.finditer(text):
            nm = m.group("n")
            toks = nm.split()
            # keep only the trailing name-like tokens (e.g. "Report of Asha ji" -> "Asha")
            while toks and toks[0].lower() in SAFE_WORDS and not self.is_name_word(toks[0]):
                toks = toks[1:]
            if not toks:
                continue
            start = m.start("n") + nm.find(toks[0])
            add(78, start, m.end("h"), self._name_rep(None, " ".join(toks), ctx))

        # dates & ages
        if ctx.shift is not None:
            self._dates(text, ctx, add)
        self._ages(text, ctx, add)

        # dictionary names (any script)
        for m in WORD_RE.finditer(text):
            w = m.group(0)
            wl = w.lower().strip("'’")
            if len(w) < 3 or wl in L.GENERIC_NAME_PARTS:
                continue
            role = self.is_name_word(w)
            if not role:
                continue
            if not has_deva(w) and not w[:1].isupper():
                nxt = text[m.end():m.end() + 12].lower()
                if not any(nxt.strip().startswith(h) for h in L.POST_HONORIFICS):
                    continue
            if (wl in SAFE_WORDS or wl in L.COMMUNITY_ROLES) and name_key(w) not in ctx.own_keys:
                if not self._name_context(text, m.start(), m.end()):
                    continue
            add(60, m.start(), m.end(), self._word_rep(role, w, ctx))

        # village names learnt from structured fields, matched in any script
        if self.D.village_keys:
            words = list(WORD_RE.finditer(text))
            keys = [name_key(w.group(0)) for w in words]
            for i in range(len(words)):
                for n in (3, 2, 1):
                    if i + n > len(words):
                        continue
                    tup = tuple(k for k in keys[i:i + n] if k)
                    if tup in self.D.village_keys and tup not in self.D.place_keys:
                        if n == 1 and not has_deva(words[i].group(0)) and not words[i].group(0)[:1].isupper():
                            continue
                        add(83, words[i].start(), words[i + n - 1].end(), self.village_out(ctx))
                        self._count(ctx, "[VILLAGE]")
                        break

        # context names next to phones / IDs (canary-style names in no dictionary)
        for pr, s, e, rep in list(spans):
            if rep in ("[PHONE]", "[AADHAAR]", "[EMAIL]") or (rep and rep.startswith("PSN-")):
                line_s = text.rfind("\n", 0, s) + 1
                line_e = text.find("\n", e)
                line_e = len(text) if line_e < 0 else line_e
                for m in CAP_SEQ_RE.finditer(text, line_s, line_e):
                    if abs(m.start() - e) > 60 and abs(s - m.end()) > 60:
                        continue
                    toks = m.group(0).split()
                    if all(t.lower() in SAFE_WORDS or t.lower() in L.PRE_HONORIFICS for t in toks):
                        continue
                    if sum(t.lower() not in SAFE_WORDS for t in toks) < 1:
                        continue
                    add(55, m.start(), m.end(), self._name_rep("other", m.group(0), ctx))

        out = self._apply(text, spans)
        if kind is None:
            out = self._unknown_names(out, ctx)
        return out

    # ------------------------------------------------------------ pieces
    def _is_safe_phrase(self, s: str) -> bool:
        toks = [t.lower() for t in re.findall(r"[A-Za-z]+", s)]
        return all(t in SAFE_WORDS for t in toks)

    def _addressy(self, text, pos):
        window = text[max(0, pos - 80):pos + 80].lower()
        return any(k in window for k in ("address", "h.no", "house", "makan", "mohalla", "tehsil", "distt",
                                         "village", "vill.", "gram", "ward ", "पता", "मकान"))

    def _name_context(self, text, s, e):
        before = text[max(0, s - 25):s].lower()
        after = text[e:e + 15].lower()
        if re.search(r"(name|naam|patient|pt\.?|s/o|d/o|w/o|c/o|mr\.?|mrs\.?|smt\.?|shri|नाम)\s*[:\-]?\s*$", before):
            return True
        if any(after.strip().startswith(h) for h in ("ji", "sahab", "bhai", "didi", ", w/o", ", s/o", ", d/o", " w/o", " s/o", " d/o")):
            return True
        if re.match(r"\s+(?:ka|ki|ke|ko|ne|se)\s", after) or re.match(r"['’]s\s", after):
            return True
        nxt = re.match(r"\s+([A-Z][a-z]+)", text[e:e + 20])
        prv = re.search(r"([A-Z][a-z]+)\s+$", text[max(0, s - 20):s])
        for g in (nxt, prv):
            if g and self.is_name_word(g.group(1)) and g.group(1).lower() not in SAFE_WORDS:
                return True
        return False

    def _name_rep(self, role, name, ctx):
        toks = [name_key(t) for t in name.split() if name_key(t)]
        given = toks[0] if toks else ""
        if role == "relative":
            self._count(ctx, "RELATIVE_NAME")
            return "[RELATIVE]"
        if role == "patient" or (given and given in ctx.own_keys):
            if not (given in ctx.rel_keys and given not in ctx.own_keys):
                self._count(ctx, "PATIENT_NAME")
                return self.patient_token(ctx)
        self._count(ctx, "RELATIVE_NAME" if given in ctx.rel_keys else "PERSON_NAME")
        return "[RELATIVE]" if given in ctx.rel_keys else "[NAME]"

    def _word_rep(self, role, w, ctx):
        k = name_key(w)
        if k in ctx.own_keys:
            self._count(ctx, "PATIENT_NAME")
            return self.patient_token(ctx)
        if k in ctx.rel_keys:
            self._count(ctx, "RELATIVE_NAME")
            return "[RELATIVE]"
        self._count(ctx, "PERSON_NAME")
        return "[NAME]"

    def _apply(self, text, spans):
        spans.sort(key=lambda x: (-x[0], -(x[2] - x[1]), x[1]))
        taken = []
        for sp in spans:
            pr, s, e, rep = sp
            if any(not (e <= ts or s >= te) for _, ts, te, _ in taken):
                continue
            taken.append(sp)
        out, pos = [], 0
        for pr, s, e, rep in sorted(taken, key=lambda x: x[1]):
            out.append(text[pos:s])
            out.append(text[s:e] if rep is None else rep)
            pos = e
        out.append(text[pos:])
        res = "".join(out)
        # merge "PSN-X PSN-X" / "[NAME] [NAME]" runs created by token-level hits
        res = re.sub(r"(PSN-[A-Z]+)(?:[\s.]+\1)+", r"\1", res)
        res = re.sub(r"(\[(?:NAME|RELATIVE|PATIENT)\])(?:[\s.]+\1)+", r"\1", res)
        return res

    def _unknown_names(self, text, ctx):
        return text

    def _dates(self, text, ctx, add):
        sh = ctx.shift
        for m in P.DATE_ISO.finditer(text):
            rep, d = PV.shift_iso(m, sh)
            if rep:
                add(70, m.start(), m.end(), rep)
        for m in P.DATE_NUM.finditer(text):
            rep, d = PV.shift_numeric(m, sh, ctx.order)
            if rep:
                add(70, m.start(), m.end(), rep)
        for m in P.DATE_DMONY.finditer(text):
            rep, d = PV.shift_dmony(m, sh, ctx.ref_year)
            if rep:
                add(69, m.start(), m.end(), rep)
        for m in P.DATE_MONDY.finditer(text):
            rep, d = PV.shift_mondy(m, sh)
            if rep:
                add(69, m.start(), m.end(), rep)
        for m in P.DATE_HINDI.finditer(text):
            rep, d = PV.shift_hindi(m, sh, ctx.ref_year)
            if rep:
                add(69, m.start(), m.end(), rep)

    def _ages(self, text, ctx, add):
        for i, rx in enumerate(P.AGE_FORMS):
            for m in rx.finditer(text):
                if i == 2:
                    num_g = 2
                else:
                    num_g = 1
                a = P.to_int(m.group(num_g))
                if not 0 <= a < 125:
                    continue
                if i in (0, 1, 3):
                    pre = text[max(0, m.start() - 4):m.start()].lower()
                    if re.search(r"(x|for|since)\s*$", pre):
                        continue
                add(71, m.start(num_g), m.end(num_g), PV.age_band(a, ctx.age_w))
                self._count(ctx, "AGE")

    def village_out(self, ctx):
        if ctx.loc == "tehsil" and ctx.tehsil:
            return ctx.tehsil
        if ctx.district:
            return ctx.district
        return "[VILLAGE]"

    def scrub_address(self, value: str, ctx: Ctx) -> str:
        parts = re.split(r"\s*,\s*", value)
        kept, dropped = [], False
        for p in parts:
            pp = p.strip()
            if not pp:
                continue
            if TEHSIL_RE.match(pp) and ctx.loc == "tehsil":
                kept.append(pp)
                continue
            if DISTRICT_RE.match(pp) or re.match(r"^(?:Uttar Pradesh|UP|U\.P\.|India|उत्तर प्रदेश)\b", pp):
                pin = re.search(r"([1-9][0-9]{5})", P.norm_digits_keep(pp))
                if pin:
                    pp = pp[:pin.start()].rstrip(" -") + " - " + PV.pin_out(pin.group(1), ctx.pin)
                kept.append(pp)
                continue
            pin = re.fullmatch(r"(?:PIN\s*[:\-]?\s*)?([1-9][0-9]{5})", P.norm_digits_keep(pp), re.I)
            if pin:
                kept.append(PV.pin_out(pin.group(1), ctx.pin))
                continue
            dropped = True
        if dropped:
            kept.insert(0, "[ADDRESS]")
        return ", ".join(kept)

    def _hidden_payloads(self, text: str, ctx: Ctx) -> str:
        def b64(m):
            tok = m.group(0)
            if len(tok) % 4 == 1 or tok.isdigit() or tok.isalpha() and tok.lower() == tok:
                return tok
            try:
                raw = base64.b64decode(tok + "=" * (-len(tok) % 4), validate=True)
                dec = raw.decode("utf-8")
            except (binascii.Error, ValueError, UnicodeDecodeError):
                return tok
            if not dec or sum(c.isprintable() or c in "\r\n\t" for c in dec) < 0.95 * len(dec):
                return tok
            clean = self.scrub(dec, ctx)
            if clean == dec:
                return tok
            self._count(ctx, "HIDDEN_PAYLOAD")
            return base64.b64encode(clean.encode("utf-8")).decode("ascii")

        def hx(m):
            tok = m.group(0)
            try:
                dec = bytes.fromhex(tok).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                return tok
            if not dec or sum(c.isprintable() for c in dec) < 0.95 * len(dec):
                return tok
            clean = self.scrub(dec, ctx)
            if clean == dec:
                return tok
            self._count(ctx, "HIDDEN_PAYLOAD")
            return clean.encode("utf-8").hex()

        if len(text) >= 20:
            text = B64_RE.sub(b64, text)
            text = HEX_RE.sub(hx, text)
        return text

    # ------------------------------------------------------------ structured values
    def value(self, kind, v, ctx: Ctx, date_order="dmy"):
        """Rewrite one structured value by field kind, preserving JSON type where possible."""
        if v is None or isinstance(v, bool):
            return v
        is_num = isinstance(v, (int, float))
        s = str(v) if not isinstance(v, str) else v
        if s.strip() == "":
            return v
        if kind in ("name", "maybe_name"):
            if kind == "maybe_name" and not looks_like_person(s):
                return self.scrub(s, ctx)
            self._count(ctx, "PATIENT_NAME")
            return self.patient_token(ctx)
        if kind == "relative":
            m = re.match(r"^\s*((?:[SDWCBFM]\s*/\s*[Oo])|(?:पुत्र|पुत्री|पत्नी|पति|पिता)\b)\s*", s)
            self._count(ctx, "RELATIVE_NAME")
            return (m.group(1) + " " if m else "") + "[RELATIVE]"
        if kind == "org" or kind == "doctor":
            return v if is_num else self._scrub_ids_only(s, ctx)
        if kind in ("phone", "contact_value"):
            if kind == "contact_value" and "@" in s:
                self._count(ctx, "[EMAIL]")
                return "[EMAIL]"
            if not re.search(r"\d{5,}", P.norm_digits_keep(s)):
                return self.scrub(s, ctx)
            self._count(ctx, "[PHONE]")
            return 0 if is_num else "[PHONE]"
        if kind == "email":
            self._count(ctx, "[EMAIL]")
            return "[EMAIL]"
        if kind == "aadhaar":
            self._count(ctx, "[AADHAAR]")
            return 0 if is_num else "[AADHAAR]"
        if kind in ("abha", "abha_addr"):
            self._count(ctx, "[ABHA]")
            return 0 if is_num else "[ABHA]"
        if kind == "pan":
            self._count(ctx, "[PAN]")
            return "[PAN]"
        if kind == "insurance":
            self._count(ctx, "[INSURANCE-ID]")
            return 0 if is_num else "[INSURANCE-ID]"
        if kind == "mrn":
            if not re.search(r"\d{3,}", s):
                return self.scrub(s, ctx)
            self._count(ctx, "[ID]")
            rep = self.D.id_to_psn.get(P.id_norm(s)) or ctx.psn or "[ID]"
            return 0 if is_num else rep
        if kind == "address":
            self._count(ctx, "[ADDRESS]")
            return self.scrub_address(s, ctx) if not is_num else 0
        if kind == "village":
            self._count(ctx, "[VILLAGE]")
            return self.village_out(ctx)
        if kind == "tehsil":
            return v if ctx.loc == "tehsil" else (ctx.district or "[LOCATION]")
        if kind in ("district", "state", "gender", "relation"):
            return v
        if kind == "pin":
            self._count(ctx, "[PIN]")
            return 0 if is_num else PV.pin_out(s, ctx.pin)
        if kind == "dob":
            self._count(ctx, "DOB")
            if ctx.shift is None:
                return "[DOB]"
            out = self._shift_value(s, ctx)
            return out if out != s else "[DOB]"
        if kind == "age":
            m = re.search(r"\d{1,3}", P.norm_digits_keep(s))
            if not m:
                return v
            band = PV.age_band(int(m.group(0)), ctx.age_w)
            self._count(ctx, "AGE")
            return band if is_num else s[:m.start()] + band + s[m.end():]
        if kind == "age_sex":
            m = re.search(r"\d{1,3}", P.norm_digits_keep(s))
            if not m:
                return v
            self._count(ctx, "AGE")
            return s[:m.start()] + PV.age_band(int(m.group(0)), ctx.age_w) + s[m.end():]
        if kind == "date":
            if is_num or ctx.shift is None:
                return v
            return self._shift_value(s, ctx)
        if kind == "base64":
            return self._hidden_payloads(s, ctx) if not is_num else v
        if is_num:
            ds = str(v)
            if re.fullmatch(r"\d{9,}", ds) or (ds in self.D.id_cores and len(ds) >= 6):
                self._count(ctx, "[ID]")
                return 0
            return v
        return self.scrub(s, ctx, kind)

    def _scrub_ids_only(self, s, ctx):
        out = P.PHONE.sub(lambda m: "[PHONE]" if not P.phone_guard(s, m.start(), m.end()) else m.group(0), s)
        out = P.EMAIL.sub("[EMAIL]", out)
        return out

    def _shift_value(self, s, ctx):
        spans = []
        self._dates(s, ctx, lambda pr, a, b, rep: spans.append((pr, a, b, rep)))
        if not spans:
            return s
        return self._apply(s, spans)
