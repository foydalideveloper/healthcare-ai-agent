"""Post-OCR quality filter (v3.3). Pure, dependency-free, unit-testable.

Splits noisy OCR output and VLM enumerations into meaningful vs drop-able so the
Full Report shows substance (numbers, prices, tickers, headlines) prominently and
demotes garbage (single particles, OCR fragments, mojibake) to a reference appendix.

Does NOT touch the extraction pipeline — this runs at aggregation/report time.
"""
from __future__ import annotations

import re

# Korean particles / postpositions / single-character tokens to drop.
KOREAN_PARTICLES = frozenset([
    "는", "을", "를", "의", "이", "가", "에", "도", "와", "과", "만",
    "로", "으로", "에서", "부터", "까지", "하고", "이고", "에게", "한테",
    "그", "그의", "그를", "그것", "저것",
])

# Recognized financial / business entities — always keep (case-insensitive).
RECOGNIZED_ENTITIES = frozenset([
    # Korean
    "삼성전자", "SK하이닉스", "SK스퀘어", "삼성전자우", "현대차", "삼성전기",
    "코스피", "코스닥", "한국은행", "기획재정부",
    # English
    "KOSPI", "KOSDAQ", "SAMSUNG", "Samsung", "Hynix", "SK", "Micron",
    "UBS", "S&P", "DXY", "NIKKEI", "HSI", "EUR", "USD", "KRW", "JPY", "CNH", "AUD",
    "WOORI", "KODEX", "TIGER", "Hana", "KBS",
    # Indicators
    "ETF", "RSI", "MACD",
])

# Mojibake: bytes that failed to decode / were mis-decoded. NEVER meaningful,
# no matter how the VLM wraps them in a sentence — so we catch them at the
# OCR-item level (and is_meaningful_observation checks the quoted token).
MOJIBAKE_PATTERNS = [
    re.compile("�"),                 # Unicode replacement char (����)
    re.compile("[\x80-\x9f]"),            # C1 control chars
    re.compile("[ -ÿ]{2,}"),    # cp1252-as-UTF8: 2+ Latin-1 chars (e.g. "Ã©")
]

# OCR garbage: broken CamelCase / mixed character sets on short tokens.
OCR_GARBAGE_PATTERNS = [
    re.compile(r"^[A-Z][a-z][A-Z]"),    # broken CamelCase start, e.g. "WiHdoWs"
    re.compile(r"^[A-Z]{2,}\d?[a-z]"),  # mixed garbage, e.g. "EXAHANUGEa"
    re.compile(r"^[가-힣][A-Za-z]"),     # Korean+Latin in one short token
    re.compile(r"^[A-Za-z][가-힣]"),     # Latin+Korean in one short token
]

_ALL_CAPS_LATIN = re.compile(r"[A-Z]+")     # used with fullmatch
# 3+ identical letters / Hangul / punctuation in a row = OCR garble. Digits are
# deliberately EXCLUDED so real numbers (e.g. 111000) survive.
_GARBLE_RUN = re.compile(r"([A-Za-z가-힣!|~?.\-])\1\1")
# A "clean" number / price token: digits + numeric punctuation only.
_CLEAN_NUMERIC = re.compile(r"[\d.,%+\-/:()]+")


def is_mojibake(text: str) -> bool:
    """True if the token contains decode-failure / mis-decode artifacts."""
    return any(p.search(text) for p in MOJIBAKE_PATTERNS)


def _entity_match(text: str) -> bool:
    tu = text.upper()
    return any(ent.upper() in tu or tu in ent.upper() for ent in RECOGNIZED_ENTITIES)


def _case_transitions(text: str) -> int:
    """Count upper<->lower flips among ASCII letters (broken-CamelCase signal)."""
    prev = None
    n = 0
    for c in text:
        if c.isascii() and c.isalpha():
            cur = c.isupper()
            if prev is not None and cur != prev:
                n += 1
            prev = cur
    return n


