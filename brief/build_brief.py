#!/usr/bin/env python3
"""Render the 2-page RakshaMed Project Brief PDF (dev tool; reportlab, not a runtime dependency)."""
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

INK = colors.HexColor("#12263a")
ACC = colors.HexColor("#0a7d6b")
MUT = colors.HexColor("#5b6b7b")
BG = colors.HexColor("#eef4f3")


class Diagram(Flowable):
    """Five-pass pipeline architecture diagram."""
    def __init__(self, w=170 * mm, h=34 * mm):
        super().__init__()
        self.width, self.height = w, h

    def draw(self):
        c = self.canv
        stages = [("Ingest", "sniff format,\ndecode, quarantine"),
                  ("Extract", "schema vote,\ndynamic PII dict"),
                  ("Link", "EM Fellegi-Sunter,\ncannot-link clusters"),
                  ("Privacy", "date shift, lattice\n+ Mondrian recode"),
                  ("Rewrite+Verify", "format-preserving,\nresidual self-scan")]
        n = len(stages)
        gap = 5 * mm
        bw = (self.width - gap * (n - 1)) / n
        bh = 20 * mm
        y = self.height - bh - 2 * mm
        for i, (title, sub) in enumerate(stages):
            x = i * (bw + gap)
            c.setFillColor(BG)
            c.setStrokeColor(ACC)
            c.setLineWidth(1)
            c.roundRect(x, y, bw, bh, 2 * mm, stroke=1, fill=1)
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 8.3)
            c.drawCentredString(x + bw / 2, y + bh - 7 * mm, title)
            c.setFillColor(MUT)
            c.setFont("Helvetica", 6.3)
            for j, line in enumerate(sub.split("\n")):
                c.drawCentredString(x + bw / 2, y + bh - 11 * mm - j * 3.1 * mm, line)
            if i < n - 1:
                c.setStrokeColor(ACC)
                c.setLineWidth(1.3)
                ay = y + bh / 2
                c.line(x + bw + 0.6 * mm, ay, x + bw + gap - 0.6 * mm, ay)
                c.setFillColor(ACC)
                pth = c.beginPath()
                pth.moveTo(x + bw + gap - 0.6 * mm, ay)
                pth.lineTo(x + bw + gap - 2.4 * mm, ay + 1.1 * mm)
                pth.lineTo(x + bw + gap - 2.4 * mm, ay - 1.1 * mm)
                pth.close()
                c.drawPath(pth, stroke=0, fill=1)
        c.setFont("Helvetica-Oblique", 6.5)
        c.setFillColor(MUT)
        c.drawString(0, y - 4.5 * mm, "Input: CSV / TSV / nested JSON / FHIR R4 / text  (EN + Devanagari Hindi + Hinglish, 4 hospitals)")
        c.drawRightString(self.width, y - 4.5 * mm, "Output: sanitized/  +  report.json  +  records.jsonl")


