"""Build the StegnoZ two-page Track 3 project brief."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


INK = colors.HexColor("#17253A")
ACCENT = colors.HexColor("#0F6B63")
MUTED = colors.HexColor("#496078")
LINE = colors.HexColor("#D7E4E3")
PALE = colors.HexColor("#F1F7F6")
BODY = ParagraphStyle("Body", fontName="Helvetica", fontSize=10.5, leading=14.5,
                      textColor=INK, spaceAfter=8)
SMALL = ParagraphStyle("Label", parent=BODY, fontSize=10, leading=13, textColor=MUTED)
HEADING = ParagraphStyle("Heading", fontName="Helvetica-Bold", fontSize=13, leading=17,
                         textColor=ACCENT, spaceBefore=8, spaceAfter=6)
TITLE = ParagraphStyle("Title", fontName="Helvetica-Bold", fontSize=26, leading=30,
                       textColor=INK, spaceAfter=6)
TABLE = ParagraphStyle("Table text", parent=BODY, fontSize=10, leading=13, spaceAfter=0)
TABLE_HEAD = ParagraphStyle("Table head", parent=TABLE, fontName="Helvetica-Bold",
                            textColor=colors.white)
FLOW = ParagraphStyle("Flow", parent=TABLE, fontName="Helvetica-Bold", textColor=ACCENT, alignment=1)


def grid(rows, widths, header=False):
    table = Table(rows, colWidths=[width * mm for width in widths], hAlign="LEFT")
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [PALE, colors.white]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), ACCENT))
    table.setStyle(TableStyle(style))
    return table


def footer(canvas, document):
    canvas.setStrokeColor(LINE)
    canvas.line(17 * mm, 15 * mm, 193 * mm, 15 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 10)
    canvas.drawString(17 * mm, 10 * mm, "StegnoZ  |  Secret Wards")
    canvas.drawRightString(193 * mm, 10 * mm, f"{document.page} / 2")


def build(path=None):
    destination = Path(path) if path else Path(__file__).with_name("StegnoZ_Project_Brief.pdf")
    doc = SimpleDocTemplate(str(destination), pagesize=A4, leftMargin=17 * mm, rightMargin=17 * mm,
                            topMargin=20 * mm, bottomMargin=21 * mm, title="StegnoZ Project Brief",
                            author="Harshit Agarwalla and Shruti Talikoti")
    story = [
        Paragraph("YUGAANTAR DEVFORGE / TRACK 3 / SECRET WARDS", SMALL),
        Paragraph("StegnoZ", TITLE),
        Paragraph("<b>Team members</b> Harshit Agarwalla and Shruti Talikoti<br/>"
                  "<b>Repository</b> <link href='https://github.com/itsmeshruti1/StegnoZ' color='#0F6B63'>"
                  "github.com/itsmeshruti1/StegnoZ</link>", BODY),
        Paragraph("An offline firewall for synthetic hospital records that resolves identities across English, Hindi, "
                  "and Hinglish before deciding which details to generalize.", BODY),
        Paragraph("Architecture", HEADING),
        Paragraph("CSV, TSV, JSON, FHIR R4, and text notes", SMALL),
        grid([[Paragraph(label, FLOW) for label in (
            "Ingest", "&gt;", "Detect", "&gt;", "Link", "&gt;", "Generalize", "&gt;", "Verify &amp; export"
        )]], [25, 9, 25, 9, 20, 9, 31, 9, 39]),
        Spacer(1, 4 * mm),
        Paragraph("Outputs  sanitized/  ·  report.json  ·  records.jsonl", SMALL),
        Paragraph("How it works", HEADING),
        Paragraph("<b>Ingestion.</b> Detects supported formats and encodings. Malformed inputs and attachments that "
                  "cannot be scrubbed safely are quarantined.", BODY),
        Paragraph("<b>Detection.</b> Schema rules, context, content voting, and a run-local dictionary distinguish "
                  "personal identifiers from clinical text. Indic phonetic keys help match spellings across scripts.", BODY),
        Paragraph("<b>Linkage.</b> Fellegi–Sunter scoring compares candidates after blocking. Explicit MRN namespaces "
                  "and conflict checks constrain merges. HMAC-SHA256 keys pseudonyms and date shifts.", BODY),
        Paragraph("<b>Privacy and verification.</b> The policy selects age bands, location granularity, and PIN masking. "
                  "Each linked patient gets one date offset for representable dates. A final scan checks residual "
                  "identifiers and validates rewritten FHIR references.", BODY),
        Paragraph("What sets it apart", HEADING),
        Paragraph("The policy search estimates utility loss before generalizing records. The export then measures "
                  "risk separately on observed groups in the candidate release and reports when it exceeds the target.", BODY),
        PageBreak(),
        Paragraph("PRACTICE EVIDENCE", SMALL),
        Paragraph("Privacy and utility", TITLE),
        grid([
            [Paragraph(label, TABLE_HEAD) for label in ("Measure", "Result on organizer practice data")],
            [Paragraph(label, TABLE) for label in ("Visible annotated identifiers / planted canaries", "0 of 3,230 / 0 of 4")],
            [Paragraph(label, TABLE) for label in ("Clinical values preserved", "4,855 of 4,855")],
            [Paragraph(label, TABLE) for label in ("Pairwise precision / recall / F0.5", "1.00 / 0.87 / 0.97")],
            [Paragraph(label, TABLE) for label in ("Manifest coverage for annotated exports", "773 of 773")],
            [Paragraph(label, TABLE) for label in ("Observed candidates in classes below k=5", "65.65% · 5% target missed")],
            [Paragraph(label, TABLE) for label in ("Windows run over 200 files", "About 2.1 seconds · 39 MB peak RSS")],
        ], [93, 83], header=True),
        Spacer(1, 4 * mm),
        Paragraph("The observed-class figure is an internal proxy. It includes recognized released facts and unresolved "
                  "records. The default run reports a target miss and publishes for challenge scoring. The optional "
                  "<b>--strict-risk</b> mode withholds the candidate records.", BODY),
        Paragraph("Security design", HEADING),
        Paragraph("The organizer mounts inputs read-only. Outside the event, provision encrypted volumes for "
                  "inputs and releases, with storage access separate from key access. RAKSHA_SECRET comes from the "
                  "environment. Raw inputs and decoded intermediates are never copied to staging. The CLI stages "
                  "verified bytes and logs counts and coarse failure reasons.", BODY),
        Paragraph("Known limitations", HEADING),
        Paragraph("Some unlabeled identifiers are ambiguous. A changed set of linkage evidence can change a "
                  "pseudonym, and finite date offsets can coincide. Local tests exercised mixed date orders, "
                  "multi-patient FHIR references, and hidden names in JSON keys. The hidden datasets and official "
                  "Linux resource limits remain unverified.", BODY),
        Paragraph("<b>Models declaration</b> None. The runtime is CPU-only and uses the Python standard library.", SMALL),
    ]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    build()
