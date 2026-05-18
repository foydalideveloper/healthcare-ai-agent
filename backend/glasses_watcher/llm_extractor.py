"""LLM-based health fact extractor — replaces brittle regex patterns.

Calls Anthropic Claude Haiku to extract structured health data from a voice
transcript. Handles:
  - Mixed Korean-English code-switching
  - "X and Y with Z" continuation phrases
  - Any food, drink, exercise, medicine, sleep, biometric, mental state
    the user mentions — no need for hardcoded patterns.

Requires ANTHROPIC_API_KEY in backend/.env.

Usage:
    from llm_extractor import extract_health_facts
    result = extract_health_facts("I had a burger and pizza with french fries and 45 min of exercise")
    # → {"foods": [{"name_ko": "버거", ...}, {"name_ko": "피자", ...}, {"name_ko": "감자튀김", ...}],
    #    "exercises": [{"type": "general", "minutes": 45}], ...}
"""

import os
import json
import re
from pathlib import Path
import httpx

# ── Config ──
# TEMPORARY: Anthropic Haiku swapped for Google Gemini due to billing on 2026-05-04.
# Revert when Anthropic billing is restored — see memory:
#   project_healthcare_haiku_temporary_gemini_swap.md
# Architecture decision (Layer 1 = Haiku) is UNCHANGED.
PROJECT_ROOT = Path(__file__).parent.parent.parent
ANTHROPIC_API_KEY = ""
GEMINI_API_KEY = ""
env_path = PROJECT_ROOT / "backend" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            ANTHROPIC_API_KEY = line.split("=", 1)[1].strip()
        elif line.startswith("GEMINI_API_KEY="):
            GEMINI_API_KEY = line.split("=", 1)[1].strip()

# Hybrid extraction: try LOCAL Gemma 4 first (free, on Mac mini). Only fall back
# to a paid cloud LLM if Gemma is unreachable or returns invalid JSON. This gives
# ~zero-cost extraction in normal operation and resilience when Mac mini is offline.
#
# Provider matrix:
#   "gemma_local" — Mac mini Gemma 4 E4B Q8 (free, ~2-3 s)
#   "gemini"      — Google Gemini 2.5 Flash (paid, ~1 s; current Haiku stand-in)
#   "haiku"       — Claude Haiku 4.5 (paid, original Layer 1 production target)
LLM_PROVIDER = "gemma_local"   # primary
LLM_FALLBACK = "gemini"        # only used when primary errors out (None return)

HAIKU_MODEL       = "claude-haiku-4-5-20251001"
GEMINI_MODEL      = "gemini-2.5-flash"
GEMMA_LOCAL_URL   = "http://100.69.125.64:8080/v1/chat/completions"  # Mac mini Tailscale
GEMMA_LOCAL_MODEL = "gemma-4-E4B-it"

