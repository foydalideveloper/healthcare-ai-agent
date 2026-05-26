"""Semantic equivalence map for cross-model food-name dedup.

When CNN cascade writes 양념치킨 and Phase 2 multimodal also returns
"fried chicken", both names refer to the same physical dish. Without
dedup we'd write 2 rows and double-count kcal. `food_class(name)` maps
synonymous names to the same canonical class id, so callers can tell
that "양념치킨" and "fried chicken" describe the same thing.

Usage in watcher.py is "MAX count across models per class group":
  CNN says   양념치킨 ×1
  Gemma says fried chicken ×2
  → take MAX(1, 2) = 2 chicken rows total. Two distinct names from the
    photo (e.g. 양념치킨 + fried chicken) populate the row labels.

This is NOT a comprehensive food taxonomy — only add a synonym group
when a real-world false-duplicate is observed across the three
recognition paths (Korean CNN, Food-101 CNN, Gemma multimodal,
Nemotron multimodal).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


def _g(*names: str) -> Tuple[str, ...]:
    """Build a lower-cased ordered group. First member = canonical id
    (deterministic across processes; frozenset would hash-randomize)."""
    return tuple(n.lower().strip() for n in names)


# Each tuple = one "dish concept". The FIRST entry is the canonical id —
# use Korean for Korean dishes so MFDS lookups hit; English for international.
_GROUPS: List[Tuple[str, ...]] = [
    # ── Korean fried chicken (양념치킨, 후라이드치킨, all generic chicken naming) ──
    _g("양념치킨", "후라이드치킨", "프라이드치킨", "닭강정", "닭튀김", "치킨", "닭",
       "chicken", "fried chicken", "fried_chicken", "korean fried chicken",
       "chicken wings", "chicken_wings", "yangnyeom chicken"),
    # ── Pickled radish side (chicken side dish) ──
    _g("치킨무", "단무지", "white radish", "pickled radish", "yellow radish",
       "pickled white radish"),
    # ── Plain rice ──
    _g("밥", "rice", "흰밥", "현미밥", "잡곡밥", "boiled rice"),
    # ── Fried rice (separate dish from plain rice) ──
    _g("볶음밥", "fried rice", "fried_rice"),
    # ── Plain tofu ──
    _g("두부", "tofu", "soft tofu"),
    # ── Fried tofu (유부 — different from plain tofu) ──
    _g("유부", "fried tofu", "fried_tofu", "유부주머니"),
    # ── Kimchi ──
    _g("김치", "kimchi", "배추김치", "napa kimchi"),
    # ── Kimbap (Korean rice+seaweed roll) ──
    _g("김밥", "gimbap", "kimbap"),
    # ── Sushi (Japanese, kept separate from kimbap intentionally) ──
    _g("초밥", "스시", "sushi", "sashimi"),
    # ── Fish cake / Korean odeng ──
    _g("어묵", "오뎅", "어묵탕", "어묵튀김", "fish cake", "fish_cake", "fishcake",
       "odeng"),
    # ── Fried squid (visually confused with fish cake — separate group) ──
    _g("오징어튀김", "fried squid", "fried_calamari", "calamari", "squid"),
    # ── Grilled mackerel ──
    _g("고등어구이", "grilled mackerel", "mackerel"),
    # ── Grilled cutlassfish ──
    _g("갈치구이", "grilled cutlassfish", "cutlassfish"),
    # ── Bibimbap ──
    _g("비빔밥", "bibimbap"),
    # ── Tteokbokki ──
    _g("떡볶이", "tteokbokki"),
    # ── Pizza ──
    _g("피자", "pizza"),
    # ── Coffee ──
    _g("커피", "coffee", "americano", "latte", "라떼", "라테", "에스프레소", "espresso"),
    # ── Tea ──
    _g("차", "tea", "녹차", "홍차", "green tea", "black tea", "iced tea"),
    # ── Water ──
    _g("물", "water"),
    # ── Beer ──
    _g("맥주", "beer"),
    # ── Soju ──
    _g("소주", "soju"),
    # ── Eggs ──
    _g("계란", "eggs", "egg", "boiled egg", "fried egg", "scrambled egg", "omelette"),
    # ── Soup / stew (broad — many models conflate them) ──
    _g("국", "찌개", "soup", "stew", "탕"),
    # ── Ramen / noodle soup ──
    _g("라면", "ramen", "noodle soup", "noodles"),
    # ── Salad ──
    _g("샐러드", "salad", "green salad"),
    # ── Orange ade (Del Monte 스퀴즈 family + brand / spelling variants) ──
    _g("오렌지 에이드", "오렌지에이드", "스퀴즈 오렌지 에이드", "스퀴이즈 오렌지 에이드",
       "스퀴즈오렌지에이드", "스퀴즈 오렌지에이드", "델몬트 스퀴즈 오렌지 에이드",
       "orangeade", "orange ade", "orange-ade"),
    # ── Cola ──
    _g("콜라", "cola", "coke", "coca-cola", "coca cola", "코카콜라", "펩시", "pepsi", "pepsi cola"),
    # ── Sprite / cider (Korean 사이다 == lemon-lime soda) ──
    _g("사이다", "스프라이트", "sprite", "7up", "7-up", "seven up", "lemon-lime soda"),
    # ── Fanta (general fruit soda) ──
    _g("환타", "fanta", "fanta orange", "orange soda"),
    # ── Energy drinks ──
    _g("에너지 드링크", "에너지드링크", "energy drink", "박카스", "bacchus", "레드불", "redbull",
       "monster energy", "monster"),
    # ── Sports drinks ──
    _g("스포츠 음료", "스포츠음료", "sports drink", "포카리스웨트", "pocari sweat",
       "게토레이", "gatorade"),
    # ── Plain juice (orange/apple/grape — non-carbonated) ──
    _g("주스", "쥬스", "juice", "fruit juice", "오렌지주스", "오렌지 주스", "orange juice",
       "사과주스", "apple juice", "포도주스", "grape juice"),
    # ── Milk ──
    _g("우유", "milk", "white milk", "low fat milk", "저지방 우유"),
    # ── Yogurt drink ──
    _g("요거트", "yogurt", "yogurt drink", "마시는 요거트", "drinkable yogurt"),
    # ── Sikhye (rice punch — Korean traditional drink) ──
    _g("식혜", "sikhye", "rice punch"),
    # ── Barley tea ──
    _g("보리차", "barley tea"),
    # ── Plum tea ──
    _g("매실차", "plum tea", "korean plum tea"),
]


# Pre-compute name → canonical-id index. Canonical id = first member of
# each tuple (deterministic, the way the source declares it).
_NAME_TO_CANON: Dict[str, str] = {}
for _grp in _GROUPS:
    _canon = _grp[0]
    for _n in _grp:
        _NAME_TO_CANON[_n] = _canon


# Class canonicals that represent DRINKS. Callers use this to route writes
# to the Hydration dashboard category (serving_g treated as ml; name
# canonicalized so the migration-006 SQL drink regex picks it up).
DRINK_CLASSES: frozenset = frozenset({
    "오렌지 에이드", "콜라", "사이다", "환타", "에너지 드링크", "스포츠 음료",
    "주스", "우유", "요거트", "식혜", "보리차", "매실차", "차", "커피", "물",
    "맥주", "소주",
})


def is_drink_class(canonical: Optional[str]) -> bool:
    """Returns True if a class canonical id represents a drink (not food)."""
    return canonical is not None and canonical in DRINK_CLASSES


_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*")

# ASR / Whisper typo normalization. Multimodal models occasionally pick up
# Korean text via OCR/dictation and produce these mis-transliterations;
# normalizing here lets a single class group cover all variants without
# enumerating every typo as a separate member.
_ASR_REPLACEMENTS: list[tuple[str, str]] = [
    ("쥬스", "주스"),       # juice variant
    ("아이드", "에이드"),    # ade variant ("squeeze orange aid" → "...ade")
    ("메이드", "에이드"),    # ade variant ("orange made" → "...ade")
    ("오랜지", "오렌지"),    # "orange" Korean spelling variant
    ("커비", "커피"),       # coffee mishear
]


def _normalize(name: str) -> str:
    if not name:
        return ""
    n = name.lower().strip()
    n = _PAREN_RE.sub(" ", n).strip()
    for src, dst in _ASR_REPLACEMENTS:
        n = n.replace(src, dst)
    return n


_WORD_RE = re.compile(r"[a-z]+")

# Pre-computed per-member token sets. Each entry: (canonical_id, words, chars).
# Iterating members (not just canonicals) lets fuzzy-match catch English
# variants of Korean-canonical groups: candidate "Orange Squeeze Ade" matches
# the English member "orange ade" → returns canonical "오렌지 에이드".
_MEMBER_TOKENS: list = []
for _grp in _GROUPS:
    _canonical = _grp[0]
    for _member in _grp:
        _m_norm = _member  # already lowercased by _g()
        _words = set(_WORD_RE.findall(_m_norm))
        _chars = set(c for c in _m_norm if '가' <= c <= '힣')
        if _words or _chars:
            _MEMBER_TOKENS.append((_canonical, _words, _chars))


def food_class(name: str) -> Optional[str]:
    """Return the canonical class id for a food name, or None if not in map.

    Three-step lookup:
      1. Exact match on the synonym list (양념치킨, fried chicken, ...).
      2. Underscore→space (Food-101 names like fried_rice).
      3. Fuzzy match against any group member: candidate must contain ALL of
         the member's word-tokens (English) OR ALL its hangul chars (Korean).
         Catches model spelling drift like "Orange Squeeze Ade" via the
         English member "orange ade", or "스퀴어즈 오렌지 에이드" via the
         Korean member "오렌지 에이드"."""
    n = _normalize(name)
    if not n:
        return None
    if n in _NAME_TO_CANON:
        return _NAME_TO_CANON[n]
    n_alt = n.replace("_", " ").strip()
    if n_alt != n and n_alt in _NAME_TO_CANON:
        return _NAME_TO_CANON[n_alt]

    n_words = set(_WORD_RE.findall(n))
    n_chars = set(c for c in n if '가' <= c <= '힣')
    # Require ≥2 tokens / ≥2 hangul chars for fuzzy match. Single-char /
    # single-word canonicals (e.g. 차/tea, 물/water) only exact-match —
    # otherwise they'd false-match any candidate that happens to contain
    # the char (e.g. 차가운 콜라 → 차).
    for canonical, m_words, m_chars in _MEMBER_TOKENS:
        if len(m_words) >= 2 and m_words.issubset(n_words):
            return canonical
        if len(m_chars) >= 2 and m_chars.issubset(n_chars):
            return canonical
    return None
