"""Generate the Healthcare AI Agent — Full Development Pipeline & Progress as a Word doc.

Color-coded by phase status:
  - DONE = green
  - PAUSED = orange/red (current)
  - NEXT = blue
  - LATER = gray

Saves to docs/Healthcare_Development_Pipeline.docx.
"""

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


# ── Color palette ──
GREEN_FILL  = "E7F5E9"   # done
GREEN_BAR   = "2E7D32"
ORANGE_FILL = "FFF4E5"   # paused / current
ORANGE_BAR  = "E65100"
BLUE_FILL   = "E7F0FA"   # next
BLUE_BAR    = "1565C0"
GRAY_FILL   = "F1F1F1"   # later
GRAY_BAR    = "555555"
RED_FILL    = "FDECEC"   # blocker
RED_BAR     = "C62828"


def shade_cell(cell, color_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color_hex)
    tcPr.append(shd)


def set_cell_border(cell, color="888888", sz="6"):
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        b = OxmlElement(f"w:{edge}")
        b.set(qn("w:val"), "single")
        b.set(qn("w:sz"), sz)
        b.set(qn("w:color"), color)
        tcBorders.append(b)
    tcPr.append(tcBorders)


def add_phase_header(doc, label, title, fill, bar):
    """Color-banded phase header bar."""
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.rows[0].cells[0]
    cell.width = Cm(17)
    shade_cell(cell, fill)
    set_cell_border(cell, color=bar, sz="14")

    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r1 = p.add_run(f"  {label}   ")
    r1.bold = True
    r1.font.size = Pt(11)
    r1.font.color.rgb = RGBColor.from_string(bar)
    r2 = p.add_run(title)
    r2.bold = True
    r2.font.size = Pt(13)
    r2.font.color.rgb = RGBColor.from_string("000000")


