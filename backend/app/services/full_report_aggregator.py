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
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# The quality filter lives in backend/glasses_watcher/ (this file is in
# backend/app/services/). It's pure (only `re`) — importing it does NOT pull in
# paddle/torch. parents[2] == .../backend; glasses_watcher resolves as a
# namespace package from there.
_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
from glasses_watcher.ocr_quality_filter import (  # noqa: E402
    filter_ocr_items,
    filter_enumerated_observations,
)
# Audio-OCR cross-reference layer (v3.4). Pure stdlib module, sibling in
# app/services — no pipeline imports pulled in.
from app.services.audio_fact_extractor import (  # noqa: E402
    extract_audio_facts,
    cross_reference_with_ocr,
    promote_to_value_updates,
    extract_audio_only_terms,
)

SCHEMA_VERSION = "v3.4"  # v3.4: audio-OCR cross-reference layer (additive)
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


# v3.3 polish: drop low-information "filler" facts (generic ambient state with
# no specific value). Facts containing a number/price/% are always kept.
_FILLER_PATTERNS = [
    re.compile(r"\bis still\b", re.I),
    re.compile(r"\bare still\b", re.I),
    re.compile(r"\bstill (display|run|show|on\b|active|present|visible|spinning)", re.I),
    re.compile(r"\bcontinues?\b", re.I),
    re.compile(r"\bremains? (consistent|unchanged|the same|stable|on|active)\b", re.I),
    re.compile(r"\bnearing (its )?end\b", re.I),
    re.compile(r"\b(concluding|wrapping up|coming to an end|about to end|drawing to a close)\b", re.I),
    re.compile(r"\bis being (shown|displayed|played)\b", re.I),
    re.compile(r"\b(user|viewer|person) is (observing|watching|looking at|viewing)\b", re.I),
    re.compile(r"\b(lighting|room lighting|the room|the lighting) (is|remains|stays) "
               r"(consistent|stable|unchanged|dim|bright|the same)\b", re.I),
    re.compile(r"\bfan is (still )?(running|on|spinning|active)\b", re.I),
    # v3.3 polish round 2 — escaped-filler patterns:
    re.compile(r"\bis finishing\b", re.I),
    re.compile(r"\bhas been about\b", re.I),
    re.compile(r"\bthe overall scene is\b", re.I),
    re.compile(r"\bvoice is clear\b", re.I),
    re.compile(r"\bfocused on\b", re.I),
]


def _is_substantive_fact(f: str) -> bool:
    """Keep facts with a value/number; drop generic ambient-state filler."""
    f = (f or "").strip()
    if not f:
        return False
    if re.search(r"\d", f):  # prices / %, dates, counts → always substantive
        return True
    return not any(p.search(f) for p in _FILLER_PATTERNS)


def _semantic_dedup(items: list[str], thresh: float = 0.7) -> list[str]:
    """Collapse near-duplicate sentences (reworded triplicates). Two items are
    duplicates if one normalized form contains the other (>=8 chars) OR their
    difflib ratio >= thresh. Keeps the most SPECIFIC (longest) of a cluster,
    preserving first-seen order."""
    from difflib import SequenceMatcher

    def _toks(s: str) -> set:
        return set(re.findall(r"[a-z0-9가-힣]+", s.lower()))

    kept: list[str] = []
    kept_norm: list[str] = []
    kept_tok: list[set] = []
    for it in items:
        n = _norm_ocr(it)
        if not n:
            continue
        tk = _toks(it)
        hit = -1
        for i, kn in enumerate(kept_norm):
            shorter, longer = (n, kn) if len(n) <= len(kn) else (kn, n)
            ratio = SequenceMatcher(None, n, kn).ratio()
            # token overlap (Jaccard) catches SHORT restatements that share the
            # same entity/content but reword the rest ("source is KBS" 3 ways) —
            # gated to short facts so longer specific facts aren't over-merged.
            jac = len(tk & kept_tok[i]) / max(1, len(tk | kept_tok[i]))
            short_both = len(n) <= 90 and len(kn) <= 90
            if (len(shorter) >= 8 and shorter in longer) or ratio >= thresh \
               or (short_both and jac >= 0.5):
                hit = i
                break
        if hit >= 0:
            if len(it) > len(kept[hit]):  # prefer the more specific wording
                kept[hit] = it
                kept_norm[hit] = n
                kept_tok[hit] = tk
        else:
            kept.append(it)
            kept_norm.append(n)
            kept_tok.append(tk)
    return kept


