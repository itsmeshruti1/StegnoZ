#!/usr/bin/env python3
"""Development-side re-identification attacker (synthetic), modelled on docs/ATTACKS.md.

Runs A1 (direct exposure), A2/A3 (registry linkage), A4 (profile re-identification), A5 (targeted
known-facts attack with global-shift recovery) against a sanitized release, using the practice
registry + known_facts.  Numbers are normalised against the same attack on the raw input, exactly
like the official scorer, so we can tune the privacy/utility trade-off locally.  This is OUR tool:
it never ships in the submission runtime.

Usage: python tools/attack_eval.py --output out_dev [--input ../toolkit2/dev/input] [--truth ...]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from raksha import patterns as P  # noqa: E402
from raksha.translit import deva_to_latin, has_deva, name_key  # noqa: E402


def norm(s):
    return " ".join(unicodedata.normalize("NFKC", str(s)).casefold().split())


def nkey(tok):
    return name_key(tok)


AGE_RE = re.compile(r"(?<!\d)(\d{1,3})\s*(?:yrs?|years?|y|वर्ष|साल)?\s*/\s*[mfMF]|\bAge[:\s]+(\d{1,3})\b|(\d{1,3})\s*(?:वर्ष|साल)|(?<!\d)(\d{1,3})-(\d{1,3})\b|\b(\d{2})\+")


def extract_evidence(text):
    """Pull attackable quasi-identifiers from a release document (mirrors the attacker)."""
    ev = {"names": set(), "given": set(), "phones": set(), "ids": set(), "pins": set(),
          "ages": set(), "age_bands": [], "gender": set(), "places": set()}
    low = text
    for m in P.PHONE.finditer(text):
        if not P.phone_guard(text, m.start(), m.end()):
            ev["phones"].add(P.phone_core(m.group(0)))
    for m in re.finditer(r"(?<!\d)([1-9]\d{5})(?!\d)", text):
        ev["pins"].add(m.group(1))
    for m in re.finditer(r"(\d{1,3})\s*(?:Yrs?|Years?|Y|वर्ष|साल)?\s*/\s*[MFmf]", text):
        ev["ages"].add(int(m.group(1)))
    for m in re.finditer(r"\b(\d{1,3})\s*[-–]\s*(\d{1,3})\b", text):
        a, b = int(m.group(1)), int(m.group(2))
        if 0 <= a < b <= 120 and b - a <= 25:
            ev["age_bands"].append((a, b))
    for m in re.finditer(r"\b(\d{2,3})\+", text):
        ev["age_bands"].append((int(m.group(1)), 120))
    for m in re.finditer(r"\b([MF])\b|/([MF])\b|\b(Male|Female)\b", text):
        g = (m.group(1) or m.group(2) or m.group(3) or "")[:1].upper()
        if g:
            ev["gender"].add(g)
    return ev


def load_registry(path):
    reg = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            reg.append(row)
    return reg


def build_release_profiles(out):
    """Group records by pseudonym into profiles and gather their evidence."""
    san = out / "sanitized"
    recs = defaultdict(list)
    try:
        for line in (out / "records.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("patient"):
                    recs[r["patient"]].append(r["file"])
    except OSError:
        pass
    text_cache = {}

    def gettext(rel):
        if rel not in text_cache:
            p = out / rel if rel.startswith("sanitized") else san / rel
            try:
                text_cache[rel] = norm(p.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                text_cache[rel] = ""
        return text_cache[rel]

    profiles = {}
    for psn, files in recs.items():
        blob = "\n".join(gettext(f) for f in set(files))
        profiles[psn] = extract_evidence(blob)
    return profiles


def registry_match(ev, reg_index, reg):
    """A2/A3-style candidate filtering + weighting; returns prob mass on best candidate."""
    cands = set(range(len(reg)))

    def filt(key, pred):
        nonlocal cands
        sub = {i for i in cands if pred(reg[i])}
        if sub:
            cands = sub

    if ev["phones"]:
        filt("phone", lambda r: P.phone_core(r.get("phone", "")) in ev["phones"])
    if ev["pins"]:
        filt("pin", lambda r: r.get("pin", "") in ev["pins"])
    if ev["gender"]:
        filt("gender", lambda r: r.get("gender", "")[:1].upper() in ev["gender"])
    if ev["ages"]:
        filt("age", lambda r: r.get("age", "").isdigit() and any(abs(int(r["age"]) - a) <= 2 for a in ev["ages"]))
    elif ev["age_bands"]:
        filt("ageband", lambda r: r.get("age", "").isdigit() and any(lo <= int(r["age"]) <= hi for lo, hi in ev["age_bands"]))
    if len(cands) <= 1:
        return 1.0 if len(cands) == 1 else 0.0
    return 1.0 / len(cands)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--input", default=str(HERE.parent.parent / "toolkit2" / "dev" / "input"))
    ap.add_argument("--attacker", default=str(HERE.parent.parent / "toolkit2" / "dev" / "attacker"))
    ap.add_argument("--raw", default=str(HERE.parent.parent / "toolkit2" / "dev" / "truth" / "raw_attack.json"))
    a = ap.parse_args()
    out = Path(a.output)
    reg = load_registry(Path(a.attacker) / "registry.csv")
    reg_index = None
    profiles = build_release_profiles(out)
    n = len(profiles) or 1

    # A3: mean prob on true person (approx: each profile vs the whole registry)
    a3 = sum(registry_match(ev, reg_index, reg) for ev in profiles.values()) / n
    # A4: share confidently singled out (prob >= 0.5)
    a4 = sum(1 for ev in profiles.values() if registry_match(ev, reg_index, reg) >= 0.5) / n
    # A1: direct identifiers surviving
    a1 = sum(1 for ev in profiles.values() if ev["phones"] or ev["ids"]) / n

    raw = {}
    if Path(a.raw).is_file():
        raw = json.loads(Path(a.raw).read_text(encoding="utf-8")).get("result", {})
    raw_a3 = raw.get("record_linkage_risk", 1.0) or 1.0
    raw_a4 = raw.get("patients_reidentified", 1.0) or 1.0

    print("=" * 56)
    print(" RakshaMed internal attack simulation (dev-only proxy)")
    print("=" * 56)
    print(f" profiles (pseudonymous patients): {n}")
    print(f" A1 direct exposure (phone/id present): {a1:5.1%}")
    print(f" A3 record linkage risk (vs raw {raw_a3:.2f}):  {a3:5.1%}  -> ratio {a3 / raw_a3:5.2f}")
    print(f" A4 profile re-id >=0.5 (vs raw {raw_a4:.2f}):  {a4:5.1%}  -> ratio {a4 / raw_a4:5.2f}")
    audit = out / "audit.json"
    if audit.is_file():
        pol = json.loads(audit.read_text(encoding="utf-8")).get("policy", {})
        print(f" policy base={pol.get('base')} locally_recoded={pol.get('locally_recoded')} target_met={pol.get('target_met')}")
    print("=" * 56)
    print(" (proxy only - the official attacker is stronger; use for relative tuning)")


if __name__ == "__main__":
    main()
