"""Identifier, date and age patterns with clinical guards (doses, frequencies, vitals, ranges)."""
from __future__ import annotations

import datetime as dt
import re

D = r"[0-9०-९]"          # ASCII or Devanagari digit
SEP = r"[\s\-./]?"

_VERHOEFF_D = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
               [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
               [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
               [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_VERHOEFF_P = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
               [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
               [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]


def verhoeff_ok(num: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(ch)]]
    return c == 0


# ---------------------------------------------------------------- strong identifiers
EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
ABHA_ADDR = re.compile(r"\b[A-Za-z0-9._\-]{3,}@(?:abdm|sbx|ndhm|abha)\b", re.I)
ABHA_NUM = re.compile(rf"(?<![\d०-९]){D}{{2}}[\s\-]{D}{{4}}[\s\-]{D}{{4}}[\s\-]{D}{{4}}(?![\d०-९])")
PAN = re.compile(r"\b[A-Z]{3}[ABCFGHLJPTK][A-Z]\d{4}[A-Z]\b")
AADHAAR = re.compile(rf"(?<![\d०-९\-/]){D}{{4}}[\s\-]?{D}{{4}}[\s\-]?{D}{{4}}(?![\d०-९\-/])")
AADHAAR_MASKED = re.compile(r"(?i)\b[X\*]{4}[\s\-]?[X\*]{4}[\s\-]?\d{4}\b")
PHONE = re.compile(
    rf"(?<![\w०-९/.])(?:(?:\+|00)?91[\s\-]?|0)?[6-9६-९]{D}{{4}}[\s\-]?{D}{{5}}(?![\w०-९])"
    rf"|(?<![\w०-९/.])(?:(?:\+|00)?91[\s\-]?|0)?[6-9६-९]{D}{{2}}[\s\-]?{D}{{3}}[\s\-]?{D}{{4}}(?![\w०-९])"
    rf"|(?<![\w०-९/.])0{D}{{5}}[\s\-]{D}{{5}}(?![\w०-९])"
)
PHONE_MASKED = re.compile(r"(?i)\b[6-9]\d[X\*]{6}\d{2}\b|\b[6-9]\d{1,3}[X\*]{4,6}\d{2,4}\b")
INSURANCE = re.compile(r"\b(?:PMJAY|AB-?PMJAY|CGHS|ESIC?|ECHS|RSBY|POL|POLICY|INS|CLM|MEM|TPA)[\-/]?[A-Z]{0,3}[\-/]?\d{2,}(?:[\-/]\d{2,})*\b", re.I)
# hospital-style record numbers: letters + digit groups (SNJ/26/064127, JJH-0076928, ADM000161, IP/26/00130)
GENERIC_ID = re.compile(r"(?<![\w/])[A-Za-z]{1,8}(?:[\-/][A-Za-z]{1,8}){0,3}[\-/]?\d{2,}(?:[\-/]\d{2,}){0,4}(?![\w])")
DIGIT_RUN = re.compile(r"\d+")

# ---------------------------------------------------------------- clinical guards
UNIT_AFTER = re.compile(r"^\s*(?:mg|mcg|µg|ug|ml|mL|g|gm|kg|iu|IU|units?|%|mmhg|mmHg|bpm|/min|mmol|mEq|"
                        r"g/dl|g/dL|mg/dl|mg/dL|cells|lakh|/ul|/uL|/cumm|x\s*\d|tabs?|caps?|days?|wks?|weeks?|"
                        r"months?|yrs?|years?|hrs?|°)", re.I)
FREQ = re.compile(r"\b[0-4½](?:\s*-\s*[0-4½]){2,3}\b")
BP = re.compile(r"\b\d{2,3}/\d{2,3}\b")
ICD = re.compile(r"\b[A-TV-Z]\d{2}(?:\.\d{1,4})?\b")


def phone_guard(text: str, start: int, end: int) -> bool:
    """True if the match is clinically shaped (dose/unit follows) rather than a phone."""
    return bool(UNIT_AFTER.match(text[end:end + 8]))


def norm_digits(s: str) -> str:
    return re.sub(r"\D", "", s.translate(str.maketrans("०१२३४५६७८९", "0123456789")))


def phone_core(s: str) -> str:
    d = norm_digits(s)
    return d[-10:] if len(d) >= 10 else d


def id_norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def id_core(s: str) -> str:
    runs = DIGIT_RUN.findall(norm_digits_keep(s))
    return runs[-1] if runs else ""


def norm_digits_keep(s: str) -> str:
    return s.translate(str.maketrans("०१२३४५६७८९", "0123456789"))


# ---------------------------------------------------------------- dates
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep",
                                            "oct", "nov", "dec"])}
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
               "October", "November", "December"]
HINDI_MONTHS = {"जनवरी": 1, "फरवरी": 2, "फ़रवरी": 2, "मार्च": 3, "अप्रैल": 4, "मई": 5, "जून": 6, "जुलाई": 7,
                "अगस्त": 8, "सितंबर": 9, "सितम्बर": 9, "अक्टूबर": 10, "नवंबर": 11, "नवम्बर": 11, "दिसंबर": 12,
                "दिसम्बर": 12}

DATE_ISO = re.compile(r"(?<![\d])(\d{4})-(\d{2})-(\d{2})(?![\d])")
DATE_NUM = re.compile(rf"(?<![\d०-९/.\-])({D}{{1,2}})([/.\-])({D}{{1,2}})\2({D}{{4}}|{D}{{2}})(?![\d०-९/.\-]|:\d)")
_MON = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
DATE_DMONY = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[\s\-]+({_MON})\.?(?:[\s,\-]+(\d{{4}}))?\b", re.I)
DATE_MONDY = re.compile(rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I)
DATE_HINDI = re.compile(rf"({D}{{1,2}})\s+(" + "|".join(HINDI_MONTHS) + rf")(?:\s+({D}{{4}}))?")


def to_int(s: str) -> int:
    return int(norm_digits_keep(s))


def make_date(y: int, m: int, d: int):
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


def parse_numeric(a: str, b: str, y: str, order: str):
    ai, bi, yi = to_int(a), to_int(b), to_int(y)
    if len(norm_digits_keep(y)) == 2:
        yi += 2000 if yi <= 40 else 1900
    if order == "mdy":
        m, d = ai, bi
        if m > 12 and d <= 12:
            m, d = d, m
    else:
        d, m = ai, bi
        if m > 12 and d <= 12:
            m, d = d, m
    return make_date(yi, m, d)


# ---------------------------------------------------------------- ages
AGE_FORMS = [
    # 52 Yrs/F, 48 Y / F, 35/F, 52 yrs, 65 वर्ष
    re.compile(rf"(?<![\d\-/.x×])({D}{{1,3}})(\s*(?:Yrs?|Years?|Y|yr|yo|वर्ष|साल)\.?\s*/\s*(?:[MFmf]|Male|Female|पुरुष|महिला)\b)"),
    re.compile(rf"(?<![\d\-/.x×])({D}{{1,3}})(\s*/\s*(?:[MFmfO]|Male|Female)\b)(?!\s*\d)"),
    re.compile(rf"((?<![A-Za-z])(?:Age|AGE|Aayu|Umar|आयु|उम्र)\s*[:\-]?\s*)({D}{{1,3}})(?!\s*[-–]\s*\d)(?![\d.])"),
    re.compile(rf"(?<![\d\-/.x×])({D}{{1,3}})(\s*(?:वर्ष|साल)(?:\s*/|\s|$))"),
]