def add_status_table(doc, rows, fill_color="FFFFFF"):
    """rows: list of (deliverable, status) tuples."""
    table = doc.add_table(rows=len(rows) + 1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Header
    hdr = table.rows[0].cells
    hdr[0].width = Cm(13)
    hdr[1].width = Cm(4)
    for i, label in enumerate(["Deliverable", "Status"]):
        shade_cell(hdr[i], "404040")
        set_cell_border(hdr[i], color="404040", sz="6")
        p = hdr[i].paragraphs[0]
        r = p.add_run(label)
        r.bold = True
        r.font.color.rgb = RGBColor.from_string("FFFFFF")
        r.font.size = Pt(10)

    # Body
    for i, (deliverable, status) in enumerate(rows, start=1):
        cells = table.rows[i].cells
        cells[0].width = Cm(13)
        cells[1].width = Cm(4)
        shade_cell(cells[0], "FFFFFF")
        shade_cell(cells[1], fill_color)
        set_cell_border(cells[0])
        set_cell_border(cells[1])
        for j, txt in enumerate([deliverable, status]):
            p = cells[j].paragraphs[0]
            r = p.add_run(txt)
            r.font.size = Pt(9)


def add_bullet_list(doc, items, indent=Cm(0.7)):
    for item in items:
        p = doc.add_paragraph(item, style="List Bullet")
        p.paragraph_format.left_indent = indent
        for run in p.runs:
            run.font.size = Pt(9.5)


def add_checkbox_list(doc, items):
    """Items as unchecked TODO list."""
    for item in items:
        p = doc.add_paragraph()
        r = p.add_run(f"☐ {item}")
        r.font.size = Pt(9.5)


def add_blocker_table(doc, rows):
    table = doc.add_table(rows=len(rows) + 1, cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    hdr = table.rows[0].cells
    for i, (label, w) in enumerate([("Blocker", Cm(7)), ("Owner", Cm(4)), ("Unblocks", Cm(6))]):
        hdr[i].width = w
        shade_cell(hdr[i], RED_BAR)
        set_cell_border(hdr[i], color=RED_BAR, sz="6")
        p = hdr[i].paragraphs[0]
        r = p.add_run(label)
        r.bold = True
        r.font.color.rgb = RGBColor.from_string("FFFFFF")
        r.font.size = Pt(10)

    for i, (blocker, owner, unblocks) in enumerate(rows, start=1):
        cells = table.rows[i].cells
        for j, txt in enumerate([blocker, owner, unblocks]):
            shade_cell(cells[j], RED_FILL)
            set_cell_border(cells[j])
            p = cells[j].paragraphs[0]
            r = p.add_run(txt)
            r.font.size = Pt(9)


def add_h1(doc, text, color="000000"):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(18)
    r.font.color.rgb = RGBColor.from_string(color)


def add_h2(doc, text, color="1F4E79"):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(13)
    r.font.color.rgb = RGBColor.from_string(color)


def add_p(doc, text, size=10, color="000000", italic=False):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.size = Pt(size)
    r.italic = italic
    r.font.color.rgb = RGBColor.from_string(color)


def add_pagebreak(doc):
    doc.add_page_break()


# ─────────────────────────────────────────────────────────────────────────
def main():
    doc = Document()

    for section in doc.sections:
        section.top_margin = Cm(2)
        section.bottom_margin = Cm(2)
        section.left_margin = Cm(2.2)
        section.right_margin = Cm(2.2)

    # ── Title page ──
    title = doc.add_heading("Healthcare AI Agent", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sr = sub.add_run("Full Development Pipeline & Progress Report")
    sr.bold = True
    sr.font.size = Pt(16)
    sr.font.color.rgb = RGBColor.from_string("1F4E79")

    sub2 = doc.add_paragraph()
    sub2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sr2 = sub2.add_run("Triple-H Co., Ltd.   |   Patent No. 10-2025-0145274   |   Apr 27, 2026")
    sr2.italic = True
    sr2.font.size = Pt(10)
    sr2.font.color.rgb = RGBColor.from_string("555555")

    doc.add_paragraph()

    # ── Executive summary ──
    add_h2(doc, "Executive Summary")
    add_p(doc,
        "Phase 3 (voice extraction decision) is complete. The healthcare AI agent has a working "
        "AIMB-G1 → OneDrive → PC → Supabase pipeline, a 41-table production database, an HRT "
        "drill-down dashboard, and a benchmarked extraction strategy: hybrid regex (fast path, 80-95% of events) "
        "with Gemma 4 E4B Q8 GPU fallback (5-15% uncertain events) achieving food F1 = 1.000 vs regex 0.458. "
        "The project is paused at the entry of Phase 4 (Production Pipeline Buildout) pending boss clarification "
        "on architecture questions, Solos AirGo V2 SDK answers, and a larger Korean test set. "
        "Estimated path to 100K-user beta: 4-6 months."
    )

    # ── Legend ──
    add_h2(doc, "Phase Color Legend")
    legend_table = doc.add_table(rows=1, cols=4)
    legend_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    legend = [
        ("✅ DONE", GREEN_FILL, GREEN_BAR),
        ("🛑 PAUSED (current)", ORANGE_FILL, ORANGE_BAR),
        ("⚡ NEXT", BLUE_FILL, BLUE_BAR),
        ("…  LATER", GRAY_FILL, GRAY_BAR),
    ]
    for i, (label, fill, bar) in enumerate(legend):
        cell = legend_table.rows[0].cells[i]
        cell.width = Cm(4)
        shade_cell(cell, fill)
        set_cell_border(cell, color=bar, sz="10")
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(label)
        r.bold = True
        r.font.size = Pt(10)
        r.font.color.rgb = RGBColor.from_string(bar)

    add_pagebreak(doc)

    # ─── PHASE 1 ──────────────────────────────────────────────
    add_phase_header(doc, "Phase 1", "Foundation (DONE ✅)", GREEN_FILL, GREEN_BAR)
    add_status_table(doc, [
        ("Patent filing", "✅ 10-2025-0145274 (Oct 2, 2025)"),
        ("Initial v1, v2, v3 plans", "✅"),
        ("LRT + HRT unified Supabase DB (Seoul, project klnykuxzucujahucvbct)", "✅"),
        ("41 tables + 5 views deployed (migrations 001-006)", "✅"),
        ("FastAPI backend + 10 routers", "✅ Running on :8000"),
        ("Free data downloads — KNHANES 49K, MFDS 275K, USDA 13K, AI Hub 150K images", "✅"),
        ("HRT drill-down dashboard (Next.js, year/month/day/hour × 7 categories)", "✅"),
        ("/predictions page — 8 trajectory charts + 8-disease risks (mock for now)", "✅"),
    ], fill_color=GREEN_FILL)

    doc.add_paragraph()

    # ─── PHASE 2 ──────────────────────────────────────────────
    add_phase_header(doc, "Phase 2", "AIMB-G1 Glasses Pipeline (DONE ✅)", GREEN_FILL, GREEN_BAR)
    add_status_table(doc, [
        ("Cyan-import → OneDrive → PC → watcher.py → Supabase end-to-end", "✅"),
        ("YOLOv8 + Whisper medium + regex extraction", "✅"),
        ("FOOD_DB (289K) + MED_DB lookup", "✅"),
        ("Drill-down auto-populate from glasses events", "✅"),
        ("9-bug audit + 7 fixes (Apr 24) — migrations 005, 006", "✅"),
        ("HEIC + iPhone-naming compatibility", "✅"),
        ("Medicine intake table (separate from prescription)", "✅"),
        ("Service-role auth bypass on RPC", "✅"),
    ], fill_color=GREEN_FILL)

    doc.add_paragraph()

    # ─── PHASE 3 ──────────────────────────────────────────────
    add_phase_header(doc, "Phase 3", "Voice Extraction Decision (DONE ✅, Apr 27)", GREEN_FILL, GREEN_BAR)
    add_status_table(doc, [
        ("CPU benchmark — regex vs Gemma 4 E2B Q4 (i3-12100)", "✅ Regex won"),
        ("GPU benchmark — regex vs Gemma 4 E4B Q8 (RTX 4070 SUPER)", "✅ Gemma F1 1.000"),
        ("Korean preservation prompt fix verified", "✅"),
        ("CUDA build vs Vulkan tested", "✅"),
        ("Hybrid architecture LOCKED — regex fast path + Gemma E4B fallback", "✅"),
        ("GEMMA4_BENCHMARK_CONFIG.md saved (reproducible)", "✅"),
    ], fill_color=GREEN_FILL)

    add_pagebreak(doc)

    # ─── PAUSED ──────────────────────────────────────────────
    add_phase_header(doc, "🛑 PAUSED", "Where We Stopped (Apr 27, 2026)", ORANGE_FILL, ORANGE_BAR)

    add_h2(doc, "Why we stopped", color=ORANGE_BAR)
    add_bullet_list(doc, [
        "Boss clarification needed on pipelines 3 + 4 (does \"PC\" mean company server vs user home PC).",
        "Solos AirGo V2 SDK answers needed before deciding Mentra vs Solos for production glasses.",
        "Korean test set is only 8 cases — too small to lock production extraction confidently.",
        "NHIS cohort approval still pending — blocks rigorous LSTM training.",
        "Mentra Live not yet procured — using AIMB-G1 as bridge prototype.",
        "Boss strategic direction needed on whether to build a custom iOS app vs use cloud GPU.",
    ])

    add_h2(doc, "Active blockers", color=RED_BAR)
    add_blocker_table(doc, [
        ("Boss meeting (pipelines 3+4 clarification)", "You + Boss", "Phase 4 architecture commitment"),
        ("Solos email reply (10 SDK questions)", "Solos dev support", "Hardware decision (Mentra vs Solos)"),
        ("Korean test set expansion (8 → 50 samples)", "You / labeler", "Production confidence in Gemma 4 E4B"),
        ("NHIS approval", "Colleague applying", "LSTM training rigor"),
        ("Mentra Live purchase", "Boss approval", "Production pipeline build"),
    ])

    add_pagebreak(doc)

    # ─── PHASE 4 ──────────────────────────────────────────────
    add_phase_header(doc, "Phase 4", "Production Pipeline Buildout (NEXT, after blockers cleared)", BLUE_FILL, BLUE_BAR)

    add_h2(doc, "4A — Cloud extractor integration (1-2 weeks)", color=BLUE_BAR)
    add_checkbox_list(doc, [
        "Add gemma_extract() HTTP call to event_processor.py",
        "Wire as escalation when regex confidence < 0.7",
        "Log dual-extraction comparison for first 100 real events",
        "Lock threshold based on real-data validation",
    ])

    add_h2(doc, "4B — Korean test set hardening (1 week)", color=BLUE_BAR)
    add_checkbox_list(doc, [
        "Collect 50+ real Whisper transcripts from your AIMB-G1 captures",
        "Hand-label ground truth for each",
        "Re-run Gemma vs regex benchmark on this larger set",
        "Confirm Gemma 4 E4B holds up beyond synthetic 8-case set",
    ])

    add_h2(doc, "4C — Production server deployment (2-3 weeks)", color=BLUE_BAR)
    add_checkbox_list(doc, [
        "Migrate RTX 5090 server from Win11 to Linux (Ubuntu 24.04)",
        "llama.cpp CUDA build + systemd service",
        "Reverse proxy (nginx) + TLS via Let's Encrypt",
        "Cloudflare Tunnel or Tailscale for safe internet exposure",
        "Job queue (Redis Streams or Kafka or webhook + retry)",
        "Worker pool fetches from S3, posts to Supabase",
    ])

    add_h2(doc, "4D — S3 + lifecycle (1 week)", color=BLUE_BAR)
    add_checkbox_list(doc, [
        "AWS account or Supabase Storage with S3-compatible policy",
        "Buckets per domain: lrt-clips/ , hrt-clips/ , re-clips/",
        "Hot 7d → Warm 30d → Glacier 90d → Archive 7y (HIPAA / PIPA)",
        "Phone uploads via pre-signed URLs",
    ])

    add_h2(doc, "4E — Phone companion app (4-6 weeks)", color=BLUE_BAR)
    add_checkbox_list(doc, [
        "HealthGlassesApp v2 — iOS + Android",
        "HealthKit / Health Connect aggregation",
        "On-device YOLO-Face + MobileNetV2 + Whisper-tiny + portion estimator",
        "Cloud Haiku chatbot (faster path than on-device for now)",
        "BLE pairing flow for glasses (Mentra SDK or AIMB-G1 fallback)",
    ])

    add_pagebreak(doc)

    # ─── PHASE 5 ──────────────────────────────────────────────
    add_phase_header(doc, "Phase 5", "Glasses Hardware Migration (after Phase 4)", GRAY_FILL, GRAY_BAR)
    add_checkbox_list(doc, [
        "Procure Mentra Live (1 unit for dev) OR Solos AirGo V2 if SDK proves out",
        "Replace AIMB-G1 manual Cyan flow with auto BLE/Wi-Fi",
        "Voice TTS reply loop through glasses speaker",
        "Pill-event detection with quick-reply confirmation notifications",
        "1-week internal pilot wearing the new glasses daily",
    ])

    doc.add_paragraph()

    # ─── PHASE 6 ──────────────────────────────────────────────
    add_phase_header(doc, "Phase 6", "ML Refinement (parallel to Phase 4-5)", GRAY_FILL, GRAY_BAR)
    add_checkbox_list(doc, [
        "Fine-tune EfficientNetV2-S on AI Hub 150K Korean food images (RTX 4070 SUPER)",
        "Knowledge distillation: EfficientNetV2-S teacher → 10 MB TFLite student",
        "Replace MobileNetV2-Food on phone with distilled student",
        "Whisper large-v3 + CUDA on 4070 SUPER (kills Korean-English code-switching mangle)",
        "LSTM-Transformer training on KNHANES (after NHIS approval)",
        "Monte Carlo Dropout for uncertainty bands",
    ])

    doc.add_paragraph()

    # ─── PHASE 7 ──────────────────────────────────────────────
    add_phase_header(doc, "Phase 7", "OpenClaw Agent Stack (after Phase 4)", GRAY_FILL, GRAY_BAR)
    add_checkbox_list(doc, [
        "Build the 11 agent skill files (currently empty directories)",
        "O1 Orchestrator — routes user requests",
        "O2 Judgement — safety gate",
        "9 Functional agents: Data Collection, HealthCore, Nutrition, Exercise, Medical, Glasses, Family, Community, Expert",
        "Wire agent_user_context + agent_memory tables (already deployed in migration 003)",
    ])

    doc.add_paragraph()

    # ─── PHASE 8 ──────────────────────────────────────────────
    add_phase_header(doc, "Phase 8", "Beta Launch (3-6 months out)", GRAY_FILL, GRAY_BAR)
    add_checkbox_list(doc, [
        "First 100 invited beta users",
        "PIPA review + Korean privacy attestation",
        "Feedback loop integration (thumbs up/down on every prediction)",
        "Scale-up to 1,000 users",
        "Add cloud GPU overflow (Modal / RunPod) when 5090 hits 70% utilization",
        "Approach 100K target",
    ])

    add_pagebreak(doc)

    # ─── Visual roadmap ──────────────────────────────────────
    add_h2(doc, "Visual Roadmap")

    roadmap = [
        ("Apr 2026 ✅",   "Phase 1 Foundation · Phase 2 AIMB-G1 Pipeline · Phase 3 Gemma 4 Decision LOCKED",  GREEN_FILL,  GREEN_BAR),
        ("🛑 Now",        "PAUSED — boss meeting, Solos reply, Korean test set",                              ORANGE_FILL, ORANGE_BAR),
        ("May 2026 ⚡",   "Phase 4A Cloud extractor wired · 4B Test set · 4C Production server · 4D S3 lifecycle", BLUE_FILL,  BLUE_BAR),
        ("Jun 2026 ⚡",   "Phase 4E Phone app v2 · Phase 6 ML refinement starts (parallel)",                   BLUE_FILL,   BLUE_BAR),
        ("Jul 2026",      "Phase 5 Mentra Live arrives + integrates · Phase 7 OpenClaw agent skills",         GRAY_FILL,   GRAY_BAR),
        ("Aug 2026",      "Phase 8 internal pilot",                                                            GRAY_FILL,   GRAY_BAR),
        ("Sep-Oct 2026",  "Beta 100 users",                                                                    GRAY_FILL,   GRAY_BAR),
        ("Nov-Dec 2026",  "Beta 1,000 users",                                                                  GRAY_FILL,   GRAY_BAR),
        ("2027",          "Production scale to 10K+",                                                          GRAY_FILL,   GRAY_BAR),
    ]
    rt = doc.add_table(rows=len(roadmap), cols=2)
    rt.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, (when, what, fill, bar) in enumerate(roadmap):
        c0, c1 = rt.rows[i].cells
        c0.width = Cm(3.5); c1.width = Cm(13.5)
        shade_cell(c0, fill); shade_cell(c1, "FFFFFF")
        set_cell_border(c0, color=bar, sz="10"); set_cell_border(c1)
        p0 = c0.paragraphs[0]; p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r0 = p0.add_run(when); r0.bold = True; r0.font.size = Pt(10); r0.font.color.rgb = RGBColor.from_string(bar)
        p1 = c1.paragraphs[0]
        r1 = p1.add_run(what); r1.font.size = Pt(10)

    doc.add_paragraph()

    # ─── How we continue ──────────────────────────────────────
    add_h2(doc, "How We Continue After This Pause")
    add_bullet_list(doc, [
        "Ask boss the 4 open questions (pipelines 3+4 clarification, Mentra vs Solos, test set ownership).",
        "Email Solos developers with the 10-question SDK checklist.",
        "Start Phase 4A in parallel — cloud extractor integration is doable today regardless of boss answers (just adds a flag to event_processor.py).",
        "Resume any future session by reading project_healthcare_complete_handoff.md — single-file 0-to-100% project state.",
    ])

    add_h2(doc, "TL;DR — Exactly Where You Are")
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Cm(0.7)
    r = p.add_run(
        "Phase 3 done. Voice extraction decision locked: hybrid regex + Gemma 4 E4B GPU fallback. "
        "Production architecture diagrammed and saved. Stopped at Phase 4 entry pending: boss "
        "clarification on 2 architecture questions, Solos SDK answers, and a larger Korean test set. "
        "Once those clear, the next 4-6 weeks builds the production server, S3 lifecycle, and phone "
        "companion app — then Mentra hardware migration in Phase 5."
    )
    r.italic = True
    r.font.size = Pt(11)
    r.font.color.rgb = RGBColor.from_string("1F4E79")

    # Save
    output = r"C:\Users\tripleh\projects\healthcare-ai-agent\docs\Healthcare_Development_Pipeline.docx"
    doc.save(output)
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
