"""Schema intelligence + identity extraction (pass 1).

* `classify_key` maps any column header / JSON key (English, Hindi, Hinglish, misspelled) to a
  field kind using an exact lexicon, keyword rules, JSON parent context (guardian.name is a
  relative; facility.name is an organisation) and FHIR resource context.
* `classify_column` adds content voting for headers it has never seen (values that look like
  phones, Aadhaar, e-mails, person names...).  Unknown columns are never passed through: they
  are scanned as free text.
* `extract_unit` collects identity attributes for linkage and feeds the run-wide dynamic PII
  dictionary used by the detector (names, relatives, villages, record numbers, doctors).
"""
from __future__ import annotations

import re
from collections import defaultdict
from functools import lru_cache

from . import lexicon as L
from . import patterns as P
from .translit import has_deva, jaro_winkler, name_key, split_name

# ---------------------------------------------------------------- key classification
_LEX_INDEX: dict[str, str] = {}
for _kind, _keys in L.FIELD_LEXICON.items():
    for _k in _keys:
        _LEX_INDEX.setdefault(_k, _kind)

ORG_PARENTS = {"facility", "hospital", "organization", "organisation", "org", "lab", "laboratory", "clinic",
               "provider", "practitioner", "doctor", "department", "panel", "panels", "test", "tests", "drug",
               "drugs", "rx", "medication", "medications", "diagnosis", "diagnoses", "package", "ward", "insurer",
               "payer", "tpa", "scheme", "coding", "code", "type", "category", "class", "location", "performer",
               "author", "custodian", "attester", "results", "result", "investigation", "procedure", "system",
               "_export_meta", "export_meta", "meta", "qualification", "service", "specialty"}
RELATIVE_PARENTS = {"guardian", "relative", "father", "husband", "spouse", "mother", "kin", "nok", "next_of_kin",
                    "attendant", "contact_person", "emergency_contact", "care_of", "relatedperson", "nominee"}
PERSON_PARENTS = {"patient", "raised_by", "caller", "visitor", "member", "beneficiary", "insured", "person",
                  "subject", "informant", "requester", "applicant", "client", "customer", "contact", "owner",
                  "witness", "signed_by", "user", "reporter", "consent_by", "policy_holder", "policyholder"}


def _nk(key: str) -> str:
    k = str(key).strip().lower()
    k = re.sub(r"[_\-.]+", " ", k)
    return re.sub(r"\s+", " ", k).strip()