def is_meaningful_ocr_item(text: str, confidence: float = 1.0) -> bool:
    """True if this OCR item is worth keeping in the report (see module doc)."""
    if not text or not text.strip():
        return False
    text = text.strip()

    # Always-drop (beats everything): mojibake content is never meaningful.
    if is_mojibake(text):
        return False
    if len(text) < 2:
        return False
    if text in KOREAN_PARTICLES:
        return False

    # Garble runs (3+ same letter/Hangul/punct) — checked BEFORE the digit rule
    # so "19!!! III!!" / "H5!!!" / "LLLVA" are dropped despite containing a digit.
    if _GARBLE_RUN.search(text):
        return False
    # Short tokens peppered with OCR-artifact punctuation ("Hs!:", "!II1", "10!1").
    if len(text) < 6 and re.search(r"[!|]", text):
        return False

    # Numbers / prices: keep a CLEAN numeric token or a digit-DOMINANT one; drop a
    # digit buried in garbage (low digit ratio, no currency/entity).
    if re.search(r"\d", text):
        if _CLEAN_NUMERIC.fullmatch(text):
            return True
        if re.search(r"[$€¥₩%]", text) or _entity_match(text):
            return True
        digit_ratio = sum(c.isdigit() for c in text) / len(text)
        return digit_ratio >= 0.4

    # Currency / change symbols, then recognized entities → keep.
    if re.search(r"[$€¥₩%+▲▼]", text):
        return True
    if _entity_match(text):
        return True

    # Remaining non-digit "maybe garbage" non-keepers:
    if _case_transitions(text) >= 3:                        # "WiHdoWs"
        return False
    if len(text) >= 6 and _ALL_CAPS_LATIN.fullmatch(text):  # "EXAHANUGE" (non-entity)
        return False
    if len(text) < 6 and any(p.match(text) for p in OCR_GARBAGE_PATTERNS):
        return False
    if confidence < 0.5:
        return False
    if len(text) <= 3 and re.fullmatch(r"[A-Za-z]+", text):  # short Latin fragment
        return False

    return len(text) >= 4


def _item_text(item) -> str:
    return item.get("text", "") if isinstance(item, dict) else str(item)


def _item_conf(item) -> float:
    return item.get("confidence", 1.0) if isinstance(item, dict) else 1.0


def filter_ocr_items(items: list) -> tuple[list, list]:
    """Split OCR items into (meaningful, filtered_out), original order preserved.

    Never returns an empty `meaningful` when there were items — falls back to the
    10 longest (avoids a "no data" panic in the UI on a pathological clip).
    """
    meaningful: list = []
    filtered_out: list = []
    for item in items:
        if is_meaningful_ocr_item(_item_text(item), _item_conf(item)):
            meaningful.append(item)
        else:
            filtered_out.append(item)
    if not meaningful and filtered_out:
        ranked = sorted(range(len(filtered_out)),
                        key=lambda i: len(_item_text(filtered_out[i])), reverse=True)[:10]
        keep = set(ranked)
        meaningful = [filtered_out[i] for i in ranked]
        filtered_out = [filtered_out[i] for i in range(len(filtered_out)) if i not in keep]
    return meaningful, filtered_out


# ── Enumerated-observation filter ────────────────────────────────────────
NOISE_PATTERNS = [
    re.compile(
        r"^The (text|character|word|term|letter|symbol|number)\s+['\"`].+?['\"`]\s+"
        r"is\s+visible(\s+on\s+the\s+screen)?\.?\s*$", re.IGNORECASE),
    re.compile(r"^['\"`].+?['\"`]\s+is\s+visible.*$", re.IGNORECASE),
]


def is_meaningful_observation(sentence: str) -> bool:
    """True if an enumerated observation conveys factual content.

    Drops "The text '의' is visible on the screen" but keeps a sentence of the
    same shape whose quoted token is itself meaningful (e.g. 'KOSPI 8,228.70').
    """
    sentence = (sentence or "").strip()
    if not sentence:
        return False
    if re.search(r"\d", sentence):  # any digit → factual content
        return True
    for pat in NOISE_PATTERNS:
        if pat.match(sentence):
            quoted = re.search(r"['\"`](.+?)['\"`]", sentence)
            if quoted:
                return is_meaningful_ocr_item(quoted.group(1))
            return False
    return True  # doesn't match a noise shape → keep


def filter_enumerated_observations(sentences: list[str]) -> tuple[list[str], list[str]]:
    """Split enumerated observations into (meaningful, dropped)."""
    meaningful: list[str] = []
    dropped: list[str] = []
    for s in sentences:
        (meaningful if is_meaningful_observation(s) else dropped).append(s)
    return meaningful, dropped
