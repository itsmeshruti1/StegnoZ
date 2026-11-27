"""Tests for the re-identification risk model.

The release used to be scored on how unique each profile was *inside the release*,
which counted spelling, column labels and preserved clinical content as if they were
things an attacker could look a person up by. These tests pin down what the cell is
made of now: the attributes the ATTACKS.md registry actually carries, canonicalised by
value, and judged against the population rather than against the 100-odd released
patients.
"""
from __future__ import annotations

import json

import pytest

from stegnoz import privacy as PV
from stegnoz.pipeline import (
    CONTENT_KINDS,
    QI_KINDS,
    Pipeline,
    age_band_width,
    canon_qi,
    load_policy,
    merge_age_facts,
    narrows_population,
    place_keys,
)
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config" / "policy.yaml"
SECRET = "fictional-exposure-key"


# ---------------------------------------------------------------- canonical facts
def test_one_sex_written_six_ways_is_one_fact():
    """Spelling is not a quasi-identifier. Counting it as one invents uniqueness."""
    assert canon_qi("gender", "m") == canon_qi("gender", "male") == canon_qi("gender", "पुरुष")
    assert canon_qi("gender", "f") == canon_qi("gender", "female") == canon_qi("gender", "महिला")
    assert canon_qi("gender", "m") != canon_qi("gender", "f")


def test_age_sex_field_splits_into_an_age_and_a_sex():
    assert set(canon_qi("age_sex", "41/M")) == {("age", "41"), ("gender", "m")}
    # Once the band is withheld the leftover unit word carries nothing.
    assert canon_qi("age", "[AGE] वर्ष") == []
    assert canon_qi("age_sex", "[AGE]/M") == [("gender", "m")]


def test_free_text_restating_a_banded_age_is_not_a_separate_fact():
    """Two patients identical but for a note repeating the band are not two cells."""
    assert canon_qi("text_qi", "Age: 40-49") == canon_qi("age", "40-49")
    assert canon_qi("text_qi", "261***") == [("pin", "261***")]


def test_place_is_keyed_by_name_not_by_the_column_it_arrived_in():
    """After generalising to district, the village and tehsil columns hold the district."""
    village = canon_qi("village", "Sitapur")
    tehsil = canon_qi("tehsil", "Sitapur")
    assert [key for _, key in village] == [key for _, key in tehsil]
    # Administrative words and redaction markers are not place names.
    assert place_keys("[ADDRESS], distt. Sitapur") == place_keys("Sitapur")
    assert place_keys("[ADDRESS]") == []
    assert place_keys("जिला सीतापुर") == place_keys("Sitapur")


def test_a_patients_two_age_bands_become_the_interval_they_imply():
    """Seen at 38 and at 41, the attacker learns only that the age is in the union."""
    merged = merge_age_facts({("age", "35-39"), ("age", "40-44"), ("gender", "m")})
    assert merged == {("age", "35-44"), ("gender", "m")}
    assert merge_age_facts({("age", "80-84"), ("age", "85+")}) == {("age", "80+")}
    assert merge_age_facts({("age", "35-39")}) == {("age", "35-39")}


# ---------------------------------------------------------------- what narrows
def test_age_band_width_and_open_ended_bands():
    assert age_band_width("35-39") == 5
    assert age_band_width("40-49") == 10
    assert age_band_width("85+") is None            # open ended, spans the whole tail
    assert age_band_width("[AGE]") is None


@pytest.mark.parametrize("signature, expected", [
    ({("district", "sitapur"), ("gender", "m")}, False),
    ({("district", "sitapur"), ("gender", "m"), ("age", "40-49")}, False),
    ({("district", "sitapur"), ("age", "35-39")}, True),      # 5-year band is narrow
    ({("place", "chandpur")}, True),                          # a village is narrow
    ({("pin", "261***")}, False),                             # masked postal region
    ({("pin", "261001")}, True),                              # a full PIN is not
    ({("house", "h.no 14")}, True),
    (set(), False),
])
def test_only_sub_district_detail_narrows_the_population(signature, expected):
    assert narrows_population(signature, 10) is expected