def classify_key(key, parents: tuple = (), rtype: str | None = None) -> str | None:
    """Kind for a header/key given its JSON parents (nearest last) and FHIR resource type."""
    raw = str(key)
    k = _nk(raw)
    k_noparen = re.sub(r"\s*\(.*?\)\s*", " ", k).strip()
    parent = _nk(parents[-1]) if parents else ""
    pset = {_nk(p).replace(" ", "_") for p in parents}

    # FHIR-specific contexts
    if rtype:
        if rtype in {"Practitioner", "Organization", "Location", "Device", "Medication", "PractitionerRole",
                     "HealthcareService", "Endpoint"}:
            if k in {"value"} and "telecom" in pset:
                return None
            return "org" if k in {"name", "text", "family", "given", "display"} else None
        if k == "div":
            return "free"
        if rtype in {"Patient", "RelatedPerson", "Person"}:
            role = "relative" if rtype == "RelatedPerson" or "contact" in pset else "name"
            if "name" in pset and k in {"text", "family", "given", "prefix", "suffix"}:
                return role if k in {"text", "family", "given"} else None
            if "telecom" in pset and k == "value":
                return "contact_value"
            if "identifier" in pset and k == "value":
                return "mrn"
            if "address" in pset:
                return {"line": "address", "text": "address", "city": "village", "district": "district",
                        "state": "state", "postalcode": "pin", "country": None}.get(k, "address")
            if k == "birthdate":
                return "dob"
        if "identifier" in pset and k == "value" and rtype in {"Encounter", "EpisodeOfCare", "Claim",
                                                                "Coverage", "ServiceRequest", "Account",
                                                                "DiagnosticReport", "Composition"}:
            return "mrn"
        if k == "display" and ("subject" in pset or "patient" in pset or "beneficiary" in pset):
            return "name"
        if k == "display" and ("author" in pset or "performer" in pset or "practitioner" in pset):
            return "doctor"
        if k == "data" and "attachment" in pset:
            return "base64"
        if k == "source" and "meta" in pset:
            return "free"
        if k in {"reference", "fullurl", "id", "system", "code", "status", "resourcetype", "url"}:
            return None

    if k in {"first", "last", "given", "family", "middle", "local", "full", "hindi", "latin"} and parent in {"name", "naam"}:
        return "relative" if pset & RELATIVE_PARENTS else "name"
    if k in {"name", "naam", "full name", "fullname"}:
        if pset & RELATIVE_PARENTS:
            return "relative"
        if pset & PERSON_PARENTS:
            return "name"
        if pset & ORG_PARENTS:
            return "org"
        return "maybe_name"
    hit = _LEX_INDEX.get(k) or _LEX_INDEX.get(k_noparen)
    if hit:
        if hit in {"phone", "email"} and pset & ORG_PARENTS:
            return hit
        if hit == "name" and pset & RELATIVE_PARENTS:
            return "relative"
        if hit == "address" and pset & ORG_PARENTS:
            return None
        if hit == "date" and parents and _nk(parents[-1]) in {"export meta", " export meta"}:
            return None
        return hit
    # keyword rules for unseen headers
    toks = set(k_noparen.split())
    if toks & {"aadhaar", "aadhar", "adhaar", "adhar", "uid"}:
        return "aadhaar"
    if toks & {"abha", "healthid"}:
        return "abha_addr" if "address" in toks else "abha"
    if toks & {"pan"}:
        return "pan"
    if toks & {"mobile", "phone", "contact", "mob", "cell", "telephone", "whatsapp", "callback", "tel"}:
        return "phone"
    if toks & {"email", "mail"}:
        return "email"
    if toks & {"dob", "birth", "janm"}:
        return "dob"
    if toks & {"pin", "pincode", "zip", "postal"} or ("post" in toks and toks & {"idx", "index", "code"}):
        return "pin"
    if toks & {"village", "gaon", "gram", "vill", "city", "town"}:
        return "village"
    if toks & {"tehsil", "tahsil", "taluka"}:
        return "tehsil"
    if toks & {"district", "distt", "jila", "zila"}:
        return "district"
    if toks & {"address", "addr", "street", "mohalla", "locality", "landmark", "house", "pata"}:
        return "address"
    if toks & {"uhid", "mrn", "crno", "ipd", "regno", "registration"} or k_noparen in {"reg no", "patient id", "cr no"}:
        return "mrn"
    if toks & {"pmjay", "policy", "insurance", "ayushman", "claim"} and not toks & {"amount", "status", "type", "date"}:
        return "insurance"
    if ("name" in toks or "naam" in toks) and toks & {"father", "husband", "guardian", "relative", "spouse",
                                                       "mother", "pita", "pati", "attendant", "kin"}:
        return "relative"
    if toks & {"doctor", "consultant", "physician", "surgeon", "clinician"} or k_noparen.startswith("dr"):
        return "doctor"
    if ("name" in toks or "naam" in toks):
        if toks & {"drug", "test", "hospital", "facility", "lab", "doctor", "department", "package", "panel",
                   "medicine", "brand", "generic", "procedure", "ward", "scheme", "insurer", "file", "user",
                   "clinic", "organisation", "organization", "company", "product", "item", "service"}:
            return None
        return "maybe_name"
    if toks & {"age", "umar", "umr", "aayu"}:
        return "age_sex" if toks & {"sex", "gender"} else "age"
    if toks & {"gender", "sex", "ling"}:
        return "gender"
    if toks & {"date", "dt", "on", "tithi"} or k_noparen.endswith("date") or k_noparen.endswith(" at"):
        return "date"
    if toks & {"nm", "fnm", "lnm", "nombre", "naam"} or any("nm" in tk and len(tk) <= 6 for tk in toks):
        return "relative" if pset & RELATIVE_PARENTS else "name"
    # schema-robust fallback: an unknown short key directly under a person/relative context
    # whose value is a name belongs to that person (handles renamed/unseen keys).
    if k not in {"id", "type", "code", "status", "ref", "value", "url", "system", "display"} \
            and not pset & ORG_PARENTS:
        if pset & RELATIVE_PARENTS:
            return "maybe_relative"
        if pset & PERSON_PARENTS:
            return "maybe_name"
    return None


