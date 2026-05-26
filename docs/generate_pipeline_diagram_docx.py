"""Generate a clean Word doc of the production data pipeline diagram.

Uses real Word tables for each box so it renders properly (no ASCII alignment
issues). Saves to docs/Healthcare_Pipeline_Diagram.docx.
"""

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


def set_cell_border(cell, color="000000", sz="8"):
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        b = OxmlElement(f"w:{edge}")
        b.set(qn("w:val"), "single")
        b.set(qn("w:sz"), sz)
        b.set(qn("w:color"), color)
        tcBorders.append(b)
    tcPr.append(tcBorders)


def shade_cell(cell, color_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color_hex)
    tcPr.append(shd)


def add_box(doc, title, body_lines, fill="FFFFFF", title_color="000000",
            border_color="000000", width=Cm(11), bold_title=True):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.rows[0].cells[0]
    cell.width = width
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    set_cell_border(cell, color=border_color, sz="12")
    shade_cell(cell, fill)

    # Title line
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(title)
    r.bold = bold_title
    r.font.size = Pt(11)
    r.font.color.rgb = RGBColor.from_string(title_color)

    # Body lines
    for line in body_lines:
        bp = cell.add_paragraph()
        bp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        br = bp.add_run(line)
        br.font.size = Pt(9)
        br.font.color.rgb = RGBColor.from_string("333333")

    return table


def add_arrow(doc, label="", down=True):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    arrow = "▼" if down else "◄"
    r = p.add_run(arrow)
    r.font.size = Pt(14)
    r.bold = True
    r.font.color.rgb = RGBColor.from_string("555555")
    if label:
        p2 = doc.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r2 = p2.add_run(label)
        r2.italic = True
        r2.font.size = Pt(9)
        r2.font.color.rgb = RGBColor.from_string("666666")


def add_branch_split(doc, left_label, left_color, right_label, right_color):
    """Two-column branch arrow: left + right paths."""
    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for cell, label, color in [
        (table.rows[0].cells[0], left_label, left_color),
        (table.rows[0].cells[1], right_label, right_color),
    ]:
        cell.width = Cm(5.5)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r1 = p.add_run("▼\n")
        r1.font.size = Pt(14)
        r1.bold = True
        r1.font.color.rgb = RGBColor.from_string(color)
        r2 = p.add_run(label)
        r2.italic = True
        r2.font.size = Pt(9)
        r2.font.color.rgb = RGBColor.from_string("444444")


def add_two_boxes_side_by_side(doc, left, right):
    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for cell, (title, body, fill, border) in [
        (table.rows[0].cells[0], left),
        (table.rows[0].cells[1], right),
    ]:
        cell.width = Cm(5.5)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
        set_cell_border(cell, color=border, sz="12")
        shade_cell(cell, fill)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(title)
        r.bold = True
        r.font.size = Pt(10)
        for line in body:
            bp = cell.add_paragraph()
            bp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            br = bp.add_run(line)
            br.font.size = Pt(9)


