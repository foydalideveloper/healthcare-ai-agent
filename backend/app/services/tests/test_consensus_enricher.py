"""Unit tests for cross-arm consensus enrichment (consensus_enricher).

Pure module — no pipeline / DB imports. Covers the spec's 12 behaviors plus 4
adaptive-threshold tests (the threshold auto-computes from the arm count).

Run: {venv} -m pytest backend/app/services/tests/test_consensus_enricher.py -v
"""
import sys
from pathlib import Path

# Put backend/ on sys.path so `app.services...` resolves regardless of rootdir.
_BACKEND = Path(__file__).resolve().parents[3]  # .../backend
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.consensus_enricher import (  # noqa: E402
    ArmFactsInput,
    ConsensusFact,
    compute_consensus_facts,
    consensus_facts_to_dict_list,
    resolve_min_agreement,
)


def _arms(*fact_lists) -> list[ArmFactsInput]:
    """Build N ArmFactsInput from N lists of facts (arm ids arm0..armN-1)."""
    return [ArmFactsInput(arm_id=f"arm{i}", observed_facts=list(fl))
            for i, fl in enumerate(fact_lists)]


# 1
def test_identical_facts_form_consensus():
    fact = "KOSPI is at 8,228.70."
    arms = _arms([fact], [fact], [fact], [fact])  # 4 arms identical
    out = compute_consensus_facts(arms)  # adaptive thr = round(4*0.67)=3
    assert len(out) == 1
    assert out[0].confidence == 1.0
    assert out[0].agreement_count == 4
    assert out[0].total_arms == 4


# 2
def test_below_threshold_no_consensus():
    fact = "Samsung at 307,000 won."
    # 3 of 6 arms have the fact; adaptive thr for 6 arms = 4 -> no consensus.
    arms = _arms([fact], [fact], [fact], ["other a"], ["other b"], ["other c"])
    out = compute_consensus_facts(arms)
    assert out == []


# 3
def test_paraphrased_facts_clustered():
    arms = _arms(
        ["KOSPI is at 8228.70"],
        ["The KOSPI index is at 8,228.70"],
        ["KOSPI is at 8228.70"],
        ["The KOSPI index is at 8,228.70"],
    )
    out = compute_consensus_facts(arms)
    assert len(out) == 1               # all four collapsed into one cluster
    assert out[0].agreement_count == 4


# 4
def test_korean_facts_preserved():
    fact = "삼성전자는 307,000원입니다."
    arms = _arms([fact], [fact], [fact], [fact])
    out = compute_consensus_facts(arms)
    assert len(out) == 1
    assert out[0].fact == fact          # Korean preserved verbatim, not lowercased


# 5
def test_number_comma_normalization():
    arms = _arms(
        ["Index closed at 8,228.70"],
        ["Index closed at 8228.70"],
        ["Index closed at 8,228.70"],
        ["Index closed at 8228.70"],
    )
    out = compute_consensus_facts(arms)
    assert len(out) == 1                # comma-variant numbers match


# 6
def test_canonical_form_is_longest():
    # Two phrasings that DO cluster (>=0.75 similarity, same family as test #3)
    # but differ in length -> the longer/more specific one wins as canonical.
    short = "KOSPI is at 8,228.70."
    longn = "The KOSPI index is at 8,228.70."
    arms = _arms([short], [longn], [short], [longn])
    out = compute_consensus_facts(arms)
    assert len(out) == 1
    assert out[0].fact == longn         # longest variant is canonical
    assert len(longn) > len(short)


# 7
def test_empty_input_returns_empty():
    assert compute_consensus_facts([]) == []


# 8
def test_single_arm_returns_empty():
    arms = _arms(["KOSPI is at 8,228.70.", "KOSDAQ is at 1,133.13."])
    # 1 arm: adaptive thr = max(2, round(1*0.67)) = 2 -> impossible -> empty.
    assert compute_consensus_facts(arms) == []


# 9
def test_arm_with_empty_facts_skipped():
    fact = "KOSPI is at 8,228.70."
    arms = _arms([fact], [], [fact], [fact], [])  # 5 arms, 2 empty
    out = compute_consensus_facts(arms)            # thr = round(5*0.67)=3
    assert len(out) == 1
    assert out[0].agreement_count == 3             # only the 3 non-empty arms


# 10
def test_sort_order():
    unanimous = "KOSPI is at 8,228.70."
    partial = "KOSDAQ is at 1,133.13."
    # unanimous in 4/4; partial in 3/4. Both >= thr(3). Sorted conf DESC.
    arms = _arms(
        [unanimous, partial],
        [unanimous, partial],
        [unanimous, partial],
        [unanimous],
    )
    out = compute_consensus_facts(arms)
    assert len(out) == 2
    assert out[0].confidence >= out[1].confidence
    assert out[0].fact == unanimous and out[0].confidence == 1.0


# 11
def test_serialization_round_trip():
    import json
    fact = "KOSPI is at 8,228.70."
    out = compute_consensus_facts(_arms([fact], [fact], [fact], [fact]))
    dicts = consensus_facts_to_dict_list(out)
    s = json.dumps(dicts, ensure_ascii=False)       # must be JSON-serializable
    back = json.loads(s)
    assert back[0]["fact"] == fact
    assert set(back[0].keys()) == {
        "fact", "confidence", "agreeing_arms", "agreement_count", "total_arms"}


# 12
def test_different_facts_not_collapsed():
    a = "KOSPI at 8228"
    b = "KOSDAQ at 1133"
    arms = _arms([a, b], [a, b], [a, b], [a, b])
    out = compute_consensus_facts(arms)
    assert len(out) == 2                            # distinct facts stay separate
    facts = {c.fact for c in out}
    assert a in facts and b in facts


# --- Adaptive threshold tests ---

# 13
def test_4_arms_threshold_is_3():
    assert resolve_min_agreement(4) == 3            # round(4*0.67)=3


# 14
def test_6_arms_threshold_is_4():
    assert resolve_min_agreement(6) == 4            # round(6*0.67)=4


# 15
def test_2_arms_threshold_is_2():
    assert resolve_min_agreement(2) == 2            # floor of 2 (round(2*0.67)=1 -> 2)
    assert resolve_min_agreement(1) == 2            # floor still 2


# 16
def test_explicit_min_overrides_fraction():
    assert resolve_min_agreement(6, min_agreement_count=5) == 5
    fact = "KOSPI is at 8,228.70."
    # 4 arms with fact; force min=4 -> qualifies; force min=5 -> not.
    arms = _arms([fact], [fact], [fact], [fact])
    assert len(compute_consensus_facts(arms, min_agreement_count=4)) == 1
    assert compute_consensus_facts(arms, min_agreement_count=5) == []