def looks_like_person(value: str) -> bool:
    v = value.strip()
    if not v or len(v) > 60 or any(ch.isdigit() for ch in v):
        return False
    toks = split_name(v)
    if not 1 <= len(toks) <= 5:
        return False
    if has_deva(v):
        return True
    low = {t.lower().strip(".") for t in toks}
    if low & (L.MEDICAL_WORDS | {"hospital", "lab", "diagnostics", "pathology", "clinic", "centre", "center",
                                  "trust", "routine", "panel", "department"}):
        return False
    caps = sum(1 for t in toks if t[:1].isupper())
    if caps < len(toks):
        return False
    known = sum(1 for t in low if t in L.GIVEN_NAMES or t in L.SURNAMES)
    return len(toks) >= 2 or known >= 1


def _looks_address(s: str) -> bool:
    return bool(re.search(r"(?i)\b(?:H\.?\s*No|House|Makan|Flat|Mohalla|Colony|Ward\s+\d|near|opp\.?|Gali|"
                          r"Nagar|Basti|Sector)\b|मकान|मोहल्ला|वार्ड", s)) and len(s) > 12


def _looks_date(s: str) -> bool:
    return bool(P.DATE_ISO.fullmatch(s) or P.DATE_NUM.fullmatch(s) or
                P.DATE_DMONY.fullmatch(s) or P.DATE_MONDY.fullmatch(s))


_KEEP_HEADERS = re.compile(r"(?i)\b(?:package|procedure|scheme|hcpcs|cpt|drug|test|loinc|icd|bill\s*no|"
                           r"bill_no|invoice|sample_?id|sample\s*no|lab\s*no|visit_?id|opd\s*no\b|"
                           r"status|package_?code|dept|department|ward|room|bed|package_name|product|"
                           r"service|diagnosis|strength|frequency|dose|dosage|unit|result|range|amount|"
                           r"qty|quantity|code|loinc_?code|icd_?code)\b")


def classify_column(header: str, values: list[str]) -> str | None:
    kind = classify_key(header)
    h = str(header)
    # clinical / coding / transactional columns are not identifiers: never content-vote them to PII
    if kind is None and _KEEP_HEADERS.search(h) and not re.search(r"(?i)name|patient|phone|mobile|aadha", h):
        return "clinical"
    vals = [v for v in values if v and str(v).strip()][:200]
    if kind not in (None, "maybe_name"):
        return kind
    if not vals:
        return kind
    n = len(vals)
    score = defaultdict(int)
    for v in vals:
        s = str(v).strip()
        if P.EMAIL.fullmatch(s):
            score["email"] += 1
        elif P.ABHA_NUM.fullmatch(s):
            score["abha"] += 1
        elif P.PAN.fullmatch(s):
            score["pan"] += 1
        elif (P.AADHAAR.fullmatch(s) and P.verhoeff_ok(P.norm_digits(s))) or P.AADHAAR_MASKED.fullmatch(s):
            score["aadhaar"] += 1
        elif P.PHONE.fullmatch(s) or P.PHONE_MASKED.fullmatch(s):
            score["phone"] += 1
        elif re.fullmatch(r"[1-9]\d{5}", P.norm_digits_keep(s)):
            score["pin"] += 1
        elif _looks_date(s):
            score["date"] += 1
        elif _looks_address(s):
            score["address"] += 1
        elif looks_like_person(s):
            score["maybe_name"] += 1
        elif re.fullmatch(r"(?=.*\d)[A-Za-z]{1,8}[A-Za-z0-9]*(?:[-/][A-Za-z0-9]+)*", s) and \
                re.search(r"\d{3,}", s) and re.match(r"[A-Za-z]", s):
            score["mrn"] += 1
    if score:
        best = max(sorted(score), key=lambda x: score[x])
        thresh = max(2, 0.6 * n) if best not in ("mrn", "pin", "aadhaar", "phone", "abha", "pan") else max(2, 0.5 * n)
        if score[best] >= thresh or (n <= 3 and score[best] == n):
            k = "name" if best == "maybe_name" else best
            # a DOB column is a date column whose header hints birth; otherwise generic date
            return k
    return kind