def test_clinical_content_is_never_part_of_the_cell():
    """Diagnoses and visit dates are published on purpose and are not in the registry."""
    assert not (QI_KINDS & CONTENT_KINDS)
    for kind in ("diagnosis", "diagnosis_code", "event_week", "source"):
        assert kind not in QI_KINDS


# ---------------------------------------------------------------- bands stay truthful
@pytest.mark.parametrize("width", [5, 10, 20, 40])
@pytest.mark.parametrize("age", [0, 1, 17, 39, 40, 64, 84, 85, 99, 124])
def test_every_band_contains_the_real_age(age, width):
    band = PV.age_band(age, width)
    bounds = [int(n) for n in band.replace("+", " ").split("-") if n.strip()]
    low = bounds[0]
    high = bounds[1] if len(bounds) > 1 else 10 ** 6
    assert low <= age <= high, f"{band} does not contain {age}"


def test_suppression_rung_writes_a_marker_not_a_guessed_band():
    assert PV.age_band(47, None) == "[AGE]"


# ---------------------------------------------------------------- the ladder
def test_recode_ladder_never_withholds_a_district_by_default():
    ladder = PV.recode_ladder((5, "tehsil", "prefix3"))
    assert ladder, "there must be somewhere to escalate to"
    assert all(rung[1] == "district" for rung in ladder)
    # District names are preserve-probes; only an explicit policy choice gives them up.
    assert any(rung[1] in ("state", "none")
               for rung in PV.recode_ladder((5, "tehsil", "prefix3"), keep_district=False))


def test_recode_ladder_gets_strictly_more_destructive():
    ladder = PV.recode_ladder((5, "tehsil", "prefix3"))
    credits = [PV.local_utility(rung) for rung in ladder]
    assert credits == sorted(credits, reverse=True)
    assert all(credit < PV.local_utility((5, "tehsil", "prefix3")) for credit in credits)


# ---------------------------------------------------------------- end to end
def _run(tmp_path, files, **policy):
    source = tmp_path / "in"
    source.mkdir(parents=True)
    for name, content in files.items():
        (source / name).write_text(content, encoding="utf-8")
    out = tmp_path / "out"
    config = {**load_policy(POLICY), **policy}
    report = Pipeline(source, out, SECRET, config, strict_risk=False).run()
    audit = json.loads((out / "audit.json").read_text("utf-8"))
    return out, report, audit["exposure"]


def test_release_of_many_patients_meets_the_risk_target(tmp_path):
    rows = ["Patient Name,Age,Sex,Village,District,Diagnosis,ICD"]
    for i in range(30):
        rows.append(f"Person{i} Surname{i},{20 + i},{'MF'[i % 2]},"
                    f"Vill{i},Dist{i % 3},Bronchial asthma,J45.9")
    _, report, exposure = _run(tmp_path, {"reg.csv": "\n".join(rows) + "\n"})
    assert exposure["singling_out_risk"] <= 0.05
    assert report["privacy"]["target_met"]
    # The uninflated number is always published beside it and can only ever be the
    # harsher of the two, so the assumption can never be used to hide a worse reading.
    assert exposure["observed_singling_out_risk"] >= exposure["singling_out_risk"]


def test_village_is_generalised_but_district_survives(tmp_path):
    out, _, _ = _run(tmp_path, {"reg.csv":
        "Patient Name,Age,Sex,Village,District,Diagnosis\n"
        "Anil Kumar,47,M,Chandpur,Sitapur,Dengue fever\n"})
    released = (out / "sanitized" / "reg.csv").read_text("utf-8")
    assert "Chandpur" not in released          # sub-district geography is withheld
    assert "Sitapur" in released               # district is a preserve-probe
    assert "Dengue fever" in released
    assert "Anil" not in released


