"""Unit tests for Job 2 label_filter (pure).

Run: {venv} -m pytest backend/training/tests/test_label_filter.py -v
"""
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from training.label_filter import (  # noqa: E402
    filter_high_confidence_only,
    split_by_confidence_tier,
    has_sufficient_labels,
)


def _f(conf):
    return {"fact": f"fact@{conf}", "confidence": conf}


def test_filter_high_only_threshold_inclusive():
    out = filter_high_confidence_only([_f(0.83), _f(1.0)])
    assert len(out) == 2                       # 0.83 is kept (>=)


def test_filter_high_only_below_threshold():
    out = filter_high_confidence_only([_f(0.82), _f(0.67)])
    assert out == []                           # 0.82 excluded


def test_split_by_tier_correct_buckets():
    tiers = split_by_confidence_tier([_f(1.0), _f(0.83), _f(0.75), _f(0.67)])
    assert {f["confidence"] for f in tiers["high"]} == {1.0, 0.83}
    assert {f["confidence"] for f in tiers["medium"]} == {0.75, 0.67}


def test_split_by_tier_no_double_counting():
    facts = [_f(1.0), _f(0.83), _f(0.7), _f(0.67)]
    tiers = split_by_confidence_tier(facts)
    ids_high = {id(f) for f in tiers["high"]}
    ids_med = {id(f) for f in tiers["medium"]}
    assert ids_high.isdisjoint(ids_med)        # each fact in exactly one tier
    assert len(tiers["high"]) + len(tiers["medium"]) == len(facts)


def test_has_sufficient_labels_boundary():
    assert has_sufficient_labels([_f(0.9), _f(0.9)], min_count=3) is False   # 2 < 3
    assert has_sufficient_labels([_f(0.9), _f(0.9), _f(0.9)], min_count=3) is True  # 3 == 3


def test_empty_input_returns_empty():
    assert filter_high_confidence_only([]) == []
    assert split_by_confidence_tier([]) == {"high": [], "medium": []}
    assert has_sufficient_labels([]) is False
