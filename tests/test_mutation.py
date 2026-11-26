import hashlib
import json
from pathlib import Path
import subprocess
import sys


def test_mutation_keeps_fhir_valid_and_updates_annotation_hashes_and_locators(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    ordinary = {"guardian": {"name": "Quenby Tarlowe", "result": 98}}
    fhir = {"resourceType": "Patient", "id": "test-patient", "name": [{"family": "Tarlowe"}]}
    for filename, obj in (("patient.json", ordinary), ("fhir.json", fhir)):
        (source / filename).write_text(json.dumps(obj), encoding="utf-8")
    truth = tmp_path / "truth.json"
    truth.write_text(json.dumps({"files": {
        filename: {"sha256": hashlib.sha256((source / filename).read_bytes()).hexdigest(),
                   "units": {"/guardian": {"entities": [], "preserve": [{"text": "98"}]}}}
        for filename in ("patient.json", "fhir.json")
    }}), encoding="utf-8")
    output = tmp_path / "mutated/input"
    new_truth = tmp_path / "mutated/truth/truth.json"
    script = Path(__file__).resolve().parents[1] / "tools/mutate_dataset.py"
    command = [sys.executable, "-B", str(script), str(source), str(output),
               "--truth", str(truth), "--truth-output", str(new_truth)]
    assert subprocess.run(command, capture_output=True).returncode == 0
    assert (output / "fhir.json").read_bytes() == (source / "fhir.json").read_bytes()
    assert json.loads((output / "patient.json").read_text())["kin_block"]["result"] == 98
    adapted = json.loads(new_truth.read_text())["files"]["patient.json"]
    assert adapted["sha256"] == hashlib.sha256((output / "patient.json").read_bytes()).hexdigest()
    assert "/kin_block" in adapted["units"]
    assert adapted["units"]["/kin_block"]["preserve"] == [{"text": "98"}]
    # Never recursively delete an existing destination to make a test rerunnable.
    assert subprocess.run(command, capture_output=True).returncode != 0
