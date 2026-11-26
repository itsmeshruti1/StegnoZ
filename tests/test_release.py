from __future__ import annotations

import csv
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

from stegnoz.extract import new_attrs
from stegnoz.link import resolve
from stegnoz.pipeline import Pipeline, load_policy


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config" / "policy.yaml"
SECRET = "fictional-release-key"


def run_pipeline(tmp_path, files, strict=False):
    source = tmp_path / "in"
    source.mkdir(parents=True)
    for name, content in files.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not isinstance(content, str):
            content = json.dumps(content)
        path.write_text(content, encoding="utf-8")
    output = tmp_path / "out"
    report = Pipeline(source, output, SECRET, load_policy(POLICY), strict_risk=strict).run()
    records = [json.loads(line) for line in (output / "records.jsonl").read_text("utf-8").splitlines()]
    return output, report, records


def released(output, relative):
    return (output / "sanitized" / relative).read_text("utf-8")


def test_known_surfaces_keys_and_unknown_text(tmp_path):
    output, report, records = run_pipeline(tmp_path, {
        "roster.csv": "Patient Name,Village\nRamesh Verma,Sundarpur\n",
        "note.txt": "ramesh verma lives in sundarpur.\nDr. Ramesh Verma reviewed the chart.",
        "followup.txt": "Quenby Tarlowe returned for a routine follow-up.",
        "patient.json": {"patient_name": "Ramesh Verma", "ramesh": {"diagnosis": "stable"}, "sundarpur": "stable"},
        "ramesh_verma.txt": "Routine follow-up.",
        "key_only.json": {"ramesh": {"diagnosis": "typhoid"}},
    })
    note = released(output, "note.txt")
    assert "[REDACTED]" in note.splitlines()[0]
    assert "Dr. Ramesh Verma" in note
    assert "Quenby Tarlowe" not in released(output, "followup.txt")
    data = json.loads(released(output, "patient.json"))
    assert not {"ramesh", "sundarpur"} & data.keys()
    assert "ramesh_verma" not in json.dumps(report)
    assert "ramesh" not in json.loads(released(output, "key_only.json"))
    assert any(r["file"].endswith("followup.txt") and r["patient"] for r in records)


def test_literal_name_used_as_json_key_without_roster(tmp_path):
    out, _, _ = run_pipeline(tmp_path, {"names.json": {
        "ramesh": {"diagnosis": "typhoid"}, "Ramesh": {"diagnosis": "stable"},
    }})
    data = json.loads(released(out, "names.json"))
    assert not {"ramesh", "Ramesh"} & data.keys()
    assert {record["diagnosis"] for record in data.values()} == {"typhoid", "stable"}


def test_header_pii_and_manifest_coverage(tmp_path):
    output, report, records = run_pipeline(tmp_path, {
        "result.csv": "Patient Name: Ramesh Verma,UHID: QA-78421,Result\n,,98\n",
        "header.csv": "Quenby Tarlowe,Result\n,98\n",
        "visits.json": {"patients": [{"name": "Johnnie Shields"}], "observations": [{"result": 88}, {"result": 99}]},
        "lab.json": {"patient": {"name": "Ramesh Verma"}, "panels": [{"value": 98}]},
        "locator.json": {"Ramesh Verma": [{"patient_name": "Ramesh Verma"}]},
    })
    assert "Ramesh Verma" not in released(output, "result.csv")
    assert "QA-78421" not in released(output, "result.csv")
    assert "Quenby Tarlowe" not in released(output, "header.csv")
    assert any(r["file"].endswith("lab.json") and r["loc"] == "doc" for r in records)
    assert any(r["loc"] == "/patients/0" for r in records)
    assert "Ramesh Verma" not in json.dumps(records)
    assert report["counts"]["files_quarantined"] == 1


def test_formatter_preserves_clinical_numbers_and_date_intervals(tmp_path):
    output, report, records = run_pipeline(tmp_path, {
        "age.json": {"patient_name": "Ramesh Verma", "pin": 226001, "age": "45.5", "result": 123456789},
        "results.csv": ("Patient Name,Visit Date (DD/MM/YYYY),Discharge Date (MM/DD/YYYY),Result\n"
                        "Ramesh Verma,05/04/2025,04/09/2025,123456789\n"),
        "anon.txt": "DOB: 1990-08-21\nVisit: 2025-03-21",
        "counter.txt": "Analyzer run counter: 234567890123",
        "no_qi.csv": "Patient Name,Diagnosis\nRamesh Verma,stable\n",
    })
    data = json.loads(released(output, "age.json"))
    assert data["pin"] == "226***"
    assert data["age"] and ".5" not in data["age"] and data["result"] == 123456789
    cells = list(csv.reader(released(output, "results.csv").splitlines()))[1]
    assert cells[3] == "123456789"
    start = dt.datetime.strptime(cells[1], "%d/%m/%Y")
    end = dt.datetime.strptime(cells[2], "%m/%d/%Y")
    assert (end - start).days == 4
    assert "1990-08-21" not in released(output, "anon.txt")
    assert "2025-03-21" not in released(output, "anon.txt")
    assert released(output, "counter.txt") == "Analyzer run counter: 234567890123"
    no_qi = next(r for r in records if r["file"].endswith("no_qi.csv"))
    assert "status" not in no_qi


