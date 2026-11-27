#!/usr/bin/env python3
"""Unseen-vocabulary generalisation harness (dev-only, offline, deterministic).

`tools/mutate_dataset.py` rehearses unseen *formats* while keeping the practice PII.
This rehearses unseen *vocabulary*: every name, place and identifier is built here from
syllable and digit patterns, so none of it appears in dev/truth.json. A pipeline that
learned the practice names will leak; one that works from context and script-aware
rules will not.

It writes the dataset and an answer key, then scores a release against that key:

    python tools/synth_dataset.py --out <dir>                 # generate only
    python tools/synth_dataset.py --out <dir> --score <release_dir>

Nothing here is imported by the runtime: it is a test fixture, not part of main.py.
"""
from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import random
import re
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------- vocabulary
# Syllables, not names. Combinations are generated, so the surfaces below cannot
# coincide with the practice data except by accident of the alphabet.
_ONSET = ["k", "kh", "g", "ch", "j", "t", "th", "d", "dh", "n", "p", "ph", "b", "bh",
          "m", "y", "r", "l", "v", "sh", "s", "h", "tr", "pr", "br", "shr"]
_NUCLEUS = ["a", "aa", "i", "ee", "u", "oo", "e", "ai", "o", "au"]
_CODA = ["", "", "n", "m", "r", "l", "sh", "nd", "nt", "k", "t"]
_DEVA_ONSET = {"k": "क", "kh": "ख", "g": "ग", "ch": "च", "j": "ज", "t": "ट", "th": "थ",
               "d": "द", "dh": "ध", "n": "न", "p": "प", "ph": "फ", "b": "ब", "bh": "भ",
               "m": "म", "y": "य", "r": "र", "l": "ल", "v": "व", "sh": "श", "s": "स",
               "h": "ह", "tr": "त्र", "pr": "प्र", "br": "ब्र", "shr": "श्र"}
_DEVA_VOWEL = {"a": "", "aa": "ा", "i": "ि", "ee": "ी", "u": "ु", "oo": "ू",
               "e": "े", "ai": "ै", "o": "ो", "au": "ौ"}
_DEVA_CODA = {"": "", "n": "न", "m": "म", "r": "र", "l": "ल", "sh": "श",
              "nd": "ंद", "nt": "ंत", "k": "क", "t": "त"}
HONORIFICS = ["ji", "sahab", "devi", "kumar", "bhai", "didi"]
# Spelling variants of one name, the classic cross-script trap.
MOHD_VARIANTS = ["Mohammad", "Mohammed", "Mohd.", "Md.", "Muhammad"]


def _syllable(rng):
    onset = rng.choice(_ONSET)
    nucleus = rng.choice(_NUCLEUS)
    coda = rng.choice(_CODA)
    latin = onset + nucleus + coda
    deva = _DEVA_ONSET[onset] + _DEVA_VOWEL[nucleus] + _DEVA_CODA[coda]
    return latin, deva


def coined_word(rng, syllables=2):
    latin, deva = "", ""
    for _ in range(syllables):
        a, b = _syllable(rng)
        latin += a
        deva += b
    return latin.capitalize(), deva


