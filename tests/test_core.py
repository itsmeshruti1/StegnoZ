"""Targeted regression tests for the traps that the scorer probes. Run: python -m pytest tests/"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from raksha import patterns as P
from raksha.extract import classify_column, classify_key, looks_like_person
from raksha.link import resolve
from raksha.privacy import age_band, choose_policy
from raksha.translit import deva_to_latin, name_key, token_sim
from raksha.util import Keys


def test_cross_script_name_keys_match():
    assert name_key("Reena") == name_key("रीना") == name_key("Rina")
    assert name_key("Mohammad") == name_key("Mohd") == name_key("Md") == name_key("मोहम्मद")
    assert token_sim("Fatima", "फ़ातिमा") >= 0.9


def test_verhoeff():
    assert P.verhoeff_ok("636135302117")  # a valid Aadhaar-style number
    assert not P.verhoeff_ok("636135302119")


def test_dose_not_phone_or_id():
    # 1-0-1 frequency and doses must not be read as identifiers
    assert P.FREQ.search("Metformin 500 mg 1-0-1 x 5 days")
    assert not any(not P.phone_guard("Paracetamol 650 mg BD", m.start(), m.end())
                   for m in P.PHONE.finditer("650"))


def test_age_band_contains_true_age():
    for a in range(1, 100):
        lo_hi = age_band(a, 5)
        if lo_hi.endswith("+"):
            assert a >= int(lo_hi[:-1])
        else:
            lo, hi = map(int, lo_hi.split("-"))
            assert lo <= a <= hi


def test_pseudonym_keyed_and_secret_sensitive():
    k1, k2 = Keys("alpha"), Keys("beta")
    assert k1.pseudonym("x#1") == k1.pseudonym("x#1")           # deterministic
    assert k1.pseudonym("x#1") != k2.pseudonym("x#1")           # secret-sensitive
    assert k1.pseudonym("x#1").startswith("PSN-")
    d = k1.shift_days("x#1", 21, 180)
    assert 21 <= abs(d) <= 180                                   # never small


def test_content_classification_of_unseen_headers():
    assert classify_column("EnrolmentRef", ["SNJ/26/064127", "JJH-0076928"]) == "mrn"
    assert classify_column("PostIdx", ["229073", "225362", "209182"]) == "pin"
    assert classify_column("Cell Contact", ["+91 72864 90658", "8081120924"]) == "phone"
    assert classify_column("full_nm", ["Mahesh Chauhan", "Usha Tiwari"]) == "name"


def test_relative_vs_person_context_keys():
    assert classify_key("name", ("guardian",)) == "relative"
    assert classify_key("name", ("patient",)) == "name"
    assert classify_key("name", ("facility",)) == "org"


def test_homonyms_not_merged():
    a = {"names": ["Ramesh Yadav"], "relatives": ["Shyam Yadav"], "dob": {"1980-01-01"}, "ages": [44],
         "gender": {"M"}, "phones": set(), "aadhaar": set(), "abha": set(), "ids": set(), "emails": set(),
         "pans": set(), "insurance": set(), "villages": ["Govindnagar"], "tehsils": [], "districts": [],
         "pins": set(), "cand_ids": set(), "cores": set(), "cand_cores": {}, "dx": set()}
    b = dict(a, relatives=["Mohan Yadav"], dob={"1962-05-05"}, ages=[62], villages=["Bhimpur"])
    assign, diag = resolve([a, b])
    assert assign[0] != assign[1]  # same name, different person -> never one cluster


def test_same_patient_linked_by_strong_id():
    base = {"names": ["Mahesh Chauhan"], "relatives": ["Naresh Chauhan"], "dob": {"1977-04-12"},
            "ages": [48], "gender": {"M"}, "phones": {"7286490658"}, "aadhaar": set(), "abha": set(),
            "ids": {"SNJ2606412"}, "emails": set(), "pans": set(), "insurance": set(), "villages": [],
            "tehsils": [], "districts": [], "pins": set(), "cand_ids": set(), "cores": set(),
            "cand_cores": {}, "dx": set()}
    other = dict(base, ids={"SNJ2606412"}, names=["M Chauhan"])
    assign, _ = resolve([base, other])
    assert assign[0] == assign[1] is not None


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    ok = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
            ok += 1
        except Exception:
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{ok}/{len(fns)} passed")
    sys.exit(0 if ok == len(fns) else 1)