def test_fhir_keeps_multi_patient_references_and_quarantines_binary(tmp_path):
    def entry(resource):
        return {"fullUrl": f"https://example.test/{resource['resourceType']}/{resource['id']}",
                "resource": resource}

    patient_a = entry({"resourceType": "Patient", "id": "MRN44771", "name": [{"given": ["Ramesh"], "family": "Verma"}]})
    patient_b = entry({"resourceType": "Patient", "id": "MRN44772", "name": [{"given": ["Quenby"], "family": "Tarlowe"}]})
    observation = entry({"resourceType": "Observation", "id": "oxygen", "status": "final",
                         "code": {"text": "Oxygen saturation"}, "subject": {"reference": "Patient/MRN44771"},
                         "valueQuantity": {"value": 98, "unit": "%"}})
    binary = entry({"resourceType": "DocumentReference", "id": "attachment", "status": "current",
                    "content": [{"attachment": {"data": "AAECAw==", "contentType": "application/pdf"}}]})
    output, report, records = run_pipeline(tmp_path, {
        "bundle.json": {"resourceType": "Bundle", "type": "collection", "entry": [patient_a, patient_b, observation]},
        "binary.json": {"resourceType": "Bundle", "type": "collection", "entry": [patient_a, binary]},
    })
    a, b, obs = json.loads(released(output, "bundle.json"))["entry"]
    assert a["resource"]["id"] != b["resource"]["id"]
    assert a["resource"]["id"].startswith("PSN-") and b["resource"]["id"].startswith("PSN-")
    assert obs["resource"]["subject"]["reference"] == a["fullUrl"]
    assert obs["resource"]["valueQuantity"]["value"] == 98
    assert records == [{"file": "sanitized/bundle.json", "loc": "doc", "patient": None}]
    assert report["counts"]["files_quarantined"] == 1


def test_matching_large_blocks_and_mrn_conflicts():
    def attrs(**changes):
        return {**new_attrs(), **changes}

    left = attrs(ids={"MRN44771"}, phones={"7000000000"})
    right = attrs(ids={"MRN44772"}, phones={"7000000000"})
    assert len(set(resolve([left, right])[0])) == 2
    same = attrs(ids={"MRN44771"}, names=["Ramesh Verma"])
    longitudinal = [{**same, "ages": [37]}, {**same, "ages": [43]}]
    assert len(set(resolve(longitudinal)[0])) == 1
    scoped = [{**same, "source": {"hospital a"}}, {**same, "source": {"hospital b"}}]
    assert len(set(resolve(scoped)[0])) == 2
    assignment, stats = resolve([same] * 401)
    assert len(set(assignment)) == 1
    assert stats["candidate_pairs"] == 400


def test_rename_keeps_pseudonym_and_replacing_identity_changes_it(tmp_path):
    _, _, first = run_pipeline(tmp_path / "first", {"a.csv": "Patient Name,MRN\nRamesh Verma,QA-78421\n"})
    _, _, renamed = run_pipeline(tmp_path / "renamed", {"b.csv": "Patient Name,MRN\nRamesh Verma,QA-78421\n"})
    _, _, replaced = run_pipeline(tmp_path / "replaced", {"a.csv": "Patient Name,MRN\nQuenby Tarlowe,QA-78422\n"})
    assert first[0]["patient"] == renamed[0]["patient"] != replaced[0]["patient"]


def test_risk_targets_and_invalid_inputs(tmp_path):
    files = {"people.csv": "Patient Name,Age,Diagnosis\nRamesh Verma,49,J45.9\n",
             "ragged.csv": "Name,Result\nQuenby Tarlowe,98,extra\n",
             "duplicate.json": '{"result":97,"result":99}'}
    output, report, records = run_pipeline(tmp_path / "default", files)
    assert report["counts"]["files_quarantined"] == 2
    assert not report["privacy"]["target_met"] and records
    exposure = json.loads((output / "audit.json").read_text("utf-8"))["exposure"]
    assert exposure["k_anonymity"]["1"] == 1
    output, report, records = run_pipeline(tmp_path / "strict", files, strict=True)
    assert report["privacy"]["strict_blocked"]
    assert report["counts"]["files_suppressed"] == 1
    assert not records and not any((output / "sanitized").iterdir())


def test_cli_requires_secret_separate_paths_and_empty_destination(tmp_path):
    source = tmp_path / "in"
    source.mkdir()
    (source / "note.txt").write_text("Stable.", encoding="utf-8")
    out = tmp_path / "out"
    env = dict(os.environ)
    env.pop("RAKSHA_SECRET", None)

    def run(input_path, dest, *flags):
        return subprocess.run([sys.executable, "-B", str(ROOT / "main.py"),
                               "--input", str(input_path), "--output", str(dest),
                               "--policy", str(POLICY), *flags], env=env, capture_output=True)

    assert run(source, out).returncode != 0 and not out.exists()
    env["RAKSHA_SECRET"] = SECRET
    assert run(tmp_path / "missing", out).returncode != 0 and not out.exists()
    assert run(source, source / "out").returncode != 0
    assert run(source, out).returncode == 0
    report = (out / "report.json").read_bytes()
    assert run(source, out).returncode != 0
    assert (out / "report.json").read_bytes() == report
    assert not (out / ".stegnoz-running").exists()
    (source / "note.txt").write_text("Patient: Ramesh Verma\nAge: 47\n", encoding="utf-8")
    strict = tmp_path / "strict"
    assert run(source, strict, "--strict-risk").returncode == 1
    assert not any((strict / "sanitized").iterdir())
