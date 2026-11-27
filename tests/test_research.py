"""Research boundary regressions: counts, suppression, and release traversal."""
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from dashboard.research_server import Handler, demo_records, load_release, normalize, query


def test_demo_counts_and_question_filters():
    rows = demo_records()
    assert query(rows, {})["patients"] == 480
    result = query(rows, {"question": "Show women with diabetes"})
    assert result["filters"]["sex"] == "Female"
    assert result["filters"]["condition"] == "Diabetes"
    assert result == query(rows, {"sex": "Female", "condition": "Diabetes"})
    with pytest.raises(ValueError):
        query(rows, {"question": "Compare mortality after insulin"})


def test_small_cells_and_overlapping_groups():
    rows = [{"patient": str(i), "condition": "Diabetes", "age": "20–39", "sex": "Female", "source": "Source 1"} for i in range(6)]
    rows.append({**rows[0], "condition": "Dengue"})
    result = query(rows, {})
    assert result["patients"] == 6
    assert result["distributions"]["condition"] == []
    assert query(rows, {"condition": "Dengue"})["patients"] is None
    assert query(rows, {"condition": "Asthma"})["patients"] == 0


def test_release_adapter_reads_only_approved_manifest(tmp_path):
    (tmp_path / "sanitized").mkdir()
    (tmp_path / "sanitized" / "patients.csv").write_text("patient,age,sex,diagnosis\nPSN-1,40-49,F,Diabetes\n", encoding="utf-8")
    report = {"files": [{"output": "sanitized/patients.csv", "status": "sanitized"}], "privacy": {"target_met": True}}
    (tmp_path / "report.json").write_text(json.dumps(report))
    entry = {"file": "sanitized/patients.csv", "loc": "row:0", "patient": "PSN-1"}
    (tmp_path / "records.jsonl").write_text(json.dumps(entry))
    rows, metadata = load_release(tmp_path)
    assert rows[0]["age"] == "40–59"
    assert rows[0]["sex"] == "Female"
    assert metadata["mode"] == "release"
    entry["file"] = "../private.csv"
    (tmp_path / "records.jsonl").write_text(json.dumps(entry))
    with pytest.raises(ValueError):
        load_release(tmp_path)
    report["privacy"]["strict_blocked"] = True
    (tmp_path / "report.json").write_text(json.dumps(report))
    with pytest.raises(ValueError):
        load_release(tmp_path)


def test_uncertain_age_band_is_not_narrowed():
    assert normalize({"age": "30-59"}, "x", "Source 1")[0]["age"] == "Unknown"


def test_integrated_http_routes_and_security_headers():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.rows = demo_records()
    server.metadata = {"mode": "demo", "title": "Synthetic research sandbox", "files": 4,
                       "privacy_target_met": None}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request("GET", "/")
        landing = connection.getresponse()
        assert landing.status == 200
        assert landing.getheader("Content-Security-Policy")
        assert b"StegnoZ" in landing.read()

        connection.request("GET", "/dashboard")
        dashboard = connection.getresponse()
        assert dashboard.status == 200
        assert b"Researcher Console" in dashboard.read()

        connection.request("GET", "/api/catalog")
        catalog = connection.getresponse()
        assert catalog.status == 200
        assert json.loads(catalog.read())["mode"] == "demo"

        body = json.dumps({"condition": "Diabetes"}).encode()
        connection.request("POST", "/api/query", body=body,
                           headers={"Content-Type": "application/json", "Content-Length": str(len(body))})
        result = connection.getresponse()
        assert result.status == 200
        assert json.loads(result.read())["filters"]["condition"] == "Diabetes"
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
