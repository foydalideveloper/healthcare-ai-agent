"""Consolidate N lifelog events from the same source_video into ONE report.

A 60s clip yields several event cards (one per topic segment the LLM finds).
The dashboard's "Full Report" feature needs a single comprehensive view across
all of them. This module is a PURE function over already-fetched Supabase rows
(no I/O), so it is trivially testable and never touches extraction logic.

Rows are expected to be "flattened" (raw_event spread into the top level, as the
/events endpoint does), so VLM fields like observed_facts/topic/segment_summary
are readable alongside the v3 JSONB columns (video/audio/combined_extraction,
enumerated_observations, panels_detected, value_updates, timeline).

Everything is defensive: missing / null / wrong-typed fields degrade to empty,
never crash. Korean text is preserved verbatim (callers serialize as UTF-8).
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "v3.2"
_QUALITY_RANK = {"poor": 0, "partial": 1, "good": 2}  # for "worst quality"


# ── small coercion helpers (Supabase JSONB can come back null / wrong type) ──
def _as_list(v: Any) -> list:
    return v if isinstance(v, list) else []


def _as_dict(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


def _as_str(v: Any) -> str:
    if v is None:
        return ""
    return v if isinstance(v, str) else str(v)


def _as_num(v: Any):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _norm_ocr(text: str) -> str:
    """Case-insensitive + whitespace-normalized key for OCR dedup."""
    return re.sub(r"\s+", " ", text.strip()).lower()


def _dedup_exact(items: list[str]) -> list[str]:
    """Exact-match dedup, order preserved (first occurrence wins)."""
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        s = _as_str(it)
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _dedup_norm(items: list[str]) -> list[str]:
    """Normalized-key dedup, keep ORIGINAL casing of first occurrence."""
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        s = _as_str(it)
        key = _norm_ocr(s)
        if key and key not in seen:
            seen.add(key)
            out.append(s)
    return out


def _dedup_lower(items: list[str]) -> list[str]:
    """Lowercase-key dedup (visual objects), keep original casing."""
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        s = _as_str(it).strip()
        key = s.lower()
        if key and key not in seen:
            seen.add(key)
            out.append(s)
    return out


def _worst_quality(qs: list[str]) -> str:
    ranked = [q for q in qs if q in _QUALITY_RANK]
    if not ranked:
        return ""
    return min(ranked, key=lambda q: _QUALITY_RANK[q])


def _most_common(items: list[str]) -> str:
    vals = [i for i in items if i]
    return Counter(vals).most_common(1)[0][0] if vals else ""


def _combined(e: dict) -> dict:
    """combined_analysis dict for an event (always a dict)."""
    return _as_dict(e.get("combined_analysis"))


def _nested_or_top(e: dict, key: str) -> list:
    """v3.1 fields (value_updates/timeline) live nested in combined_analysis on
    most rows but may also be top-level columns — prefer whichever is populated."""
    c = _combined(e)
    nested = _as_list(c.get(key))
    if nested:
        return nested
    return _as_list(e.get(key))


# ── timeline + value_updates merges ──────────────────────────────────────
def _merge_timeline(events: list[dict]) -> list[dict]:
    """Merge each event's 4 windows by `window_sec`: concat summaries with ' | ',
    union + dedup key_items. Output ordered by the window's start second."""
    by_window: dict[str, dict] = {}
    for e in events:
        for w in _nested_or_top(e, "timeline"):
            if not isinstance(w, dict):
                continue
            key = _as_str(w.get("window_sec")).strip()
            if not key:
                continue
            slot = by_window.setdefault(key, {"window_sec": key, "_summaries": [], "key_items": []})
            summ = _as_str(w.get("summary")).strip()
            if summ:
                slot["_summaries"].append(summ)
            slot["key_items"].extend(_as_str(x) for x in _as_list(w.get("key_items")))

    def _start(win: str) -> float:
        m = re.match(r"\s*(\d+(?:\.\d+)?)", win)
        return float(m.group(1)) if m else 0.0

    out = []
    for key in sorted(by_window, key=_start):
        slot = by_window[key]
        out.append({
            "window_sec": key,
            "summary": " | ".join(_dedup_exact(slot["_summaries"])),
            "key_items": _dedup_exact(slot["key_items"]),
        })
    return out


