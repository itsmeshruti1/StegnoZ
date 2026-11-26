#!/usr/bin/env python3
"""Build a self-contained, offline Privacy Release dashboard (audit.html) from a run's
report.json + audit.json.  No external assets, no network, no PII (only aggregate counts).

Usage: python dashboard/build_dashboard.py --output out_dev [--dest out_dev/audit.html]

This is a presentation tool for the desk review / demo; it is NOT part of the scored runtime.
"""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

PII_TOKENS = re.compile(r"\[(?:NAME|RELATIVE|PATIENT|ADDRESS|HOUSE|LOCALITY|LANDMARK|VILLAGE)\]")

CSS = """
:root{--ink:#12263a;--acc:#0a7d6b;--acc2:#1d6fb8;--mut:#5b6b7b;--bg:#f4f8f7;--card:#fff;
--line:#dbe5e2;--good:#1a9e78;--warn:#d98b1f;--bad:#c6413a;--grid:#e8efed}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--ink:#e8eef2;--mut:#9fb0bd;
--bg:#0f1720;--card:#16202b;--line:#263340;--grid:#22303c}}
:root[data-theme=dark]{--ink:#e8eef2;--mut:#9fb0bd;--bg:#0f1720;--card:#16202b;--line:#263340;--grid:#22303c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;line-height:1.45}
.wrap{max-width:1080px;margin:0 auto;padding:24px 16px 60px}
header{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;border-bottom:2px solid var(--acc);
padding-bottom:12px;margin-bottom:20px}
h1{font-size:22px;margin:0;letter-spacing:-.3px}.tag{color:var(--mut);font-size:13px}
h2{font-size:14px;text-transform:uppercase;letter-spacing:.5px;color:var(--acc);margin:28px 0 12px}
.grid{display:grid;gap:14px}.kpis{grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.cards{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px}
.kpi .n{font-size:26px;font-weight:700;letter-spacing:-.5px}
.kpi .l{color:var(--mut);font-size:12px;margin-top:3px}
.kpi .s{font-size:11px;margin-top:6px}
.ok{color:var(--good)}.wn{color:var(--warn)}.bd{color:var(--bad)}
.bar{display:flex;align-items:center;gap:8px;margin:5px 0;font-size:12px}
.bar .lab{width:120px;color:var(--mut);text-align:right;flex:none}
.bar .track{flex:1;background:var(--grid);border-radius:4px;height:16px;overflow:hidden}
.bar .fill{height:100%;background:var(--acc);border-radius:4px}
.bar .val{width:54px;flex:none;font-variant-numeric:tabular-nums}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
th{color:var(--mut);font-weight:600;font-size:11px;text-transform:uppercase}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
tr.pick{background:color-mix(in srgb,var(--acc) 12%,transparent);font-weight:600}
.pill{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600}
.pill.g{background:color-mix(in srgb,var(--good) 18%,transparent);color:var(--good)}
.note{color:var(--mut);font-size:11.5px;margin-top:8px}
.foot{margin-top:34px;color:var(--mut);font-size:11px;border-top:1px solid var(--line);padding-top:12px}
svg{display:block;width:100%;height:auto}
.legend{display:flex;gap:14px;font-size:11px;color:var(--mut);margin-top:6px;flex-wrap:wrap}
.legend b{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
"""


def esc(s):
    return html.escape(str(s))


def bar(label, value, maxv, suffix="", color=None):
    w = 0 if not maxv else max(0.5, 100 * value / maxv)
    st = f'style="width:{w:.1f}%{";background:" + color if color else ""}"'
    return (f'<div class="bar"><div class="lab">{esc(label)}</div>'
            f'<div class="track"><div class="fill" {st}></div></div>'
            f'<div class="val">{esc(value)}{esc(suffix)}</div></div>')


