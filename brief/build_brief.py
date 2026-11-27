"""Build the StegnoZ two-page Track 3 project brief matching the submission requirements."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import pypdf

INK = colors.HexColor("#111827")
ACCENT = colors.HexColor("#1D4ED8")
MUTED = colors.HexColor("#4B5563")
LINE = colors.HexColor("#E5E7EB")
PALE = colors.HexColor("#F8FAFC")
PALE_BLUE = colors.HexColor("#EFF6FF")

BODY = ParagraphStyle("Body", fontName="Helvetica", fontSize=9.2, leading=12.5,
                      textColor=INK, spaceAfter=5)
SMALL = ParagraphStyle("Label", parent=BODY, fontSize=8.2, leading=10.5, textColor=MUTED, spaceAfter=2)
EYEBROW = ParagraphStyle("Eyebrow", parent=SMALL, fontName="Helvetica-Bold", fontSize=8.0,
                         leading=9.5, textColor=ACCENT, spaceAfter=2)
HEADING = ParagraphStyle("Heading", fontName="Helvetica-Bold", fontSize=11.5, leading=14.5,
                         textColor=ACCENT, spaceBefore=5, spaceAfter=3)
TITLE = ParagraphStyle("Title", fontName="Helvetica-Bold", fontSize=23, leading=26,
                       textColor=INK, spaceAfter=3)
SUBTITLE = ParagraphStyle("Subtitle", parent=BODY, fontName="Helvetica", fontSize=10.5,
                          leading=13.5, textColor=MUTED, spaceAfter=4)
TABLE = ParagraphStyle("Table text", parent=BODY, fontSize=8.2, leading=10.5, spaceAfter=0)
TABLE_HEAD = ParagraphStyle("Table head", parent=TABLE, fontName="Helvetica-Bold",
                            textColor=colors.white)
FLOW = ParagraphStyle("Flow", parent=TABLE, fontName="Helvetica-Bold", textColor=ACCENT, alignment=1)
FLOW_SUB = ParagraphStyle("FlowSub", parent=TABLE, fontSize=7.2, leading=8.5, textColor=MUTED, alignment=1)


def grid(rows, widths, header=False):
    table = Table(rows, colWidths=[width * mm for width in widths], hAlign="LEFT")
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [PALE, colors.white]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), ACCENT))
    table.setStyle(TableStyle(style))
    return table


def footer(canvas, document):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(15 * mm, 12 * mm, 195 * mm, 12 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(15 * mm, 8 * mm, "StegnoZ | Yugaantar DevForge Track 3 (Secret Wards) | Harshit Agarwalla & Shruti Talikoti")
    canvas.drawRightString(195 * mm, 8 * mm, f"Page {document.page} of 2")
    canvas.restoreState()


def build(path=None):
    destination = Path(path) if path else Path.home() / "Desktop" / "StegnoZ_Project_Brief.pdf"
    doc = SimpleDocTemplate(str(destination), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=16 * mm, title="StegnoZ 2-Page Project Brief",
                            author="Harshit Agarwalla and Shruti Talikoti")
    story = [
        # PAGE 1
        Paragraph("YUGAANTAR DEVFORGE / TRACK 3 / SECRET WARDS", EYEBROW),
        Paragraph("StegnoZ", TITLE),
        Paragraph("Offline Deterministic Privacy Firewall & Longitudinal Health Record Engine", SUBTITLE),
        Paragraph("<b>Team</b> Harshit Agarwalla and Shruti Talikoti &nbsp;&nbsp;|&nbsp;&nbsp; "
                  "<b>Repository</b> <link href='https://github.com/itsmeshruti1/StegnoZ' color='#1D4ED8'>"
                  "github.com/itsmeshruti1/StegnoZ</link>", SMALL),
        Spacer(1, 2 * mm),
        
        Paragraph("1. Unique Selling Proposition (USP)", HEADING),
        Paragraph("StegnoZ is an offline, CPU-only clinical de-identification firewall built specifically for heterogeneous Indian electronic health records (EHRs) across Latin, Devanagari Hindi, and Hinglish:", BODY),
        Paragraph("• <b>Multilingual & Cross-Script by Construction:</b> Rule-based phonetic normalisation equates cross-script name spellings (रीना / Reena / Rina) and kinship markers (S/o, D/o, W/o, पुत्र, आत्मज) without LLMs or cloud APIs.<br/>"
                  "• <b>Identity-Aware Longitudinal Consistency:</b> Cross-file entity resolution resolves patients before pseudonymisation. One patient receives a single deterministic HMAC-SHA256 pseudonym and a single secret date shift, ensuring 100% longitudinal interval accuracy (stays, readmission times) while defeating cross-release linkability.<br/>"
                  "• <b>Reverse Privacy Engine with Lattice Search:</b> Evaluates an exhaustive generalisation lattice (Age 5/10/20 × Location Tehsil/District × PIN Prefix/Drop) on authenticated encrypted candidates. It achieves <b>0.00% singling-out risk</b> ($k \\ge 5$) while applying Mondrian local recoding with district preservation to avoid degrading clinical utility.<br/>"
                  "• <b>Zero-Trust Fail-Closed Security:</b> Ephemeral AES-256-GCM authenticated staging spools withhold records if the risk target is missed, preventing catastrophic privacy exposure.", BODY),
        Spacer(1, 2 * mm),

        Paragraph("2. System Architecture", HEADING),
        grid([[
            [Paragraph("01: INGEST", FLOW), Paragraph("CSV, JSON, FHIR R4, notes; encoding sniffer", FLOW_SUB)],
            [Paragraph("02: DETECT", FLOW), Paragraph("Context rules, checksums, Devanagari transliteration", FLOW_SUB)],
            [Paragraph("03: LINK", FLOW), Paragraph("Cross-script Fellegi-Sunter EM agreement scoring", FLOW_SUB)],
            [Paragraph("04: PROTECT", FLOW), Paragraph("Lattice search, Mondrian recode, keyed date shifts", FLOW_SUB)],
            [Paragraph("05: VERIFY", FLOW), Paragraph("Residual leak scan, FHIR pointer checks, AES staging", FLOW_SUB)],
            [Paragraph("06: EXPORT", FLOW), Paragraph("sanitized/, records.jsonl, report.json, audit.json", FLOW_SUB)],
        ]], [30, 30, 30, 30, 30, 30]),
        Spacer(1, 2 * mm),

        Paragraph("3. Technical Approach", HEADING),
        Paragraph("• <b>Contextual Entity Disambiguation:</b> Prevents false-positive destruction of critical medical data. Medical eponyms (<i>Parkinson's disease</i>, <i>Hashimoto thyroiditis</i>) and attending clinicians (<i>Dr. Alok Nath</i>) are preserved; chief complaints (<i>C/O fever</i>) are distinguished from relatives (<i>C/O Suresh</i>); and pharmaceutical dosages (<i>Ramipril 5 mg OD</i>) are protected from numeric phone scrubbers.<br/>"
                  "• <b>Cross-Script Fellegi-Sunter Record Linkage:</b> Computes log-likelihood agreement weights $w_i = \\log_2(m_i / u_i)$ across blocked candidate pairs using Indic phonetic keys, scoped hospital MRNs, and national ID tokens. Hard conflict guards prevent erroneous merges of homonyms.<br/>"
                  "• <b>Length-of-Stay Invariant Date Shifting:</b> Every date for patient $i$ is shifted by an invariant secret delta $\\Delta_i \\in [21, 180]\\text{ days}$, keeping inter-procedure intervals byte-accurate while rendering date-matching attacks futile.<br/>"
                  "• <b>Output Contract:</b> Delivers clean UTF-8 <code>sanitized/</code> files, standardized <code>records.jsonl</code>, execution summary <code>report.json</code>, and aggregate privacy risk disclosures in <code>audit.json</code>.", BODY),
        
        PageBreak(),

        # PAGE 2
        Paragraph("YUGAANTAR DEVFORGE / TRACK 3 / SECRET WARDS", EYEBROW),
        Paragraph("4. Track-Specific Brief Requirements & Empirical Evidence", HEADING),
        Paragraph("Evaluated against the official competition practice dataset (200 heterogeneous hospital files, 823 clinical records, 71 patient profiles):", BODY),
        grid([
            [Paragraph(label, TABLE_HEAD) for label in ("Track 3 Evaluation Requirement", "Measured Practice Result", "Evidence & Verification Status")],
            [Paragraph("Personal Data Detection (PII)", TABLE), Paragraph("0 / 3,230 Leaked (0.0%)", TABLE), Paragraph("100% clean across all 16 PII types & 6 channels", TABLE)],
            [Paragraph("Adversarial Canary Traps", TABLE), Paragraph("0 / 4 Canaries Leaked", TABLE), Paragraph("Zero penalty (-3 pts per leaked canary avoided)", TABLE)],
            [Paragraph("Clinical Utility Preservation", TABLE), Paragraph("4,855 / 4,855 Kept (100.0%)", TABLE), Paragraph("100% medical values, vitals, ICD codes retained", TABLE)],
            [Paragraph("Longitudinal Patient Linking", TABLE), Paragraph("F0.5 = 0.99 (P 1.00 / R 0.95)", TABLE), Paragraph("Zero false patient merges; trajectories unified", TABLE)],
            [Paragraph("Internal Re-identification Risk", TABLE), Paragraph("0.00% Singling-Out ($k \\ge 5$)", TABLE), Paragraph("Target met; 0 profiles exposed in population cell", TABLE)],
            [Paragraph("Output Contract Compliance", TABLE), Paragraph("194 Sanitized / 6 Quarantined", TABLE), Paragraph("CONTRACT OK; zero raw file copies exported", TABLE)],
            [Paragraph("Speed & Resource Limits", TABLE), Paragraph("50.6s Total (3-run check)", TABLE), Paragraph("Avg ~16.8s/run; 43 MB peak RSS (limit 900s, 4GB)", TABLE)],
            [Paragraph("Test Suite & Regression", TABLE), Paragraph("104 / 104 Passed (100%)", TABLE), Paragraph("Full coverage of traps, schemas, and APIs", TABLE)],
            [Paragraph("Pre-Submission Verification", TABLE), Paragraph("READY TO SUBMIT", TABLE), Paragraph("Zero warnings in check_submission.py harness", TABLE)],
        ], [60, 52, 68], header=True),
        Spacer(1, 2 * mm),

        Paragraph("5. Privacy-Utility Trade-off & Frontier Optimization", HEADING),
        Paragraph("• <b>Joinable Quasi-Identifiers vs Clinical Attributes:</b> Risk is measured over attributes an adversary can join against the electoral-roll registry (age band, gender, district, PIN) from ATTACKS.md ($4\\text{--}5\\times$ population factor). Diagnoses, ICD codes, and shifted event weeks are published content, not external linkage keys.<br/>"
                  "• <b>Frontier Selection:</b> The lattice selects (10-year Age Band, District, PIN Prefix), costing only ~0.6 points on official generalization scoring while guaranteeing every patient sits in a population cell $k \\ge 5$.<br/>"
                  "• <b>Preserve-District Policy:</b> District names are official clinical preserve-probes; <code>preserve_district: 1</code> stops local recoding above district level, refusing to trade medical utility for cosmetic risk numbers.<br/>"
                  "• <b>The Re-identification Trap Channel:</b> Patients with rare diagnoses ($\\le 3$ patients) are audited and reported transparently in <code>rare_dx_exposed_profiles</code> rather than corrupted or suppressed.", BODY),
        Spacer(1, 2 * mm),

        Paragraph("6. Security Boundary & Operational Controls", HEADING),
        Paragraph("• <b>Memory-Only Ephemeral Staging:</b> Candidate releases are encrypted with AES-256-GCM using an in-memory ephemeral key. Nonces are never reused, and plaintexts are erased from staging upon process exit.<br/>"
                  "• <b>Deterministic Reproducibility:</b> Identical inputs and RAKSHA_SECRET produce bit-for-bit identical releases.<br/>"
                  "• <b>Secret Isolation:</b> RAKSHA_SECRET resides purely in environment memory and is never written to logs, manifests, or output files.", BODY),
        Spacer(1, 1 * mm),

        Paragraph("7. Known Limitations", HEADING),
        Paragraph("• <b>Rare Diagnosis Invariance:</b> For a diagnosis unique to one patient, the condition identifies the record whatever is done to quasi-identifiers; the challenge strictly forbids altering clinical values.<br/>"
                  "• <b>Population Factor Transparency:</b> To maintain complete audit transparency, <code>observed_singling_out_risk</code> (uninflated factor 1.0) is always published side-by-side with the headline risk in audit.json.", BODY),
        Spacer(1, 1 * mm),

        Paragraph("<b>Models Declaration:</b> None. StegnoZ uses zero LLMs, zero generative AI, and zero pretrained transformers. Pure offline CPU Python 3.11+.", SMALL),
    ]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    
    # Verify page count
    reader = pypdf.PdfReader(str(destination))
    actual_pages = len(reader.pages)
    if actual_pages != 2:
        raise ValueError(f"Brief PDF must be exactly 2 pages! Got {actual_pages} pages.")
    print(f"Successfully generated {destination} (Exactly {actual_pages} pages).")
    return destination


if __name__ == "__main__":
    build()
