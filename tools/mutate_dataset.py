#!/usr/bin/env python3
"""Unseen-format stress generator (dev-only).

Rewrites a copy of the practice input with variations that never appear in it - renamed /
misspelled column headers and JSON keys, new label phrasings, new ID shapes, and alternative
date formats - WITHOUT changing the PII surfaces (names, numbers), so the practice truth.json
still scores it.  A context-driven system should barely lose recall here; a system tuned to the
exact practice headers will collapse.  This is how we rehearse the hidden unseen-format dataset.

Usage: python tools/mutate_dataset.py <in_dir> <out_dir>
It rewrites the *inputs*; score the result against the ORIGINAL truth.json with check_dev.py by
pointing --output at your run of the mutated inputs (leaks are matched on PII surfaces, which are
unchanged).
"""
from __future__ import annotations

import csv
import io
import json
import re
import shutil
import sys
from pathlib import Path

# header synonyms NOT present in the practice data (the classifier must infer from content/keywords)
HEADER_MAP = {
    "Patient Name": "Beneficiary Full Name", "patient_name": "beneficiary_full_name",
    "Patient's Name": "Beneficiary Full Name", "name": "full_nm",
    "UHID": "EnrolmentRef", "uhid": "enrolment_ref", "Reg No": "EnrolmentRef", "patient_ref": "enrol_ref",
    "Mobile": "Cell Contact", "Mobile No": "Cell Contact", "mobile": "cell_contact", "phone": "cell_contact",
    "Aadhaar No": "UID Token", "aadhar_no": "uid_token", "Aadhaar": "UID Token",
    "ABHA No": "HealthAcct", "abha": "health_acct",
    "DOB": "Birth Dt", "dob": "birth_dt", "DOB (MM/DD/YYYY)": "Birth Dt (ISO)",
    "Age": "Yrs", "age": "yrs", "Gender": "Sx", "gender": "sx", "Sex": "Sx",
    "Address": "Residence Line", "address": "residence_line",
    "Village/Mohalla": "Habitation", "village": "habitation", "City": "Habitation",
    "Tehsil": "SubDiv", "tehsil": "sub_div", "District": "Zone", "district": "zone",
    "PIN": "PostIdx", "pin": "post_idx", "Zip": "PostIdx",
    "Relative Name": "Kin Full Name", "Relation": "Kin Rel", "Guardian": "Kin Full Name",
    "payer_pan": "fiscal_code", "pmjay_id": "scheme_ref", "policy_no": "cover_ref",
    "ref_doctor": "ordering_clinician", "doctor": "ordering_clinician",
}
KEY_MAP = {
    "name": "full_nm", "first": "fnm", "last": "lnm", "local": "nm_vernacular",
    "uhid": "enrolment_ref", "patient_ref": "enrol_ref", "mobile": "cell_contact",
    "aadhar_no": "uid_token", "abha": "health_acct", "dob": "birth_dt", "age": "yrs",
    "age_sex": "yrs_sx", "gender": "sx", "pin": "post_idx", "village": "habitation",
    "district": "zone", "tehsil": "sub_div", "guardian": "kin_block", "relation": "kin_rel",
}


def mut_dates(text: str) -> str:
    # dd/mm/yyyy or dd-mm-yyyy -> dd.Mon.yyyy occasionally (adds an unseen date format)
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    def repl(m):
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{d:02d}-{months[mo - 1]}-{y}"
        return m.group(0)

    return re.sub(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", repl, text)


def mut_csv(text, delim):
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delim))
    if not rows:
        return text
    rows[0] = [HEADER_MAP.get(h, HEADER_MAP.get(h.strip(), h)) for h in rows[0]]
    buf = io.StringIO(newline="")
    w = csv.writer(buf, delimiter=delim, lineterminator="\n")
    w.writerows(rows)
    return buf.getvalue()


def mut_json(obj, depth=0):
    if depth > 60:
        return obj
    if isinstance(obj, dict):
        return {KEY_MAP.get(k, k): mut_json(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [mut_json(x, depth + 1) for x in obj]
    return obj


def main():
    if len(sys.argv) != 3:
        print("usage: mutate_dataset.py <in_dir> <out_dir>")
        return 1
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    if dst.exists():
        shutil.rmtree(dst)
    for p in src.rglob("*"):
        rel = p.relative_to(src)
        o = dst / rel
        if p.is_dir():
            continue
        o.parent.mkdir(parents=True, exist_ok=True)
        raw = p.read_bytes()
        ext = p.suffix.lower()
        try:
            if ext in (".csv", ".tsv") and b"\x00" not in raw[:4]:
                txt = raw.decode("utf-8-sig", errors="strict")
                delim = "\t" if ext == ".tsv" else ","
                o.write_text(mut_dates(mut_csv(txt, delim)), encoding="utf-8")
                continue
            if ext == ".json":
                obj = json.loads(raw.decode("utf-8-sig"))
                txt = json.dumps(mut_json(obj), ensure_ascii=False, indent=2)
                o.write_text(txt, encoding="utf-8")
                continue
            if ext == ".txt":
                enc = "utf-8"
                try:
                    txt = raw.decode("utf-8")
                except UnicodeDecodeError:
                    o.write_bytes(raw)
                    continue
                txt = txt.replace("Patient Name:", "Beneficiary:").replace("Name:", "Beneficiary:") \
                         .replace("UHID:", "Enrolment Ref:").replace("Mobile:", "Cell:") \
                         .replace("Consultant:", "Ordering Clinician:")
                o.write_text(mut_dates(txt), encoding="utf-8")
                continue
        except (UnicodeDecodeError, ValueError, csv.Error):
            pass
        o.write_bytes(raw)
    print(f"mutated dataset written to {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
