#!/usr/bin/env python3
"""StegnoZ - offline, CPU-only, LLM-free privacy firewall for multilingual hospital records.

Usage:  RAKSHA_SECRET=<secret> python main.py --input <input dir> --output <empty output dir>

Never prints or stores personal data or the secret: stdout/stderr carry stage names and counts only.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from stegnoz.ingest import iter_input
from stegnoz.pipeline import Pipeline, load_policy  # noqa: E402
from stegnoz.util import env_secret  # noqa: E402


def _emergency_report(inp: Path, out: Path, t0: float, why: str):
    """Last-resort: if the pipeline itself fails, quarantine everything (never export raw data)
    and still write an honest report so the run is not a silent drop."""
    import hashlib
    (out / "sanitized").mkdir(parents=True, exist_ok=True)
    files = []
    for path, _ in iter_input(inp):
        try:
            with path.open("rb") as source:
                sha = hashlib.file_digest(source, "sha256").hexdigest()
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


def publish(stage: Path, out: Path):
    """Publish the report last. Roll back entries moved from this staging directory on failure."""
    moved = []
    try:
        for path in sorted(stage.iterdir(), key=lambda path: (path.name == "report.json", path.name)):
            path.rename(out / path.name)
            moved.append(path)
    except OSError:
        for path in reversed(moved):
            (out / path.name).rename(path)
        raise


def main() -> int:
    ap = argparse.ArgumentParser(description="StegnoZ privacy firewall")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--policy", default=os.environ.get("RAKSHA_POLICY", str(HERE / "config" / "policy.yaml")))
    risk = ap.add_mutually_exclusive_group()
    risk.add_argument("--strict-risk", dest="strict_risk", action="store_true", default=True,
                      help="withhold a release that misses the risk target (default)")
    risk.add_argument("--allow-risk-miss", dest="strict_risk", action="store_false",
                      help="explicitly publish the best candidate even if the risk target is missed (challenge scoring)")
    a = ap.parse_args()

    def _unquote(s: str) -> str:
        s = s.strip()
        if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
            s = s[1:-1]
        return s

    inp, out = Path(_unquote(a.input)).resolve(), Path(_unquote(a.output)).resolve()
    secret = env_secret()
    if not secret.strip():
        sys.stderr.write("[stegnoz] RAKSHA_SECRET is required\n")
        return 2
    if not inp.is_dir() or not any(iter_input(inp)):
        sys.stderr.write("[stegnoz] input must be a directory containing files\n")
        return 2
    if inp == out or inp in out.parents or out in inp.parents:
        sys.stderr.write("[stegnoz] input and output directories must be separate\n")
        return 2
    try:
        policy = load_policy(Path(a.policy))
        out.mkdir(parents=True, exist_ok=True)
        lock = out / ".stegnoz-running"
        lock.mkdir()
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"[stegnoz] could not start ({type(exc).__name__})\n")
        return 2
    t0 = time.time()
    exit_code = 0
    try:
        if any(path != lock for path in out.iterdir()):
            sys.stderr.write("[stegnoz] output directory must be empty\n")
            return 2
        with tempfile.TemporaryDirectory(dir=lock) as work:
            stage = Path(work)
            try:
                rep = Pipeline(inp, stage, secret, policy, strict_risk=a.strict_risk).run()
            except Exception as exc:
                sys.stderr.write(f"[stegnoz] pipeline failure ({type(exc).__name__}); files quarantined\n")
                exit_code = 1
            else:
                publish(stage, out)
        if exit_code:
            with tempfile.TemporaryDirectory(dir=lock) as work:
                stage = Path(work)
                _emergency_report(inp, stage, t0, "pipeline_failure")
                publish(stage, out)
            return exit_code
    except OSError as exc:
        sys.stderr.write(f"[stegnoz] could not publish release ({type(exc).__name__})\n")
        return 1
    finally:
        lock.rmdir()
    if not rep["privacy"]["target_met"]:
        sys.stderr.write("[stegnoz] final release risk target missed\n")
    c = rep["counts"]
    print(f"files {c['files_total']} sanitized {c['files_sanitized']} quarantined {c['files_quarantined']} "
          f"records {c['records_processed']} linked {c['records_linked']} time {rep['timing']['seconds']}s")
    return int(rep['privacy']['strict_blocked'])


if __name__ == "__main__":
    raise SystemExit(main())