def main():
    doc = Document()

    # Page setup
    for section in doc.sections:
        section.top_margin = Cm(1.8)
        section.bottom_margin = Cm(1.8)
        section.left_margin = Cm(2)
        section.right_margin = Cm(2)

    # ─── Title ───
    title = doc.add_heading("Healthcare AI Agent — Production Data Pipeline", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sr = sub.add_run("Triple-H Co., Ltd.   |   Mentra Live + Wearables → Phone → Hybrid (RTX 5090 + Cloud GPU) → Supabase")
    sr.italic = True
    sr.font.size = Pt(10)
    sr.font.color.rgb = RGBColor.from_string("555555")

    doc.add_paragraph()  # spacer

    # ─── Section header: DATA SOURCES ───
    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    hr = h.add_run("DATA SOURCES")
    hr.bold = True
    hr.font.size = Pt(11)
    hr.font.color.rgb = RGBColor.from_string("1F4E79")

    # ─── Mentra Live Glasses ───
    add_box(
        doc,
        title="Mentra Live Glasses",
        body_lines=["camera (12 MP) · 3-mic · IMU · speaker", "captures: photo + audio + IMU window", "voice reply ↑ via bone-conduction"],
        fill="E7F0FA", border_color="1F4E79",
    )
    add_arrow(doc, label="BLE 5.0 / Wi-Fi 802.11ac")

    # ─── Wearables ───
    add_box(
        doc,
        title="Apple Watch / Galaxy Watch / Smart Ring / Smart Scale / BP cuff / Glucose CGM",
        body_lines=["HR, sleep, HRV, ECG, SpO₂, weight, BP, glucose", "structured numeric data — no ML needed"],
        fill="EAF7EE", border_color="2E7D32",
    )
    add_arrow(doc, label="BLE → HealthKit (iOS) / Health Connect (Android)")

    # ─── Phone ───
    h2 = doc.add_paragraph()
    h2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    h2r = h2.add_run("PROCESSING")
    h2r.bold = True
    h2r.font.size = Pt(11)
    h2r.font.color.rgb = RGBColor.from_string("1F4E79")

    add_box(
        doc,
        title="User's Phone (Galaxy S25 / iPhone 16)",
        body_lines=[
            "Aggregator: HealthKit / Health Connect · Mentra SDK · Calendar",
            "On-device ML (~75 ms total):",
            "YOLO-Face (3 MB) · Food classifier (8 MB) · Portion estimator (12 MB)",
            "Whisper-tiny (39 MB) · Gemma 4 E2B Q4 (3.2 GB)",
            "MFDS SQLite (108 MB) · USDA SQLite (62 MB)",
            "→ TTS / chatbot reply ↑ to glasses",
        ],
        fill="FFF7E6", border_color="B26B00",
    )
    add_arrow(doc, label="HTTPS")

    # ─── Branch split: confidence routing ───
    sp = doc.add_paragraph()
    sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    spr = sp.add_run("Routing by confidence")
    spr.bold = True
    spr.font.size = Pt(10)
    add_branch_split(
        doc,
        left_label="confidence ≥ 0.7\n(95% — fast path)\n+ all wearable data",
        left_color="2E7D32",
        right_label="confidence < 0.7\n(5% — slow path)\nuncertain glasses events",
        right_color="C62828",
    )

    # ─── Two terminal boxes ───
    h3 = doc.add_paragraph()
    h3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    h3r = h3.add_run("STORAGE & RE-ANALYSIS")
    h3r.bold = True
    h3r.font.size = Pt(11)
    h3r.font.color.rgb = RGBColor.from_string("1F4E79")

    add_two_boxes_side_by_side(
        doc,
        left=(
            "Supabase",
            ["• event row (Postgres)", "• thumbnail (Storage, ~100 KB WebP)", "always written"],
            "EAF7EE", "2E7D32",
        ),
        right=(
            "S3 — raw clip (~5 MB)",
            ["only for low-conf events", "↓", "Cloud GPU / RTX 5090 server", "Gemma 4 E4B Q8 + Whisper large-v3", "writes corrected event back to Supabase"],
            "FDECEC", "C62828",
        ),
    )

    doc.add_paragraph()

    # ─── Notes / legend ───
    legend = doc.add_paragraph()
    legend.alignment = WD_ALIGN_PARAGRAPH.LEFT
    lr = legend.add_run("Notes:")
    lr.bold = True
    lr.font.size = Pt(10)

    notes = [
        "• Wearable data (watch, ring, scale, cuff) is already structured — always takes the fast path. No ML, no S3, no cloud GPU needed.",
        "• Glasses photos run through 4 light models on the phone in ~75 ms. Most events resolve here.",
        "• Only uncertain glasses events (~5% of total) trigger a raw-clip upload to S3 and re-analysis on the server.",
        "• Hybrid server = RTX 5090 primary (90-95% of cloud-fallback work) + Cloud GPU overflow (5-10% peaks + failover).",
        "• End-to-end latency: ~2 sec for high-conf events, ~6-8 sec for low-conf events.",
        "• Estimated server cost at 100K users: ~$200-300/month (electricity + cloud overflow + S3 + monitoring).",
    ]
    for n in notes:
        np = doc.add_paragraph()
        npr = np.add_run(n)
        npr.font.size = Pt(9)
        npr.font.color.rgb = RGBColor.from_string("333333")

    # Save
    output = r"C:\Users\tripleh\projects\healthcare-ai-agent\docs\Healthcare_Pipeline_Diagram.docx"
    doc.save(output)
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