def test_population_assumption_is_reported_and_reversible(tmp_path):
    files = {"reg.csv": "Patient Name,Age,Sex,Village,District,Diagnosis\n"
                        "Anil Kumar,47,M,Chandpur,Sitapur,Dengue fever\n"}
    _, _, declared = _run(tmp_path / "a", files)
    _, _, plain = _run(tmp_path / "b", files, population_factor=1)
    assert declared["population_factor"] == 4
    assert plain["population_factor"] == 1
    # Both numbers are always published, so a reader can check the assumption's effect.
    for exposure in (declared, plain):
        assert "observed_singling_out_risk" in exposure
        assert exposure["risk_basis"] == "population_quasi_identifier_cells"


def test_audit_reports_counts_and_never_values(tmp_path):
    out, _, _ = _run(tmp_path, {"reg.csv":
        "Patient Name,Age,Sex,Village,District,Mobile\n"
        "Anil Kumar,47,M,Chandpur,Sitapur,+91 98765 43210\n"})
    audit = (out / "audit.json").read_text("utf-8")
    for secret in ("Anil", "Kumar", "Chandpur", "9876543210", "98765"):
        assert secret not in audit
    assert "Sitapur" not in audit               # not even preserved values are echoed


# ---------------------------------------------------------------- context traps
def test_co_complaint_is_kept_and_co_person_is_removed(tmp_path):
    """"C/O fever" is a complaint; "C/O Ramesh" is a relative. Same two letters."""
    out, _, _ = _run(tmp_path, {"note.txt":
        "Patient: Suresh Yadav\n"
        "C/O fever and body ache since 2 days.\n"
        "C/O Ramesh Yadav, resident of the same ward.\n"
        "K/C/O diabetes. H/O tuberculosis in 2019.\n"
        "Reviewed by Dr. Ramesh Gupta in Medicine ward.\n"})
    released = (out / "sanitized" / "note.txt").read_text("utf-8")
    assert "C/O fever and body ache" in released        # complaint survives
    assert "K/C/O diabetes" in released
    assert "H/O tuberculosis" in released
    assert "Dr. Ramesh Gupta" in released               # the doctor is not a patient
    assert "Medicine ward" in released
    assert "Suresh Yadav" not in released               # the patient goes
    assert "C/O Ramesh Yadav" not in released           # the relative goes


def test_doses_and_frequencies_are_not_mistaken_for_identifiers(tmp_path):
    out, _, _ = _run(tmp_path, {"rx.txt":
        "Rx: Ramipril 5 mg OD, Dolo 650 BD x 5 days, Metformin 1-0-1.\n"
        "BP 138/86 mmHg, Pulse 92/min, Hb 11.4 g/dL.\n"
        "Mobile: +91 98765 43210\n"})
    released = (out / "sanitized" / "rx.txt").read_text("utf-8")
    for kept in ("Ramipril 5 mg OD", "Dolo 650 BD x 5 days", "1-0-1",
                 "BP 138/86 mmHg", "Pulse 92/min", "Hb 11.4 g/dL"):
        assert kept in released, kept
    assert "98765" not in released and "9876543210" not in released


def test_an_eponym_is_a_disease_not_a_person(tmp_path):
    out, _, _ = _run(tmp_path, {"dx.txt":
        "Diagnosis: Parkinson's disease with Hashimoto thyroiditis.\n"
        "Attending: Dr. Alok Nath.\n"})
    released = (out / "sanitized" / "dx.txt").read_text("utf-8")
    assert "Parkinson's disease" in released
    assert "Hashimoto thyroiditis" in released
    assert "Dr. Alok Nath" in released


def test_date_shift_preserves_the_length_of_stay(tmp_path):
    out, _, _ = _run(tmp_path, {"stay.csv":
        "Patient Name,UHID,Admission,Discharge\n"
        "Suresh Yadav,REG-50021,01/03/2025,10/03/2025\n"})
    released = (out / "sanitized" / "stay.csv").read_text("utf-8")
    import csv as _csv
    import datetime as _dt
    row = list(_csv.reader(released.splitlines()))[1]
    admitted, discharged = (_dt.datetime.strptime(v, "%d/%m/%Y").date() for v in row[2:4])
    assert (discharged - admitted).days == 9        # the true stay, on shifted dates
    assert "01/03/2025" not in released             # and the real dates are gone
    assert "Suresh" not in released


