#!/usr/bin/env python3
"""Inspect a release's recorded risk and pseudonym consistency locally."""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from stegnoz.ingest import _sniff_delimiter
from stegnoz.pipeline import get_ptr


def inspect_release(out):
    sanitized = (out / "sanitized").resolve()

    @lru_cache(maxsize=32)
    def load(path, csv_record, is_json):
        text = path.read_text(encoding="utf-8")
        if csv_record:
            delimiter = _sniff_delimiter(text, path.suffix.lower())
            return list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
        return json.loads(text) if is_json else text

    counts = dict(records=0, unresolved=0, inaccessible=0, missing_pseudonym=0)
    with (out / "records.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            counts["records"] += 1
            patient = record["patient"]
            if patient is None:
                counts["unresolved"] += 1
            loc = record.get("out", record["loc"])
            path = (out / record["file"]).resolve()
            try:
                if not path.is_relative_to(sanitized):
                    raise ValueError("path outside release")
                value = load(path, loc.startswith("row:"), loc.startswith("/"))
                if loc.startswith("row:"):
                    index = int(loc[4:])
                    if index < 0:
                        raise ValueError("invalid source row")
                    value = value[index + 1]
                elif loc.startswith("/"):
                    value = get_ptr(value, loc)
                elif loc != "doc":
                    raise ValueError("unsupported locator")
            except (OSError, ValueError, IndexError, TypeError, KeyError):
                counts["inaccessible"] += 1
                continue
            if patient and patient not in json.dumps(value, ensure_ascii=False):
                counts["missing_pseudonym"] += 1
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output
    result = inspect_release(output)
    audit = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    print(json.dumps({"manifest": result, "release_risk_proxy": audit["exposure"]["singling_out_risk"],
                      "target_met": audit["policy"]["target_met"]}, indent=2))
    return int(bool(result["inaccessible"] or result["missing_pseudonym"]))


if __name__ == "__main__":
    raise SystemExit(main())
