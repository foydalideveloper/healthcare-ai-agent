"""Query DB events and compute PER-CHUNK consensus for dataset building (Job 2).

Read-only. Reuses Job 1's `compute_consensus_facts` (and preserves its determinism
property). Three realities of this DB, verified in Phase 0, drive the design:

1. The VLM fields (`observed_facts`, `video_extraction`, `audio_extraction`) are NOT
   top-level columns — they live inside the `raw_event` JSONB and are only readable
   after FLATTENING raw_event into the row (exactly as the /full-report endpoint does).
   Selecting `observed_facts` as a column 400s.
2. Chunks are keyed by `chunk_idx` (0, 1, …). `start_sec`/`end_sec` are NULL in this DB,
   so they cannot be used to group or window.
3. The same table holds non-VLM (food/activity) events with no `observed_facts`; those
   arms can't contribute consensus and are filtered out.
"""
from __future__ import annotations

from collections import defaultdict

from app.database import get_db_admin
from app.services.consensus_enricher import ArmFactsInput, compute_consensus_facts


def flatten_raw_event(rows: list[dict]) -> list[dict]:
    """Spread each row's `raw_event` JSONB up to the top level (first-wins, never
    overwrites an existing key), matching the /full-report endpoint's flatten so
    `observed_facts` etc. become readable. Mutates and returns the same list."""
    for row in rows:
        extras = row.pop("raw_event", None) or {}
        for k, v in extras.items():
            if k not in row:
                row[k] = v
    return rows


def _arms_with_facts(events: list[dict]) -> set[str]:
    """Distinct source_models in `events` that contributed >=1 non-empty observed_fact."""
    arms: set[str] = set()
    for e in events:
        arm = e.get("source_model")
        if arm and any(isinstance(f, str) and f.strip() for f in (e.get("observed_facts") or [])):
            arms.add(arm)
    return arms


async def list_multi_arm_videos(min_arms: int = 2) -> dict[str, set[str]]:
    """Census of `{source_video: {arms}}` for videos with >= min_arms distinct
    source_model. Uses only REAL columns (cheap) and paginates past PostgREST's
    default row cap so the census is complete."""
    db = get_db_admin()
    by_video: dict[str, set[str]] = defaultdict(set)
    offset, page = 0, 1000
    while True:
        resp = await db._client.get("/lifelog_event", params=[
            ("select", "source_video,source_model"),
            ("order", "source_video.asc,source_model.asc"),
            ("limit", str(page)),
            ("offset", str(offset)),
        ])
        resp.raise_for_status()
        batch = resp.json()
        if not isinstance(batch, list) or not batch:
            break
        for r in batch:
            v, m = r.get("source_video"), r.get("source_model")
            if v and m:
                by_video[v].add(m)
        if len(batch) < page:
            break
        offset += page
    return {v: arms for v, arms in by_video.items() if len(arms) >= min_arms}


async def fetch_events_for_video(source_video: str) -> list[dict]:
    """Every event row for one video, `raw_event` flattened. No user filter, so
    consensus spans ALL arms. Ordered by (observed_at, chunk_idx)."""
    db = get_db_admin()
    resp = await db._client.get("/lifelog_event", params=[
        ("select", "*"),
        ("source_video", f"eq.{source_video}"),
        ("order", "observed_at.asc"),
    ])
    resp.raise_for_status()
    rows = resp.json()
    return flatten_raw_event(rows if isinstance(rows, list) else [])


async def fetch_multi_arm_events(min_arms: int = 2) -> dict[str, list[dict]]:
    """`{source_video: [flattened events]}` for videos with >= min_arms distinct arms
    that ALSO have >= min_arms arms contributing non-empty `observed_facts` (i.e. real
    VLM clips — food/activity-only clips are excluded since they can't yield consensus)."""
    candidates = await list_multi_arm_videos(min_arms)
    out: dict[str, list[dict]] = {}
    for video in sorted(candidates):
        events = await fetch_events_for_video(video)
        if len(_arms_with_facts(events)) >= min_arms:
            out[video] = events
    return out


def group_events_into_chunks(events: list[dict]) -> dict[int, list[dict]]:
    """Group flattened events by `chunk_idx` (the real chunk key — start_sec/end_sec
    are NULL in this DB). Returns `{chunk_idx: [events]}` ordered by chunk_idx."""
    by_chunk: dict[int, list[dict]] = defaultdict(list)
    for e in events:
        ci = e.get("chunk_idx")
        ci = int(ci) if isinstance(ci, (int, float)) and not isinstance(ci, bool) else 0
        by_chunk[ci].append(e)
    return dict(sorted(by_chunk.items()))


def compute_per_chunk_consensus(
    chunk_events: list[dict],
    min_agreement_fraction: float = 0.67,
) -> list[dict]:
    """Per-CHUNK consensus (finer than Job 1's per-VIDEO consensus), reusing Job 1's
    algorithm + adaptive threshold. Arms are sorted (alphabetical) before clustering
    so the result is deterministic regardless of event order. Returns serialized dicts."""
    arm_to_facts: dict[str, list[str]] = defaultdict(list)
    for e in chunk_events:
        arm = e.get("source_model")
        if not arm:
            continue
        for f in (e.get("observed_facts") or []):
            if isinstance(f, str) and f.strip():
                arm_to_facts[arm].append(f.strip())
    if len(arm_to_facts) < 2:
        return []  # need >=2 arms for consensus
    arm_inputs = [ArmFactsInput(arm_id=a, observed_facts=fs)
                  for a, fs in sorted(arm_to_facts.items())]
    consensus = compute_consensus_facts(
        arm_inputs,
        min_agreement_count=None,            # adaptive max(2, round(arms*fraction))
        min_agreement_fraction=min_agreement_fraction,
    )
    return [
        {
            "fact": c.fact,
            "confidence": c.confidence,
            "agreement_count": c.agreement_count,
            "total_arms": c.total_arms,
            "agreeing_arms": c.agreeing_arms,
        }
        for c in consensus
    ]
