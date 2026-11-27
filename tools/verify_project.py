"""Reproduce local and organizer checks. Run after installing dev requirements.

python tools/verify_project.py --toolkit /path/to/Secret-Wards-ToolKit --output /empty/path
On Linux, run this under unshare --user --map-root-user --net for offline verification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]


def digests(directory):
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob("*")) if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolkit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    toolkit, work = args.toolkit.resolve(), args.output.resolve()
    if work.exists() and any(work.iterdir()):
        parser.error("verification output must be empty")
    work.mkdir(parents=True, exist_ok=True)
    inp = toolkit / "dev/input"
    before = digests(inp)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8",
               RAKSHA_SECRET="synthetic-verification-key")
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    limits = {}
    if sys.platform == "linux":
        import resource
        cpus = sorted(os.sched_getaffinity(0))[:2]
        os.sched_setaffinity(0, cpus)
        resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
        limits = {"cpus": cpus, "address_space_bytes": 4 * 1024**3}
    results = {}
    def run(label, command, marker=None, expected=0):
        start = time.monotonic()
        process = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                 text=True, encoding="utf-8", timeout=900)
        output = process.stdout + process.stderr
        (work / (label + ".log")).write_text(output, encoding="utf-8")
        passed = process.returncode == expected and (marker is None or marker in output)
        results[label] = {"passed": passed, "exit_code": process.returncode,
                          "seconds": round(time.monotonic() - start, 3)}
        print(label, "PASS" if passed else "FAIL", flush=True)
        return output

    def practice_check(label, release, truth=None):
        command = py + [str(toolkit / "check_dev.py"), "--output", str(release)]
        if truth:
            command += ["--truth", str(truth)]
        output = run(label, command)
        patterns = {
            "identifiers": r"PERSONAL DATA: (\d+) of (\d+)",
            "canaries": r"CANARIES: (\d+) of (\d+)",
            "medical": r"MEDICAL DATA KEPT: (\d+) of (\d+)",
            "linkage": r"PATIENT LINKING: precision ([\d.]+), recall ([\d.]+), F0.5 ([\d.]+)",
        }
        metrics = {name: [float(v) for v in match.groups()] for name, pattern in patterns.items()
                   if (match := re.search(pattern, output))}
        results[label]["metrics"] = metrics
        results[label]["passed"] &= (len(metrics) == len(patterns)
            and metrics["identifiers"][0] == metrics["canaries"][0] == 0
            and metrics["medical"][0] == metrics["medical"][1] > 0
            and metrics["linkage"][0] == 1.0)
        if not results[label]["passed"]:
            print(label, "METRICS FAIL", flush=True)

    py = [sys.executable, "-B"]
    run("regressions", py + ["-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"])
    release = work / "release"
    run("practice_run", py + ["main.py", "--input", str(inp), "--output", str(release), "--allow-risk-miss"])
    run("contract", py + [str(toolkit / "validate_output.py"), "--input", str(inp), "--output", str(release)], "CONTRACT OK")
    practice_check("practice_check", release)
    run("submission", py + [str(toolkit / "check_submission.py"), "--repo", str(ROOT), "--run"], "READY TO SUBMIT")
    mutated = work / "mutated/input"
    mutated_truth = work / "mutated/truth/truth.json"
    run("mutate", py + ["tools/mutate_dataset.py", str(inp), str(mutated),
                        "--truth", str(toolkit / "dev/truth/truth.json"), "--truth-output", str(mutated_truth)])
    mutated_release = work / "mutated_release"
    run("mutated_run", py + ["main.py", "--input", str(mutated), "--output", str(mutated_release), "--allow-risk-miss"])
    run("mutated_contract", py + [str(toolkit / "validate_output.py"), "--input", str(mutated), "--output", str(mutated_release)], "CONTRACT OK")
    practice_check("mutated_check", mutated_release, mutated_truth)
    # The fail-closed default must PUBLISH on the practice data: since the risk model
    # measures the attacker's join surface rather than release-internal uniqueness, the
    # target is met without --allow-risk-miss. An exit of 1 here would mean the release
    # was withheld again, which is a regression worth catching.
    strict_release = work / "strict_release"
    run("strict_run", py + ["main.py", "--input", str(inp), "--output", str(strict_release)], expected=0)
    run("strict_contract", py + [str(toolkit / "validate_output.py"), "--input", str(inp),
                                 "--output", str(strict_release)], "CONTRACT OK")
    practice_check("strict_check", strict_release, toolkit / "dev/truth/truth.json")
    results["input_unchanged"] = {"passed": before == digests(inp)}
    summary = {"python": sys.version, "platform": platform.platform(), "limits": limits,
               "checks": results, "passed": all(r["passed"] for r in results.values())}
    (work / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
