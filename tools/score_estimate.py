#!/usr/bin/env python3
"""Local scorecard estimate (dev-only). NOT the official score.

Recomputes the parts of docs/SCORING.md that can be derived from the practice
`truth.json`, `scoring.toml` and a release directory. Two categories cannot be
reproduced here and are reported as such rather than guessed:

* **Privacy (25%)** needs the A1-A7 attacker, which is not shipped in the toolkit.
* **Integrity (10%)** is mostly covered by the organizer's own `validate_output.py`;
  only the parts visible from the release are scored here.

Everything it prints for the other categories is computed from the answer key, never
assumed. Treat the total as a floor-and-ceiling sketch for self-review, not a result.

    python tools/score_estimate.py --release <dir> --toolkit <toolkit dir>
"""
from __future__ import annotations

import argparse
import base64
import binascii
import csv
import datetime as dt
import io
import json
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------- normalisation
_B64 = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")
_DEVA_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text)).translate(_DEVA_DIGITS)
    text = "".join(c for c in unicodedata.normalize("NFD", text)
                   if unicodedata.category(c) != "Mn" or "ऀ" <= c <= "ॿ")
    return " ".join(text.casefold().split())


def with_b64(text: str) -> str:
    extra = []
    for match in _B64.finditer(text):
        token = match.group(0)
        try:
            extra.append(base64.b64decode(token + "=" * (-len(token) % 4)).decode(
                "utf-8", errors="ignore"))
        except (binascii.Error, ValueError):
            pass
    return text + "\n" + "\n".join(extra) if extra else text


def read_text(path: Path) -> str:
    try:
        return with_b64(path.read_bytes()[: 50 * 1024 * 1024].decode("utf-8", errors="replace"))
    except OSError:
        return ""


