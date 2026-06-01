"""Lifelog events API — serves rows from the `lifelog_event` table.

Single endpoint reads all events for a user on a given day (KST), ordered
chronologically. Powers the `/lifelog` dashboard page (Daily Lifelog view).

Filters:
  - user_id (required)
  - date (YYYY-MM-DD, treated as KST day)
  - source_model (optional) — 'gemma_4_e4b' | 'qwen_3_5_vlm' | 'llama_4_maverick'
  - category (optional)

Returns:
  { "events": [ {lifelog_id, observed_at, category, ...}, ... ] }
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, StreamingResponse

from app.database import get_db_admin
from app.services.full_report_aggregator import aggregate_events_to_full_report
from app.services.word_exporter import generate_word_report

_DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

router = APIRouter(prefix="/lifelog", tags=["lifelog"])

_KST = timezone(timedelta(hours=9))


@router.get("/events")
async def lifelog_events(
    user_id: int = Query(..., description="User ID"),
    date: str = Query(..., description="YYYY-MM-DD (treated as KST day)"),
    source_model: Optional[str] = Query(None, description="'gemma_4_e4b' | 'qwen_3_5_vlm' | 'llama_4_maverick'"),
    category: Optional[str] = Query(None, description="filter by event category"),
    limit: int = Query(2000, ge=1, le=10000),
):
    """Returns one row per extracted event for the given (user, day)."""
    try:
        year, month, day = map(int, date.split("-"))
        kst_start = datetime(year, month, day, 0, 0, 0, tzinfo=_KST)
        kst_end = kst_start + timedelta(days=1)
    except Exception:
        return {"events": [], "error": f"invalid date: {date!r}"}

    db = get_db_admin()
    # Base columns + v3/v3.1 fields (migrations 007/008, already applied).
    base_select = (
        "lifelog_id,user_id,observed_at,duration_sec,category,"
        "description,people,people_count,location,indoor_outdoor,"
        "posture,mood,energy_signs,objects,screen,topic,decision,"
        "audio_heard,numbers_mentioned,kcal,amount_ml,source_model,"
        "source_video,chunk_idx,raw_event,"
        # v3 modality fields (migration 007)
        "video_extraction,audio_extraction,combined_analysis,"
        "ocr_text_full,recall_estimate,broadcast_mode,"
        # v3.1 OCR recall fields (migration 008)
        "frame_sampling_rate,panels_detected,value_updates,timeline"
    )
    # v3.2 columns (migration 009). Selected only opportunistically: if 009
    # hasn't been applied yet, PostgREST 400s with code 42703 and we transparently
    # retry with base_select — so the dashboard never goes blank during the
    # migration window (this project repeatedly hits code-before-migration races).
    optional_cols = ["enumerated_observations"]

    def _params(select_str: str):
        p = [
            ("select",       select_str),
            ("user_id",      f"eq.{user_id}"),
            ("observed_at",  f"gte.{kst_start.isoformat()}"),
            ("observed_at",  f"lt.{kst_end.isoformat()}"),
            ("order",        "observed_at.asc"),
            ("limit",        str(limit)),
        ]
        if source_model:
            p.append(("source_model", f"eq.{source_model}"))
        if category:
            p.append(("category", f"eq.{category}"))
        return p

    resp = await db._client.get(
        "/lifelog_event", params=_params(base_select + "," + ",".join(optional_cols)))
    if resp.status_code == 400 and "42703" in resp.text:
        resp = await db._client.get("/lifelog_event", params=_params(base_select))
    resp.raise_for_status()
    rows = resp.json()
    if not isinstance(rows, list):
        return {"events": [], "count": 0}

    # Spread the catch-all `raw_event` JSONB into each row so the frontend
    # sees v2 fields (confidence, observed_facts, screen_analysis, etc.)
    # as flat properties. Real top-level columns always win over JSON keys
    # of the same name so we don't accidentally overwrite mapped data with
    # a stale prompt artefact.
    for row in rows:
        extras = row.pop("raw_event", None) or {}
        for k, v in extras.items():
            if k not in row:
                row[k] = v

    return {"events": rows, "count": len(rows)}


# ──────────────────────────────────────────────────────────────────────
# Full Report — consolidate ALL events for one source_video into one view
# ──────────────────────────────────────────────────────────────────────

async def _fetch_events_for_video(
    user_id: int, source_video: str, source_model: Optional[str],
) -> list[dict]:
    """Fetch every event row for one (user, source_video[, source_model]) and
    flatten raw_event into each row (so VLM fields like observed_facts / topic
    are readable alongside the v3 JSONB columns). Mirrors the /events pattern."""
    db = get_db_admin()
    params = [
        ("select", "*"),
        ("user_id", f"eq.{user_id}"),
        ("source_video", f"eq.{source_video}"),
        ("order", "observed_at.asc"),
    ]
    if source_model:
        params.append(("source_model", f"eq.{source_model}"))
    resp = await db._client.get("/lifelog_event", params=params)
    resp.raise_for_status()
    rows = resp.json()
    if not isinstance(rows, list):
        return []
    for row in rows:
        extras = row.pop("raw_event", None) or {}
        for k, v in extras.items():
            if k not in row:
                row[k] = v
    return rows


@router.get("/full-report")
async def lifelog_full_report(
    source_video: str = Query(..., description="e.g. 20260528144922838.mp4"),
    user_id: int = Query(1, description="User ID"),
    source_model: Optional[str] = Query(
        None, description="one arm's tag; omit to aggregate ALL arms"),
):
    """Consolidate every event for one source_video into one comprehensive
    report (arm-scoped by default; cross-arm when source_model is omitted)."""
    try:
        events = await _fetch_events_for_video(user_id, source_video, source_model)
    except httpx.TimeoutException:
        return JSONResponse(
            {"error": "supabase timeout", "source_video": source_video}, status_code=504)
    except Exception as e:  # network / PostgREST error — surface, don't 500 opaquely
        return JSONResponse(
            {"error": f"{type(e).__name__}: {str(e)[:200]}", "source_video": source_video},
            status_code=502)
    if not events:
        return JSONResponse(
            {"error": "No events found", "source_video": source_video}, status_code=404)
    return aggregate_events_to_full_report(events)


@router.get("/full-report.docx")
async def lifelog_full_report_docx(
    source_video: str = Query(..., description="e.g. 20260528144922838.mp4"),
    user_id: int = Query(1, description="User ID"),
    source_model: Optional[str] = Query(None, description="omit to aggregate ALL arms"),
):
    """Stream the consolidated report as a Word .docx (same data as /full-report)."""
    try:
        events = await _fetch_events_for_video(user_id, source_video, source_model)
    except httpx.TimeoutException:
        return JSONResponse({"error": "supabase timeout"}, status_code=504)
    except Exception as e:
        return JSONResponse(
            {"error": f"{type(e).__name__}: {str(e)[:200]}"}, status_code=502)
    if not events:
        return JSONResponse(
            {"error": "No events found", "source_video": source_video}, status_code=404)

    report = aggregate_events_to_full_report(events)
    buf = generate_word_report(report)  # seek(0) BytesIO

    safe = source_video.replace(".mp4", "").replace(".", "_")
    stamp = _re_compact_date(report.get("video_date", ""))
    arm = source_model or "all-arms"
    filename = f"lifelog_report_{safe}_{arm}_{stamp}.docx".replace(" ", "_")
    return StreamingResponse(
        buf,
        media_type=_DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _re_compact_date(d: str) -> str:
    """'2026-06-01' -> '20260601' (best-effort; empty if unparseable)."""
    return "".join(ch for ch in (d or "") if ch.isdigit())[:8]