def test_two_runs_of_the_same_input_are_byte_identical(tmp_path):
    files = {"reg.csv": "Patient Name,Age,Sex,District,Diagnosis\n"
                        "Anil Kumar,47,M,Sitapur,Dengue fever\n"}
    first, _, _ = _run(tmp_path / "one", files)
    second, _, _ = _run(tmp_path / "two", files)
    for name in ("sanitized/reg.csv", "records.jsonl"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


# ---------------------------------------------------------------- anti-gaming
def test_the_population_assumption_cannot_buy_a_finer_release(tmp_path):
    """Raising the factor must not make the engine publish more.

    A population multiplier applied to node selection would let a bigger factor make
    generalisation look unnecessary, so the release would disclose more geography while
    still reporting a passing number. Selection runs on the uninflated figure, so the
    factor can only change the verdict, never the output.
    """
    files = {"reg.csv": "\n".join(
        ["Patient Name,Age,Sex,Village,Tehsil,District,Diagnosis"]
        + [f"Person{i} Surname{i},{20 + i},{'MF'[i % 2]},Vill{i},Teh{i % 4},Dist{i % 3},"
           "Bronchial asthma" for i in range(24)]) + "\n"}
    low, _, low_exposure = _run(tmp_path / "f1", files, population_factor=1)
    high, _, high_exposure = _run(tmp_path / "f5", files, population_factor=5)
    assert (low / "sanitized" / "reg.csv").read_bytes() == \
           (high / "sanitized" / "reg.csv").read_bytes()
    assert low_exposure["observed_singling_out_risk"] == \
           high_exposure["observed_singling_out_risk"]


def test_risk_is_measured_not_asserted(tmp_path):
    """Data that genuinely singles people out must register as risk.

    A metric that cannot report a problem is not a metric. This calls the risk view
    directly, because the pipeline's whole job is to generalise until the number is
    zero - the end-to-end run is supposed to come out clean.
    """
    pipeline = Pipeline.__new__(Pipeline)
    pipeline.policy = {"k_target": 5, "population_factor": 1,
                       "coarse_age_band_years": 10, "rare_dx_max_patients": 3}
    unique_village = {f"PSN-{i}": {("place", f"vill{i}"), ("gender", "m"),
                                   ("age", "40-49")} for i in range(3)}
    assert len(pipeline._risk_view(unique_village)["at_risk"]) == 3
    narrow_band = {f"PSN-{i}": {("district", "d"), ("gender", "m"),
                                ("age", f"4{i}-4{i}")} for i in range(3)}
    assert len(pipeline._risk_view(narrow_band)["at_risk"]) == 3
    coarse = {f"PSN-{i}": {("district", "d"), ("gender", "m"),
                           ("age", "40-49")} for i in range(3)}
    assert not pipeline._risk_view(coarse)["at_risk"]


def test_place_folding_does_not_merge_different_districts():
    """Folding spellings must not quietly merge real places and inflate cells."""
    from stegnoz.pipeline import _fold_place_keys
    from stegnoz.translit import name_key
    names = ["Sitapur", "Barabanki", "Bahraich", "Sultanpur", "Hardoi", "Unnao",
             "Lucknow", "Kanpur", "Kannauj", "Hamirpur", "Hapur", "Mau", "Maunath"]
    keys = {name_key(n) for n in names}
    folded = _fold_place_keys(keys)
    assert len(set(folded.values())) == len(keys), "distinct districts were merged"
    # and the cross-script fold it exists for still works
    for latin, deva in [("Barabanki", "बाराबंकी"), ("Sitapur", "सीतापुर")]:
        pair = _fold_place_keys({name_key(latin), name_key(deva)})
        assert pair[name_key(latin)] == pair[name_key(deva)]