def frontier_svg(frontier, base):
    """Privacy-utility scatter: utility (x) vs resistance=1-risk (y)."""
    W, H, pad = 460, 240, 36
    pts = []
    for f in frontier:
        util = f["utility"]
        res = 1 - f["risk"]
        chosen = (f["age_band"], f["location"], f["pin"]) == tuple(base)
        pts.append((util, res, chosen, f))
    if not pts:
        return ""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    xmin, xmax = min(xs + [0.4]), max(xs + [1.0])
    ymin, ymax = min(ys), max(ys + [1.0])
    xmin, xmax = (xmin - 0.02, xmax + 0.02)
    ymin, ymax = (ymin - 0.02, min(1.01, ymax + 0.02))

    def X(u):
        return pad + (u - xmin) / (xmax - xmin) * (W - 2 * pad)

    def Y(r):
        return H - pad - (r - ymin) / (ymax - ymin) * (H - 2 * pad)

    g = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="privacy versus utility frontier">']
    g.append(f'<line x1="{pad}" y1="{H-pad}" x2="{W-pad}" y2="{H-pad}" stroke="var(--line)"/>')
    g.append(f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{H-pad}" stroke="var(--line)"/>')
    # 0.40 utility coupling threshold
    if xmin <= 0.4 <= xmax:
        g.append(f'<line x1="{X(0.4):.1f}" y1="{pad}" x2="{X(0.4):.1f}" y2="{H-pad}" stroke="var(--warn)" '
                 f'stroke-dasharray="3 3" opacity="0.7"/>')
        g.append(f'<text x="{X(0.4)+3:.1f}" y="{pad+10}" font-size="9" fill="var(--warn)">utility floor 0.40</text>')
    for u, r, chosen, f in pts:
        c = "var(--acc)" if chosen else "var(--mut)"
        rad = 6 if chosen else 3.5
        g.append(f'<circle cx="{X(u):.1f}" cy="{Y(r):.1f}" r="{rad}" fill="{c}" '
                 f'{"stroke=\"var(--ink)\" stroke-width=\"1.5\"" if chosen else "opacity=\"0.6\""}>'
                 f'<title>age {f["age_band"]}y · {f["location"]} · PIN {f["pin"]} — utility {u:.2f}, resistance {r:.2f}</title></circle>')
    g.append(f'<text x="{W/2:.0f}" y="{H-6}" font-size="10" fill="var(--mut)" text-anchor="middle">information utility →</text>')
    g.append(f'<text x="12" y="{H/2:.0f}" font-size="10" fill="var(--mut)" text-anchor="middle" '
             f'transform="rotate(-90 12 {H/2:.0f})">attack resistance →</text>')
    g.append("</svg>")
    return "".join(g)


def build(out_dir: Path, dest: Path):
    report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    audit = json.loads((out_dir / "audit.json").read_text(encoding="utf-8"))
    c = report["counts"]
    ent = report.get("entities", {})
    pol = audit.get("policy", {})
    lk = audit.get("linkage", {})
    ver = audit.get("verification", {})
    exp = audit.get("exposure", {})
    qr = audit.get("quarantine_reasons", {})

    # group entity counts into readable families
    fam = {"Patient names": ent.get("PATIENT_NAME", 0), "Relative names": ent.get("RELATIVE_NAME", 0),
           "Other person names": ent.get("PERSON_NAME", 0), "Phones": ent.get("[PHONE]", 0),
           "Aadhaar / ABHA": ent.get("[AADHAAR]", 0) + ent.get("[ABHA]", 0),
           "Hospital record IDs": ent.get("[ID]", 0),
           "PAN / Insurance": ent.get("[PAN]", 0) + ent.get("[INSURANCE-ID]", 0),
           "Addresses & village": ent.get("[ADDRESS]", 0) + ent.get("[HOUSE]", 0) + ent.get("[LOCALITY]", 0)
           + ent.get("[LANDMARK]", 0) + ent.get("[VILLAGE]", 0) + ent.get("[PIN]", 0),
           "DOB / age (generalised)": ent.get("DOB", 0) + ent.get("AGE", 0),
           "Hidden-channel payloads": ent.get("HIDDEN_PAYLOAD", 0)}
    fam = {k: v for k, v in fam.items() if v}
    fmax = max(fam.values()) if fam else 1

    san_pct = 100 * c["files_sanitized"] / max(1, c["files_total"])
    link_pct = 100 * c["records_linked"] / max(1, c["records_processed"])

    H = []
    H.append(f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
             f'<meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<title>StegnoZ Privacy Release</title><style>{CSS}</style></head><body><div class="wrap">')
    H.append('<header><h1>StegnoZ &middot; Privacy Release Audit</h1>'
             '<span class="tag">offline, CPU-only, LLM-free &middot; aggregate evidence, no identities</span></header>')

    # KPIs
    H.append('<div class="grid kpis">')
    kpis = [
        (f'{c["files_sanitized"]}<span style="font-size:14px;color:var(--mut)">/{c["files_total"]}</span>',
         "files sanitised", f'{c["files_quarantined"]} quarantined', "ok"),
        (f'{c["records_processed"]:,}', "records processed", f'{c["records_linked"]:,} linked across records', ""),
        (f'{c["identifiers_detected"]:,}', "identifiers detected", "names, IDs, phones, locations", ""),
        (f'{exp.get("patients", pol.get("patients", 0))}', "profiles assessed", f'{pol.get("locally_recoded", 0)} local policy overrides', ""),
        (f'{report["timing"]["seconds"]}s', "run time", f'{report["resources"].get("peak_rss_mb", 0)} MB peak', "ok"),
        (f'{ver.get("residual_quarantined", 0)}', "files held by verification", f'{ver.get("residual_fixes", 0)} auto-corrected', "ok"),
    ]
    for n, l, s, cls in kpis:
        H.append(f'<div class="card kpi"><div class="n">{n}</div><div class="l">{esc(l)}</div>'
                 f'<div class="s {cls}">{esc(s)}</div></div>')
    H.append('</div>')

    H.append('<div class="grid cards">')

    # PII removed by family
    H.append('<div class="card"><h2>Identifier detections by category</h2>')
    for k, v in sorted(fam.items(), key=lambda kv: -kv[1]):
        H.append(bar(k, v, fmax, " hits"))
    H.append('<div class="note">Counts summarize matching rules. Multiple rules can match one occurrence.</div></div>')

    # Privacy-utility frontier
    H.append('<div class="card"><h2>Privacy–utility frontier</h2>')
    H.append(frontier_svg(pol.get("frontier", []), pol.get("base", [])))
    base = pol.get("base", [])
    H.append(f'<div class="legend"><span><b style="background:var(--acc)"></b>applied policy '
             f'({esc(base[0]) if base else "?"}-yr bands, {esc(base[1]) if len(base)>1 else "?"}, PIN {esc(base[2]) if len(base)>2 else "?"})</span>'
             f'<span><b style="background:var(--mut)"></b>other candidates</span></div>')
    H.append('<div class="note">The policy search compares candidates by modeled risk and utility. '
             'The final observed risk check uses the candidate release.</div></div>')

    # K-anonymity distribution
    ka = exp.get("k_anonymity", {})
    H.append('<div class="card"><h2>Re-identification exposure (k-anonymity)</h2>')
    kmax = max(ka.values()) if ka else 1
    colmap = {"1": "var(--bad)", "2-4": "var(--warn)", "5-9": "var(--acc)", "10+": "var(--good)"}
    labels = {"1": "unique (k=1)", "2-4": "k = 2–4", "5-9": "k = 5–9", "10+": "k ≥ 10"}
    for k in ("1", "2-4", "5-9", "10+"):
        H.append(bar(labels[k], ka.get(k, 0), kmax, " profiles", colmap[k]))
    H.append('<div class="note">Observed groups based on age band, gender, location, PIN, '
             'and other recognized facts in the candidate release. Unresolved records count separately.</div></div>')

    # Linkage quality
    H.append('<div class="card"><h2>Patient identity resolution</h2><table>')
    rows = [("Candidate pairs considered", lk.get("candidate_pairs", 0)),
            ("Links accepted", lk.get("accepted_edges", 0)),
            ("Merges rejected (cannot-link / homonym guard)", lk.get("rejected_merges", 0)),
            ("Fragment records re-attached", lk.get("fragment_links", 0)),
            ("Resolved patients (clusters)", lk.get("clusters", 0)),
            ("Records left unlinked (insufficient evidence)", exp.get("unlinked_records", 0))]
    for a, b in rows:
        H.append(f'<tr><td>{esc(a)}</td><td class="n">{esc(b)}</td></tr>')
    H.append('</table>')
    cs = exp.get("cluster_sizes", {})
    if cs:
        cmax = max(cs.values()) or 1
        H.append('<div style="margin-top:10px">')
        for k in ("1", "2-3", "4-6", "7+"):
            H.append(bar(f'{k} record(s)', cs.get(k, 0), cmax, " patients"))
        H.append('</div>')
    H.append('<div class="note">Cross-script Fellegi–Sunter linkage with EM-estimated weights; cannot-link '
             'constraints limit ambiguous merges.</div></div>')

    # Frontier table
    H.append('<div class="card"><h2>Candidate policies</h2><table>'
             '<tr><th>Age band</th><th>Location</th><th>PIN</th><th class="n">Risk</th><th class="n">Utility</th></tr>')
    for f in pol.get("frontier", []):
        pick = (f["age_band"], f["location"], f["pin"]) == tuple(pol.get("base", []))
        H.append(f'<tr class="{"pick" if pick else ""}"><td>{esc(f["age_band"])} yr</td>'
                 f'<td>{esc(f["location"])}</td><td>{esc(f["pin"])}</td>'
                 f'<td class="n">{f["risk"]:.3f}</td><td class="n">{f["utility"]:.2f}</td></tr>')
    risk = exp.get("singling_out_risk")
    target = pol.get("risk_target")
    status = "target met" if pol.get("target_met") else "target missed"
    detail = f"Candidate release {risk:.1%} · target {target:.1%} · {status}" if risk is not None and target is not None else "Final risk unavailable"
    H.append(f'</table><div class="note">{esc(detail)}</div></div>')

    # Verification + quarantine
    H.append('<div class="card"><h2>Verification &amp; quarantine</h2><table>')
    H.append(f'<tr><td>Quarantined by residual scan</td><td class="n">{ver.get("residual_quarantined", 0)}</td></tr>')
    H.append(f'<tr><td>Auto-corrected sanitisation fixes</td><td class="n">{ver.get("residual_fixes", 0)}</td></tr>')
    for reason, n in sorted(qr.items()):
        H.append(f'<tr><td>Quarantined: {esc(reason.replace("_", " "))}</td><td class="n">{n}</td></tr>')
    H.append('</table><div class="note">Unprocessable files are quarantined with a PII-free reason, never '
             'copied out raw. Secret, logs and temp files carry no identifiers.</div></div>')

    H.append('</div>')  # cards
    H.append('<div class="foot">Generated from report.json + audit.json of a StegnoZ run. '
             'No large language model, generative model or pretrained transformer is used. '
             'Figures summarize aggregate checks over the candidate release.</div>')
    H.append('</div></body></html>')
    out = "".join(H)

    # safety: this page must itself be leak-free
    leaks = PII_TOKENS.findall(out)
    assert not leaks, f"dashboard would contain redaction tokens: {leaks[:3]}"
    dest.write_text(out, encoding="utf-8")
    print("wrote", dest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True, help="a StegnoZ output folder (with report.json + audit.json)")
    ap.add_argument("--dest", default=None)
    a = ap.parse_args()
    out = Path(a.output)
    dest = Path(a.dest) if a.dest else out / "audit.html"
    build(out, dest)


if __name__ == "__main__":
    main()