SYSTEM_PROMPT = """You extract structured health data from a voice transcript.
The user speaks mixed Korean and English about their daily health.

Output ONLY valid JSON matching this schema (no markdown, no explanation):

{
  "foods": [
    {"name_en": "string", "name_ko": "string",
     "kcal": number, "protein_g": number, "fat_g": number, "carb_g": number,
     "portion_g": number}
  ],
  "drinks": [
    {"name_en": "string", "name_ko": "string", "ml": number, "kcal": number}
  ],
  "exercises": [
    {"type": "string", "minutes": number, "intensity": "low|moderate|high",
     "event_time": "HH:MM or null"}
  ],
  "medications": [
    {"drug_name": "string", "dose": number, "unit": "string"}
  ],
  "sleep": {"hours": number, "wake_time": "HH:MM", "quality": "good|fair|poor"},
  "biometrics": {
    "heart_rate": number, "sbp": number, "dbp": number,
    "glucose_mgdl": number, "weight_kg": number
  },
  "mental": {"stress_level": number, "mood": "string", "energy": "string"},
  "tobacco": [{"type": "string", "quantity": number}]
}

Rules:
- Include a field ONLY if explicitly mentioned in the transcript.
- Use null for single-value fields not mentioned.
- Use empty array [] for list fields with no items.
- Extract EVERYTHING health-related — food, drink, exercise, medicine,
  sleep, biometric, mental state — no matter how it's phrased.
- Korean food/drink names MUST be in Korean (e.g. "고등어구이",
  "김치찌개"). If user said in English, translate to Korean.
- Estimate realistic nutrition values per standard portion if user
  didn't specify amounts (burger ~550 kcal, rice ~300 kcal, etc.).
- Estimate ml for drinks (cup ~250, bottle ~500, glass ~200).
- Estimate kcal for drinks based on typical calorie content:
  black coffee/tea/water ~5 kcal, latte/milk ~120, juice ~110,
  soda ~140, beer ~150, wine ~125 per standard serving. Multiply
  by ml/250 if portion differs from standard.
- stress_level 1-10 where 10 = maximum stress.
- Phonetic Korean misrecognitions: if an English-looking word could
  be a mangled Korean food (e.g. "codenburg wheat" ≈ "고등어구이",
  "gogu" ≈ "고등어구이"), use the likely Korean food name.
- SPEECH-TO-TEXT HOMOPHONES — CRITICAL: The phrase "I had/have [X] of
  this/these" is ALWAYS a counting expression, never a food type.
  [X] is a misheard number: "tea"→THREE, "to"→TWO, "for"→FOUR, "won"→ONE.
  "this/these" refers back to the most recently mentioned food/drink.
  Example: "I already had tea of this" = user had THREE of the coffee
  mentioned just before. Do NOT extract "tea" as a separate drink here.
  Other mishearing patterns: "for pieces" → FOUR pieces,
  "to of these" → TWO of these. Correct silently — extract the count
  and apply it to the referenced item, not a new food/drink.
- EXERCISE TIMING: if user says exercise happened at a specific past
  time (e.g. "at 9am I had 47 minutes of exercise"), set event_time
  to "09:00". If no time mentioned, set event_time to null.
- EXERCISE — DETECT EVEN WITHOUT EXPLICIT MINUTES: if the user mentions
  warm-ups, stretching, push-ups, squats, lunges, jumping jacks, planks,
  yoga poses, walking, running, or counting reps ("1, 2, 3...", "1세트",
  "한 세트"), it IS exercise. If no duration is stated, default to
  minutes=1. Do NOT skip exercise just because no minute count is given.
- DO NOT INVENT FOODS: if the transcript is purely about exercise,
  emotion, or conversation with no food/drink/medication mentioned,
  return foods=[] and drinks=[]. Never output a placeholder food name
  like "unknown" / "알 수 없음" / "?" — return an empty list instead.
"""


def _extract_via_haiku(transcript: str) -> dict | None:
    """=== HAIKU ORIGINAL — production-locked Layer 1 extractor ==="""
    if not ANTHROPIC_API_KEY:
        print("    [llm_extractor] ANTHROPIC_API_KEY not found — check backend/.env")
        return None
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": HAIKU_MODEL,
            "max_tokens": 2000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": transcript}],
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["content"][0]["text"].strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _extract_via_gemini(transcript: str) -> dict | None:
    """=== GEMINI TEMPORARY (May 2026) — revert to Haiku when billing restored ==="""
    if not GEMINI_API_KEY:
        print("    [llm_extractor] GEMINI_API_KEY not found — check backend/.env")
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    resp = httpx.post(
        url,
        headers={
            "x-goog-api-key": GEMINI_API_KEY,
            "content-type": "application/json",
        },
        json={
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": transcript}]}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 2000,
                "responseMimeType": "application/json",
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _extract_via_gemma_local(transcript: str) -> dict | None:
    """=== GEMMA LOCAL (Mac mini, free) — primary extractor in hybrid mode ===
    Calls llama.cpp OpenAI-compatible /v1/chat/completions on Tailscale IP."""
    resp = httpx.post(
        GEMMA_LOCAL_URL,
        headers={"content-type": "application/json"},
        json={
            "model": GEMMA_LOCAL_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": transcript},
            ],
            "temperature": 0,
            "max_tokens": 2000,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False},
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"].strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


_PROVIDER_FNS = {
    "haiku":       _extract_via_haiku,
    "gemini":      _extract_via_gemini,
    "gemma_local": _extract_via_gemma_local,
}


def _try_provider(provider: str, transcript: str) -> tuple[dict | None, str | None]:
    """Run a single provider and return (result, error_str). Never raises."""
    fn = _PROVIDER_FNS.get(provider)
    if fn is None:
        return None, f"unknown provider: {provider}"
    try:
        return fn(transcript), None
    except httpx.HTTPStatusError as e:
        body = ""
        try:
            body = e.response.text[:200]
        except Exception:
            pass
        return None, f"http_{e.response.status_code}: {body}"
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:200]}"


