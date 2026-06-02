"""Audio-OCR cross-reference layer: parse the Whisper transcript for structured
facts (numbers, %, currency, entities), then cross-reference them against the
OCR text so audio-mentioned values can flow into the Value Updates table and a
dedicated "Audio-only mentions" Key-Terms sub-section.

PURE module — depends ONLY on the stdlib (`re`, `dataclasses`, `typing`). It
imports nothing from the extraction pipeline, so it is trivially unit-testable
and can never regress OCR/LLM behaviour. It is consumed at aggregator time
(post-processing); it never re-extracts or touches Supabase.

Korean text is preserved verbatim (callers serialize UTF-8). All functions are
defensive: empty / None / garbled input degrades to an empty result, never
crashes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# ============================================================================
# Recognized entities (overlap with ocr_quality_filter is OK — independent copy)
# ============================================================================

KOREAN_FINANCIAL_ENTITIES = frozenset([
    "삼성전자", "SK하이닉스", "SK스퀘어", "현대차", "삼성전기",
    "마이크론", "Micron",
    "KOSPI", "KOSDAQ", "코스피", "코스닥",
    "USD", "KRW", "달러", "원",
    "UBS", "한국은행",
    "ETF", "레버리지",
])

# Entity ranking/context phrases that mark meaningful claims.
RANKING_PHRASES = frozenset([
    "세계 1위", "세계 2위", "세계 3위", "세계 4위", "세계 5위",
    "첫 번째", "두 번째", "세 번째",
    "국내 1위", "국내 2위", "국내 3위",
    "최고가", "신고가", "최저가",
])

# ============================================================================
# Pattern definitions (ordered; first match wins per span via non-overlap)
# ============================================================================

CURRENCY_VALUE_PATTERNS = [
    # Korean trillion won/usd: "1,600조 원", "1조 달러"
    (re.compile(r'(\d+(?:,\d+)*)\s*조\s*(원|달러|엔|위안)'), 'trillion_currency'),
    # Korean won amounts: "307,000원", "30만 7천 원"
    (re.compile(r'(\d+(?:,\d+)*)\s*만\s*\d*\s*천?\s*원'), 'won'),
    # Percentages: "2.7%", "9.3%", "19%"
    (re.compile(r'(\d+(?:\.\d+)?)\s*%'), 'percentage'),
    # USD amounts: "$535", "$1,625"
    (re.compile(r'\$(\d+(?:,\d+)*)'), 'usd'),
    # Year ranges: "3년에서 5년"
    (re.compile(r'(\d+)년에서\s*(\d+)년'), 'year_range'),
    # Multipliers: "3배", "2배"
    (re.compile(r'(\d+)배'), 'multiplier'),
]


# ============================================================================
# Data class
# ============================================================================

@dataclass
class AudioFact:
    """A structured fact extracted from the transcript."""
    raw_match: str               # The matched text, e.g. "1,600조 원"
    value: str                   # Normalized value, e.g. "1,600조 원"
    unit_type: str               # 'trillion_currency', 'won', 'percentage', ...
    context_left: str            # Up to 30 chars before match
    context_right: str           # Up to 30 chars after match
    entity: Optional[str]        # Detected entity (e.g. "SK하이닉스") or None
    claim_type: Optional[str]    # 'market_cap', 'gain', 'target_price', ... or None
    char_position: int           # Position in transcript


# ============================================================================
# Public API
# ============================================================================

def extract_audio_facts(transcript: str) -> list:
    """Parse transcript for structured facts (numbers, percentages, entities).

    Returns a list of AudioFact in transcript order. Empty list if the
    transcript is empty/None. Spans are de-overlapped so a "won" amount that
    also contains a bare number isn't double-counted by the percentage/number
    patterns.
    """
    if not transcript or not transcript.strip():
        return []

    facts: list = []
    claimed: list = []  # (start, end) spans already consumed by a stronger pattern
    for pattern, unit_type in CURRENCY_VALUE_PATTERNS:
        for match in pattern.finditer(transcript):
            s, e = match.start(), match.end()
            # Skip if this span overlaps one already captured by an earlier
            # (higher-priority) pattern — e.g. the "원" inside "1,600조 원".
            if any(s < ce and e > cs for cs, ce in claimed):
                continue
            claimed.append((s, e))

            context_left = transcript[max(0, s - 30):s]
            context_right = transcript[e:min(len(transcript), e + 30)]
            entity = _detect_entity_in_context(context_left, context_right)
            claim_type = _detect_claim_type(context_left, context_right, unit_type)

            facts.append(AudioFact(
                raw_match=match.group(0).strip(),
                value=match.group(0).strip(),
                unit_type=unit_type,
                context_left=context_left,
                context_right=context_right,
                entity=entity,
                claim_type=claim_type,
                char_position=s,
            ))

    facts.sort(key=lambda f: f.char_position)
    return facts


def _detect_entity_in_context(left: str, right: str) -> Optional[str]:
    """Find the nearest financial entity in the surrounding context.

    Left context wins (the entity usually precedes the value in Korean); among
    left matches the CLOSEST to the value (largest index) is preferred. Falls
    back to the closest right-context entity. Returns None if none found.
    """
    best_ent = None
    best_idx = -1
    for ent in KOREAN_FINANCIAL_ENTITIES:
        i = left.rfind(ent)
        if i > best_idx:
            best_idx = i
            best_ent = ent
    if best_ent is not None:
        return best_ent

    best_ent = None
    best_idx = len(right) + 1
    for ent in KOREAN_FINANCIAL_ENTITIES:
        i = right.find(ent)
        if i != -1 and i < best_idx:
            best_idx = i
            best_ent = ent
    return best_ent


def _detect_claim_type(left: str, right: str, unit_type: str) -> Optional[str]:
    """Heuristically classify what kind of claim a value represents."""
    combined = left + " " + right

    if unit_type == 'percentage':
        if any(w in combined for w in ['급등', '상승', '오른', '뛰']):
            return 'gain'
        if any(w in combined for w in ['하락', '떨어', '내림']):
            return 'loss'
        return 'change'

    if unit_type == 'trillion_currency':
        if '시가총액' in left or '시총' in left or '시가총액' in right:
            return 'market_cap'
        if '클럽' in right or '돌파' in right:
            return 'milestone'
        return 'trillion_value'

    if unit_type == 'won':
        if any(w in combined for w in ['주가', '가격', '원']):
            return 'price'
        return 'amount'

    if unit_type == 'usd':
        if '목표' in left or '목표' in right or 'target' in combined.lower():
            return 'target_price'
        return 'usd_amount'

    if unit_type == 'year_range':
        if '계약' in left or '계약' in right or '기간' in right:
            return 'contract_period'
        return 'time_range'

    if unit_type == 'multiplier':
        if any(w in combined for w in ['올렸', '올리', '상향', '인상', '높였']):
            return 'price_increase_multiplier'
        return 'multiplier'

    return None


def cross_reference_with_ocr(audio_facts: list, ocr_items: list) -> tuple:
    """Split audio facts into (also_in_ocr, audio_only).

    A fact is "also in OCR" if its whitespace/comma-stripped form appears in the
    OCR blob, or (fallback) its >=3-digit numeric core appears there. Small
    numeric differences (2.7% vs 2.68%) are NOT matched — separate observations.
    """
    ocr_blob = " · ".join(_as_str(x) for x in ocr_items).lower()
    ocr_blob_clean = re.sub(r'[\s,]', '', ocr_blob)

    also_in_ocr: list = []
    audio_only: list = []

    for fact in audio_facts:
        normalized = re.sub(r'[\s,]', '', fact.raw_match.lower())
        digits_only = re.sub(r'[^\d.]', '', fact.raw_match)

        if normalized and normalized in ocr_blob_clean:
            also_in_ocr.append(fact)
        elif digits_only and len(digits_only) >= 3 and digits_only in ocr_blob_clean:
            also_in_ocr.append(fact)
        else:
            audio_only.append(fact)

    return also_in_ocr, audio_only


def promote_to_value_updates(audio_facts: list, existing_updates: list) -> list:
    """Convert audio facts into value_update dicts and merge with existing.

    Existing (OCR-derived) entries get source="video" added if missing. Each
    promotable audio fact becomes a new entry with source="audio". Idempotent:
    re-running over an already-augmented list does NOT duplicate audio rows
    (entries already tagged source="audio" are passed through unchanged and the
    same fact won't be appended twice).
    """
    promoted: list = []
    existing_audio_keys: set = set()
    for upd in existing_updates:
        if not isinstance(upd, dict):
            continue
        upd_copy = dict(upd)
        upd_copy.setdefault('source', 'video')
        if upd_copy.get('source') == 'audio':
            existing_audio_keys.add(_audio_key(upd_copy.get('label', ''),
                                               _first_value(upd_copy)))
        promoted.append(upd_copy)

    for fact in audio_facts:
        if fact.claim_type is None:
            continue
        # Skip low-info facts that carry no entity context.
        if fact.entity is None and fact.claim_type in ('change', 'multiplier'):
            continue

        label = fact.entity if fact.entity else fact.claim_type
        key = _audio_key(label, fact.raw_match)
        if key in existing_audio_keys:
            continue  # idempotent: already promoted this exact audio fact
        existing_audio_keys.add(key)

        promoted.append({
            'label': label,
            'values': [{'value': fact.raw_match, 'timestamp_sec': None, 'frame_idx': None}],
            'change_count': 1,
            'source': 'audio',
            'context': (fact.context_left.strip() + " [" + fact.raw_match + "] "
                        + fact.context_right.strip()),
            'claim_type': fact.claim_type,
        })

    return promoted


def extract_audio_only_terms(audio_facts: list) -> list:
    """Return human-readable strings for the 'Audio-only mentions' sub-section.

    e.g. "SK하이닉스 시가총액 1,600조 원", "마이크론 19% 급등". Order-preserving
    dedup.
    """
    terms: list = []
    for fact in audio_facts:
        if fact.entity:
            if fact.claim_type == 'market_cap':
                terms.append(f"{fact.entity} 시가총액 {fact.raw_match}")
            elif fact.claim_type == 'milestone':
                terms.append(f"{fact.entity} {fact.raw_match} 달성")
            elif fact.claim_type == 'gain':
                terms.append(f"{fact.entity} {fact.raw_match} 급등")
            elif fact.claim_type == 'target_price':
                terms.append(f"{fact.entity} 목표 주가 {fact.raw_match}")
            elif fact.claim_type == 'contract_period':
                terms.append(f"{fact.entity} 계약기간 {fact.raw_match}")
            else:
                terms.append(f"{fact.entity} {fact.raw_match}")
        else:
            # No entity — still keep if the claim type is strong on its own.
            if fact.claim_type in ('market_cap', 'milestone', 'target_price'):
                terms.append(fact.raw_match)

    seen: set = set()
    unique_terms: list = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            unique_terms.append(t)
    return unique_terms


# ============================================================================
# Internal helpers
# ============================================================================

def _as_str(v) -> str:
    if v is None:
        return ""
    return v if isinstance(v, str) else str(v)


def _first_value(upd: dict) -> str:
    vals = upd.get('values')
    if isinstance(vals, list) and vals and isinstance(vals[0], dict):
        return _as_str(vals[0].get('value'))
    return ""


def _audio_key(label: str, value: str) -> str:
    """Idempotency key for a promoted audio fact (label + normalized value)."""
    return _as_str(label).strip() + "||" + re.sub(r'\s+', '', _as_str(value))