def _merge_value_updates(events: list[dict]) -> list[dict]:
    """Group value_updates by `label`; merge `values` arrays, dedup by `value`."""
    by_label: dict[str, dict] = {}
    for e in events:
        for vu in _nested_or_top(e, "value_updates"):
            if not isinstance(vu, dict):
                continue
            label = _as_str(vu.get("label")).strip()
            if not label:
                continue
            slot = by_label.setdefault(label, {"label": label, "_values": [], "_seen": set()})
            for val in _as_list(vu.get("values")):
                if not isinstance(val, dict):
                    continue
                vkey = _as_str(val.get("value"))
                if vkey and vkey not in slot["_seen"]:
                    slot["_seen"].add(vkey)
                    slot["_values"].append(val)
    out = []
    for label, slot in by_label.items():
        vals = slot["_values"]
        out.append({
            "label": label,
            "values": vals,
            "change_count": len(vals),
            "first_seen_sec": min((_as_num(v.get("timestamp_sec")) or 0) for v in vals) if vals else 0,
            "last_seen_sec": max((_as_num(v.get("timestamp_sec")) or 0) for v in vals) if vals else 0,
        })
    return out


def _build_visual_summary(events: list[dict]) -> dict:
    visual_objects: list[str] = []
    ui_elements: list[str] = []
    charts: list[str] = []
    headlines: list[str] = []
    panels_count = 0
    broadcast = False
    for e in events:
        ve = _as_dict(e.get("video_extraction"))
        visual_objects.extend(_as_str(x) for x in _as_list(ve.get("visual_objects")))
        sc = _as_dict(ve.get("screen_content"))
        ui_elements.extend(_as_str(x) for x in _as_list(sc.get("ui_elements")))
        charts.extend(_as_str(x) for x in _as_list(sc.get("charts")))
        headlines.extend(_as_str(x) for x in _as_list(sc.get("headlines")))
        # panels_detected lives nested in video_extraction (preferred) or top-level
        panels = _as_list(ve.get("panels_detected")) or _as_list(e.get("panels_detected"))
        panels_count += len(panels)
        if (ve.get("broadcast_mode") is True) or (e.get("broadcast_mode") is True):
            broadcast = True
    return {
        "visual_objects": _dedup_lower(visual_objects),
        "ui_elements": _dedup_exact(ui_elements),
        "charts_detected": _dedup_lower(charts),
        "headlines": _dedup_exact(headlines),
        "panels_detected_count": panels_count,
        "broadcast_mode": broadcast,
    }


def _empty_report(generated_at: str | None = None) -> dict:
    return {
        "source_video": "", "source_model": "", "event_count": 0,
        "video_date": "", "video_time_range": {"start_sec": 0, "end_sec": 0},
        "duration_sec": 0,
        "overview": "", "topics_covered": [],
        "all_observed_facts": [], "all_enumerated_observations": [], "all_ocr_text": [],
        "audio_transcript_full": "", "audio_quality": "", "audio_events": [],
        "language_detected": "",
        "timeline": [], "value_updates": [],
        "visual_summary": {
            "visual_objects": [], "ui_elements": [], "charts_detected": [],
            "headlines": [], "panels_detected_count": 0, "broadcast_mode": False,
        },
        "metrics": {
            "total_ocr_items_captured": 0, "total_enumerated_observations": 0,
            "recall_estimate_avg": 0.0, "frame_sampling_rate_used": 0,
        },
        "metadata": {
            "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
            "schema_version": SCHEMA_VERSION,
        },
    }


