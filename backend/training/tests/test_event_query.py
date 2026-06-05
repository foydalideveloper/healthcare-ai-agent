"""Unit tests for Job 2 event_query (pure functions — no DB).

Run: {venv} -m pytest backend/training/tests/test_event_query.py -v
"""
import random
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]  # .../backend
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from training.event_query import (  # noqa: E402
    flatten_raw_event,
    group_events_into_chunks,
    compute_per_chunk_consensus,
)


def _ev(arm, chunk_idx, facts):
    return {"source_model": arm, "chunk_idx": chunk_idx, "observed_facts": list(facts)}


# 1 — flatten surfaces raw_event JSONB but never overwrites an existing key
def test_flatten_surfaces_raw_event():
    rows = [{"source_model": "a", "video_extraction": {"ocr_text_full": ["x"]},
             "raw_event": {"observed_facts": ["f1", "f2"], "source_model": "SHOULD_NOT_WIN"}}]
    out = flatten_raw_event(rows)
    assert out[0]["observed_facts"] == ["f1", "f2"]      # surfaced from raw_event
    assert out[0]["source_model"] == "a"                  # existing key not overwritten
    assert "raw_event" not in out[0]                      # raw_event popped


# 2 — group by chunk_idx, sorted; missing/non-numeric chunk_idx -> 0
def test_group_by_chunk_idx():
    evs = [_ev("a", 1, ["x"]), _ev("b", 0, ["y"]), {"source_model": "c", "observed_facts": ["z"]}]
    grouped = group_events_into_chunks(evs)
    assert list(grouped.keys()) == [0, 1]                 # sorted; 'c' (no chunk_idx) -> 0
    assert len(grouped[0]) == 2 and len(grouped[1]) == 1


# 3 — two arms agreeing on enough facts -> consensus (adaptive thr for 2 arms = 2)
def test_per_chunk_consensus_basic():
    shared = ["KOSPI is at 8,228.70.", "Samsung at 307,000 won.", "SK Hynix at 2,243,000 won."]
    evs = [_ev("arm_a", 0, shared), _ev("arm_b", 0, shared)]
    cons = compute_per_chunk_consensus(evs)
    assert len(cons) == 3
    assert all(c["agreement_count"] == 2 and c["total_arms"] == 2 for c in cons)
    assert all(c["confidence"] == 1.0 for c in cons)


# 4 — a chunk with only one arm yields no consensus
def test_single_arm_chunk_no_consensus():
    evs = [_ev("arm_a", 0, ["a", "b", "c"]), _ev("arm_a", 0, ["d"])]  # same arm twice
    assert compute_per_chunk_consensus(evs) == []


# 5 — empty inputs don't crash
def test_empty_events_returns_empty():
    assert group_events_into_chunks([]) == {}
    assert compute_per_chunk_consensus([]) == []


# 6 — determinism: shuffled event order -> identical consensus (preserves Job 1 property)
def test_determinism_preserved():
    facts_a = ["KOSPI is at 8,228.70.", "Samsung at 307,000 won.", "A unique to a."]
    facts_b = ["The KOSPI index is at 8,228.70.", "Samsung at 307,000 won.", "B unique to b."]
    facts_c = ["KOSPI is at 8228.70", "Samsung at 307,000 won.", "C unique to c."]
    base = [_ev("arm_a", 0, facts_a), _ev("arm_b", 0, facts_b), _ev("arm_c", 0, facts_c)]
    ref = compute_per_chunk_consensus(base)
    for seed in range(5):
        shuffled = base[:]
        random.Random(seed).shuffle(shuffled)
        assert compute_per_chunk_consensus(shuffled) == ref
