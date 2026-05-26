"""HRT Multi-Dimensional Drill-Down API
Patent Feature: Lifelong Health Record (birth to 120 years)
4-Level drill-down: Year -> Month -> Day -> Hour

Updated 2026-04-22 (Phase 2):
  - /drilldown now returns the complete DrilldownResponse shape matching
    frontend/hrt-dashboard/app/components/DrilldownGrid.tsx DrilldownResponse.
  - Backed by hrt_drilldown_full() SQL function (migration 004).
  - Single RPC call returns all 7 categories pre-aggregated.

Updated 2026-05-07:
  - /detail for category="food" now queries user_food_log directly
    (`hrt_event_detail` RPC was returning [] for hours that have rows;
    bypass it for the food category so the dashboard's per-item pill
    breakdown actually populates with real kcal numbers).
"""

import re
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Query
from app.database import get_db_admin

router = APIRouter(prefix="/hrt", tags=["hrt-drilldown"])

_KST = timezone(timedelta(hours=9))

# Mirror migration 006's hydration regex so the food endpoint excludes
# drink rows (the SQL function does this automatically; our direct-SELECT
# fast path for category="food" must do it too — otherwise rows like
# 'drink (cup)' appear in both Food & Nutrition and Hydration views).
_DRINK_TOKENS = (
    "drink", "water", "coffee", "tea", "juice", "milk",
    "물", "커피", "차", "주스", "우유", "홍차", "녹차", "아이스티", "라떼",
)
# Words like "fruit drink" (the suffix) should still count as drinks. The
# SQL has a `food_sfx_re` exclusion for things ending in food-suffixes;
# we don't currently have any such names being written, so we don't need it.
_LATIN_DRINK_RE = re.compile(
    r"\b(" + "|".join(t for t in _DRINK_TOKENS if t.isascii()) + r")\b",
    re.IGNORECASE,
)
_NON_LATIN_DRINK = tuple(t for t in _DRINK_TOKENS if not t.isascii())


def _is_drink_name(name: str) -> bool:
    if not name:
        return False
    if _LATIN_DRINK_RE.search(name):
        return True
    if any(tok in name for tok in _NON_LATIN_DRINK):
        return True
    return False


@router.get("/drilldown")
async def drilldown(
    user_id: int = Query(..., description="User ID"),
    level: int = Query(1, ge=1, le=4, description="Drill-down level: 1=year, 2=month, 3=day, 4=hour"),
    year: int | None = Query(None, description="Year (required for level 2+)"),
    month: int | None = Query(None, ge=1, le=12, description="Month (required for level 3+)"),
    day: int | None = Query(None, ge=1, le=31, description="Day (required for level 4)"),
):
    """Multi-dimensional HRT drill-down for all 7 categories.

    Returns shape matching frontend's DrilldownResponse interface:
      {
        "level": int,
        "columns": [{ "key": str, "label": str }],
        "rows": [
          {
            "category_id": str,       # 'food'|'exercise'|'sleep'|'medicine'|'biometrics'|'mental'|'hydration'
            "category_name": str,
            "category_icon": str,
            "cells": { [colKey]: { "value": str, "count": int, "intensity": int, "details"?: list } }
          }
        ]
      }

    Level 1: /hrt/drilldown?user_id=1&level=1
      → Yearly summary (columns: 2020-2026, 7 category rows)

    Level 2: /hrt/drilldown?user_id=1&level=2&year=2026
      → Monthly breakdown for the year (columns: Jan-Dec)

    Level 3: /hrt/drilldown?user_id=1&level=3&year=2026&month=4
      → Daily detail for the month (columns: 1-30/31)

    Level 4: /hrt/drilldown?user_id=1&level=4&year=2026&month=4&day=17
      → Hourly detail for the day (columns: 00:00-23:00)
    """
    db = get_db_admin()
    result = await db.rpc(
        "hrt_drilldown_full_unchecked",
        {
            "p_user_id": user_id,
            "p_level":   level,
            "p_year":    year,
            "p_month":   month,
            "p_day":     day,
        },
    )
    # The function returns a JSONB object already matching DrilldownResponse.
    # Return it directly so the dashboard's fetch().json() receives the right shape.
    return result