# ---------------------------------------------------------------- text extraction regexes
_NAME_TOK = r"(?:[A-Z][a-zA-Z'’]+\.?|[A-Z]{2,}|[ऀ-ॿ]+)"
NAME_SEQ = rf"{_NAME_TOK}(?:[ \t]{_NAME_TOK}){{0,3}}"
_LABELS = "|".join(sorted(L.NAME_LABELS_LATIN, key=len, reverse=True))
_DEVA_LABELS = "|".join(sorted(map(re.escape, L.NAME_LABELS_DEVA), key=len, reverse=True))
NAME_LABEL_RE = re.compile(rf"(?:(?<![A-Za-z])(?i:{_LABELS})\s*[:\-–]\s*|(?<![A-Za-z])(?i:report\s+of|called\s+by|raised\s+by|witnessed\s+by|signed\s+by|brought\s+by|accompanied\s+by)\s+|(?:{_DEVA_LABELS})\s*[:\-]\s*)(?P<n>{NAME_SEQ})")
_KIN = "|".join(L.KIN_MARKERS_LATIN)
_KIN_DEVA = "|".join(sorted(map(re.escape, L.KIN_MARKERS_DEVA), key=len, reverse=True))
KIN_RE = re.compile(rf"(?P<rel>(?<![A-Za-z])(?:{_KIN})|(?:{_KIN_DEVA}))\s*[:\-–.]?\s*(?:(?i:Mr|Mrs|Smt|Shri|Sri|Late)\.?\s+)?(?P<n>{NAME_SEQ})")
DOB_RE = re.compile(r"(?i:DOB|D\.O\.B\.?|Date\s+of\s+Birth|Birth\s*Date|जन्म\s*तिथि|Janm\s*Tithi)\s*[:\-]?\s*(?P<d>[0-9०-९]{1,4}[/.\-][0-9०-९]{1,2}[/.\-][0-9०-९]{2,4})")
ID_LABEL_RE = re.compile(r"(?i:UHID|MRN|MR\s*No|Reg(?:istration)?\.?\s*No|IPD\s*No|IP\s*No|OPD\s*No|CR\s*No|Patient\s*ID|Hosp(?:ital)?\.?\s*No|Case\s*No|Adm(?:ission)?\.?\s*No|पंजीकरण\s*सं|आईपीडी\s*सं)\.?\s*[:\-#]?\s*(?P<id>[A-Za-z0-9][A-Za-z0-9/\-]{3,})")
VILLAGE_RE = re.compile(r"(?:(?<![A-Za-z])(?:Vill(?:age)?\.?|Gram|Gaon|Mauza)\s*[:\-]?\s+|(?:ग्राम|गाँव|गांव)\s*[:\-]?\s*)(?P<v>(?:[A-Z][a-zA-Z]+|[ऀ-ॿ]+)(?:\s(?:[A-Z][a-zA-Z]+|[ऀ-ॿ]+)){0,2})")
AADHAAR_LABEL_RE = re.compile(r"(?i)(?:aadha?a?r|आधार)\s*(?:(?:no|number)\.?\s*)?[:#-]?\s*$")
TEXT_SUBJECT_RE = re.compile(
    r"(?m)(?<!\w)(?P<name>[A-Z][a-z'’]+(?:[ \t]+[A-Z][a-z'’]+){1,2})[ \t]+"
    r"(?i:returned|reported|arrived|presented|attended|visited|complained|was admitted|was discharged)\b"
)
FULL_DATE_PATTERNS = (P.DATE_ISO, P.DATE_NUM, P.DATE_DMONY, P.DATE_MONDY, P.DATE_HINDI)


def subject_names(text):
    for match in TEXT_SUBJECT_RE.finditer(text):
        tokens = match.group("name").split()
        if not any(token.casefold() in L.MEDICAL_WORDS | L.COMMON_EN | L.HINGLISH_MEDICAL for token in tokens):
            yield match