# ---------------------------------------------------------------- identifiers
def verhoeff(digits: str) -> str:
    d = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
         [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
         [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
         [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
         [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
    p = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
         [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
         [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
         [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]
    inv = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = d[c][p[(i + 1) % 8][int(ch)]]
    return str(inv[c])


ASCII_TO_DEVA_DIGIT = str.maketrans("0123456789", "०१२३४५६७८९")


def make_ids(rng):
    """One of every Indian identifier shape, in several separator styles."""
    aadhaar_core = "".join(str(rng.randint(0, 9)) for _ in range(11))
    aadhaar = aadhaar_core + verhoeff(aadhaar_core)
    abha = "".join(str(rng.randint(0, 9)) for _ in range(14))
    phone_core = rng.choice("6789") + "".join(str(rng.randint(0, 9)) for _ in range(9))
    pan = ("".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(5))
           + "".join(str(rng.randint(0, 9)) for _ in range(4))
           + rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
    return {
        "aadhaar_digits": aadhaar,
        "aadhaar_text": rng.choice([
            f"{aadhaar[:4]} {aadhaar[4:8]} {aadhaar[8:]}",
            f"{aadhaar[:4]}-{aadhaar[4:8]}-{aadhaar[8:]}",
            aadhaar]),
        "abha_digits": abha,
        "abha_text": f"{abha[:2]}-{abha[2:6]}-{abha[6:10]}-{abha[10:]}",
        "phone_digits": phone_core,
        "phone_text": rng.choice([
            f"+91 {phone_core[:5]} {phone_core[5:]}", f"0{phone_core}",
            f"+91-{phone_core}", f"({phone_core[:4]}) {phone_core[4:]}",
            phone_core.translate(ASCII_TO_DEVA_DIGIT)]),
        "pan": pan,
        "uhid": f"{rng.choice(['REG', 'ENR', 'CASE', 'IPNO'])}-{rng.randint(10000, 99999)}",
        "insurance": f"{rng.choice(['POL', 'SCH', 'CARD'])}/{rng.randint(1000, 9999)}/{rng.randint(10, 99)}",
    }


# ---------------------------------------------------------------- clinical content
# These strings must survive untouched. They are the Challenge-2 trap families:
# doses that look like phone numbers, 1-0-1 frequencies, eponyms that look like
# people, complaints after C/O, and doctor names that must be kept.
DRUGS = ["Ramipril", "Dolo", "Metformin", "Amlodipine", "Azithromycin", "Pantoprazole"]
LABS = [("Hb", "11.4 g/dL"), ("Creatinine", "1.2 mg/dL"), ("HbA1c", "7.8 %"),
        ("Platelets", "1.45 lakh/uL"), ("TSH", "3.21 mIU/L")]
VITALS = ["BP 138/86 mmHg", "Pulse 92/min", "SpO2 97%", "Temp 101.2 F"]
DIAGNOSES = [("Dengue fever", "A90"), ("Type 2 diabetes mellitus", "E11.9"),
             ("Parkinson's disease", "G20"), ("Acute gastroenteritis", "A09"),
             ("Essential hypertension", "I10"), ("Bronchial asthma", "J45.9")]
PROCEDURES = ["USG abdomen", "ECG", "Chest X-ray PA view", "Dialysis session"]


def clinical_block(rng):
    """Returns (text, [strings that must still be there afterwards])."""
    drug = rng.choice(DRUGS)
    dose = f"{drug} {rng.choice([5, 10, 40, 500, 650])} mg {rng.choice(['OD', 'BD', 'TDS'])}"
    freq = rng.choice(["1-0-1", "0-0-1", "1-1-1"])
    lab, value = rng.choice(LABS)
    vital = rng.choice(VITALS)
    dx, icd = rng.choice(DIAGNOSES)
    proc = rng.choice(PROCEDURES)
    days = rng.randint(3, 12)
    text = (f"C/O fever and cough since 3 days. K/C/O {dx}.\n"
            f"O/E {vital}. {lab}: {value}.\n"
            f"Rx: {dose} x {days} days ({freq}).\n"
            f"Procedure: {proc}. ICD: {icd}.\n")
    keep = [dose, freq, f"{lab}: {value}", vital, dx, icd, proc, "C/O fever"]
    return text, keep, days


# ---------------------------------------------------------------- people
def make_person(rng, index, places):
    first_l, first_d = coined_word(rng, 2)
    last_l, last_d = coined_word(rng, 2)
    rel_l, rel_d = coined_word(rng, 2)
    doctor_l, _ = coined_word(rng, 2)
    style = index % 5
    if style == 0:                       # plain
        name_latin = f"{first_l} {last_l}"
    elif style == 1:                     # surname first
        name_latin = f"{last_l} {first_l}"
    elif style == 2:                     # initial
        name_latin = f"{first_l[0]}. {last_l}"
    elif style == 3:                     # honorific attached
        name_latin = f"{first_l} {rng.choice(HONORIFICS).capitalize()}"
    else:                                # spelling-variant trap
        name_latin = f"{rng.choice(MOHD_VARIANTS)} {last_l}"
    villages, tehsils, districts = places
    village, village_d = villages[index % len(villages)]
    tehsil, _ = tehsils[index % len(tehsils)]
    district, _ = districts[index % len(districts)]
    ids = make_ids(rng)
    return {
        "name_latin": name_latin,
        "name_deva": f"{first_d} {last_d}",
        "first": first_l, "last": last_l,
        "relative_latin": f"{rel_l} {last_l}", "relative_deva": f"{rel_d} {last_d}",
        "doctor": f"Dr. {doctor_l}",
        "age": rng.randint(18, 88),
        "sex": rng.choice(["M", "F"]),
        "village": village, "village_deva": village_d,
        "tehsil": tehsil, "district": district,
        "pin": f"{rng.randint(201, 285)}{rng.randint(100, 999)}",
        "house": f"H.No {rng.randint(1, 240)}/{rng.choice('ABC')}",
        "locality": f"{coined_word(rng, 2)[0]} Mohalla",
        "landmark": f"near {coined_word(rng, 2)[0]} Mandir",
        "email": f"{first_l.lower()}.{last_l.lower()}@example.invalid",
        **ids,
    }


def generate(out_dir: Path, seed: int, patients: int):
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Disjoint pools: a village name must never also be some other patient's district,
    # or a correctly preserved district would read as a leaked village.
    places = ([coined_word(rng, 3) for _ in range(12)],      # villages
              [coined_word(rng, 2) for _ in range(5)],       # tehsils
              [coined_word(rng, 2) for _ in range(4)])       # districts
    people = [make_person(rng, i, places) for i in range(patients)]
    # Every surface that must NOT survive, and everything that must.
    pii, keep = [], []

    def add_pii(person_index, kind, surface):
        if surface:
            pii.append({"patient": person_index, "kind": kind, "surface": str(surface)})

    for i, p in enumerate(people):
        for kind in ("name_latin", "name_deva", "relative_latin", "relative_deva",
                     "village", "village_deva", "house", "locality", "landmark",
                     "email", "pan", "uhid", "insurance", "pin"):
            add_pii(i, kind, p[kind])
        add_pii(i, "aadhaar", p["aadhaar_digits"])
        add_pii(i, "abha", p["abha_digits"])
        add_pii(i, "phone", p["phone_digits"])
        # The bare surname of a person with an honorific or initial still identifies.
        add_pii(i, "name_token", p["last"])

    # 1. CSV register ------------------------------------------------------
    rows = [["Beneficiary Name", "Guardian", "Age/Sex", "Mobile", "Aadhaar No",
             "ABHA", "PAN", "Reg No", "Village", "Tehsil", "District", "PIN",
             "Diagnosis", "ICD", "Attending"]]
    for p in people:
        dx, icd = rng.choice(DIAGNOSES)
        keep += [dx, icd, p["doctor"], p["district"]]
        rows.append([p["name_latin"], f"S/o {p['relative_latin']}", f"{p['age']}/{p['sex']}",
                     p["phone_text"], p["aadhaar_text"], p["abha_text"], p["pan"],
                     p["uhid"], p["village"], p["tehsil"], p["district"], p["pin"],
                     dx, icd, p["doctor"]])
    buf = io.StringIO(newline="")
    csv.writer(buf, lineterminator="\n").writerows(rows)
    (out_dir / "register.csv").write_text(buf.getvalue(), encoding="utf-8")

    # 2. Devanagari / Hinglish notes --------------------------------------
    notes = out_dir / "notes"
    notes.mkdir(exist_ok=True)
    for i, p in enumerate(people):
        body, keeps, days = clinical_block(rng)
        keep += keeps + [p["doctor"]]
        admit, discharge = f"0{rng.randint(1, 9)}/0{rng.randint(1, 9)}/2025", None
        text = (f"रोगी: {p['name_deva']}\n"
                f"पुत्र: {p['relative_deva']}\n"
                f"आयु: {str(p['age']).translate(ASCII_TO_DEVA_DIGIT)} वर्ष\n"
                f"गाँव: {p['village_deva']}, तहसील {p['tehsil']}, जिला {p['district']}\n"
                f"मोबाइल: {p['phone_text']}\n"
                f"{p['house']}, {p['locality']}, {p['landmark']}\n"
                f"Admission: {admit}  Stay: {days} days\n"
                f"{body}"
                f"Reviewed by {p['doctor']}. Patient attendant W/o {p['relative_latin']}.\n")
        (notes / f"note_{i:03}.txt").write_text(text, encoding="utf-8")
        keep.append(f"Stay: {days} days")

    # 3. JSON with PII in keys, values and a base64 attachment -------------
    payload = []
    for i, p in enumerate(people[: max(1, patients // 2)]):
        hidden = base64.b64encode(
            f"contact {p['name_latin']} on {p['phone_text']}".encode()).decode()
        payload.append({
            "enrolment": p["uhid"],
            "demographics": {"full_nm": p["name_latin"], "care_of": f"D/o {p['relative_latin']}",
                             "yrs": p["age"], "sex": p["sex"]},
            "contact": {"cell": p["phone_text"], "mail": p["email"]},
            "residence": {"gram": p["village"], "tehsil": p["tehsil"],
                          "zila": p["district"], "pincode": p["pin"]},
            "attachment": {"contentType": "text/plain", "data": hidden},
        })
    (out_dir / "enrolment.json").write_text(
        json.dumps({"records": payload}, ensure_ascii=False, indent=2), encoding="utf-8")

    # 4. FHIR bundle -------------------------------------------------------
    entries = []
    for i, p in enumerate(people[: max(1, patients // 3)]):
        entries.append({"resource": {
            "resourceType": "Patient",
            "id": f"pat-{i}",
            "identifier": [{"system": "urn:uhid", "value": p["uhid"]},
                           {"system": "urn:abha", "value": p["abha_text"]}],
            "name": [{"family": p["last"], "given": [p["first"]]}],
            "telecom": [{"system": "phone", "value": p["phone_text"]},
                        {"system": "email", "value": p["email"]}],
            "address": [{"line": [p["house"], p["locality"]], "city": p["village"],
                         "district": p["district"], "postalCode": p["pin"]}],
            "text": {"status": "generated",
                     "div": f"<div>{p['name_latin']}, {p['age']}/{p['sex']}, {p['village']}</div>"},
        }})
    (out_dir / "bundle.fhir.json").write_text(
        json.dumps({"resourceType": "Bundle", "type": "collection", "entry": entries},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    # 5. A clean reference file that must come through untouched -----------
    clean = "Dengue management protocol\nFluid: 10 ml/kg bolus.\nParacetamol 650 mg SOS.\n"
    (out_dir / "protocol.txt").write_text(clean, encoding="utf-8")
    keep += ["10 ml/kg", "Paracetamol 650 mg SOS", "Dengue management protocol"]

    # 6. Awkward encodings and a file that cannot be parsed ----------------
    legacy = f"Name,Phone\n{people[0]['name_latin']},{people[0]['phone_text']}\n"
    (out_dir / "legacy_cp1252.csv").write_bytes(legacy.encode("cp1252", errors="replace"))
    (out_dir / "legacy_utf16.csv").write_bytes(legacy.encode("utf-16"))
    (out_dir / "broken.json").write_bytes(b'{"records": [{"full_nm": "unterminated')

    # 7. PII in a file name -------------------------------------------------
    (out_dir / f"discharge_{people[0]['last']}_{people[0]['uhid']}.txt").write_text(
        f"Discharge summary for {people[0]['name_latin']}.\n{clinical_block(rng)[0]}",
        encoding="utf-8")

    key = {"pii": pii, "keep": sorted(set(keep)), "patients": patients, "seed": seed}
    return key


# ---------------------------------------------------------------- scoring
_B64 = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(str.maketrans("०१२३४५६७८९", "0123456789"))
    return " ".join(text.casefold().split())


def _all_text(root: Path) -> str:
    parts = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        parts.append(path.as_posix())
        raw = path.read_bytes()[: 20 * 1024 * 1024].decode("utf-8", errors="replace")
        parts.append(raw)
        for match in _B64.finditer(raw):            # attachments hide PII in base64
            token = match.group(0)
            try:
                parts.append(base64.b64decode(token + "=" * (-len(token) % 4)).decode(
                    "utf-8", errors="ignore"))
            except (ValueError, TypeError):
                pass
    return _norm("\n".join(parts))


def score(release: Path, key: dict):
    haystack = _all_text(release)
    leaked = [item for item in key["pii"]
              if len(_norm(item["surface"])) >= 3 and _norm(item["surface"]) in haystack]
    by_kind: dict[str, list[int]] = {}
    for item in key["pii"]:
        hit = item in leaked
        bucket = by_kind.setdefault(item["kind"], [0, 0])
        bucket[0] += hit
        bucket[1] += 1
    kept = [text for text in key["keep"] if _norm(text) in haystack]
    return {
        "pii_total": len(key["pii"]),
        "pii_leaked": len(leaked),
        "leak_rate": len(leaked) / max(1, len(key["pii"])),
        "by_kind": {k: {"leaked": v[0], "total": v[1]} for k, v in sorted(by_kind.items())},
        "clinical_total": len(key["keep"]),
        "clinical_kept": len(kept),
        "clinical_rate": len(kept) / max(1, len(key["keep"])),
        "examples": [item["kind"] for item in leaked[:10]],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="directory to write the dataset into")
    ap.add_argument("--seed", type=int, default=20261127)
    ap.add_argument("--patients", type=int, default=40)
    ap.add_argument("--score", help="a release directory to score against the answer key")
    args = ap.parse_args()

    out = Path(args.out)
    key_path = out.parent / f"{out.name}-key.json"
    if args.score:
        key = json.loads(key_path.read_text(encoding="utf-8"))
        result = score(Path(args.score), key)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["pii_leaked"] == 0 else 1
    key = generate(out, args.seed, args.patients)
    key_path.write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.patients} synthetic patients to {out}")
    print(f"answer key: {key_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
