"""Local StegnoZ research explorer. Patient-level records never leave this process."""
from __future__ import annotations

import argparse
import csv
import io
import json
import random
import re
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

STATIC = Path(__file__).parent / "research"
CONDITIONS = {"Diabetes": r"diabet|E11", "Hypertension": r"hypertension|I10",
              "Dengue": r"dengue|A90", "Asthma": r"asthma|J45",
              "Tuberculosis": r"tuberculosis|A15", "Typhoid": r"typhoid|A01"}
AGES = ["0–19", "20–39", "40–59", "60–79", "80+", "Unknown"]
SEXES = ["Female", "Male", "Unknown"]
MIN_CELL = 5


def demo_records():
    rng = random.Random(42)
    rows = []
    for patient in range(480):
        age = rng.choices(AGES[:-1], [10, 24, 35, 25, 6])[0]
        sex = rng.choice(SEXES[:2])
        for observation in range(2):
            condition = rng.choices(list(CONDITIONS), [26, 28, 18, 13, 8, 7])[0]
            rows.append({"patient": f"demo-{patient}", "condition": condition,
                         "age": age, "sex": sex,
                         "source": f"Source {(patient * 2 + observation) % 4 + 1}"})
    return rows


def flatten(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                yield from flatten(child)
            else:
                yield str(key).lower(), str(child)
    elif isinstance(value, list):
        for child in value:
            yield from flatten(child)


def normalize(value, patient, source):
    fields = list(flatten(value))
    text = json.dumps(value, ensure_ascii=False)
    conditions = [name for name, pattern in CONDITIONS.items() if re.search(pattern, text, re.I)]
    age, sex = "Unknown", "Unknown"
    for key, val in fields:
        if key in {"sex", "gender", "लिंग"}:
            sex = {"f": "Female", "female": "Female", "महिला": "Female", "m": "Male", "male": "Male", "पुरुष": "Male"}.get(val.lower(), "Unknown")
        if key in {"age", "age_band", "age band", "आयु"}:
            nums = re.findall(r"\d+", val)
            if nums and len(nums) <= 2:
                lo, hi = int(nums[0]), int(nums[-1])
                for label, lower, upper in [("0–19", 0, 19), ("20–39", 20, 39), ("40–59", 40, 59), ("60–79", 60, 79), ("80+", 80, 130)]:
                    if lower <= lo <= hi <= upper:
                        age = label
    return [{"patient": patient, "condition": condition, "age": age, "sex": sex, "source": source}
            for condition in conditions or ["Unclassified"]]


def load_release(root):
    root = root.resolve()
    report = json.loads((root / "report.json").read_text("utf-8"))
    if report.get("privacy", {}).get("strict_blocked"):
        raise ValueError("This release was withheld by the privacy policy.")
    approved = {f["output"] for f in report["files"] if f["status"] == "sanitized" and f.get("output")}
    cache, rows = {}, []
    sources = {name: f"Source {i + 1}" for i, name in enumerate(sorted(approved))}
    for line in (root / "records.jsonl").read_text("utf-8").splitlines():
        item = json.loads(line)
        name, loc = item["file"], item["loc"]
        path = (root / name).resolve()
        if name not in approved or not path.is_relative_to(root / "sanitized"):
            raise ValueError("Manifest refers to an unapproved release file.")
        if name not in cache:
            if path.suffix.lower() in {".csv", ".tsv"}:
                cache[name] = list(csv.DictReader(io.StringIO(path.read_text("utf-8-sig")), delimiter="\t" if path.suffix.lower() == ".tsv" else ","))
            elif path.suffix.lower() == ".json":
                cache[name] = json.loads(path.read_text("utf-8"))
            else:
                cache[name] = path.read_text("utf-8")
        value = cache[name]
        if loc.startswith("row:"):
            value = value[int(loc[4:])]
        elif loc.startswith("/"):
            for part in loc[1:].split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                value = value[int(part)] if isinstance(value, list) else value[part]
        rows.extend(normalize(value, item.get("patient") or f"unlinked-{len(rows)}", sources[name]))
    return rows, {"mode": "release", "title": "StegnoZ sanitized release",
                  "privacy_target_met": report.get("privacy", {}).get("target_met"),
                  "files": len(approved), "records_processed": report.get("counts", {}).get("records_processed")}


def query(rows, params):
    selected = {key: params.get(key, "All") for key in ("condition", "age", "sex", "source")}
    allowed = {"condition": list(CONDITIONS) + ["Unclassified"], "age": AGES, "sex": SEXES,
               "source": sorted({row["source"] for row in rows})}
    for key, val in selected.items():
        if val != "All" and val not in allowed[key]:
            raise ValueError(f"Select a valid {key} filter.")
    question = params.get("question", "")
    if not isinstance(question, str) or len(question) > 500:
        raise ValueError("Keep the research question under 500 characters.")
    question = question.strip()
    if question:
        terms = [name for name, pattern in CONDITIONS.items() if re.search(pattern, question, re.I)]
        if len(terms) > 1:
            raise ValueError("Explore one condition at a time using the condition filter.")
        if terms:
            selected["condition"] = terms[0]
        if re.search(r"\b(female|women)\b", question, re.I):
            selected["sex"] = "Female"
        elif re.search(r"\b(male|men)\b", question, re.I):
            selected["sex"] = "Male"
        bands = re.findall(r"\b(0|20|40|60)[–-](19|39|59|79)\b", question)
        if bands:
            selected["age"] = "–".join(bands[0])
            if selected["age"] not in AGES:
                raise ValueError("Choose a supported age band.")
        recognized = re.sub(r"\b(show|me|all|compare|the|a|an|of|by|with|and|in|for|patients?|records?|cohorts?|distribution|conditions?|age|ages|sex|gender|female|women|male|men|across|sources?|diabetes|diabetic|hypertension|hypertensive|dengue|asthma|tuberculosis|typhoid)\b|\d+[–-]\d+|[?. ,]", "", question, flags=re.I)
        if recognized.strip():
            raise ValueError("Use a supported question such as ‘Show women with diabetes’ or use the filters. Supported fields are condition, sex, and age bands 0–19, 20–39, 40–59, 60–79.")
    result = [row for row in rows if all(val == "All" or row[key] == val for key, val in selected.items())]
    patients = len({row["patient"] for row in result})
    suppressed = 0 < patients < MIN_CELL
    distributions = {}
    for key in ("condition", "age", "sex", "source"):
        groups = {}
        for row in result:
            groups.setdefault(row[key], set()).add(row["patient"])
        small = any(len(ids) < MIN_CELL for ids in groups.values())
        # Suppress the full breakdown when any cell is small to prevent subtraction disclosure.
        distributions[key] = [] if small or suppressed else [{"label": label, "count": len(ids)} for label, ids in sorted(groups.items(), key=lambda x: -len(x[1]))]
    return {"filters": selected, "patients": None if suppressed else patients, "suppressed": suppressed,
            "distributions": distributions, "minimum_cell": MIN_CELL,
            "note": f"Counts are distinct linked profiles within each group. Profiles may appear in multiple groups. Unlinked records count separately. Breakdowns containing fewer than {MIN_CELL} profiles are withheld. Repeated-query privacy is not guaranteed."}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, content, mime="application/json"):
        body = json.dumps(content).encode() if mime == "application/json" else content
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                         "style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; "
                         "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/catalog":
            self.respond(200, {**self.server.metadata, "conditions": list(CONDITIONS) + ["Unclassified"], "ages": AGES, "sexes": SEXES,
                               "sources": sorted({row["source"] for row in self.server.rows})})
            return
        # Retain older shared cohort URLs that used the root route.
        if path == "/" and urlsplit(self.path).query:
            self.send_response(302)
            self.send_header("Location", "/dashboard?" + urlsplit(self.path).query)
            self.end_headers()
            return
        paths = {"/": ("landing.html", "text/html; charset=utf-8"),
                 "/dashboard": ("index.html", "text/html; charset=utf-8"),
                 "/dashboard/": ("index.html", "text/html; charset=utf-8"),
                 "/reference.css": ("reference.css", "text/css"),
                 "/reference-fonts.css": ("reference-fonts.css", "text/css"),
                 "/reference-dashboard.css": ("reference-dashboard.css", "text/css"),
                 "/reference-dashboard.js": ("reference-dashboard.js", "text/javascript; charset=utf-8"),
                 "/reference-landing.js": ("reference-landing.js", "text/javascript; charset=utf-8"),
                 "/three.min.js": ("three.min.js", "text/javascript; charset=utf-8"),
                 "/ScrollTrigger.min.js": ("ScrollTrigger.min.js", "text/javascript; charset=utf-8"),
                 "/gsap.min.js": ("gsap.min.js", "text/javascript; charset=utf-8"),
                 "/stegnoz-mark.svg": ("stegnoz-mark.svg", "image/svg+xml")}
        for family in ("Geist", "Space-Grotesk", "Fraunces", "Material-Symbols-Outlined"):
            paths[f"/fonts/{family}.woff2"] = (f"fonts/{family}.woff2", "font/woff2")
        if path not in paths:
            self.respond(404, {"error": "Page not found"})
            return
        name, mime = paths[path]
        self.respond(200, (STATIC / name).read_bytes(), mime)

    def do_POST(self):
        if self.path != "/api/query":
            self.respond(404, {"error": "Endpoint not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("Query body must be between 1 and 4096 bytes.")
            params = json.loads(self.rfile.read(length))
            if not isinstance(params, dict):
                raise ValueError("Provide a query object.")
            self.respond(200, query(self.server.rows, params))
        except (ValueError, TypeError, AttributeError):
            self.respond(400, {"error": "Use condition, sex, and age-band filters, or a supported question such as ‘Show women with diabetes’. Queries support one condition at a time."})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, help="Pipeline output folder with report.json and records.jsonl")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if args.release and not args.release.is_dir():
        parser.error("--release must point to an existing pipeline output directory")
    rows, metadata = load_release(args.release) if args.release else (demo_records(), {"mode": "demo", "title": "Synthetic research sandbox", "files": 4, "privacy_target_met": None})
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.rows, server.metadata = rows, metadata
    print(f"StegnoZ Research http://127.0.0.1:{args.port} ({metadata['mode']})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStegnoZ Research stopped.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