def aadhaar_candidate(text, match):
    digits = P.norm_digits(match.group())
    return digits[0] not in "01" and (
        P.verhoeff_ok(digits) or bool(AADHAAR_LABEL_RE.search(text[max(0, match.start() - 35):match.start()]))
    )


TEHSIL_RE = re.compile(r"(?:(?<![A-Za-z])(?:Tehsil|Tahsil|Teh\.)\s*[:\-]?\s+|तहसील\s*[:\-]?\s*)(?P<v>(?:[A-Z][a-zA-Z]+|[ऀ-ॿ]+)(?:\s(?:[A-Z][a-zA-Z]+|[ऀ-ॿ]+))?)")
DISTRICT_RE = re.compile(r"(?:(?<![A-Za-z])(?:Distt?\.?|District|Dist\.)\s*[:\-]?\s+|(?:जिला|ज़िला)\s*[:\-]?\s*)(?P<v>(?:[A-Z][a-zA-Z]+|[ऀ-ॿ]+)(?:\s(?:[A-Z][a-zA-Z]+|[ऀ-ॿ]+))?)")
GENDER_RE = re.compile(r"(?:/\s*|\b)(?P<g>M|F|Male|Female|पुरुष|महिला)\b")

_STOP_TOKENS = {t.lower() for t in ["Age", "Sex", "UHID", "IPD", "Mob", "Mobile", "Reg", "No", "Date", "DOB",
                                     "Address", "Ward", "Bed", "Dr", "Ph", "Phone", "Tel", "Gender", "Yrs",
                                     "Years", "Consultant", "Patient", "Name", "Attendant", "Visit",
                                     "Diagnosis", "History", "Rx", "Adv", "Advice", "Report", "Hospital",
                                     "Of", "The", "And", "For", "With", "Is", "Was", "In", "On", "At",
                                     "Discharged", "Admitted", "Treated", "Sample", "Test", "Collected"]}
_STOP_TOKENS |= {"आयु", "उम्र", "पता", "मोबाइल", "पंजीकरण", "सं.", "लिंग", "का", "की", "के", "नाम"}


def clean_name(seq: str) -> str:
    out = []
    for t in seq.split():
        tl = t.lower().strip(".:,'’")
        if tl in _STOP_TOKENS or tl in L.POST_HONORIFICS or tl in L.MEDICAL_WORDS:
            break
        if tl in L.PRE_HONORIFICS:
            continue
        out.append(t.strip(",:;"))
    return " ".join(out)


# ---------------------------------------------------------------- unit attribute extraction
def new_attrs() -> dict:
    return {"names": [], "relatives": [], "dob": set(), "ages": [], "gender": set(), "phones": set(),
            "aadhaar": set(), "abha": set(), "ids": set(), "emails": set(), "pans": set(), "insurance": set(),
            "villages": [], "tehsils": [], "districts": [], "pins": set(), "cand_ids": set(), "cores": set(),
            "cand_cores": {}, "id_scopes": {}, "source": set(), "event_dates": set()}


def norm_gender(v: str) -> str | None:
    v = str(v).strip().lower()
    if v in {"m", "male", "पुरुष", "man", "boy", "purush"}:
        return "M"
    if v in {"f", "female", "महिला", "woman", "girl", "mahila", "stree", "स्त्री"}:
        return "F"
    return None