@router.get("/detail")
async def event_detail(
    user_id: int = Query(..., description="User ID"),
    category: str = Query(..., description="food|hydration|medicine|exercise|sleep|biometrics|mental"),
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    day: int = Query(..., ge=1, le=31),
    hour: int | None = Query(None, ge=0, le=23, description="Omit for whole day"),
):
    """Returns individual events for a given (user, category, day, hour)
    so the DetailPanel can render a REAL timeline — not hardcoded mock."""
    db = get_db_admin()

    # Food category: direct SELECT against user_food_log. The hrt_event_detail
    # RPC (created out-of-band, not in our migrations) returns [] for hours
    # that have real rows — likely a timestamptz/KST-vs-UTC mismatch in the
    # WHERE clause we can't audit because the function body isn't local.
    # Querying the table directly produces correct per-item kcal for the
    # dashboard's hourly pill breakdown.
    if category == "food":
        kst_start = datetime(year, month, day, hour or 0, 0, 0, tzinfo=_KST)
        kst_end = kst_start + (timedelta(hours=1) if hour is not None else timedelta(days=1))
        # PostgREST accepts the same column filter twice (gte AND lt) as
        # repeated query params; httpx serializes a list-of-tuples that way.
        params_list = [
            ("select",       "food_id,consumed_at,food_name,portion_g,nutrients_json"),
            ("user_id",      f"eq.{user_id}"),
            ("consumed_at",  f"gte.{kst_start.isoformat()}"),
            ("consumed_at",  f"lt.{kst_end.isoformat()}"),
            ("order",        "consumed_at.asc"),
        ]
        # Reuse the same admin httpx client db.select uses internally.
        resp = await db._client.get("/user_food_log", params=params_list)
        resp.raise_for_status()
        rows = resp.json()
        # Build the realEvents shape DetailPanel expects:
        #   { time: "HH:MM", label: <food_name>, detail?: <portion>, value: "<kcal> kcal" }
        # Exclude drinks from the food category (mirroring migration 006's
        # `NOT (food_name ~* v_drink_re AND food_name !~* v_food_sfx_re)`).
        events = []
        for r in rows or []:
            name = r.get("food_name") or ""
            if _is_drink_name(name):
                continue  # Hydration handles drink rows
            ts = r.get("consumed_at") or ""
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(_KST)
                tstr = dt.strftime("%H:%M")
            except Exception:
                tstr = ""
            nut = r.get("nutrients_json") or {}
            kcal = nut.get("energy_kcal")
            portion_g = r.get("portion_g")
            events.append({
                "time":   tstr,
                "label":  name,
                "detail": (f"{int(portion_g)}g" if portion_g else None),
                "value":  (f"{int(round(kcal))} kcal" if kcal is not None else ""),
            })
        return {"events": events}

    # All other categories: existing RPC path.
    events = await db.rpc(
        "hrt_event_detail",
        {
            "p_user_id":  user_id,
            "p_category": category,
            "p_year":     year,
            "p_month":    month,
            "p_day":      day,
            "p_hour":     hour,
        },
    )
    return {"events": events or []}


@router.get("/categories")
async def get_categories():
    """Get all HRT category definitions for the drill-down grid Y-axis."""
    db = get_db_admin()
    result = await db.select("hrt_categories", order="display_order.asc")
    return {"categories": result}


@router.get("/summary/{user_id}")
async def get_lifetime_summary(user_id: int):
    """Legacy endpoint — returns Level 1 drill-down in the old grouped format.
    Kept for backward compatibility with earlier callers.
    """
    db = get_db_admin()
    result = await db.rpc(
        "hrt_drilldown",  # old function, food-only
        {"p_user_id": user_id, "p_level": 1},
    )

    grid = {}
    if result:
        for item in result:
            year = item.get("year")
            cat  = item.get("category")
            if year not in grid:
                grid[year] = {}
            grid[year][cat] = {
                "value": item.get("value"),
                "unit":  item.get("unit"),
                "count": item.get("event_count"),
            }

    return {
        "user_id":    user_id,
        "grid":       grid,
        "years":      sorted(grid.keys()),
        "categories": ["food", "exercise", "sleep", "medicine", "biometric"],
    }
