"""Cross-arm consensus enrichment (Self-Improvement Job 1).

The lifelog pipeline runs N LLM arms in parallel (Gemma 4, Qwen, Llama 4, three
Gemini variants), each producing its own observed_facts for the same source video.
This module compares those per-arm facts and surfaces the ones that MULTIPLE arms
independently agree on, tagging each with a cross-arm confidence score.

The boss-demo win: "every consensus fact comes with a cross-model agreement score."
The flywheel value: consensus facts become the auto-labels for Job 2's fine-tuning
dataset, which trains the local Gemma in Job 3.

PURE module — no extraction-pipeline / DB / network imports. Fully unit-testable.
Stdlib only (re, difflib). Korean text is preserved verbatim (never lowercased).

Threshold is ADAPTIVE: with no explicit min_agreement_count, consensus requires
~67% of the arms present (floor 2), so it reads sensibly at 4, 6, or 8 arms and
scales automatically as more arms populate future clips.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

# Confidence badge tiers (fraction of arms agreeing). Adaptive across arm counts:
#   6 arms -> HIGH = 5-6/6 (>=83%), MEDIUM = 4/6 (67%)
#   4 arms -> HIGH = 4/4 (100%),    MEDIUM = 3/4 (75%)
HIGH_CONFIDENCE_FRACTION = 0.83
MEDIUM_CONFIDENCE_FRACTION = 0.67

# Default consensus threshold as a fraction of arms present (when no explicit
# min_agreement_count is given). 0.67 == "more than two-thirds of our LLMs agreed".
DEFAULT_MIN_AGREEMENT_FRACTION = 0.67


@dataclass
class ArmFactsInput:
    """Per-arm input for consensus computation."""
    arm_id: str  # e.g., 'gemma4_26b_a4b_it_q8_0'
    observed_facts: list[str]


@dataclass
class ConsensusFact:
    """A fact with cross-arm agreement metadata."""
    fact: str  # canonical form (longest / most informative variant)
    confidence: float  # 0.0-1.0 == agreement_count / total_arms
    agreeing_arms: list[str]  # which arms reported it (sorted)
    agreement_count: int  # how many arms agreed
    total_arms: int  # how many arms were compared


# === Fact normalization (for matching) ===

def _normalize_for_match(fact: str) -> str:
    """Normalize a fact string for fuzzy matching.

    - Lowercase Latin letters only (Korean preserved as-is, never mangled)
    - Strip ends, collapse internal whitespace, drop a trailing period
    - Remove digit-group commas so '8,228.70' matches '8228.70'
    """
    text = fact.strip().rstrip(".")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(\d),(\d)", r"\1\2", text)  # number commas
    # Lowercase only ASCII letters; preserve every non-ASCII char (Korean) verbatim.
    text = "".join(c.lower() if c.isascii() and c.isalpha() else c for c in text)
    return text


def _fact_similarity(a: str, b: str) -> float:
    """Similarity of two normalized facts via SequenceMatcher (Ratcliff-Obershelp).
    1.0 == identical, 0.0 == completely different."""
    return SequenceMatcher(None, a, b).ratio()


def _are_facts_equivalent(fact_a: str, fact_b: str, threshold: float = 0.75) -> bool:
    """Whether two facts are 'the same fact' for consensus purposes.

    Exact normalized match, else normalized-form similarity >= threshold. The 0.75
    default is conservative — it prefers keeping distinct facts separate (false
    negatives) over collapsing genuinely different facts (false positives), so a
    consensus claim is never an artifact of over-merging.
    """
    norm_a = _normalize_for_match(fact_a)
    norm_b = _normalize_for_match(fact_b)
    if norm_a == norm_b:
        return True
    return _fact_similarity(norm_a, norm_b) >= threshold


# === Consensus computation ===

def resolve_min_agreement(
    total_arms: int,
    min_agreement_count: int | None = None,
    min_agreement_fraction: float = DEFAULT_MIN_AGREEMENT_FRACTION,
) -> int:
    """Resolve the agreement threshold (number of arms) for `total_arms`.

    If `min_agreement_count` is given, it is used verbatim. Otherwise it is
    auto-computed as max(2, round(total_arms * min_agreement_fraction)) — a floor
    of 2 keeps "consensus" meaningful (a single arm can never self-agree).
    """
    if min_agreement_count is not None:
        return min_agreement_count
    return max(2, round(total_arms * min_agreement_fraction))


def compute_consensus_facts(
    arm_inputs: list[ArmFactsInput],
    min_agreement_count: int | None = None,
    min_agreement_fraction: float = DEFAULT_MIN_AGREEMENT_FRACTION,
    similarity_threshold: float = 0.75,
) -> list[ConsensusFact]:
    """Compute cross-arm consensus facts.

    Algorithm:
    1. For each arm's facts, attempt to match against existing clusters.
    2. If a match is found (similarity >= threshold), add the arm to that cluster.
    3. If no match, create a new cluster.
    4. Clusters reaching >= the resolved agreement threshold become consensus facts.
    5. Canonical form = the longest variant in the cluster (most informative).

    Note: the same arm reporting a fact twice does not inflate agreement — agreement
    is counted over DISTINCT arms (a set), so confidence reflects cross-arm support.

    Args:
        arm_inputs: per-arm facts.
        min_agreement_count: explicit threshold; None -> adaptive (see resolve_min_agreement).
        min_agreement_fraction: fraction used when min_agreement_count is None (default 0.67).
        similarity_threshold: fact similarity to count as 'same fact' (default 0.75).

    Returns:
        list[ConsensusFact] sorted by confidence DESC, then fact text ASC.
    """
    if not arm_inputs:
        return []

    total_arms = len(arm_inputs)
    threshold = resolve_min_agreement(total_arms, min_agreement_count, min_agreement_fraction)

    # Determinism: greedy single-link clustering is order-sensitive, so canonicalize
    # the input order. Process arms by sorted arm_id, and within each arm seed with
    # the longest facts first (longer == more specific representative, and ties broken
    # alphabetically). This makes the result a function of the INPUT SET, independent
    # of DB row order — the consensus count can't silently flap between identical runs.
    ordered_arms = sorted(arm_inputs, key=lambda a: a.arm_id)

    # Each cluster: {representative_fact, agreeing_arms: set, variants: list}
    clusters: list[dict] = []

    for arm_input in ordered_arms:
        arm_id = arm_input.arm_id
        ordered_facts = sorted(
            (f for f in arm_input.observed_facts if (f or "").strip()),
            key=lambda f: (-len(f.strip()), f.strip()),
        )
        for fact in ordered_facts:
            fact = fact.strip()
            if not fact:
                continue
            matched = False
            for cluster in clusters:
                if _are_facts_equivalent(fact, cluster["representative_fact"], similarity_threshold):
                    cluster["agreeing_arms"].add(arm_id)
                    cluster["variants"].append(fact)
                    # Promote the longer/more specific wording as representative.
                    if len(fact) > len(cluster["representative_fact"]):
                        cluster["representative_fact"] = fact
                    matched = True
                    break
            if not matched:
                clusters.append({
                    "representative_fact": fact,
                    "agreeing_arms": {arm_id},
                    "variants": [fact],
                })

    consensus: list[ConsensusFact] = []
    for cluster in clusters:
        agreement_count = len(cluster["agreeing_arms"])
        if agreement_count >= threshold:
            consensus.append(ConsensusFact(
                fact=cluster["representative_fact"],
                confidence=agreement_count / total_arms,
                agreeing_arms=sorted(cluster["agreeing_arms"]),
                agreement_count=agreement_count,
                total_arms=total_arms,
            ))

    consensus.sort(key=lambda c: (-c.confidence, c.fact))
    return consensus


def consensus_facts_to_dict_list(facts: list[ConsensusFact]) -> list[dict]:
    """Serialize ConsensusFact instances for JSON output."""
    return [
        {
            "fact": f.fact,
            "confidence": round(f.confidence, 3),
            "agreeing_arms": f.agreeing_arms,
            "agreement_count": f.agreement_count,
            "total_arms": f.total_arms,
        }
        for f in facts
    ]
