"""Filter cross-arm consensus facts into training-quality labels (Job 2, read-only).

Consensus facts arrive already above the adaptive consensus threshold (>=0.67 by
construction in event_query). This layer splits them into confidence tiers for
multi-target training and gates out chunks with too few labels to be useful.

Boundary semantics (explicit, `>=`):
  confidence == 0.83  -> high
  confidence == 0.67  -> medium
  confidence  < 0.67  -> excluded (shouldn't occur; filtered upstream)
"""
from __future__ import annotations

HIGH_CONFIDENCE = 0.83
MEDIUM_CONFIDENCE = 0.67


def filter_high_confidence_only(consensus_facts: list[dict], min_confidence: float = HIGH_CONFIDENCE) -> list[dict]:
    """Keep only facts at >= min_confidence (default 0.83 == >=5/6 arms, or 4/4 on 4-arm clips)."""
    return [f for f in consensus_facts if f.get("confidence", 0.0) >= min_confidence]


def split_by_confidence_tier(
    consensus_facts: list[dict],
    high_threshold: float = HIGH_CONFIDENCE,
    medium_threshold: float = MEDIUM_CONFIDENCE,
) -> dict[str, list[dict]]:
    """Split into {'high': >=high, 'medium': medium<=c<high}. Strictly disjoint —
    a fact lands in exactly one tier (medium is < high, no double-counting)."""
    high = [f for f in consensus_facts if f.get("confidence", 0.0) >= high_threshold]
    medium = [
        f for f in consensus_facts
        if medium_threshold <= f.get("confidence", 0.0) < high_threshold
    ]
    return {"high": high, "medium": medium}


def has_sufficient_labels(consensus_facts: list[dict], min_count: int = 3) -> bool:
    """True if a chunk has >= min_count labels — fewer is too little signal to train on."""
    return len(consensus_facts) >= min_count