def build(path="brief/RakshaMed_Project_Brief.pdf"):
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=12 * mm, bottomMargin=11 * mm, title="RakshaMed Project Brief")
    ss = getSampleStyleSheet()
    H = ParagraphStyle("H", parent=ss["Heading2"], textColor=ACC, fontSize=10.5, spaceBefore=5,
                       spaceAfter=2, fontName="Helvetica-Bold")
    T = ParagraphStyle("T", parent=ss["Title"], textColor=INK, fontSize=17, spaceAfter=1, alignment=TA_LEFT)
    sub = ParagraphStyle("sub", parent=ss["Normal"], textColor=MUT, fontSize=8.5, spaceAfter=5)
    B = ParagraphStyle("B", parent=ss["Normal"], textColor=INK, fontSize=8.4, leading=11.2, spaceAfter=2)
    LI = ParagraphStyle("LI", parent=B, leftIndent=8, bulletIndent=0)
    e = []

    def bullets(items):
        for it in items:
            e.append(Paragraph("• " + it, LI))

    e.append(Paragraph("RakshaMed", T))
    e.append(Paragraph("An offline, CPU-only, LLM-free privacy firewall for multilingual hospital records "
                       "&nbsp;·&nbsp; Track 3 · Secret Wards", sub))

    e.append(Paragraph("1. In one paragraph", H))
    e.append(Paragraph(
        "RakshaMed turns a chaotic, multi-hospital, multi-script hospital dump into a research-safe "
        "release: it removes every direct and quasi-identifier, keeps every medical value exact, and "
        "gives each real patient one stable pseudonym across all files and languages. The idea that "
        "makes it more than a PII scrubber is that it reads the whole dump once to learn a run-only "
        "dictionary of every identity, then resolves patients and <i>searches backwards from a privacy "
        "objective</i> to the least-destructive generalisation that defeats the attacker — understanding "
        "context (“C/O fever” vs “C/O Ramesh”, a dose <b>1-0-1</b> vs a phone) instead of "
        "memorising the practice files, so it survives hidden datasets whose formats it has never seen.", B))

    e.append(Paragraph("2. Architecture", H))
    e.append(Diagram())
    e.append(Spacer(1, 3 * mm))

    e.append(Paragraph("3. How it works", H))
    bullets([
        "<b>Ingestion:</b> content-sniffed format detection (JSON behind a .csv, FHIR by resourceType), "
        "UTF-8/BOM/UTF-16/cp1252 decoding, Devanagari-digit and zero-width normalisation; deeply nested, "
        "truncated, corrupt, binary and empty files are quarantined with a PII-free reason, never copied out raw.",
        "<b>Detection:</b> rules + gazetteers + our own Devanagari↔Latin transliteration across English, "
        "Hindi and Hinglish; schema intelligence classifies every header/key by lexicon, fuzzy match, JSON/FHIR "
        "context <i>and content voting</i>, so unseen columns are still understood. Meaning traps are handled: "
        "doctors, wards, eponyms (Parkinson’s), ASHA workers, doses and <b>1-0-1</b> frequencies are kept; a "
        "Philter-style safe-list catches canary names in no list.",
        "<b>Linkage &amp; pseudonyms:</b> blocking by strong IDs and a cross-script phonetic key; Fellegi–Sunter "
        "scoring whose m/u weights are <i>EM-estimated per run</i> (adapts to unseen data); constrained merge-center "
        "clustering with cannot-link rules keeps same-name patients apart; uncertain links abstain. IDs are keyed "
        "HMAC-SHA256 (HKDF-separated), non-reversible and secret-specific.",
        "<b>Privacy layer:</b> per-patient secret date shifts (never small, never shared) keep stays exact and defeat "
        "global-offset recovery; a Patient Exposure Graph drives an exhaustive k-anonymity lattice search for the "
        "least-destructive feasible policy, with Mondrian local recoding of only the still-risky patients; age bands "
        "always contain the true age.",
        "<b>Security:</b> HKDF key separation, secret never printed/written, counter-only PII-free logs, no temp files, "
        "no network; byte-identical output for the same secret, different pseudonyms/shifts for a different secret.",
    ])

    e.append(Paragraph("4. USP", H))
    bullets([
        "<b>Goal-driven Reverse Privacy Engine</b> — works backwards from a risk target to the minimum information loss, "
        "instead of a fixed one-size policy.",
        "<b>Patient Exposure Graph</b> — measures risk from each patient’s <i>combined</i> cross-hospital record, catching "
        "rare clinical signatures k-anonymity alone misses.",
        "<b>Context over memorisation</b> — content-based schema inference + EM linkage + dynamic dictionary keep recall "
        "high on formats never seen in the practice data.",
    ])

    e.append(Paragraph("5. Privacy–utility trade-off (measured on the practice dataset)", H))
    rows = [["Measure", "Value"],
            ["Personal data leaked  (overall / Hindi / Hinglish)", "0.0%  /  0.0%  /  0.0%"],
            ["Leaked on unseen-format stress test (content channel)", "0.0%   (0 canaries)"],
            ["Medical values preserved", "100.0%  (4855 / 4855)"],
            ["Linking precision / recall / F0.5  (false merges)", "1.00 / 0.86 / 0.97   (0)"],
            ["Canaries leaked", "0 / 4"],
            ["Re-identification policy", "5-yr bands + tehsil + PIN-prefix base; 19 at-risk patients coarsened"],
            ["Run time / determinism", "~1.6 s / 200 files;  byte-identical on repeat, secret-sensitive"]]
    tbl = Table(rows, colWidths=[112 * mm, 58 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACC), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"), ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d6d3")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 2.4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4), ("LEFTPADDING", (0, 0), (-1, -1), 5)]))
    e.append(tbl)
    e.append(Spacer(1, 2 * mm))
    e.append(Paragraph(
        "<b>Why these settings:</b> the privacy score couples to utility (privacy is only fully credited above 40% "
        "utility), and both the utility and privacy categories reward keeping information. So we generalise as little "
        "as the risk target allows — the finest lattice node globally — and coarsen only the few patients whose combined "
        "profile is genuinely singling-out (very old patients, tiny villages, rare diagnoses). We give up precise age and "
        "village for those patients; we gain resistance to the targeted known-facts attack while keeping research "
        "statistics (diagnosis mix, length-of-stay, lab medians) intact for everyone else.", B))

    e.append(Paragraph("6. Known limitations", H))
    bullets([
        "Reported re-identification risk is a measured proxy, not a guarantee; an attacker with richer side knowledge "
        "may still single out a genuinely unique clinical signature.",
        "Detection is deliberately high-recall and can over-redact a rare name that collides with a medical term; "
        "transliteration covers common Hindi/Hinglish morphology but not every regional spelling.",
        "No learned model ships: a small self-trained CRF is a declared future add-on, gated on an ablation showing "
        "recall gains without preserve loss.",
    ])
    e.append(Spacer(1, 1.5 * mm))
    e.append(Paragraph("<b>Models declaration:</b> none. No LLM, no generative model, no pretrained transformer. All "
                       "detection, transliteration, EM record linkage, lattice search and Mondrian recoding are original "
                       "code. Runtime is the Python standard library only, fully offline.", sub))
    doc.build(e)
    print("wrote", path)


if __name__ == "__main__":
    build()
