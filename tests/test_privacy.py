import json

import pytest
from cryptography.exceptions import InvalidTag

from stegnoz.extract import name_sim, new_attrs
from stegnoz.link import resolve
from stegnoz.pipeline import Pipeline
from stegnoz.privacy import choose_policy
from stegnoz.staging import EncryptedStaging


def test_policy_uses_actual_risk_and_bounds_the_population_assumption():
    calls = []
    def evaluate(node):
        calls.append(node)
        return {"risk": 0.0 if node[0] == 10 else 1.0, "patients": 10, "valid": True}
    result = choose_policy(evaluate, {})
    assert result["base"] == (10, "tehsil", "prefix3")
    assert result["target_met"] and result["selected_risk"] == 0
    assert (5, "tehsil", "prefix3") in calls
    # The population assumption is declared, not unlimited: a factor inside the range
    # ATTACKS.md states is accepted, anything that would wish the risk away is not.
    assert choose_policy(evaluate, {"population_factor": 5})["target_met"]
    for bad in (0, 0.5, 11, 1000):
        with pytest.raises(ValueError):
            choose_policy(evaluate, {"population_factor": bad})


def test_policy_cannot_improve_risk_by_dropping_files_or_rounding():
    def evaluate(node):
        return {"risk": .0500001 if node[0] == 5 else 0,
                "patients": 10, "valid": node[0] == 5}
    result = choose_policy(evaluate, {"max_singling_out": .05})
    assert not result["target_met"]
    assert result["base"] == (5, "tehsil", "prefix3")
    assert result["search_exhausted"]


def test_preserved_facts_lower_bound_stops_pointless_generalization():
    calls = []
    def evaluate(node):
        calls.append(node)
        return {"risk": 1.0, "risk_floor": 1.0, "patients": 1, "valid": True}
    result = choose_policy(evaluate, {})
    assert calls == [(5, "tehsil", "prefix3")]
    assert not result["target_met"]
    assert result["stop_reason"] == "preserved_facts_lower_bound"


def test_candidate_staging_is_encrypted_authenticated_and_bound_to_file(tmp_path):
    store = EncryptedStaging()
    path = tmp_path / "0"
    plain = b"Synthetic patient Quenby Tarlowe: diagnosis J45.9"
    store.write(path, plain)
    first = path.read_bytes()
    assert plain not in first and store.read(path) == plain
    store.write(path, plain)
    assert path.read_bytes() != first
    other = tmp_path / "1"
    other.write_bytes(path.read_bytes())
    with pytest.raises(InvalidTag):
        store.read(other)
    path.write_bytes(first[:-1] + bytes([first[-1] ^ 1]))
    with pytest.raises(InvalidTag):
        store.read(path)
    path.write_bytes(first)
    with pytest.raises(InvalidTag):
        EncryptedStaging().read(path)


def test_real_candidate_search_preserves_medical_values_and_matches_final_risk(tmp_path):
    inp, out = tmp_path / "in", tmp_path / "out"
    inp.mkdir()
    # Five distinct patients span two 5-year bands but one 10-year band.
    rows = [f"CASE-{80000+i},{age},J45.9,98" for i, age in enumerate([20,21,25,26,27])]
    (inp / "people.csv").write_text("MRN,Age,Diagnosis,SpO2\n" + "\n".join(rows), encoding="utf-8")
    pipeline = Pipeline(inp, out, "synthetic-test-key", {"k_target": 5, "max_singling_out": .05})
    report = pipeline.run()
    audit = json.loads((out / "audit.json").read_text("utf-8"))
    assert report["privacy"]["target_met"]
    assert audit["policy"]["base"] == [10, "tehsil", "prefix3"]
    assert audit["policy"]["selected_risk"] == audit["exposure"]["singling_out_risk"] == 0
    text = (out / "sanitized/people.csv").read_text("utf-8")
    assert text.count("20-29,J45.9,98") == 5
    assert report["counts"]["records_generalized"] == 5
    assert report["entities"]["AGE"] == 5  # not multiplied by candidate attempts
    assert not list(out.glob(".verified-*"))


def test_lone_record_with_only_coarse_attributes_is_published(tmp_path):
    """One patient is not "singled out" by a wide age band and no geography.

    The cell that matters is the population cell. A banded age with no location and no
    identifier leaves tens of thousands of people, so withholding the record would cost
    utility and buy no privacy. It used to be withheld because the risk proxy counted
    release-internal uniqueness, which a one-record release always maximises.
    """
    inp, out = tmp_path / "in", tmp_path / "out"
    inp.mkdir()
    (inp / "one.csv").write_text("MRN,Age,Diagnosis\nCASE-81234,47,J45.9\n", encoding="utf-8")
    result = Pipeline(inp, out, "synthetic-test-key", {}).run()
    assert not result["privacy"]["strict_blocked"] and result["privacy"]["target_met"]
    assert list((out / "sanitized").iterdir())
    released = (out / "sanitized" / "one.csv").read_text("utf-8")
    assert "J45.9" in released and "47" not in released       # diagnosis kept, age banded
    assert "CASE-81234" not in released


def test_strict_mode_still_withholds_when_the_target_cannot_be_met(tmp_path):
    """The fail-closed backstop fires whenever the measured risk misses the target.

    Local recoding can nearly always reach the target now, so this drives the risk
    directly rather than hunting for data that defeats the recoder: the point under
    test is that a missed target withholds the release, not how it came to be missed.
    """
    inp, out = tmp_path / "in", tmp_path / "out"
    inp.mkdir()
    (inp / "one.csv").write_text("MRN,Age,Diagnosis\nCASE-81234,47,J45.9\n", encoding="utf-8")
    pipeline = Pipeline(inp, out, "synthetic-test-key", {}, strict_risk=True)
    real = pipeline._exposure_stats
    pipeline._exposure_stats = lambda: {**real(), "singling_out_risk": 0.9}
    result = pipeline.run()
    assert result["privacy"]["strict_blocked"] and not result["privacy"]["target_met"]
    assert result["counts"]["records_suppressed"] == 1
    assert not list((out / "sanitized").iterdir())


def test_complete_common_component_names_match_across_scripts():
    assert name_sim("Mohammad Farhan", "मोहम्मद फरहान") == (1.0, 1.0)
    assert name_sim("Mohammad Farhan", "Farhan")[1] < .92
    assert name_sim("Mohammad Farhan", "Mohammad Imran")[1] < .92


def test_unknown_mrn_namespaces_do_not_block_corroborated_identity():
    def attrs(**kwargs):
        return {**new_attrs(), **kwargs}
    shared = dict(names=["Quenby Tarlowe"], dob={"1980-03-04"}, gender={"F"})
    a = attrs(**shared, ids={"A12345"})
    b = attrs(**shared, ids={"B12345"})
    assigned, _ = resolve([a, b])
    assert assigned[0] == assigned[1]
    a["source"] = b["source"] = {"same hospital"}
    assigned, _ = resolve([a, b])
    assert assigned[0] != assigned[1]
    b["source"] = set()
    b["dob"] = {"1970-01-01"}
    assigned, _ = resolve([a, b])
    assert assigned[0] != assigned[1]