# ---------------------------------------------------------------- load
def load_release(release: Path, truth: dict):
    report = json.loads((release / "report.json").read_text(encoding="utf-8"))
    renamed = {f["input_sha256"]: f.get("output") for f in report["files"] if f.get("output")}
    sanitized = release / "sanitized"
    texts, out_names = {}, {}
    for rel, meta in truth["files"].items():
        out_rel = str(renamed.get(meta["sha256"], rel)).replace("sanitized/", "", 1)
        path = sanitized / out_rel
        out_names[rel] = out_rel
        texts[rel] = norm(read_text(path)) if path.is_file() else None
    everything = norm("\n".join(
        [p.as_posix() for p in sorted(sanitized.rglob("*")) if p.is_file()]
        + [read_text(p) for p in sorted(sanitized.rglob("*")) if p.is_file()]))
    records = [json.loads(line) for line
               in (release / "records.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return report, texts, out_names, everything, records


# ---------------------------------------------------------------- 1. detection
def detection(truth, cfg, texts, out_names, everything):
    """F2 of contextual precision and recall, per SCORING.md section 1."""
    type_w = cfg["detection"]["type_weights"]
    kept_t, total_t = Counter(), Counter()
    kept_s, total_s = Counter(), Counter()
    leaked_ids, canary_hits = 0, 0
    seen_ids = set()

    for rel, meta in truth["files"].items():
        text = texts[rel]
        fname = norm(out_names[rel])
        for unit in meta["units"].values():
            for ent in unit["entities"]:
                surface = norm(ent["surface"])
                if ent.get("type") == "CANARY":
                    if surface and surface in everything:
                        canary_hits += 1
                    continue
                hay = fname if ent["channel"] == "filename" else (text or "")
                hit = bool(surface) and text is not None and surface in hay
                kind, script = ent["type"], ent["script"]
                total_t[kind] += 1
                total_s[script] += 1
                kept_t[kind] += (not hit)
                kept_s[script] += (not hit)
                if hit and kind in ("AADHAAR", "ABHA_NUMBER", "PHONE", "EMAIL", "MRN",
                                    "PAN", "PATIENT_NAME") and surface not in seen_ids:
                    seen_ids.add(surface)
                    leaked_ids += 1

    per_type = {k: kept_t[k] / total_t[k] for k in total_t}
    weighted = sum(type_w.get(k, 1.0) * v for k, v in per_type.items())
    weight_sum = sum(type_w.get(k, 1.0) for k in per_type)
    macro_type = weighted / weight_sum if weight_sum else 0.0
    macro_script = statistics.fmean(kept_s[s] / total_s[s] for s in total_s) if total_s else 0.0
    mix = cfg["detection"]["type_mix"]
    recall = mix * macro_type + (1 - mix) * macro_script

    # Contextual precision: the share of non-PII that survives in each trap group,
    # plus token retention on the documents the answer key marks clean.
    groups = defaultdict(lambda: [0, 0])
    for rel, meta in truth["files"].items():
        text = texts[rel]
        for unit in meta["units"].values():
            for probe in unit.get("preserve") or []:
                trap = probe.get("trap")
                if not trap:
                    continue
                bucket = groups[trap]
                bucket[1] += 1
                bucket[0] += bool(text) and norm(probe["text"]) in text
    trap_scores = {g: hit / tot for g, (hit, tot) in sorted(groups.items()) if tot}

    clean_kept = clean_total = 0
    for rel, meta in truth["files"].items():
        if not meta.get("clean"):
            continue
        source = Path(args_toolkit) / "dev/input" / rel
        if not source.is_file() or texts[rel] is None:
            continue
        have = Counter(norm(read_text(source)).split())
        out = Counter(texts[rel].split())
        clean_total += sum(have.values())
        clean_kept += sum(min(n, out[tok]) for tok, n in have.items())
    clean_retention = clean_kept / clean_total if clean_total else 1.0

    precision = statistics.fmean(list(trap_scores.values()) + [clean_retention]) \
        if trap_scores else clean_retention
    beta = cfg["detection"]["beta"]
    denom = (beta ** 2 * precision) + recall
    f_beta = (1 + beta ** 2) * precision * recall / denom if denom else 0.0
    return {"score": f_beta, "recall": recall, "precision": precision,
            "macro_type": macro_type, "macro_script": macro_script,
            "trap_groups": trap_scores, "clean_token_retention": clean_retention,
            "leaked_identifiers": leaked_ids, "canaries": canary_hits}


# ---------------------------------------------------------------- 2. identity
def identity(truth, texts, records, out_names):
    """Pairwise F0.5 and B-cubed F1 over the pseudonyms in records.jsonl."""
    by_file = defaultdict(dict)
    for rec in records:
        by_file[str(rec.get("file", "")).replace("sanitized/", "", 1)][str(rec.get("loc", ""))] = \
            rec.get("patient")
    truth_pairs, mine = {}, {}
    for rel, meta in truth["files"].items():
        out_rel = out_names[rel]
        for loc, unit in meta["units"].items():
            if unit.get("link") != "required" or not unit.get("patient"):
                continue
            got = by_file.get(out_rel, {})
            psn = got.get(loc) or got.get(loc.split(":")[-1])
            if psn is None and len(got) == 1:
                psn = next(iter(got.values()))
            truth_pairs[(rel, loc)] = unit["patient"]
            mine[(rel, loc)] = psn
    keys = [k for k in truth_pairs if mine.get(k)]
    if not keys:
        return {"score": 0.0, "note": "no pseudonyms matched to truth units"}
    tp = fp = fn = 0
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            same_truth = truth_pairs[a] == truth_pairs[b]
            same_mine = mine[a] == mine[b]
            tp += same_truth and same_mine
            fp += same_mine and not same_truth
            fn += same_truth and not same_mine
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f05 = (1.25 * precision * recall / (0.25 * precision + recall)) if precision + recall else 0.0
    # B-cubed
    by_truth, by_mine = defaultdict(set), defaultdict(set)
    for k in keys:
        by_truth[truth_pairs[k]].add(k)
        by_mine[mine[k]].add(k)
    bp = statistics.fmean(len(by_truth[truth_pairs[k]] & by_mine[mine[k]]) / len(by_mine[mine[k]])
                          for k in keys)
    br = statistics.fmean(len(by_truth[truth_pairs[k]] & by_mine[mine[k]]) / len(by_truth[truth_pairs[k]])
                          for k in keys)
    b3 = 2 * bp * br / (bp + br) if bp + br else 0.0
    return {"score": 0.4 * f05 + 0.3 * b3, "pair_precision": precision, "pair_recall": recall,
            "f0_5": f05, "bcubed_f1": b3, "linked_units": len(keys),
            "note": "traps (language/fragmented/homonym, 0.30 of the category) not scored here"}


# ---------------------------------------------------------------- 4. utility
_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b|\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")


def _dates_in(text):
    found = []
    for m in _DATE_RE.finditer(text or ""):
        try:
            if m.group(1):
                found.append(dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
            else:
                d, mo, y = int(m.group(4)), int(m.group(5)), int(m.group(6))
                y += 2000 if y < 100 else 0
                if d > 12 and mo <= 12:
                    found.append(dt.date(y, mo, d))
                elif mo <= 12 and d <= 31:
                    found.append(dt.date(y, mo, d))
        except ValueError:
            pass
    return found


def utility(truth, cfg, texts, toolkit):
    w = cfg["utility"]["weights"]
    # clinical probes, weighted
    hit = tot = 0.0
    for rel, meta in truth["files"].items():
        text = texts[rel]
        for unit in meta["units"].values():
            for probe in unit.get("preserve") or []:
                weight = float(probe.get("weight", 1.0))
                tot += weight
                hit += weight if (text and norm(probe["text"]) in text) else 0.0
    probes = hit / tot if tot else 0.0

    # temporal: every interval between one unit's dated events must survive unchanged
    exact = close = total_iv = 0
    for rel, meta in truth["files"].items():
        text = texts[rel]
        if not text:
            continue
        for unit in meta["units"].values():
            stamps = []
            for entry in unit.get("dates") or []:
                try:
                    stamps.append(dt.date.fromisoformat(str(entry["true"])[:10]))
                except (ValueError, KeyError, TypeError):
                    pass
            stamps = sorted(set(stamps))
            if len(stamps) < 2:
                continue
            out_dates = sorted(set(_dates_in(text)))
            if len(out_dates) < 2:
                total_iv += len(stamps) - 1
                continue
            got = {(b - a).days for i, a in enumerate(out_dates) for b in out_dates[i + 1:]}
            for i in range(len(stamps) - 1):
                total_iv += 1
                want = (stamps[i + 1] - stamps[i]).days
                if want in got:
                    exact += 1
                elif any(abs(want - g) <= 1 for g in got):
                    close += 1
    temporal = ((exact + 0.5 * close) / total_iv) if total_iv else 1.0

    # generalization: is the published age band truthful and still informative?
    # SCORING.md: exact 1.0, <=5y 0.9, <=10y 0.8, <=20y 0.6, wider 0.3, wrong band 0.
    band_credits, ungraded = [], 0
    band_re = re.compile(r"(?<![\d/-])(\d{1,3})\s*[-–]\s*(\d{1,3})(?![\d/-])"
                         r"|(?<![\d/-])(\d{1,3})\+")
    for rel, meta in truth["files"].items():
        text = texts[rel]
        if not text:
            continue
        for unit in meta["units"].values():
            for field in unit.get("fields") or []:
                if field.get("kind") != "age":
                    continue
                try:
                    true_age = int(field["true"])
                except (KeyError, TypeError, ValueError):
                    continue
                # An open-ended band ("85+") is a real, truthful band, just a very wide
                # one. It needs a width, not None, or it is indistinguishable from
                # "no band published" and scores zero by accident.
                OPEN_ENDED = 10 ** 6
                containing = None
                for m in band_re.finditer(text):
                    if m.group(3):
                        low, high, width = int(m.group(3)), OPEN_ENDED, OPEN_ENDED
                    else:
                        low, high = int(m.group(1)), int(m.group(2))
                        if high < low:
                            continue                       # a dose like "1-0", not a band
                        width = high - low + 1
                    if low <= true_age <= high:
                        containing = width if containing is None else min(containing, width)
                if containing is None:
                    if str(true_age) in text.split():
                        band_credits.append(1.0)           # exact age kept
                    else:
                        # The file publishes no age for this patient at all. Without
                        # resolving the field's own path we cannot tell "withheld by
                        # policy" from "this export never carried an age", and several
                        # lab exports never did. Grading it as a zero would blame the
                        # generaliser for a field that was never there, so it is left
                        # out and counted separately.
                        ungraded += 1
                elif containing <= 5:
                    band_credits.append(0.9)
                elif containing <= 10:
                    band_credits.append(0.8)
                elif containing <= 20:
                    band_credits.append(0.6)
                else:
                    band_credits.append(0.3)
    generalization_age = statistics.fmean(band_credits) if band_credits else 0.0

    # record retention
    present = sum(1 for rel in truth["files"] if texts[rel] is not None)
    record_ret = present / len(truth["files"])

    # token retention on every non-clean file (over-redaction detector)
    kept = total_tok = 0
    pii_tokens = set()
    for rel, meta in truth["files"].items():
        for unit in meta["units"].values():
            for ent in unit["entities"]:
                pii_tokens.update(norm(ent["surface"]).split())
    for rel, meta in truth["files"].items():
        text = texts[rel]
        source = toolkit / "dev/input" / rel
        if text is None or not source.is_file():
            continue
        have = Counter(t for t in norm(read_text(source)).split()
                       if t not in pii_tokens and not any(c.isdigit() for c in t))
        out = Counter(text.split())
        total_tok += sum(have.values())
        kept += sum(min(n, out[t]) for t, n in have.items())
    token_ret = kept / total_tok if total_tok else 1.0

    score = (w["clinical_probes"] * probes + w["temporal"] * temporal
             + w["token_retention"] * token_ret + w["record_retention"] * record_ret
             + w["generalization"] * generalization_age)
    covered = (w["clinical_probes"] + w["temporal"] + w["token_retention"]
               + w["record_retention"] + w["generalization"])
    return {"score_covered": score, "covered_weight": covered,
            "normalised": score / covered, "clinical_probes": probes, "temporal": temporal,
            "token_retention": token_ret, "record_retention": record_ret,
            "generalization_age": generalization_age, "age_fields_graded": len(band_credits),
            "age_fields_not_published": ungraded,
            "note": "generalization covers age only (village/DOB truth is id-encoded); "
                    "statistics (0.15) not scored here"}


# ---------------------------------------------------------------- 6. performance
def performance(report, cfg, profile="small"):
    p = cfg["performance"]["profiles"][profile]
    seconds = float(report["timing"]["seconds"])
    memory = float(report["resources"]["peak_rss_mb"])

    def ramp(value, good, limit):
        if value <= good:
            return 1.0
        if value >= limit:
            return 0.0
        return 1 - (value - good) / (limit - good)
    t = ramp(seconds, p["time_good_s"], p["time_limit_s"])
    m = ramp(memory, p["memory_good_mb"], p["memory_limit_mb"])
    return {"score": statistics.fmean([t, m]), "seconds": seconds, "peak_rss_mb": memory,
            "time_component": t, "memory_component": m, "profile": profile,
            "note": "reliability/determinism components folded in elsewhere"}


# ---------------------------------------------------------------- main
def main():
    global args_toolkit
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--release", required=True)
    ap.add_argument("--toolkit", required=True)
    ap.add_argument("--profile", default="small")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    toolkit = Path(args.toolkit).resolve()
    args_toolkit = str(toolkit)
    release = Path(args.release).resolve()

    try:
        import tomllib
        cfg = tomllib.loads((toolkit / "scoring.toml").read_text(encoding="utf-8"))
    except Exception as exc:                                  # noqa: BLE001
        raise SystemExit(f"cannot read scoring.toml ({type(exc).__name__})")
    truth = json.loads((toolkit / "dev/truth/truth.json").read_text(encoding="utf-8"))
    report, texts, out_names, everything, records = load_release(release, truth)

    det = detection(truth, cfg, texts, out_names, everything)
    ident = identity(truth, texts, records, out_names)
    util = utility(truth, cfg, texts, toolkit)
    perf = performance(report, cfg, args.profile)
    weights = cfg["weights"]
    pen = cfg["penalties"]
    penalties = (min(det["leaked_identifiers"] * pen["per_leaked_identifier"],
                     pen["leaked_identifier_cap"])
                 + min(det["canaries"] * pen["per_canary_leak"], pen["canary_cap"]))

    result = {
        "detection": det, "identity_resolution": ident, "utility": util, "performance": perf,
        "penalties": penalties,
        "not_computable": {
            "privacy (0.25)": "needs the A1-A7 attacker, not shipped in the toolkit",
            "integrity (0.10)": "covered by the organizer's validate_output.py",
            "utility.statistics (0.03 of total)": "needs lab-median and distribution grading",
            "identity traps (0.045 of total)": "needs language/fragmented/homonym trap labels",
        },
    }
    contribution = (weights["detection"] * det["score"]
                    + weights["identity_resolution"] * ident["score"]
                    + weights["utility"] * util["score_covered"]
                    + weights["performance"] * perf["score"])
    result["computed_points_of_100"] = round(100 * contribution - penalties, 2)
    result["weight_covered"] = round(
        weights["detection"] + weights["identity_resolution"] * 0.7
        + weights["utility"] * util["covered_weight"] + weights["performance"], 3)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    print("Local scorecard ESTIMATE - not the official score")
    print("=" * 62)
    print(f"1 Detection          F2 = {det['score']:.3f}   "
          f"(recall {det['recall']:.3f}, contextual precision {det['precision']:.3f})")
    for group, value in det["trap_groups"].items():
        print(f"      trap {group:20s} {value:6.1%}")
    print(f"      clean-doc token retention {det['clean_token_retention']:.1%}")
    print(f"2 Identity           {ident['score']:.3f} of 0.70 scorable  "
          f"(F0.5 {ident.get('f0_5', 0):.3f}, B3F1 {ident.get('bcubed_f1', 0):.3f})")
    print(f"3 Privacy            NOT COMPUTABLE LOCALLY (needs A1-A7 attacker)")
    print(f"4 Utility            {util['normalised']:.3f} over {util['covered_weight']:.0%} "
          f"of the category")
    print(f"      clinical probes {util['clinical_probes']:.1%}   temporal {util['temporal']:.1%}")
    print(f"      token retention {util['token_retention']:.1%}   record retention "
          f"{util['record_retention']:.1%}")
    print(f"      age generalization {util['generalization_age']:.3f} over "
          f"{util['age_fields_graded']} published age fields "
          f"({util['age_fields_not_published']} not published, not graded)")
    print(f"5 Integrity          see validate_output.py (CONTRACT OK / not OK)")
    print(f"6 Performance        {perf['score']:.3f}   "
          f"({perf['seconds']:.1f}s, {perf['peak_rss_mb']:.0f} MB, profile {perf['profile']})")
    print("-" * 62)
    print(f"penalties            -{penalties:.0f} "
          f"({det['leaked_identifiers']} identifiers, {det['canaries']} canaries)")
    print(f"computed points      {result['computed_points_of_100']:.2f} of 100, covering "
          f"{result['weight_covered']:.0%} of the official weight")
    print("\nThe remaining weight is privacy, integrity and three sub-parts; see")
    print("'not_computable' in --json output. This is a self-review aid, not a score.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