def add_value(attrs: dict, kind: str, value, date_order: str = "dmy"):
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        sval = str(int(value)) if isinstance(value, int) or float(value).is_integer() else str(value)
    elif isinstance(value, str):
        sval = value.strip()
    else:
        return
    if not sval:
        return
    if kind == "name":
        nm = clean_name(sval) if not has_deva(sval) else sval
        if nm and not any(ch.isdigit() for ch in nm):
            attrs["names"].append(nm)
    elif kind == "relative":
        m = KIN_RE.search(sval)
        nm = clean_name(m.group("n")) if m else clean_name(re.sub(r"^(?i:S/O|D/O|W/O|C/O|H/O)\s*", "", sval))
        if has_deva(sval) and not m:
            nm = sval
        if nm:
            attrs["relatives"].append(nm)
    elif kind in ("maybe_name", "maybe_relative"):
        if looks_like_person(sval):
            tgt = "relatives" if kind == "maybe_relative" else "names"
            attrs[tgt].append(clean_name(sval) if not has_deva(sval) else sval)
    elif kind in ("dob", "date"):
        d = parse_any_date(sval, date_order)
        if d:
            attrs["dob" if kind == "dob" else "event_dates"].add(d.isoformat())
    elif kind == "age":
        m = re.search(r"\d{1,3}", P.norm_digits_keep(sval))
        if m and 0 <= int(m.group(0)) < 125:
            attrs["ages"].append(int(m.group(0)))
    elif kind == "age_sex":
        m = re.search(r"(\d{1,3})", P.norm_digits_keep(sval))
        if m:
            attrs["ages"].append(int(m.group(1)))
        g = re.search(r"/\s*([MFmf])", sval)
        if g:
            attrs["gender"].add(g.group(1).upper())
    elif kind == "gender":
        g = norm_gender(sval)
        if g:
            attrs["gender"].add(g)
    elif kind in {"phone", "contact_value"}:
        for m in P.PHONE.finditer(sval):
            attrs["phones"].add(P.phone_core(m.group(0)))
        if kind == "contact_value" and P.EMAIL.search(sval):
            attrs["emails"].add(sval.lower())
        d = P.norm_digits(sval)
        if kind == "phone" and len(d) >= 10 and not P.PHONE.search(sval):
            attrs["phones"].add(d[-10:])
    elif kind == "email":
        if "@" in sval:
            attrs["emails"].add(sval.lower())
    elif kind == "aadhaar":
        d = P.norm_digits(sval)
        if len(d) == 12:
            attrs["aadhaar"].add(d)
    elif kind == "abha":
        d = P.norm_digits(sval)
        if len(d) == 14:
            attrs["abha"].add(d)
    elif kind == "abha_addr":
        attrs["emails"].add(sval.lower())
    elif kind == "mrn":
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 /.-]{2,}", sval) and any(c.isdigit() for c in sval):
            attrs["ids"].add(P.id_norm(sval))
            attrs["cores"].add(P.id_core(sval))
    elif kind == "pan":
        attrs["pans"].add(sval.upper())
    elif kind == "insurance":
        attrs["insurance"].add(P.id_norm(sval))
    elif kind == "village":
        attrs["villages"].append(sval)
    elif kind == "tehsil":
        attrs["tehsils"].append(sval)
    elif kind == "district":
        attrs["districts"].append(sval)
    elif kind == "pin":
        d = P.norm_digits(sval)
        if len(d) == 6:
            attrs["pins"].add(d)
    elif kind == "address":
        extract_text(attrs, sval, date_order, address=True)


def parse_any_date(s: str, order: str = "dmy"):
    s = P.norm_digits_keep(s)
    m = P.DATE_ISO.search(s)
    if m:
        return P.make_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = P.DATE_NUM.search(s)
    if m:
        return P.parse_numeric(m.group(1), m.group(3), m.group(4), order)
    return None