def aggregate_events_to_full_report(events: list[dict], generated_at: str | None = None) -> dict:
    """Aggregate events (same source_video) into one consolidated report dict.

    `generated_at` is injectable for deterministic tests; defaults to now (UTC).
    """
    if not events:
        return _empty_report(generated_at)

    # Order by recording time (observed_at is a real column; start_sec is not).
    events = sorted(events, key=lambda e: (_as_str(e.get("observed_at")), _as_num(e.get("chunk_idx")) or 0))

    source_video = _as_str(events[0].get("source_video"))
    models = sorted({_as_str(e.get("source_model")) for e in events if e.get("source_model")})
    source_model = models[0] if len(models) == 1 else "multi-arm"
    video_date = _as_str(events[0].get("observed_at"))[:10]

    starts = [_as_num(e.get("start_sec")) for e in events if _as_num(e.get("start_sec")) is not None]
    ends = [_as_num(e.get("end_sec")) for e in events if _as_num(e.get("end_sec")) is not None]
    durs = [_as_num(e.get("duration_sec")) for e in events if _as_num(e.get("duration_sec")) is not None]
    start_sec = min(starts) if starts else 0
    end_sec = max(ends) if ends else (max(durs) if durs else 0)
    duration_sec = (end_sec - start_sec) if end_sec else (max(durs) if durs else 0)

    # Overview = combined what_is_happening / segment_summary / description, deduped.
    overviews = []
    for e in events:
        w = (_as_str(_combined(e).get("what_is_happening")).strip()
             or _as_str(e.get("segment_summary")).strip()
             or _as_str(e.get("description")).strip())
        if w:
            overviews.append(w)
    overview = " ".join(_dedup_exact(overviews))

    topics_covered = _dedup_exact([_as_str(e.get("topic")).strip() for e in events])

    all_observed_facts = _dedup_exact(
        [f for e in events for f in _as_list(e.get("observed_facts"))])
    all_enumerated = _dedup_exact(
        [o for e in events for o in _as_list(e.get("enumerated_observations"))])

    # OCR: union of video_extraction.ocr_text_full + the flat ocr_text_full string.
    ocr_items: list[str] = []
    for e in events:
        ve = _as_dict(e.get("video_extraction"))
        ocr_items.extend(_as_str(x) for x in _as_list(ve.get("ocr_text_full")))
        flat = _as_str(e.get("ocr_text_full"))
        if flat:
            ocr_items.extend(line for line in flat.split("\n") if line.strip())
    all_ocr_text = _dedup_norm(ocr_items)

    # Audio: order-preserving EXACT dedup of transcripts. (The same per-chunk
    # Whisper transcript is attached to every event of that chunk, so naive
    # concatenation would repeat it N times; exact-dedup keeps distinct segments
    # in order while collapsing those identical repeats.)
    transcripts, qualities, audio_events_all, langs = [], [], [], []
    for e in events:
        ae = _as_dict(e.get("audio_extraction"))
        tf = _as_str(ae.get("transcript_full")).strip()
        if tf:
            transcripts.append(tf)
        q = _as_str(ae.get("audio_quality"))
        if q:
            qualities.append(q)
        audio_events_all.extend(_as_str(x) for x in _as_list(ae.get("audio_events")))
        lang = _as_str(ae.get("language_detected"))
        if lang:
            langs.append(lang)
    uniq_transcripts = _dedup_exact(transcripts)
    audio_transcript_full = (
        "\n\n--- next segment ---\n\n".join(uniq_transcripts)
        if len(uniq_transcripts) > 1 else (uniq_transcripts[0] if uniq_transcripts else ""))

    timeline = _merge_timeline(events)
    value_updates = _merge_value_updates(events)
    visual_summary = _build_visual_summary(events)

    # recall_estimate: prefer combined_analysis.recall_estimate, fall back to column.
    recalls = []
    for e in events:
        r = _as_num(_combined(e).get("recall_estimate"))
        if r is None:
            r = _as_num(e.get("recall_estimate"))
        if r is not None:
            recalls.append(r)
    fsr = [_as_num(e.get("frame_sampling_rate")) for e in events
           if _as_num(e.get("frame_sampling_rate")) is not None]
    # fall back to nested video_extraction.frame_sampling_rate
    for e in events:
        n = _as_num(_as_dict(e.get("video_extraction")).get("frame_sampling_rate"))
        if n is not None:
            fsr.append(n)

    return {
        "source_video": source_video,
        "source_model": source_model,
        "event_count": len(events),
        "video_date": video_date,
        "video_time_range": {"start_sec": start_sec, "end_sec": end_sec},
        "duration_sec": duration_sec,
        "overview": overview,
        "topics_covered": topics_covered,
        "all_observed_facts": all_observed_facts,
        "all_enumerated_observations": all_enumerated,
        "all_ocr_text": all_ocr_text,
        "audio_transcript_full": audio_transcript_full,
        "audio_quality": _worst_quality(qualities),
        "audio_events": _dedup_exact(audio_events_all),
        "language_detected": _most_common(langs),
        "timeline": timeline,
        "value_updates": value_updates,
        "visual_summary": visual_summary,
        "metrics": {
            "total_ocr_items_captured": len(all_ocr_text),
            "total_enumerated_observations": len(all_enumerated),
            "recall_estimate_avg": round(sum(recalls) / len(recalls), 3) if recalls else 0.0,
            "frame_sampling_rate_used": max(fsr) if fsr else 0,
        },
        "metadata": {
            "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
            "schema_version": SCHEMA_VERSION,
        },
    }