def extract_health_facts(transcript: str) -> dict | None:
    """Extract structured health facts from a voice transcript.
    Hybrid: try LLM_PROVIDER first; if that fails, try LLM_FALLBACK.
    Returns None if both fail — caller falls back to regex extraction."""
    if not transcript or len(transcript.strip()) < 3:
        return None

    # Primary
    result, err = _try_provider(LLM_PROVIDER, transcript)
    if result is not None:
        print(f"    [llm_extractor] {LLM_PROVIDER} succeeded")
        return result

    print(f"    [llm_extractor] {LLM_PROVIDER} failed: {err}")

    # Fallback (skip if same as primary or no fallback configured)
    if not LLM_FALLBACK or LLM_FALLBACK == LLM_PROVIDER:
        return None

    result, err = _try_provider(LLM_FALLBACK, transcript)
    if result is not None:
        print(f"    [llm_extractor] fallback {LLM_FALLBACK} succeeded")
        return result

    print(f"    [llm_extractor] fallback {LLM_FALLBACK} also failed: {err}")
    return None


def to_legacy_format(llm_result: dict) -> dict:
    """Convert LLM output to the shape event_processor.extract_from_transcript
    returns, so downstream code doesn't need to change much."""
    out = {"foods": [], "medications": [], "tobacco": [],
           "exercise": None, "sleep": None, "hydration": None, "drinks": []}

    # Names LLMs use when they're hallucinating a food they didn't see/hear.
    # Skip these — better to log nothing than to write fake food rows.
    _HALLUCINATED_NAMES = {
        "unknown", "n/a", "none", "nothing", "no food", "no item", "?",
        "알 수 없음", "알 수 없는", "모름", "없음",
    }

    def _is_hallucinated_name(name: str) -> bool:
        if not name:
            return True
        n = name.lower().strip()
        if n in _HALLUCINATED_NAMES:
            return True
        if "알 수 없" in name or "unknown" in n:
            return True
        return False

    for f in (llm_result.get("foods") or []):
        name = f.get("name_ko") or f.get("name_en") or ""
        if _is_hallucinated_name(name):
            continue
        out["foods"].append({
            "name":       name,
            "english":    f.get("name_en"),
            "kcal":       f.get("kcal") or 0,
            "protein_g":  f.get("protein_g") or 0,
            "fat_g":      f.get("fat_g") or 0,
            "carb_g":     f.get("carb_g") or 0,
            "serving_g":  f.get("portion_g") or 200,
        })

    for d in (llm_result.get("drinks") or []):
        name = d.get("name_ko") or d.get("name_en") or ""
        if _is_hallucinated_name(name):
            continue
        ml = d.get("ml") or 250
        out["drinks"].append({
            "name":      name or "water",
            "ml":        ml,
            "serving_g": ml,
            "kcal":      d.get("kcal") or 0,
            "protein_g": 0, "fat_g": 0, "carb_g": 0,
        })

    for m in (llm_result.get("medications") or []):
        out["medications"].append({
            "drug_name": m.get("drug_name", "unknown"),
            "drug_code": "",
            "dose":      m.get("dose", 0),
            "unit":      m.get("unit", "mg"),
        })

    exs = llm_result.get("exercises") or []
    if exs:
        total_min = sum(e.get("minutes", 0) for e in exs)
        # event_time: prefer the first exercise that has an explicit stated time.
        event_time = next((e.get("event_time") for e in exs if e.get("event_time")), None)
        out["exercise"] = {
            "minutes":    total_min,
            "type":       exs[0].get("type", "general"),
            "event_time": event_time,  # "HH:MM" or None — from user's stated time
        }

    slp = llm_result.get("sleep") or {}
    if slp and (slp.get("hours") or slp.get("wake_time")):
        out["sleep"] = {
            "hours":     slp.get("hours"),
            "wake_time": slp.get("wake_time"),
            "quality":   slp.get("quality"),
        }

    # Hydration: if drinks list populated, total ml → hydration summary
    if out["drinks"]:
        out["hydration"] = {
            "ml":   sum(d["ml"] for d in out["drinks"]),
            "type": out["drinks"][0]["name"],
        }

    out["biometrics"] = llm_result.get("biometrics") or {}
    out["mental"]     = llm_result.get("mental")     or {}

    return out
