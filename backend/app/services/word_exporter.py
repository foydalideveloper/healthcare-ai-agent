"""Render an aggregated Full Report dict (full_report_aggregator) to a .docx.

Returns a BytesIO so the endpoint can StreamingResponse it (never writes to
disk, never holds two copies). 9 sections + title page + metadata.

KOREAN RENDERING NOTE: python-docx's run.font.name only sets the *ASCII*
(w:ascii) font. CJK glyphs use a separate w:eastAsia font; if it's unset Word
falls back to a default and Korean can render as boxes. So _apply_fonts sets
w:eastAsia = "Malgun Gothic" (맑은 고딕) on every run, and we also set it on the
base styles. Calibri is used for Latin text.
"""
from __future__ import annotations

import re
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

ASCII_FONT = "Calibri"
CJK_FONT = "Malgun Gothic"  # 맑은 고딕 — clean Korean rendering in Word + LibreOffice
SECTION_CAP = 500           # cap items per section to bound doc size
PAGE_EVERY = 50             # page break cadence for long lists
GREEN = RGBColor(0x1A, 0x7F, 0x37)
RED = RGBColor(0xC0, 0x2B, 0x2B)
MUTED = RGBColor(0x80, 0x80, 0x80)
BLUE = RGBColor(0x1F, 0x4E, 0x79)  # audio-sourced rows (Value Updates source col)


def _s(v) -> str:
    return "" if v is None else (v if isinstance(v, str) else str(v))


def _set_run_fonts(run, size=None, bold=None, italic=None, color=None):
    """Set Latin + CJK fonts (and optional size/bold/italic/color) on a run."""
    run.font.name = ASCII_FONT
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic
    if color is not None:
        run.font.color.rgb = color
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    rfonts.set(qn("w:ascii"), ASCII_FONT)
    rfonts.set(qn("w:hAnsi"), ASCII_FONT)
    rfonts.set(qn("w:eastAsia"), CJK_FONT)
    return run


def _para(doc, text="", *, size=None, bold=False, italic=False, align=None, style=None):
    p = doc.add_paragraph(style=style)
    if align is not None:
        p.alignment = align
    if text:
        _set_run_fonts(p.add_run(text), size=size, bold=bold, italic=italic)
    return p


def _heading(doc, text, level=1):
    h = doc.add_heading(level=level)
    _set_run_fonts(h.add_run(text), bold=True)
    return h


def _set_styles_cjk(doc):
    """Set eastAsia font on the base styles so inherited text also renders CJK."""
    try:
        normal = doc.styles["Normal"]
        normal.font.name = ASCII_FONT
        normal.font.size = Pt(11)
    except KeyError:
        pass
    for name in ("Normal", "Title", "Heading 1", "Heading 2"):
        try:
            st = doc.styles[name]
        except KeyError:
            continue
        rpr = st.element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.insert(0, rfonts)
        rfonts.set(qn("w:eastAsia"), CJK_FONT)


def _new_table(doc, headers):
    table = doc.add_table(rows=1, cols=len(headers))
    for style_name in ("Light Grid Accent 1", "Light List Accent 1", "Table Grid"):
        try:
            table.style = style_name
            break
        except KeyError:
            continue
    for cell, txt in zip(table.rows[0].cells, headers):
        _set_cell(cell, txt, bold=True)
    return table


def _set_cell(cell, text, *, bold=False, size=10, color=None):
    cell.text = ""  # drop the default empty paragraph's run
    _set_run_fonts(cell.paragraphs[0].add_run(_s(text)), size=size, bold=bold, color=color)


def _capped(items: list, cap=SECTION_CAP):
    """Return (items[:cap], n_truncated)."""
    items = items or []
    if len(items) > cap:
        return items[:cap], len(items) - cap
    return items, 0