def extract_text(attrs: dict, text: str, date_order: str = "dmy", address: bool = False):
    if not address:
        for m in NAME_LABEL_RE.finditer(text):
            nm = clean_name(m.group("n"))
            if nm:
                attrs["names"].append(nm)
        for match in subject_names(text):
            attrs["names"].append(match.group("name"))
        for pattern in FULL_DATE_PATTERNS:
            for match in pattern.finditer(text):
                d = parse_any_date(match.group(), date_order)
                if d:
                    attrs["event_dates"].add(d.isoformat())
        for m in DOB_RE.finditer(text):
            d = parse_any_date(m.group("d"), date_order)
            if d:
                attrs["dob"].add(d.isoformat())
        for rx in P.AGE_FORMS:
            for m in rx.finditer(text):
                g = [x for x in m.groups() if x and re.fullmatch(r"[0-9०-९]{1,3}", x.strip())]
                if g:
                    a = P.to_int(g[0])
                    if 0 < a < 125:
                        attrs["ages"].append(a)
        for m in re.finditer(r"(?:\d\s*(?:Yrs?|Y|Years?)?\s*/\s*|Sex\s*:\s*|/\s*)(?P<g>M|F|Male|Female|पुरुष|महिला)\b|(?P<h>पुरुष|महिला)", text):
            g = norm_gender(m.group("g") or m.group("h") or "")
            if g:
                attrs["gender"].add(g)
        for m in ID_LABEL_RE.finditer(text):
            if re.search(r"\d{3,}", m.group("id")):
                attrs["ids"].add(P.id_norm(m.group("id")))
                attrs["cores"].add(P.id_core(m.group("id")))
        for m in P.GENERIC_ID.finditer(text):
            tok = m.group(0)
            if len(P.id_core(tok)) >= 5 and re.match(r"[A-Za-z]{2,}", tok):
                attrs["cand_ids"].add(P.id_norm(tok))
                attrs["cand_cores"][P.id_norm(tok)] = P.id_core(tok)
        for m in P.EMAIL.finditer(text):
            attrs["emails"].add(m.group(0).lower())
        for m in P.ABHA_NUM.finditer(text):
            attrs["abha"].add(P.norm_digits(m.group(0)))
        for m in P.AADHAAR.finditer(text):
            d = P.norm_digits(m.group(0))
            if aadhaar_candidate(text, m):
                attrs["aadhaar"].add(d)
        for m in P.PAN.finditer(text):
            attrs["pans"].add(m.group(0))
    for m in KIN_RE.finditer(text):
        rel = m.group("rel").lower().replace(" ", "")
        nm = clean_name(m.group("n"))
        if not nm:
            continue
        if rel.startswith("c/o") or rel == "c/o":
            if nm.split()[0].lower() in L.MEDICAL_WORDS:
                continue
        attrs["relatives"].append(nm)
    for m in P.PHONE.finditer(text):
        if not P.phone_guard(text, m.start(), m.end()):
            attrs["phones"].add(P.phone_core(m.group(0)))
    for m in VILLAGE_RE.finditer(text):
        attrs["villages"].append(m.group("v"))
    for m in TEHSIL_RE.finditer(text):
        attrs["tehsils"].append(m.group("v"))
    for m in DISTRICT_RE.finditer(text):
        attrs["districts"].append(m.group("v"))
    for m in re.finditer(r"(?<!\d)([1-9]\d{5})(?!\d)", P.norm_digits_keep(text)):
        if address or re.search(r"(?i)(pin|pincode|-\s*$|distt|district|जिला)", text[max(0, m.start() - 30):m.start()]):
            attrs["pins"].add(m.group(1))


# ---------------------------------------------------------------- name helpers for linkage
@lru_cache(maxsize=200000)
def name_tokens(name: str) -> tuple:
    toks = []
    for t in split_name(name):
        tl = t.lower().strip(".'’")
        if tl in L.PRE_HONORIFICS or tl in L.POST_HONORIFICS:
            continue
        k = name_key(t)
        if k and len(k) >= 2:
            toks.append(k)
    return tuple(toks)


@lru_cache(maxsize=500000)
def name_sim(a: str, b: str) -> tuple[float, float]:
    """(given-name similarity, full-name token-set similarity) on Indic phonetic keys."""
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return 0.0, 0.0
    # Honorific filtering must not downgrade an otherwise complete matching name
    # merely because one component (e.g. Mohammad or Kumar) is common.
    if len(ta) >= 2 and sorted(ta) == sorted(tb) and any(t not in _GENERIC_KEYS for t in ta):
        return 1.0, 1.0
    ga, gb = [t for t in ta if t not in _GENERIC_KEYS] or ta, [t for t in tb if t not in _GENERIC_KEYS] or tb
    given = max(jaro_winkler(ga[0], x) for x in gb[:2])
    # token-set: every token of the shorter name must match some token of the longer
    short, long_ = (ga, gb) if len(ga) <= len(gb) else (gb, ga)
    scores = [max(jaro_winkler(s, l) for l in long_) for s in short]
    full = min(scores) if len(short) >= 2 else (scores[0] * 0.85 if scores else 0.0)
    return given, full


_GENERIC_KEYS = {name_key(x) for x in L.GENERIC_NAME_PARTS} | {"mhmd"}