def _dedup_objects(items: list[str], head_merge: bool = False) -> list[str]:
    """Dedup visual objects / UI elements: case-insensitive exact, plus drop any
    item that is a substring of a kept item (or vice versa) — 'news anchor' vs
    'news anchor (on screen)'. With head_merge, also merge items sharing the same
    head noun (last token, >=3 chars) — 'desk fan' vs 'electric fan'. Keeps the
    more specific (longer) wording."""
    def _head(s: str) -> str:
        toks = re.findall(r"[a-z0-9가-힣]+", s.lower())
        return toks[-1] if toks else ""
    kept: list[str] = []
    for it in _dedup_lower(items):
        il = it.lower()
        merged = False
        for i, k in enumerate(kept):
            kl = k.lower()
            if il in kl or kl in il or (head_merge and len(_head(it)) >= 3 and _head(it) == _head(k)):
                if len(it) > len(kept[i]):
                    kept[i] = it
                merged = True
                break
        if not merged:
            kept.append(it)
    return kept


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

    def _bounds(win: str) -> tuple:
        nums = re.findall(r"\d+(?:\.\d+)?", win)
        start = float(nums[0]) if nums else 0.0
        end = float(nums[1]) if len(nums) > 1 else start
        return (start, end)  # tie-break by end so 0-5 sorts before 0-15

    windows = []
    for key in sorted(by_window, key=_bounds):
        slot = by_window[key]
        windows.append({
            "window_sec": key,
            "summary": " | ".join(_dedup_exact(slot["_summaries"])),
            "key_items": _dedup_exact(slot["key_items"]),
        })

    # Collapse overlapping windows (e.g. chunk-1's "0-5" inside chunk-0's
    # "0-15"): merge the smaller into the larger so readers see clean,
    # non-overlapping windows. Process larger windows first as anchors.
    out: list[dict] = []
    for w in sorted(windows, key=lambda x: (_bounds(x["window_sec"])[1] - _bounds(x["window_sec"])[0]), reverse=True):
        ws, we = _bounds(w["window_sec"])
        host = None
        for h in out:
            hs, he = _bounds(h["window_sec"])
            if ws >= hs and we <= he and not (ws == hs and we == he):  # strictly contained
                host = h
                break
        if host:
            if w["summary"]:
                host["summary"] = " | ".join(_dedup_exact(
                    [s for s in [host["summary"], w["summary"]] if s]))
            host["key_items"] = _dedup_exact(host["key_items"] + w["key_items"])
        else:
            out.append(w)
    return sorted(out, key=lambda x: _bounds(x["window_sec"]))


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
        "visual_objects": _dedup_objects(visual_objects, head_merge=True),
        "ui_elements": _dedup_objects(ui_elements),
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
        "all_observed_facts": [], "all_enumerated_observations": [],
        "enumerated_dropped_count": 0,
        "all_ocr_text": [], "ocr_appendix_full": [],
        "audio_transcript_full": "", "audio_quality": "", "audio_events": [],
        "language_detected": "",
        "timeline": [], "value_updates": [],
        "audio_only_terms": [],
        "visual_summary": {
            "visual_objects": [], "ui_elements": [], "charts_detected": [],
            "headlines": [], "panels_detected_count": 0, "broadcast_mode": False,
        },
        "metrics": {
            "total_ocr_items_captured": 0, "total_enumerated_observations": 0,
            "recall_estimate_avg": 0.0, "frame_sampling_rate_used": 0,
            "meaningful_ocr_items": 0, "filtered_ocr_items": 0,
            "meaningful_observations": 0, "filtered_observations": 0,
            "audio_facts_extracted": 0, "audio_facts_cross_referenced": 0,
            "audio_only_facts": 0,
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

    # Topics: drop weak filler topics ("News conclusion." etc.).
    _topic_filler = re.compile(r"\b(conclusion|wrap.?up|ending|end of (the )?(broadcast|report|news))\b", re.I)
    topics_covered = [t for t in _dedup_exact([_as_str(e.get("topic")).strip() for e in events])
                      if not _topic_filler.search(t)]

    # Visual summary computed early so observed_facts can drop headline-fragment
    # facts ("The text 'X' is visible." where X is already in a headline).
    visual_summary = _build_visual_summary(events)
    _headlines_norm = [_norm_ocr(h) for h in visual_summary["headlines"] if _norm_ocr(h)]

    def _is_headline_fragment(fact: str) -> bool:
        m = re.search(r"['\"`](.+?)['\"`]", fact)
        if not m:
            return False
        q = _norm_ocr(m.group(1))
        return len(q) >= 4 and any(q in h for h in _headlines_norm)

    # v3.3 polish: exact-dedup → drop filler + headline-fragments → collapse
    # reworded near-duplicates.
    _facts = [f for f in _dedup_exact(
        [f for e in events for f in _as_list(e.get("observed_facts"))])
        if _is_substantive_fact(f) and not _is_headline_fragment(f)]
    all_observed_facts = _semantic_dedup(_facts)
    all_enumerated = _semantic_dedup(_dedup_exact(
        [o for e in events for o in _as_list(e.get("enumerated_observations"))]))

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
    # visual_summary already computed above (needed for headline-fragment filter).

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

    # === v3.3 quality filter pass ===
    # all_ocr_text becomes the MEANINGFUL subset (same field name, cleaner data);
    # the rejected items move to the NEW ocr_appendix_full (raw, for reference).
    # Enumerations are split the same way. total_*_captured keeps the full count
    # (meaningful + filtered) so "how much was captured" stays comparable.
    ocr_meaningful, ocr_filtered = filter_ocr_items(all_ocr_text)
    enum_meaningful, enum_dropped = filter_enumerated_observations(all_enumerated)

    report = {
        "source_video": source_video,
        "source_model": source_model,
        "event_count": len(events),
        "video_date": video_date,
        "video_time_range": {"start_sec": start_sec, "end_sec": end_sec},
        "duration_sec": duration_sec,
        "overview": overview,
        "topics_covered": topics_covered,
        "all_observed_facts": all_observed_facts,
        "all_enumerated_observations": enum_meaningful,
        "enumerated_dropped_count": len(enum_dropped),
        "all_ocr_text": ocr_meaningful,
        "ocr_appendix_full": ocr_filtered,
        "audio_transcript_full": audio_transcript_full,
        "audio_quality": _worst_quality(qualities),
        "audio_events": _dedup_exact(audio_events_all),
        "language_detected": _most_common(langs),
        "timeline": timeline,
        "value_updates": value_updates,
        "visual_summary": visual_summary,
        "metrics": {
            "total_ocr_items_captured": len(ocr_meaningful) + len(ocr_filtered),
            "total_enumerated_observations": len(enum_meaningful) + len(enum_dropped),
            "recall_estimate_avg": round(sum(recalls) / len(recalls), 3) if recalls else 0.0,
            "frame_sampling_rate_used": max(fsr) if fsr else 0,
            "meaningful_ocr_items": len(ocr_meaningful),
            "filtered_ocr_items": len(ocr_filtered),
            "meaningful_observations": len(enum_meaningful),
            "filtered_observations": len(enum_dropped),
        },
        "metadata": {
            "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
            "schema_version": SCHEMA_VERSION,
        },
    }

    # === Audio-OCR cross-reference layer (v3.4) ============================
    # PURELY ADDITIVE post-processing: parse the (already-built) transcript for
    # structured facts, cross-reference against the OCR text, then ADD audio-
    # derived value_updates (source="audio") + an audio_only_terms list. The
    # existing OCR-derived value_updates are tagged source="video" but otherwise
    # untouched. Nothing existing is removed or renamed. Empty/garbled transcript
    # degrades to no-op (audio_facts == []).
    transcript = report.get("audio_transcript_full", "")
    audio_facts = extract_audio_facts(transcript)
    ocr_items_for_xref = report.get("all_ocr_text", []) + report.get("ocr_appendix_full", [])
    also_in_ocr, audio_only_facts = cross_reference_with_ocr(audio_facts, ocr_items_for_xref)

    report["value_updates"] = promote_to_value_updates(audio_facts, report.get("value_updates", []))
    report["audio_only_terms"] = extract_audio_only_terms(audio_only_facts)
    report["metrics"]["audio_facts_extracted"] = len(audio_facts)
    report["metrics"]["audio_facts_cross_referenced"] = len(also_in_ocr)
    report["metrics"]["audio_only_facts"] = len(audio_only_facts)

    return report
