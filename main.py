#!/usr/bin/env python3
"""RakshaMed - offline, CPU-only, LLM-free privacy firewall for multilingual hospital records.

Usage:  RAKSHA_SECRET=<secret> python main.py --input <input dir> --output <empty output dir>

Never prints or stores personal data or the secret: stdout/stderr carry stage names and counts only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from raksha.pipeline import Pipeline, load_policy  # noqa: E402
from raksha.util import env_secret  # noqa: E402


def _emergency_report(inp: Path, out: Path, t0: float, why: str):
    """Last-resort: if the pipeline itself fails, quarantine everything (never export raw data)
    and still write an honest report so the run is not a silent drop."""
    import hashlib
    (out / "sanitized").mkdir(parents=True, exist_ok=True)
    files = []
    for p in sorted(inp.rglob("*")):
        if p.is_file():
            try:
                sha = hashlib.sha256(p.read_bytes()).hexdigest()
            except OSError:
                sha = ""
            files.append({"input_sha256": sha, "output": None, "status": "quarantined", "reason": why})
    rep = {"schema": "raksha-report/1", "files": files,
           "counts": {"files_total": len(files), "files_sanitized": 0, "files_quarantined": len(files),
                      "records_processed": 0, "identifiers_detected": 0, "records_linked": 0,
                      "records_generalized": 0, "records_suppressed": 0, "records_quarantined": 0},
           "entities": {}, "timing": {"seconds": round(time.time() - t0, 2)}, "resources": {"peak_rss_mb": 0}}
    (out / "report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    (out / "records.jsonl").write_text("", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="RakshaMed privacy firewall")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--policy", default=os.environ.get("RAKSHA_POLICY", str(HERE / "config" / "policy.yaml")))
    a = ap.parse_args()
    inp, out = Path(a.input).resolve(), Path(a.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    secret = env_secret()
    if not secret:
        sys.stderr.write("[rakshamed] warning: RAKSHA_SECRET is not set\n")
    policy = load_policy(Path(a.policy))
    t0 = time.time()
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 5000))
    try:
        rep = Pipeline(inp, out, secret, policy).run()
    except Exception as e:  # noqa: BLE001 - type only, never the message (it may contain data)
        sys.stderr.write(f"[rakshamed] pipeline failure ({type(e).__name__}); all files quarantined\n")
        _emergency_report(inp, out, t0, "pipeline_failure")
        return 1
    c = rep["counts"]
    print(f"files {c['files_total']} sanitized {c['files_sanitized']} quarantined {c['files_quarantined']} "
          f"records {c['records_processed']} linked {c['records_linked']} time {rep['timing']['seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