# ── Sections ──────────────────────────────────────────────────────────
def _add_title_page(doc, r):
    _para(doc, "Lifelog Full Report", size=26, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    _para(doc, _s(r.get("source_video")), size=14, align=WD_ALIGN_PARAGRAPH.CENTER)
    _para(doc, f"Recorded {_s(r.get('video_date'))}", size=12, align=WD_ALIGN_PARAGRAPH.CENTER)
    doc.add_paragraph()
    tr = r.get("video_time_range") or {}
    meta = [
        ("Events consolidated", str(r.get("event_count", 0))),
        ("Source model(s)", _s(r.get("source_model"))),
        ("Duration", f"{r.get('duration_sec', 0)} s ({tr.get('start_sec', 0)}–{tr.get('end_sec', 0)} s)"),
        ("OCR items captured", str((r.get("metrics") or {}).get("total_ocr_items_captured", 0))),
        ("Avg recall estimate", f"{(r.get('metrics') or {}).get('recall_estimate_avg', 0)}"),
        ("Audio facts extracted", str((r.get("metrics") or {}).get("audio_facts_extracted", 0))),
        ("Audio-only mentions", str(len(r.get("audio_only_terms") or []))),
        ("Generated", _s((r.get("metadata") or {}).get("generated_at"))),
    ]
    t = _new_table(doc, ["Field", "Value"])
    for k, v in meta:
        cells = t.add_row().cells
        _set_cell(cells[0], k, bold=True)
        _set_cell(cells[1], v)
    doc.add_paragraph()
    _para(doc, "Triple-H Co., Ltd. | Patent No. 10-2025-0145274",
          size=9, italic=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    doc.add_page_break()


def _add_overview_section(doc, r):
    _heading(doc, "Key Findings", 1)
    ov = _s(r.get("overview")).strip()
    _para(doc, ov if ov else "No overview available.", italic=not ov)
    topics = r.get("topics_covered") or []
    if topics:
        _para(doc, "Topics covered", bold=True)
        for t in topics[:SECTION_CAP]:
            _para(doc, _s(t), style="List Bullet")


def _add_observed_facts_section(doc, r):
    facts, extra = _capped(r.get("all_observed_facts"))
    _heading(doc, f"Observed Facts ({len(r.get('all_observed_facts') or [])})", 1)
    if not facts:
        _para(doc, "No observed facts captured.", italic=True)
        return
    for f in facts:
        _para(doc, _s(f), style="List Number")
    if extra:
        _para(doc, f"... and {extra} more", italic=True)


def _add_enumerated_observations_section(doc, r):
    obs, extra = _capped(r.get("all_enumerated_observations"))
    total = len(r.get("all_enumerated_observations") or [])
    _heading(doc, f"Detailed Observations ({total} items)", 1)
    if not obs:
        _para(doc, "No detailed observations captured.", italic=True)
        return
    for i, o in enumerate(obs):
        _para(doc, _s(o), size=10)
        if (i + 1) % PAGE_EVERY == 0 and (i + 1) < len(obs):
            doc.add_page_break()
    if extra:
        _para(doc, f"... and {extra} more", italic=True)


def _add_audio_section(doc, r):
    _heading(doc, "Audio Transcript", 1)
    q = _s(r.get("audio_quality")) or "unknown"
    lang = _s(r.get("language_detected")) or "unknown"
    evs = ", ".join(r.get("audio_events") or []) or "none"
    _para(doc, f"Quality: {q}    Language: {lang}    Events: {evs}", size=10, italic=True)
    transcript = _s(r.get("audio_transcript_full")).strip()
    if not transcript:
        _para(doc, "No audio captured for this clip.", italic=True)
        return
    for block in transcript.split("\n\n"):
        _para(doc, block.strip())


def _add_timeline_section(doc, r):
    _heading(doc, "Timeline", 1)
    tl = r.get("timeline") or []
    if not tl:
        _para(doc, "No timeline windows captured.", italic=True)
        return
    t = _new_table(doc, ["Window (s)", "Summary", "Key items"])
    # Sort chronologically by window start (tie-break by end) — defensive; the
    # aggregator already sorts, but guard against any unsorted input.
    def _bounds(w):
        nums = re.findall(r"\d+(?:\.\d+)?", _s(w.get("window_sec")))
        return (float(nums[0]) if nums else 0.0, float(nums[1]) if len(nums) > 1 else 0.0)
    for w in sorted(tl[:SECTION_CAP], key=_bounds):
        cells = t.add_row().cells
        _set_cell(cells[0], _s(w.get("window_sec")) or "—", bold=True)
        _set_cell(cells[1], _s(w.get("summary")) or "—")
        _set_cell(cells[2], ", ".join(_s(x) for x in (w.get("key_items") or [])) or "—")


def _direction_color(values):
    nums = []
    for v in values or []:
        if not isinstance(v, dict):
            continue
        m = re.search(r"-?\d[\d,\.]*", _s(v.get("value")))
        if m:
            try:
                nums.append(float(m.group(0).replace(",", "")))
            except ValueError:
                pass
    if len(nums) >= 2:
        if nums[-1] > nums[0]:
            return GREEN
        if nums[-1] < nums[0]:
            return RED
    return None


def _add_value_updates_section(doc, r):
    _heading(doc, "Value Updates", 1)
    vus = r.get("value_updates") or []
    if not vus:
        _para(doc, "No metric value changes detected.", italic=True)
        return
    # "Times Observed" (not "Changes"): change_count counts sightings of the
    # value, so on noisy OCR a single snapshot reads as 1 — labeling it
    # "Changes" would falsely imply "changed once".
    # v3.4: a 4th "Source" column attributes each row to Video (OCR) or Audio
    # (transcript). Audio rows are blue; a claim_type, if present, shows as a
    # small muted subtitle under the label. Plain "Audio"/"Video" text (not
    # emoji) keeps rendering identical across MS Word and LibreOffice.
    t = _new_table(doc, ["Label", "Values (in order)", "Times Observed", "Source"])
    for vu in vus[:SECTION_CAP]:
        cells = t.add_row().cells
        is_audio = _s(vu.get("source")) == "audio"
        # Label cell: bold label + optional claim_type subtitle line.
        cells[0].text = ""
        _set_run_fonts(cells[0].paragraphs[0].add_run(_s(vu.get("label"))),
                       size=10, bold=True, color=(BLUE if is_audio else None))
        claim = _s(vu.get("claim_type"))
        if claim:
            sub = cells[0].add_paragraph()
            _set_run_fonts(sub.add_run(claim), size=8, italic=True, color=MUTED)
        vals = vu.get("values") or []
        seq = " → ".join(_s(v.get("value")) for v in vals if isinstance(v, dict)) or "—"
        color = _direction_color(vals) if (vu.get("change_count") or 0) > 1 else None
        _set_cell(cells[1], seq, color=color)
        _set_cell(cells[2], str(vu.get("change_count", len(vals))))
        _set_cell(cells[3], "Audio" if is_audio else "Video",
                  bold=is_audio, color=(BLUE if is_audio else None))


def _add_visual_summary_section(doc, r):
    _heading(doc, "Visual Content", 1)
    v = r.get("visual_summary") or {}

    def _line(label, items):
        items = items or []
        if items:
            _para(doc, f"{label}: ", bold=True)
            _para(doc, " · ".join(_s(x) for x in items[:SECTION_CAP]), size=10)

    _line("Visual objects", v.get("visual_objects"))
    _line("UI elements", v.get("ui_elements"))
    _line("Charts detected", v.get("charts_detected"))
    headlines = v.get("headlines") or []
    if headlines:
        _para(doc, "Headlines", bold=True)
        for h in headlines[:SECTION_CAP]:
            _para(doc, _s(h), style="List Bullet")
    _para(doc,
          f"Panels detected: {v.get('panels_detected_count', 0)}    "
          f"Broadcast mode: {'yes' if v.get('broadcast_mode') else 'no'}",
          size=10, italic=True)


def _add_key_terms_section(doc, r):
    """Prominent: the MEANINGFUL filtered OCR (numbers, prices, names, headlines)."""
    ocr = r.get("all_ocr_text") or []
    items, extra = _capped(ocr)
    _heading(doc, f"Key Terms Captured ({len(ocr)})", 1)
    if not items:
        _para(doc, "No meaningful terms captured.", italic=True)
        return
    _para(doc,
          f"Filtered OCR captured {len(ocr)} meaningful items (numbers, prices, "
          f"names, headlines). The full raw OCR is in the Technical OCR Reference "
          f"appendix.", size=9, italic=True)
    chunk = PAGE_EVERY * 4
    for start in range(0, len(items), chunk):
        seg = items[start:start + chunk]
        _para(doc, " · ".join(_s(x) for x in seg), size=10)
    if extra:
        _para(doc, f"... and {extra} more", italic=True)

    # v3.4: audio-only mentions — values spoken in the transcript but never
    # rendered on screen as OCR text. Hidden entirely when the list is empty.
    audio_only = r.get("audio_only_terms") or []
    if audio_only:
        doc.add_paragraph()
        _para(doc, f"Audio-only Mentions ({len(audio_only)})", bold=True)
        _para(doc, "Items mentioned in the audio transcript but not visible on "
                   "screen as text.", size=9, italic=True)
        ao_items, ao_extra = _capped(audio_only)
        _para(doc, " · ".join(_s(x) for x in ao_items), size=10)
        if ao_extra:
            _para(doc, f"... and {ao_extra} more", italic=True)


def _add_technical_ocr_appendix(doc, r):
    """Demoted: the raw rejected OCR, 8pt, on its own page, marked reference-only."""
    doc.add_page_break()
    items_all = r.get("ocr_appendix_full") or []
    items, extra = _capped(items_all)
    _heading(doc, f"Technical OCR Reference — Appendix ({len(items_all)})", 1)
    _para(doc,
          "For technical verification only. Raw OCR items that did not pass quality "
          "filtering (single characters, particles, OCR fragments, mojibake). Provided "
          "for completeness and debugging.", size=9, italic=True)
    if not items:
        _para(doc, "No additional raw items.", italic=True)
        return
    chunk = PAGE_EVERY * 6
    for start in range(0, len(items), chunk):
        seg = items[start:start + chunk]
        _para(doc, " · ".join(_s(x) for x in seg), size=8)
        if start + chunk < len(items):
            doc.add_page_break()
    if extra:
        _para(doc, f"... and {extra} more", size=8, italic=True)


def _add_metadata_footer(doc, r):
    md = r.get("metadata") or {}
    doc.add_paragraph()
    _para(doc,
          f"Schema {md.get('schema_version', '?')}  |  Source model(s): {_s(r.get('source_model'))}  "
          f"|  Generated {_s(md.get('generated_at'))}  |  AI-glasses lifelog pipeline",
          size=8, italic=True, align=WD_ALIGN_PARAGRAPH.CENTER)


def generate_word_report(report: dict) -> BytesIO:
    """Build the .docx from an aggregated report dict; return a seek(0) BytesIO."""
    doc = Document()
    _set_styles_cjk(doc)
    _add_title_page(doc, report)
    _add_overview_section(doc, report)
    _add_observed_facts_section(doc, report)
    # Detailed Observations intentionally NOT rendered in the .docx (v3.3 decision):
    # observed_facts (~48) already covers the micro-details, and a separate section
    # was redundant. The enumerated_observations field is still in the JSON API.
    _add_audio_section(doc, report)
    _add_timeline_section(doc, report)
    _add_value_updates_section(doc, report)
    _add_visual_summary_section(doc, report)
    _add_key_terms_section(doc, report)        # prominent: meaningful OCR
    _add_technical_ocr_appendix(doc, report)   # demoted: raw rejected OCR (8pt)
    _add_metadata_footer(doc, report)
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf
