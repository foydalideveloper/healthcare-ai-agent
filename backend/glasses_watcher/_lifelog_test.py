"""Lifelog extraction test — capture EVERY observable event from a video.

Standalone test script. No Supabase writes — produces a single JSON file
you can inspect to see what Gemma 4 (and optionally Qwen 3.5 VLM and/or
Llama 4 Maverick via NVIDIA NIM) extracted from your video.

Usage:
  python _lifelog_test.py <video_path>                       # Gemma only
  python _lifelog_test.py <video_path> --compare             # Gemma + Qwen NIM
  python _lifelog_test.py <video_path> --llama4              # Gemma + Llama 4 NIM
  python _lifelog_test.py <video_path> --compare --llama4    # all three

Output:
  <video_path>.lifelog.json    (Gemma-only)
  <video_path>.compare.json    (any multi-model run)

Pipeline per chunk (60 sec each):
  1. Sample 8 frames evenly from the chunk
  2. (optional) Slice Whisper transcript covering that chunk
  3. Send frames + transcript + LIFELOG_PROMPT to Gemma 4 E4B (Mac mini)
  4. (optional, --compare) Same to Qwen 3.5 VLM 397B via NVIDIA NIM
  5. (optional, --llama4)  Same to Llama 4 Maverick 17B/128E via NVIDIA NIM
  6. Parse JSON, append events with absolute timestamps
  7. Aggregate all events from all chunks, save to JSON
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional

import httpx
from PIL import Image

KST = timezone(timedelta(hours=9))

# ── CRITICAL IMPORT ORDER: torch BEFORE PaddlePaddle ───────────────────
# PaddlePaddle (pulled in by ocr_preprocessor -> paddleocr below) and
# torch/ctranslate2 (faster-whisper) bundle conflicting CUDA/cuDNN DLLs.
# Whichever loads first wins; the loser hits "WinError 127: procedure not
# found". Verified: paddle-then-torch BREAKS torch (and Whisper); torch-then-
# paddle works for ALL three. Importing torch here — before the
# ocr_preprocessor import — preloads torch's cuDNN9/cuBLAS so both Whisper and
# Paddle work. This is the real fix for the intermittent "[whisper] failed:
# WinError 127" (it was deterministic on the watcher path, where paddle is
# imported before Whisper ever runs).
try:
    import torch  # noqa: F401  (import-order side effect; not used directly here)
except Exception as _torch_e:  # pragma: no cover
    print(f"[WARN] torch preimport failed ({type(_torch_e).__name__}); "
          f"Whisper (faster-whisper/ctranslate2) may hit WinError 127")

# Reuse Gemma helpers
sys.path.insert(0, str(Path(__file__).parent))
from gemma_dual_extractor import (
    GEMMA_BASE_URL,
    GEMMA_TIMEOUT_SEC,
    _img_to_data_url,
    _GEMMA_SYSTEM_INSTRUCTION,
)

# v3 — optional OCR preprocessor (lazy, degrades gracefully if missing).
try:
    import ocr_preprocessor as _ocr
    OCR_AVAILABLE = bool(getattr(_ocr, "OCR_AVAILABLE", False))
except Exception as _e:  # pragma: no cover
    _ocr = None
    OCR_AVAILABLE = False
    print(f"[WARN] _lifelog_test: ocr_preprocessor import failed - OCR pass disabled ({type(_e).__name__}: {_e})")

# Failed-parse dump dir. JSON parse failures (long-prompt edge cases) are
# logged here as {arm}_{epoch_ms}.txt so they don't crash the watcher.
FAILED_PARSES_DIR = Path(__file__).parent / "failed_parses"


def _log_failed_parse(arm: str, raw_text: str, err: str) -> None:
    """Dump a raw model response that failed JSON parsing. Never raises."""
    try:
        FAILED_PARSES_DIR.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)
        p = FAILED_PARSES_DIR / f"{arm}_{ts}.txt"
        p.write_text(
            f"=== {arm} JSON parse FAILED ({err}) ===\n\n{raw_text}",
            encoding="utf-8", errors="replace",
        )
        print(f"[WARN] {arm}: JSON parse failed - raw saved to {p.name}")
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────
# THE LIFELOG PROMPT — extract everything observable
# ──────────────────────────────────────────────────────────────────────

LIFELOG_PROMPT = """\
/no_think
You are observing a video clip from a person's AI glasses. Extract EVERY
observable event, AND if FINANCIAL / MARKET content appears (charts, tickers,
prices, market news, analyst commentary), extract DETAILED ANALYST-LEVEL data
that a downstream asset-management agent can act on: tickers, numerical levels,
recommendations, sentiment, predictions, action signals.

Be thorough but factual — only extract what you actually see or hear.
Do NOT invent. Do NOT skip mundane events (sitting at desk counts).
For FINANCE content: do NOT just describe ("user watching news"). ANALYZE.

Output ONLY valid JSON. Schema:
{
  "events": [
    {
      "t_sec": int,                  // seconds from clip start
      "duration_sec": int,           // estimate, default 5 if unsure
      "category": "activity" | "interaction" | "conversation" | "food" |
                  "drink" | "exercise" | "medication" | "task_received" |
                  "commitment_made" | "purchase" | "location_change" |
                  "object_use" | "screen_content" | "observation" |
                  "finance_analysis",   // ← USE THIS when financial content is visible/audible
      "description": "<short factual sentence>",
      "people":   ["boss" | "colleague" | "friend" | "stranger" |
                   "family" | "child" | "manager" | "customer", ...],
      "people_count": int,           // total people visible in scene
      "location":  "office_desk" | "conference_room" | "kitchen" |
                   "restaurant" | "outdoor" | "vehicle" | "home" |
                   "store" | "bathroom" | "hallway" | "other",
      "objects":  [list of objects the user interacts with],
      "screen":   "<if a screen is visible, what app/site/doc>",
      "topic":    "<conversation topic if any>",
      "decision": "<decision or commitment made in conversation, if any>",
      "mood":     "focused" | "tired" | "happy" | "stressed" |
                  "anxious" | "relaxed" | "neutral" | null,
      "posture":  "sitting" | "standing" | "walking" | "lying" |
                  "driving" | null,
      "indoor_outdoor": "indoor" | "outdoor" | null,
      "audio_heard":   "<music, announcement, notification, phone ring, etc.>",
      "numbers_mentioned": "<prices, dates, quantities heard>",
      "kcal":     int or null,       // only for food/drink
      "amount_ml": int or null,      // only for drink
      "energy_signs": "yawning" | "slumping" | "alert" | "rubbing_eyes" |
                      "stretching" | null,

      // ─── NEW v2 INTELLIGENCE FIELDS (fill for every event) ───
      "start_sec":  float,                // precise start within clip (0.0-duration)
      "end_sec":    float,                // precise end within clip
      "confidence": float,                // 0.0-1.0 — how sure are you?
      "importance": int,                  // 1-10 — how important is this event?
                                          //   1-3=mundane, 4-6=notable,
                                          //   7-8=valuable, 9-10=critical
      "memory_relevance": "none" | "low" | "medium" | "high",
                                          // should this be stored long-term?
      "observed_facts":  ["<things you directly SAW or HEARD>"],
      "inferred_context":["<things you GUESSED from what you saw — clearly mark inference>"],
      "attention_target": "<what the wearer was focused on: screen | person | chart | object | road | none>",
      "attention_duration_sec": float,    // how long focused on that target

      // ─── SCREEN ANALYSIS (when a screen is visible) ───
      "screen_analysis": {
        "device_type":      "phone" | "laptop" | "monitor" | "tv" | "tablet" | null,
        "app_visible":      "<e.g. TradingView, YouTube, Excel, Slack, Bloomberg>",
        "ui_elements":      ["<key UI elements visible>"],
        "documents_visible":["<documents/articles visible>"],
        "charts_detected":  ["<chart types: candlestick, line, bar, etc.>"],
        "text_detected":    "<verbatim short text fragments you can read>"
      },

      // ─── FINANCE-SPECIFIC FIELDS (REQUIRED when category="finance_analysis") ───
      // Leave null/empty for non-finance events. Fill DEEPLY for finance events.
      "instruments": [
        {
          "symbol": "<KOSPI | NVDA | 005930.KS | BTC | etc.>",
          "name":   "<full instrument/company/index name>",
          "type":   "index" | "stock" | "etf" | "crypto" | "sector" | "commodity" | "currency" | "bond"
        }
      ],
      "prices_seen": [
        {
          "instrument": "<symbol or name>",
          "value":      "<numeric with unit, e.g. '8,012.45' or '+2.3%' or '$420'>",
          "context":    "current" | "target" | "support" | "resistance" |
                        "open" | "close" | "high" | "low" | "52w_high" |
                        "52w_low" | "previous_close" | "market_cap" | "volume" | "pe"
        }
      ],
      "recommendations": [
        {
          "by":         "<anchor | analyst | strategist | brokerage name | host | unknown>",
          "instrument": "<symbol>",
          "action":     "BUY" | "STRONG_BUY" | "SELL" | "STRONG_SELL" |
                        "HOLD" | "ACCUMULATE" | "REDUCE" | "AVOID" | "WATCH",
          "horizon":    "intraday" | "short_term" | "medium_term" | "long_term" | null,
          "target_price": "<numeric or null>",
          "reasoning":  "<one-line reason given>"
        }
      ],
      "sentiment": {
        "overall": "very_bullish" | "bullish" | "neutral" | "bearish" | "very_bearish" | null,
        "by_instrument": [
          { "instrument": "<symbol>", "sentiment": "bullish" | "bearish" | "neutral",
            "evidence": "<which words/chart features drove this read>" }
        ]
      },
      "predictions": [
        {
          "subject":    "<what is being predicted>",
          "forecast":   "<the prediction text — concrete and specific>",
          "confidence": "high" | "medium" | "low" | "speculative" | null,
          "timeframe":  "<when this should play out, e.g. 'by end of Q2', 'next 3 months'>",
          "conditions": "<if-X-then-Y conditional, if any>"
        }
      ],
      "key_levels": [
        {
          "instrument": "<symbol>",
          "level":      "<numeric>",
          "type":       "support" | "resistance" | "breakout" | "stop_loss" |
                        "pivot" | "trendline" | "moving_avg"
        }
      ],
      "catalysts": [
        // upcoming earnings, FOMC, CPI, conferences, product launches etc.
        "<event name + when>"
      ],
      "narrative_summary": "<2-3 sentences in ANALYST voice — what the user just saw matters BECAUSE...>",
      "action_signals": [
        {
          "type":       "consider_buy" | "consider_sell" | "watch" |
                        "research_further" | "alert_threshold" | "rebalance" | "hedge",
          "instrument": "<symbol or asset class>",
          "trigger":    "<concrete condition, e.g. 'KOSPI closes above 8,050' or 'NVDA earnings beat'>",
          "urgency":    "high" | "medium" | "low"
        }
      ],

      // ─── DEEPER TECHNICAL ANALYSIS (when a chart is visible) ───
      "technical_analysis": {
        "trend":              "uptrend" | "downtrend" | "sideways" | null,
        "trend_strength":     "strong" | "moderate" | "weak" | null,
        "patterns":           ["<e.g. ascending_triangle, double_top, head_shoulders, breakout>"],
        "indicators":         {
          "rsi":              "<value if visible>",
          "macd":             "<bullish_cross | bearish_cross | flat | null>",
          "moving_avg":       "<e.g. price above 50MA, below 200MA>",
          "bollinger":        "<at upper | at lower | mid | null>"
        },
        "volume_confirmation":"strong" | "weak" | "absent" | null,
        "momentum":           "strong" | "moderate" | "weak" | "fading" | null,
        "breakout_probability":"high" | "medium" | "low" | null
      },

      // ─── MACRO / MARKET REGIME (when broad market commentary appears) ───
      "macro": {
        "market_regime":      "risk_on" | "risk_off" | "neutral" | null,
        "volatility_state":   "elevated" | "normal" | "subdued" | null,
        "sector_strength":    ["<sectors performing well, e.g. semiconductors, AI>"],
        "sector_weakness":    ["<sectors lagging>"],
        "macro_factors":      ["<rate cuts mentioned, FOMC concerns, geopolitics, etc.>"],
        "risk_factors":       ["<USD strength, bond yields, etc.>"]
      },

      // ─── CONVERSATION / SPOKEN CONTENT (one-sided OR two-way) ───
      // Fill this whenever ANY spoken content is present in the audio
      // transcript — including one-sided speech like a TV anchor, podcast
      // narrator, YouTube monologue, in-video instructor, or single-person
      // voice memo. Anchor monologue COUNTS as a conversation event.
      "conversation_detail": {
        "participants":   ["<roles only — e.g. 'anchor', 'narrator', 'host', 'guest', 'colleague', 'boss', 'user', 'stranger'>"],
        "key_points":     ["<main points raised — must have at least 1 entry if any speech was transcribed>"],
        "questions_asked":["<questions asked by user or others>"],
        "requests_received":["<things being asked of the user>"],
        "agreements":     ["<things explicitly agreed to>"],
        "action_items":   ["<concrete actions resulting>"]
      }
    }
  ],

  // ─── CLIP-LEVEL FIELDS (NEW v2) ───
  "segment_summary":  "<one sentence describing the whole clip>",
  "dominant_activity":"<the main thing the user was doing>",
  "finance_summary":  "<IF the clip contained finance content: a paragraph-long
                       ANALYST-QUALITY summary of what was said + shown, written
                       so an asset-management agent can act on it. Include the
                       single most important takeaway up front. If no finance
                       content at all: null.>",

  // ─── HUMAN STATE — soft-fill, OK to leave null for short clips ───
  "cognitive_state": {
    "focus_level":      "high" | "medium" | "low" | null,
    "engagement_level": "high" | "medium" | "low" | null,
    "fatigue_level":    "high" | "medium" | "low" | "none" | null,
    "stress_indicators":["<rubbing eyes | tense jaw | etc., if visible>"]
  },

  // ─── ANOMALIES — anything unusual ───
  "anomalies": [
    "<e.g. 'sudden market panic language', 'user working unusually late',
     'rapid context-switching between apps', 'long static stare', 'gesture
      of frustration'>"
  ],

  // ─── DIRECT TASKS FOR DOWNSTREAM AGENT — concrete, actionable ───
  // Empty list if no clear actions; else specific items the asset-mgmt or
  // assistant agent could execute on the user's behalf.
  "agent_tasks": [
    {
      "task":     "<e.g. 'Set price alert for NVDA above $145'>",
      "category": "alert | reminder | research | calendar | trade_idea | note",
      "due":      "<when, if any: 'today_market_close' | 'tomorrow_9am' | 'asap' | null>",
      "priority": "high" | "medium" | "low"
    }
  ],

  // ─── v3: MODALITY-SEPARATED CLIP-LEVEL EXTRACTION ───
  // Three NEW top-level objects. Powers the dashboard's 3 modality
  // panels (Video / Audio / Combined). Fill these in ADDITION to the
  // v2 fields above — never skip the v2 fields. If a modality is
  // absent (silent clip, no screen, etc.) set fields to [] / null /
  // {} as appropriate; do not omit the keys.
  "video_extraction": {
    "ocr_text_full":  ["<EVERY text item / number / ticker / price visible on screen, VERBATIM, one per element>"],
    "visual_objects": ["<people, devices, environment objects you SEE>"],
    "screen_content": {
      "app_or_source": "<e.g. 'YouTube', 'CNBC broadcast', 'KBS News', 'TradingView', 'Bloomberg Terminal'>",
      "ui_elements":   ["<player controls, ticker bar, headline overlay, etc.>"],
      "charts":        ["<chart types: candlestick, line, sparkline, etc.>"],
      "headlines":     ["<verbatim headline / chyron text>"]
    },
    "broadcast_mode": true | false
  },
  "audio_extraction": {
    "transcript_full":        "<full transcript as one string — use the audio_transcript block above verbatim if present>",
    "speaker_count_estimate": int,
    "audio_events":           ["<music, beep, applause, silence_dominant, etc.>"],
    "language_detected":      "<en | ko | mixed | none>",
    "audio_quality":          "good" | "partial" | "poor"
  },
  "combined_analysis": {
    "what_is_happening":       "<one-sentence cross-modal summary that uses BOTH video and audio>",
    "cross_modal_confidence":  float,   // 0.0-1.0 — how well do video + audio agree?
    "user_activity_inferred":  "<what the wearer is doing right now (1 short phrase)>",
    "importance_score":        float,   // 0.0-1.0 — overall clip importance
    "recall_estimate":         float,   // 0.0-1.0 — how much of what was visible/audible did you actually capture?
    // v3.1 Fix 3 — metrics whose displayed value changed during this chunk:
    "value_updates": [
      {
        "label":        "<the metric label, e.g. 'SK하이닉스'>",
        "values": [
          {"value": "<numeric string>", "frame_idx": int, "timestamp_sec": float}
        ],
        "change_count":   int,
        "first_seen_sec": float,
        "last_seen_sec":  float
      }
    ],
    // v3.1 Fix 4 — narrative timeline across the 4 sub-windows (if provided):
    "timeline": [
      {"window_sec": "0-15",  "summary": "<what was on screen during this 15-second window>", "key_items": ["<top 3-7 items>"]},
      {"window_sec": "15-30", "summary": "...", "key_items": [...]},
      {"window_sec": "30-45", "summary": "...", "key_items": [...]},
      {"window_sec": "45-60", "summary": "...", "key_items": [...]}
    ]
  },

  // ─── v3.3: DETAILED ENUMERATION (boss-facing — meaningful items only) ───
  // A flat list of one-sentence plain-English facts, ONE per MEANINGFUL item
  // (skip particles / single chars / OCR garbage — see the rule at the bottom).
  // This is what the user reads in the dashboard. Required (use [] if nothing).
  "enumerated_observations": [
    "<one plain-English sentence per MEANINGFUL on-screen / audio item>"
  ]
}

Rules:
- Each DISTINCT event is a SEPARATE object.
- Use ROLES for people (boss/colleague/stranger), not names — you don't know names.
- Sitting at a desk for 5 min = ONE event (don't repeat per second).
- If conversation: extract topic + any decisions/commitments separately.
- If food/drink: estimate kcal based on visible portion.
- Korean speech → keep Korean in short fields. Numbers → use digits. Tickers → uppercase Latin.
- v2 ENRICHMENT RULES (apply to EVERY event):
    * ALWAYS fill `confidence` (0.0-1.0). If you're guessing, ≤0.5.
    * `observed_facts`: list 15-30 SUBSTANTIVE factual statements about what is on
      screen / what the user sees. Each MUST follow WHO-or-WHAT + RELATIONSHIP/VALUE.
      GOOD:
        - "KOSPI index displayed at 8,228.70, up 181.19 points (+2.25%)."
        - "Samsung Electronics at 307,000 won, gaining 8,000 won (+2.68%)."
        - "Headline reports SK Hynix joined the $1 trillion market-cap club."
        - "UBS raised Micron target price from $535 to $1,625 (3x upgrade)."
        - "News broadcast shown on KBS11 with a sign-language interpreter overlay."
      BAD (DO NOT WRITE): "KOSPI is visible" (no value); "Stock chart on screen"
        (no subject); "Korean text shown" (no content).
      If >=15 unique substantive facts are available from OCR + context, include
      them ALL; fewer only if the scene genuinely lacks content. Keep
      `inferred_context` for GUESSES, clearly separate from observed_facts.
    * ALWAYS fill `importance` (1-10). Stock recommendation = 8-9; sip of water = 2.
    * ALWAYS fill `memory_relevance`. Random office sitting = "low"; financial advice = "high".
    * Fill `screen_analysis` whenever ANY screen is visible.
    * Fill `technical_analysis` whenever ANY chart is visible — including TA indicators
      if you can read them (RSI value, MA crossover, breakout pattern, etc.).
    * Fill `macro` block only when broader market regime / sector commentary appears.
    * Fill `conversation_detail` whenever ANY spoken content is present in
      the audio transcript — even on a screen-content event. A TV anchor,
      podcast narrator, YouTube monologue, instructor, or single-person
      voice memo COUNTS as a conversation event. Use participants like
      ["anchor"], ["narrator"], ["host"] for one-sided speech. key_points
      MUST have at least one entry if any speech was transcribed.
    * Use start_sec and end_sec for precise time bounds (0.0 to clip_duration_seconds).
- CLIP-LEVEL ANALYSIS:
    * `cognitive_state`: ONLY fill if you have solid visual/audio cues. OK to leave null.
    * `anomalies`: list anything unusual or salient — empty list if nothing.
    * `agent_tasks`: concrete actions for the downstream agent. Empty list if none.
- FINANCE content rules (CRITICAL):
    * ALWAYS emit a "finance_analysis" event when ANY of these appear: chart,
      candlestick, ticker, price ticker, stock name, market index name, earnings
      number, "buy/sell/hold", "bullish/bearish", interest-rate talk, financial
      anchor in a studio, candlestick chart on phone/PC screen.
    * READ THE CHART VISUALLY. Identify trend (uptrend/downtrend/sideways),
      pattern (breakout, double-top, head-and-shoulders, etc.), key levels.
      Don't just say "a chart is shown".
    * Extract EVERY NUMBER you can see, with its context.
    * Extract EVERY RECOMMENDATION the anchor/analyst makes.
    * Infer sentiment from anchor's word choice + chart visuals.
    * Output is for a downstream stock-trading agent. Be CONCRETE and ACTIONABLE,
      not vague. "Anchor suggests KOSPI may consolidate below 8,000 due to FX
      pressure" is good. "User watched financial news" is useless.
- If genuinely nothing observable, return {"events": [], "finance_summary": null, ...}.
- DO NOT invent events that aren't in the clip.
- v3 MODALITY EXTRACTION RULES (apply to EVERY clip):
    * Fill `video_extraction.ocr_text_full` by enumerating EVERY text item
      you can see on screen. If an OCR pre-pass text block was injected
      above this prompt under "## On-screen text detected by OCR", that
      list is GROUND TRUTH from a dedicated OCR engine. Include EVERY one
      of those items in your `ocr_text_full` array verbatim — do NOT
      summarize, do NOT drop entries, do NOT translate. Then add any
      additional text you yourself can read that the OCR missed.
    * Fill `audio_extraction.transcript_full` with the audio transcript
      verbatim. Do not summarize. Estimate speaker count from voice
      distinctness (1 if anchor monologue, 2+ if dialogue).
    * `combined_analysis.recall_estimate` is your honest self-assessment:
      0.95+ if you captured everything you could possibly observe, 0.7 if
      you missed a few minor items, 0.4 if you summarized away significant
      detail. Be honest — downstream uses this to flag low-recall clips.
    * `combined_analysis.cross_modal_confidence` is high (>=0.8) when video
      and audio AGREE (e.g. anchor visible AND anchor speaking about NVDA),
      low (<=0.4) when they disagree or one is missing.
- v3.3 DETAILED ENUMERATION (do NOT skip — this is what the user actually reads):
    Populate the top-level `enumerated_observations` array with one factual
    sentence per MEANINGFUL on-screen / audio item. A MEANINGFUL item conveys
    information. Items WITHOUT information MUST be SKIPPED (do not write a
    sentence for them):
      * Single Korean particles ("의","를","는","이","가") -> SKIP
      * Single Latin letters -> SKIP
      * OCR-garbled tokens (mixed character sets, broken CamelCase, repeated
        junk like "LLLVA"/"WiHdoWs", mojibake / replacement chars) -> SKIP
      * Standalone "X is visible" with no value or context -> SKIP
    For MEANINGFUL items, write a sentence with subject + value/relationship:
      GOOD:
        - "Stock index KOSPI shows value 8,228.70."
        - "Samsung Electronics stock price displayed at 307,000 won."
        - "Foreign exchange rate USD/KRW shown at 1,501.80."
        - "Headline reads 'ETF 업고 반도체 독주 이틀째 최고치'."
        - "QR code visible in the bottom-left corner of the screen."
      BAD (DO NOT WRITE THESE):
        - "The text '의' is visible on the screen." (particle, no info)
        - "The character '를' is visible." (single character)
        - "The text 'WiHdoWs' is visible on the screen." (OCR garbage)
        - "The number '0' is visible." (no context for the digit)
    Target 50-150 MEANINGFUL sentences. Quality beats quantity — if an OCR item
    is ambiguous or garbled, OMIT it rather than write a low-info sentence.
    `observed_facts` is the substantive high-level layer; `enumerated_observations`
    is the detailed per-item layer. BOTH are required.
"""


# ──────────────────────────────────────────────────────────────────────
# Frame sampling from a time window of a video
# ──────────────────────────────────────────────────────────────────────

def sample_frames_window(video_path: Path, start_sec: float, end_sec: float,
                          n_frames: int = 8) -> list:
    """Sample n_frames evenly across [start_sec, end_sec] of the video."""
    import av
    container = av.open(str(video_path))
    stream = container.streams.video[0]
    fps = float(stream.average_rate or 30)
    target_pts_list = [
        start_sec + (end_sec - start_sec) * (i + 0.5) / n_frames
        for i in range(n_frames)
    ]
    target_pts_set = sorted({int(round(t * fps)) for t in target_pts_list})

    frames = []
    for i, frame in enumerate(container.decode(video=0)):
        if i in target_pts_set:
            frames.append(frame.to_image())
            if len(frames) >= n_frames:
                break
    container.close()
    return frames


# ──────────────────────────────────────────────────────────────────────
# Audio extraction + Whisper transcript (optional, hugely improves quality)
# ──────────────────────────────────────────────────────────────────────

# Local faster-whisper. Model is cached at module scope after first load.
# DEVICE = "cpu" on purpose: Gemma 4 26B Q8 needs ~30GB of the 32GB GPU, so
# Paddle (OCR, ~1.5GB) + Gemma already nearly fill it. Putting Whisper on the
# GPU too (its model + torch's CUDA context) made Ollama spill Gemma to CPU and
# time out. CPU Whisper (int8, ~30-60s for a 60s clip on the Ryzen 9800X3D)
# keeps the GPU free for Gemma — and sidesteps the ctranslate2 cuDNN WinError
# 127 entirely (CPU backend needs no cuDNN). Override to "cuda"/"float16" only
# for cloud-only arm runs where no big local model competes for VRAM.
WHISPER_MODEL_NAME = "large-v3"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"
_WHISPER_MODEL = None


def _get_whisper_model():
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        # torch is preimported at module top (BEFORE paddle) — that ordering is
        # what lets ctranslate2 resolve cuDNN9/cuBLAS and avoids WinError 127.
        from faster_whisper import WhisperModel
        _WHISPER_MODEL = WhisperModel(
            WHISPER_MODEL_NAME,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )
    return _WHISPER_MODEL


def extract_audio(video_path: Path) -> Optional[Path]:
    """ffmpeg-extract mono 16kHz WAV from the video."""
    import subprocess
    audio_path = video_path.with_suffix(".lifelog_audio.wav")
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-ac", "1", "-ar", "16000", "-f", "wav",
        str(audio_path),
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=300)
        return audio_path
    except Exception as e:
        print(f"  [audio] ffmpeg failed: {e}")
        return None


def whisper_transcribe(audio_path: Path) -> Optional[dict]:
    """Returns {"text": full_transcript, "segments": [{start, end, text}, ...]}"""
    try:
        model = _get_whisper_model()
        segments_iter, info = model.transcribe(
            str(audio_path),
            language=None,
            temperature=0,
            vad_filter=True,
        )
        seg_list = []
        text_parts = []
        for s in segments_iter:
            text = (s.text or "").strip()
            seg_list.append({"start": float(s.start), "end": float(s.end), "text": text})
            text_parts.append(text)
        return {
            "text": " ".join(text_parts).strip(),
            "language": info.language,
            "segments": seg_list,
        }
    except Exception as e:
        print(f"  [whisper] failed: {e}")
        return None


def transcript_slice(transcript: Optional[dict], start_sec: float, end_sec: float) -> str:
    """Extract the transcript text covering a time window."""
    if not transcript:
        return ""
    parts = []
    for s in transcript.get("segments", []):
        if s["start"] >= end_sec or s["end"] <= start_sec:
            continue
        parts.append(s["text"])
    return " ".join(parts).strip()


def _build_user_prompt(transcript_text: str = "", ocr_text: str = "",
                       value_updates: Optional[list] = None,
                       ocr_by_window: Optional[list[dict]] = None) -> str:
    """Compose the user-turn text block: OCR ground-truth + transcript + schema.

    Section order (matters):
      1. OCR ground-truth — v3 Fix 1/2 dense OCR dump (optionally split into
         per-window sub-sections from Fix 4 when ocr_by_window is supplied).
      2. Value updates — v3 Fix 3, metrics that changed value mid-chunk.
      3. Audio transcript.
      4. LIFELOG_PROMPT schema instructions.
    """
    parts: list[str] = []
    if ocr_by_window:
        # Fix 4: temporally-organized OCR results across 4 sub-windows
        win_blocks = ["## OCR text by sub-window (temporally organized)"]
        for w in ocr_by_window:
            label = w.get("window_sec", "?")
            n_frames = w.get("frame_count", 0)
            n_panels = w.get("panels_detected", 0)
            items = w.get("items", [])
            items_block = ", ".join(items[:100]) if items else "(no text detected)"
            win_blocks.append(
                f"### Window {label}s ({n_frames} frames, {n_panels} panels)\n"
                f"Items: {items_block}"
            )
        win_blocks.append(
            "Use the per-window structure to track how content evolved. In "
            "`combined_analysis.timeline`, produce a sub-window-by-sub-window "
            "narrative (one entry per window). DO NOT collapse windows. In "
            "`video_extraction.ocr_text_full`, list every unique item across "
            "all windows."
        )
        parts.append("\n\n".join(win_blocks))
    elif ocr_text:
        parts.append(
            "## On-screen text detected by OCR (high confidence, ground-truth):\n"
            f"{ocr_text}\n\n"
            "Your job: enumerate EVERY item above in the appropriate field "
            "(`video_extraction.ocr_text_full`). Do not summarize. Do not skip "
            "any number, ticker symbol, percentage, or currency value."
        )
    if value_updates:
        lines = ["## Value updates detected during this chunk",
                 "The following metrics changed value during the recording window:"]
        for vu in value_updates:
            label = vu.get("label", "?")
            vals = vu.get("values", [])
            seq = " -> ".join(f"{v.get('value','?')} (at {v.get('timestamp_sec',0)}s)" for v in vals)
            lines.append(f"- {label}: {seq}")
        lines.append(
            "List ALL of these in `combined_analysis.value_updates` and explain "
            "the change in `combined_analysis.what_is_happening`."
        )
        parts.append("\n".join(lines))
    else:
        # No pre-detected changes (noisy OCR can't pair labels<->values). Still
        # ask the VLM to report any value change it sees directly in the frames,
        # so value_updates isn't silently empty on broadcasts with live tickers.
        parts.append(
            "## Value updates\n"
            "If any on-screen metric, index, stock price, or FX rate shows DIFFERENT "
            "values at different points in this clip (a ticker ticking up/down, a "
            "price that updates), report each in `combined_analysis.value_updates` as "
            "{label, values:[{value, timestamp_sec}], change_count}. Empty list if none."
        )
    if transcript_text:
        parts.append(f'Audio transcript for this clip: "{transcript_text}"')
    parts.append(LIFELOG_PROMPT)
    return "\n\n".join(parts)


# ──────────────────────────────────────────────────────────────────────
# Gemma vision call (local Ollama)
# ──────────────────────────────────────────────────────────────────────

# Single source of truth for the Gemma model name. Used both in the API
# body and (normalized) as the DB event source tag so the two cannot drift.
GEMMA_MODEL = "gemma4:26b-a4b-it-q8_0"


def _model_to_source_tag(name: str) -> str:
    """Normalize a model name into a DB-safe source tag.

    Drops vendor prefix (text before the first '/'), then lowercases and
    replaces separators ( : - . space ) with '_'. Result is capped at 30
    chars to fit the lifelog_event.source_model VARCHAR(30) column.
    """
    import re as _re
    base = name.split("/", 1)[-1]
    s = _re.sub(r"[:\-.\s]+", "_", base.lower())
    s = _re.sub(r"_+", "_", s).strip("_")
    return s[:30]

GEMMA_MAX_FRAMES = 6  # Mac mini Gemma 4 E4B 500s on 8 real frames (vision-
                      # encoder OOM in the mmproj forward pass). Healthcare
                      # watcher runs at 6 for the same reason. Qwen and Llama 4
                      # via NIM still see all 8 — NIM has the headroom.

# Mac mini's llama-server can host one Gemma inference at a time; two
# concurrent requests crash the server (500 / disconnect) due to vision-
# encoder contention. Serialize all Gemma calls process-wide. NIM-hosted
# Qwen/Llama4 stay fully concurrent — only Gemma is gated.
# Shared by BOTH local Ollama arms (Gemma 4 + Qwen3-VL). They run on the same
# single GPU at localhost:11434, so only one may infer at a time — otherwise
# they contend and one stalls past its timeout (observed: Gemma timing out
# while Qwen held the GPU under full 4-arm parallelism). Cloud arms (Llama4,
# Gemini) are unaffected and still run fully in parallel with the local one.
_LOCAL_OLLAMA_LOCK = threading.Lock()

def call_gemma_lifelog(frames: list, transcript_text: str = "",
                       max_tokens: int = 12000,  # v3.2: room for enumerated_observations
                       ocr_text: str = "",
                       value_updates: Optional[list] = None,
                       ocr_by_window: Optional[list[dict]] = None) -> tuple[Optional[dict], int, Optional[str]]:
    """Send frames + transcript + LIFELOG_PROMPT to Gemma 4 (local Ollama).

    Serialized via _LOCAL_OLLAMA_LOCK — shared with Qwen3-VL so the two local
    arms never infer simultaneously on the single GPU.
    """
    if not frames:
        return None, 0, "no_frames"
    # Evenly subsample down to GEMMA_MAX_FRAMES.
    if len(frames) > GEMMA_MAX_FRAMES:
        step = len(frames) / GEMMA_MAX_FRAMES
        frames = [frames[int(i * step)] for i in range(GEMMA_MAX_FRAMES)]
    content = [{"type": "image_url", "image_url": {"url": _img_to_data_url(f)}}
               for f in frames]
    prompt = _build_user_prompt(transcript_text, ocr_text,
                                value_updates=value_updates,
                                ocr_by_window=ocr_by_window)
    content.append({"type": "text", "text": prompt})

    body = {
        "model": GEMMA_MODEL,
        "messages": [
            {"role": "system", "content": _GEMMA_SYSTEM_INSTRUCTION},
            {"role": "user", "content": content},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    t0 = time.perf_counter()
    try:
        with _LOCAL_OLLAMA_LOCK:
            with httpx.Client(timeout=GEMMA_TIMEOUT_SEC * 2) as client:
                resp = client.post(f"{GEMMA_BASE_URL}/v1/chat/completions", json=body)
                resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            parsed, mode = _try_parse_lifelog_json(text)
            if parsed is None:
                ms = int((time.perf_counter() - t0) * 1000)
                _log_failed_parse("gemma", text, f"mode={mode}, len={len(text)}")
                return None, ms, f"json_parse_failed (mode={mode}, len={len(text)})"
        ms = int((time.perf_counter() - t0) * 1000)
        return parsed, ms, None
    except httpx.HTTPStatusError as e:
        # Surface the server's actual error body — httpx truncates the
        # default message to a one-liner that hides the diagnostic.
        ms = int((time.perf_counter() - t0) * 1000)
        body_snip = ""
        try:
            body_snip = (e.response.text or "")[:300].replace("\n", " ")
        except Exception:
            pass
        return None, ms, f"HTTP {e.response.status_code}: {body_snip}"
    except Exception as e:
        ms = int((time.perf_counter() - t0) * 1000)
        return None, ms, f"{type(e).__name__}: {str(e)[:160]}"


# ──────────────────────────────────────────────────────────────────────
# Tolerant JSON parser for NIM responses
# ──────────────────────────────────────────────────────────────────────
# Llama4 and (occasionally) Qwen produce malformed JSON: missing commas
# between adjacent objects, unterminated strings on the very last event,
# stray markdown fences, etc. This helper tries the raw text first, then
# applies common regex fixes, then falls back to extracting just the
# `events` array. Returns (parsed_dict, recovered_flag) — recovered_flag
# is True if any cleanup step beyond the direct parse succeeded.

def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    if text.endswith("```"):
        text = text[:-3].rstrip()
    return text


def _try_parse_lifelog_json(text: str) -> tuple[Optional[dict], str]:
    """Parse a lifelog JSON response with progressive cleanup fallbacks.

    Returns (parsed_dict_or_None, recovery_mode) where recovery_mode is one
    of: "clean" (direct parse worked), "regex_fix" (regex repair worked),
    "events_only" (extracted just the events array), "failed".
    """
    text = _strip_markdown_fences(text)

    # 1. Direct parse — happy path.
    try:
        return json.loads(text), "clean"
    except json.JSONDecodeError:
        pass

    # 2. Common LLM JSON mistakes — regex repairs.
    fixed = text
    # Missing comma between adjacent objects in an array:  `}` then `{`
    fixed = re.sub(r"\}(\s*)\{", r"},\1{", fixed)
    # Missing comma between an array close and the next key:  `]` then `"`
    fixed = re.sub(r"\](\s*)\"", r"],\1\"", fixed)
    # Missing comma between two string values on adjacent lines.
    fixed = re.sub(r'"(\s*\n\s*)"', r'",\1"', fixed)
    # Trailing commas before `}` or `]` (some models add these).
    fixed = re.sub(r",(\s*[}\]])", r"\1", fixed)
    if fixed != text:
        try:
            return json.loads(fixed), "regex_fix"
        except json.JSONDecodeError:
            pass

    # 3. Last resort: pull out just the `events` array. We walk the bracket
    # depth ourselves so a single bad string in the tail doesn't kill the
    # whole array.
    m = re.search(r'"events"\s*:\s*\[', text)
    if m:
        start = m.end() - 1  # position of the opening [
        depth = 0
        end = -1
        last_obj_end = -1  # index just after a top-level element closed at depth 1
        in_str = False
        esc = False
        for i in range(start, len(text)):
            c = text[i]
            if esc:
                esc = False
                continue
            if c == "\\":
                esc = True
                continue
            if c == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
            elif c == "}" and depth == 1:
                last_obj_end = i + 1
        # Pick the array text: full close if found, else (TRUNCATED output —
        # the common Qwen/Llama4 failure when a verbose enumeration overruns
        # max_tokens) salvage up to the last COMPLETE element and close it.
        if end > 0:
            arr_text, mode = text[start:end], "events_only"
        elif last_obj_end > 0:
            arr_text, mode = text[start:last_obj_end] + "]", "events_truncated"
        else:
            # Truncated within the first/only object (Qwen repetition loop):
            # balance-close open strings/brackets to recover its complete fields.
            arr_text, mode = _close_truncated_array(text[start:]), "events_balanced"
        if arr_text:
            arr_text = re.sub(r"\}(\s*)\{", r"},\1{", arr_text)
            arr_text = re.sub(r",(\s*])", r"\1", arr_text)  # trailing comma
            try:
                events = json.loads(arr_text)
                if isinstance(events, list) and events:
                    result = {"events": events, "segment_summary": "",
                              "dominant_activity": ""}
                    enum = _salvage_enumerated_observations(text)
                    if enum:
                        result["enumerated_observations"] = enum
                    return result, mode
            except json.JSONDecodeError:
                pass

    return None, "failed"


def _close_truncated_array(s: str) -> Optional[str]:
    """Given text starting at an opening '[' that was truncated before closing,
    balance-close open strings/brackets so json.loads can parse it. Recovers
    the complete fields of a partially-emitted final object. Returns None if it
    can't form anything plausible. The caller still json.loads-guards the
    result, so a malformed close just falls through to 'failed'."""
    if not s or s[0] != "[":
        return None
    stack: list[str] = []
    in_str = False
    esc = False
    for c in s:
        if esc:
            esc = False
            continue
        if c == "\\":
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c in "[{":
            stack.append(c)
        elif c in "]}":
            if stack:
                stack.pop()
    res = s.rstrip()
    if in_str:
        res += '"'              # close the truncated string value
    else:
        # Drop a dangling separator / value-less key at the truncation point.
        res = re.sub(r'(,|"[^"]*"\s*:)\s*$', "", res)
    for b in reversed(stack):
        res += "]" if b == "[" else "}"
    return res


def _salvage_enumerated_observations(text: str) -> list[str]:
    """Best-effort recovery of the flat enumerated_observations string array
    from a truncated response. It's the last/longest field in the schema, so
    when an arm overruns max_tokens this array is what gets cut — grab every
    complete quoted string up to the array close (or end of text if truncated).
    """
    m = re.search(r'"enumerated_observations"\s*:\s*\[', text)
    if not m:
        return []
    sub = text[m.end():]
    close = sub.find("]")
    if close != -1:
        sub = sub[:close]
    return [s for s in re.findall(r'"((?:[^"\\]|\\.)*)"', sub) if s.strip()]


# ──────────────────────────────────────────────────────────────────────
# Qwen3-VL via local Ollama (only when --compare is set)
# ──────────────────────────────────────────────────────────────────────

QWEN_BASE_URL = "http://localhost:11434"  # Local Ollama
# Qwen3-VL 30B A3B (MoE — 31.1B total params, ~3.8B active per token, 256K
# context). Using Q4_K_M (~19 GB) — Q8_0 (33 GB) OOM'd on the RTX 5090's 32 GB
# VRAM once mmproj + KV cache were factored in. Q4 fits with ~13 GB headroom.
QWEN_MODEL = "qwen3-vl:30b-a3b-instruct-q4_K_M"
# Qwen3-VL Q4 is slow and inconsistent (130-180s when it returns; sometimes
# longer). 300s single attempt + no retry beats 2x180s: gives a slow-but-valid
# response time to finish so the truncation salvage can recover it, without
# doubling wall-clock on a genuine hang.
QWEN_TIMEOUT_SEC = 300
QWEN_RETRIES = 0

def call_qwen_lifelog(frames: list, transcript_text: str = "",
                      max_tokens: int = 15000,  # v3.2: room for enumerated_observations
                      ocr_text: str = "",
                      value_updates: Optional[list] = None,
                      ocr_by_window: Optional[list[dict]] = None) -> tuple[Optional[dict], int, Optional[str]]:
    """Send same payload to local Qwen3-VL via Ollama's OpenAI-compat endpoint."""
    if not frames:
        return None, 0, "no_frames"

    content = [{"type": "image_url", "image_url": {"url": _img_to_data_url(f)}}
               for f in frames]
    prompt = _build_user_prompt(transcript_text, ocr_text,
                                value_updates=value_updates,
                                ocr_by_window=ocr_by_window)
    content.append({"type": "text", "text": prompt})

    body = {
        "model": QWEN_MODEL,
        "messages": [
            {"role": "system", "content": _GEMMA_SYSTEM_INSTRUCTION},
            {"role": "user", "content": content},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
        # Qwen3-VL Q4 is prone to degenerate repetition loops (observed: it
        # repeated "...US dollar to X exchange rate" until it overran the token
        # budget and truncated mid-string, breaking the JSON). Frequency +
        # presence penalties break the loop so it emits complete, valid JSON.
        "frequency_penalty": 0.5,
        "presence_penalty": 0.3,
    }
    headers = {
        "Content-Type": "application/json",
    }
    t0 = time.perf_counter()
    last_err: Optional[str] = None
    for attempt in range(QWEN_RETRIES + 1):
        try:
            # Serialize against Gemma on the shared GPU. Waiting on the lock is
            # NOT bounded by QWEN_TIMEOUT_SEC (that only starts on the POST once
            # acquired), so Qwen no longer times out merely because Gemma is
            # mid-inference. Reported ms includes the wait (accurate wall-clock).
            with _LOCAL_OLLAMA_LOCK:
                with httpx.Client(timeout=QWEN_TIMEOUT_SEC) as client:
                    resp = client.post(f"{QWEN_BASE_URL}/v1/chat/completions", headers=headers, json=body)
                    resp.raise_for_status()
                data = resp.json()
            text = data["choices"][0]["message"]["content"]
            parsed, mode = _try_parse_lifelog_json(text)
            if parsed is None:
                last_err = f"JSONDecodeError after cleanup ({len(text)} chars returned)"
                _log_failed_parse("qwen", text, last_err)
                break
            ms = int((time.perf_counter() - t0) * 1000)
            note = None if mode == "clean" else f"json_recovered:{mode}"
            return parsed, ms, note
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError) as e:
            last_err = f"{type(e).__name__}: {str(e)[:160]}"
            if attempt < QWEN_RETRIES:
                time.sleep(5)
                continue
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:160]}"
            break
    ms = int((time.perf_counter() - t0) * 1000)
    return None, ms, last_err


# ──────────────────────────────────────────────────────────────────────
# Llama 4 Maverick via NVIDIA NIM API (only when --llama4 is set)
# ──────────────────────────────────────────────────────────────────────

NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

# Per NVIDIA Developer catalog (build.nvidia.com), May 2026:
#   Llama 4 Maverick — 17B active / 400B total (128 experts, MoE).
#   Natively multimodal (image+text) via early fusion; trained on video frame
#   stills. Beats GPT-4o on coding/reasoning, LMArena ELO 1417.
#   Same OpenAI-compat NIM endpoint + free tier credits as Qwen.
#   Live probe 2026-05-12: status 200, vision input accepted.
#   (Scout returned 410 Gone — Maverick is the only Llama 4 ID on NIM.)
LLAMA4_MODEL = "meta/llama-4-maverick-17b-128e-instruct"
# 17B active params — usually faster than Qwen 3.5 VLM 397B but still
# NIM-hosted, so cold starts + queueing can spike. 120s is a safe cap.
LLAMA4_TIMEOUT_SEC = 120
LLAMA4_RETRIES = 2  # NIM intermittently rejects concurrent requests; retry covers it

def call_llama4_lifelog(frames: list, transcript_text: str = "",
                        max_tokens: int = 8192,  # NIM Maverick caps completion tokens; 8192 is safe (Llama4 stays terse)
                        ocr_text: str = "",
                       value_updates: Optional[list] = None,
                       ocr_by_window: Optional[list[dict]] = None) -> tuple[Optional[dict], int, Optional[str]]:
    """Send same payload to Llama 4 Maverick via NVIDIA NIM."""
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        env_path = Path(__file__).parent.parent.parent / "backend" / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("NVIDIA_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
    if not api_key:
        return None, 0, "no_NVIDIA_API_KEY"
    if not frames:
        return None, 0, "no_frames"

    content = [{"type": "image_url", "image_url": {"url": _img_to_data_url(f)}}
               for f in frames]
    prompt = _build_user_prompt(transcript_text, ocr_text,
                                value_updates=value_updates,
                                ocr_by_window=ocr_by_window)
    content.append({"type": "text", "text": prompt})

    body = {
        "model": LLAMA4_MODEL,
        "messages": [
            {"role": "system", "content": _GEMMA_SYSTEM_INSTRUCTION},
            {"role": "user", "content": content},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    t0 = time.perf_counter()
    last_err: Optional[str] = None
    for attempt in range(LLAMA4_RETRIES + 1):
        try:
            with httpx.Client(timeout=LLAMA4_TIMEOUT_SEC) as client:
                resp = client.post(NIM_URL, headers=headers, json=body)
                resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            parsed, mode = _try_parse_lifelog_json(text)
            if parsed is None:
                last_err = f"JSONDecodeError after cleanup ({len(text)} chars returned)"
                _log_failed_parse("llama4", text, last_err)
                break
            ms = int((time.perf_counter() - t0) * 1000)
            note = None if mode == "clean" else f"json_recovered:{mode}"
            return parsed, ms, note
        except httpx.HTTPStatusError as e:
            sc = e.response.status_code
            try:
                body = e.response.text[:300]
            except Exception:
                body = ""
            last_err = f"HTTP {sc}: {body}"
            # NIM intermittently 5xx/400's on large multimodal requests (server
            # side — an immediate retry hits the same failing instance), so back
            # off longer to land on a healthy instance. Non-transient 4xx won't
            # recover but the extra wait is bounded by LLAMA4_RETRIES.
            if attempt < LLAMA4_RETRIES and sc in (400, 408, 409, 425, 429, 500, 502, 503, 504):
                time.sleep(12)
                continue
            break
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError) as e:
            last_err = f"{type(e).__name__}: {str(e)[:160]}"
            if attempt < LLAMA4_RETRIES:
                time.sleep(5)
                continue
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:160]}"
            break
    ms = int((time.perf_counter() - t0) * 1000)
    return None, ms, last_err


# ──────────────────────────────────────────────────────────────────────
# Gemini (Google AI Studio) — only when --gemini is set
# ──────────────────────────────────────────────────────────────────────

GEMINI_MODEL_DEFAULT = "gemini-3.1-pro"
GEMINI_TIMEOUT_SEC = 120
GEMINI_RETRIES = 1


def _gemini_config() -> tuple[Optional[str], str]:
    """Return (api_key, model_id). Reads env first, then backend/.env."""
    api_key = os.environ.get("GEMINI_API_KEY")
    model = os.environ.get("GEMINI_MODEL") or GEMINI_MODEL_DEFAULT
    env_path = Path(__file__).parent.parent.parent / "backend" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if not api_key and line.startswith("GEMINI_API_KEY="):
                api_key = line.split("=", 1)[1].strip()
            elif not os.environ.get("GEMINI_MODEL") and line.startswith("GEMINI_MODEL="):
                v = line.split("=", 1)[1].strip()
                if v:
                    model = v
    return api_key, model


def call_gemini_lifelog(frames: list, transcript_text: str = "",
                        max_tokens: int = 20000,  # v3.2: room for enumerated_observations
                        ocr_text: str = "",
                       value_updates: Optional[list] = None,
                       ocr_by_window: Optional[list[dict]] = None) -> tuple[Optional[dict], int, Optional[str]]:
    """Send the same multimodal payload to Gemini (Google AI Studio).

    Modeled after [call_llama4_lifelog]: same LIFELOG_PROMPT, same JSON
    parsing path, same retry/timeout shape. Differences:
      - Endpoint is Gemini's generativelanguage REST API (not NIM/OpenAI-shape).
      - Frames are inlined as base64 `inline_data` parts (Gemini multimodal),
        not OpenAI-shape `image_url` content blocks.
      - System instruction goes in a separate `systemInstruction` field.
      - `responseMimeType="application/json"` to encourage clean JSON output.
    """
    api_key, model = _gemini_config()
    if not api_key:
        return None, 0, "no_GEMINI_API_KEY"
    if not frames:
        return None, 0, "no_frames"

    prompt = _build_user_prompt(transcript_text, ocr_text,
                                value_updates=value_updates,
                                ocr_by_window=ocr_by_window)

    # _img_to_data_url returns "data:image/jpeg;base64,XXX" — Gemini wants
    # the raw base64 string with mime_type in a separate field.
    parts: list[dict] = [{"text": prompt}]
    for f in frames:
        data_url = _img_to_data_url(f)
        b64 = data_url.split(",", 1)[1] if "," in data_url else data_url
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})

    body = {
        "systemInstruction": {"parts": [{"text": _GEMMA_SYSTEM_INSTRUCTION}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    t0 = time.perf_counter()
    last_err: Optional[str] = None
    for attempt in range(GEMINI_RETRIES + 1):
        try:
            with httpx.Client(timeout=GEMINI_TIMEOUT_SEC) as client:
                resp = client.post(url, headers=headers, json=body)
                resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                last_err = f"no_candidates: {str(data)[:160]}"
                break
            cand0 = candidates[0]
            parts_resp = (cand0.get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts_resp if isinstance(p, dict))
            if not text:
                last_err = f"empty_text (finishReason={cand0.get('finishReason')})"
                break
            parsed, mode = _try_parse_lifelog_json(text)
            if parsed is None:
                last_err = f"JSONDecodeError after cleanup ({len(text)} chars returned)"
                _log_failed_parse("gemini", text, last_err)
                break
            ms = int((time.perf_counter() - t0) * 1000)
            note = None if mode == "clean" else f"json_recovered:{mode}"
            return parsed, ms, note
        except httpx.HTTPStatusError as e:
            # 429 = quota exhaustion. Wait the server-suggested time when
            # provided (Retry-After header), otherwise 30s; retry once.
            if e.response is not None and e.response.status_code == 429 and attempt < GEMINI_RETRIES:
                wait_s = 30
                ra = e.response.headers.get("Retry-After") if e.response is not None else None
                if ra:
                    try: wait_s = max(5, min(120, int(float(ra))))
                    except (TypeError, ValueError): pass
                last_err = f"HTTP 429 — sleeping {wait_s}s then retrying"
                time.sleep(wait_s)
                continue
            last_err = f"{type(e).__name__}: {str(e)[:160]}"
            break
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError) as e:
            last_err = f"{type(e).__name__}: {str(e)[:160]}"
            if attempt < GEMINI_RETRIES:
                time.sleep(5)
                continue
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:160]}"
            break
    ms = int((time.perf_counter() - t0) * 1000)
    return None, ms, last_err


# ──────────────────────────────────────────────────────────────────────
# Supabase writer (writes each event row into lifelog_event)
# ──────────────────────────────────────────────────────────────────────

def _load_supabase_creds() -> tuple[str, str]:
    """Read SUPABASE_URL + service-role key from backend/.env."""
    env_path = Path(__file__).parent.parent.parent / "backend" / ".env"
    url = key = ""
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("SUPABASE_URL="):
                url = line.split("=", 1)[1].strip()
            elif line.startswith("SUPABASE_SERVICE_ROLE_KEY="):
                key = line.split("=", 1)[1].strip()
    return url, key


def write_events_to_supabase(events: list, source_model: str, source_video: str,
                              video_start_utc: datetime, user_id: int) -> int:
    """Bulk-insert lifelog events. observed_at = video_start_utc + t_sec_abs."""
    if not events:
        return 0
    url, key = _load_supabase_creds()
    if not url or not key:
        print(f"    [supabase] skipped — no SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in backend/.env")
        return 0

    rows = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        try:
            t_off = float(ev.get("t_sec_abs", 0) or 0)
        except (TypeError, ValueError):
            t_off = 0.0
        observed_at = (video_start_utc + timedelta(seconds=t_off)).isoformat()

        def _maybe_int(v):
            try: return int(v) if v not in (None, "") else None
            except (TypeError, ValueError): return None

        # v3 side-channel attached by _process_chunk. Pulled before raw_event
        # is built so raw_event remains the pure VLM output (no _-prefixed cruft).
        v3_video    = ev.pop("_video_extraction", None)
        v3_audio    = ev.pop("_audio_extraction", None)
        v3_combined = ev.pop("_combined_analysis", None)
        ocr_full    = ev.pop("_ocr_text_full", None)
        broadcast   = ev.pop("_broadcast_mode", False)
        fs_rate     = ev.pop("_frame_sampling_rate", None)
        enumerated  = ev.pop("_enumerated_observations", None)
        if not isinstance(enumerated, list):
            enumerated = []

        try:
            recall = float(v3_combined.get("recall_estimate")) if isinstance(v3_combined, dict) else None
        except (TypeError, ValueError):
            recall = None

        row = {
            "user_id":           user_id,
            "observed_at":       observed_at,
            "duration_sec":      _maybe_int(ev.get("duration_sec")),
            "category":          (ev.get("category") or "")[:50] or None,
            "description":       (ev.get("description") or "")[:2000] or "(no description)",
            "people":            ev.get("people") if isinstance(ev.get("people"), list) else None,
            "people_count":      _maybe_int(ev.get("people_count")),
            "location":          (ev.get("location") or "")[:50] or None,
            "indoor_outdoor":    (ev.get("indoor_outdoor") or "")[:20] or None,
            "posture":           (ev.get("posture") or "")[:30] or None,
            "mood":              (ev.get("mood") or "")[:30] or None,
            "energy_signs":      (ev.get("energy_signs") or "")[:30] or None,
            "objects":           ev.get("objects") if isinstance(ev.get("objects"), list) else None,
            "screen":            ev.get("screen") or None,
            "topic":             ev.get("topic") or None,
            "decision":          ev.get("decision") or None,
            "audio_heard":       ev.get("audio_heard") or None,
            "numbers_mentioned": ev.get("numbers_mentioned") or None,
            "kcal":              _maybe_int(ev.get("kcal")),
            "amount_ml":         _maybe_int(ev.get("amount_ml")),
            "source_model":      source_model,
            "source_video":      source_video,
            "chunk_idx":         _maybe_int(ev.get("_chunk_idx")),
            "raw_event":         ev,
            # v3 columns (migration 007) — all NULL-able for back-compat.
            "video_extraction":  v3_video,
            "audio_extraction":  v3_audio,
            "combined_analysis": v3_combined,
            "ocr_text_full":     ocr_full,
            "recall_estimate":   recall,
            "broadcast_mode":    broadcast,
            # v3.1 columns (migration 008) — also NULL-able.
            "frame_sampling_rate": _maybe_int(fs_rate),
            # v3.2 column (migration 009) — detailed per-item enumeration.
            "enumerated_observations": enumerated,
        }
        rows.append(row)

    # PostgREST: batch insert in chunks of 100 to keep payload small
    inserted = 0
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    for i in range(0, len(rows), 100):
        batch = rows[i:i+100]
        try:
            resp = httpx.post(f"{url}/rest/v1/lifelog_event", json=batch, headers=headers, timeout=30)
            if resp.status_code >= 400:
                print(f"    [supabase] insert batch {i//100} HTTP {resp.status_code} body: {resp.text[:1000]}")
                first = batch[0] if batch else {}
                sample = {k: (repr(v)[:120] if not isinstance(v, (int, type(None))) else v) for k, v in first.items()}
                print(f"    [supabase] first row keys+sample: {sample}")
            resp.raise_for_status()
            inserted += len(batch)
        except Exception as e:
            print(f"    [supabase] insert batch {i//100} failed: {e}")
    return inserted


# ──────────────────────────────────────────────────────────────────────
# Main: chunk the video, run extractor(s) per chunk, aggregate
# ──────────────────────────────────────────────────────────────────────

def get_video_duration_sec(video_path: Path) -> float:
    import av
    c = av.open(str(video_path))
    s = c.streams.video[0]
    fps = float(s.average_rate or 30)
    n = s.frames or 0
    if n == 0:
        n = sum(1 for _ in c.decode(video=0))
    c.close()
    return n / fps


# ──────────────────────────────────────────────────────────────────────
# Per-chunk worker (used by both sequential & parallel paths)
# ──────────────────────────────────────────────────────────────────────

def _process_chunk(i: int, video_path: Path, chunk_sec: int, duration: float,
                   transcript: Optional[dict], frames_per_chunk: int,
                   compare: bool, llama4: bool, gemini: bool = False,
                   parallel_models: bool = True, gemma: bool = True) -> dict:
    """Sample frames + run all model arms for chunk *i*.

    Returns a dict shaped for the aggregator in run(). All print output for
    the chunk is buffered into `log_lines` so the parallel path can emit
    each chunk's lines atomically once it finishes (otherwise output from
    concurrent chunks would interleave illegibly).
    """
    start = i * chunk_sec
    end = min(start + chunk_sec, duration)
    log_lines: list[str] = []
    chunk_t0 = time.perf_counter()

    try:
        frames = sample_frames_window(video_path, start, end, frames_per_chunk)
    except Exception as e:
        log_lines.append(f"  chunk {i+1}  ERROR sampling frames: {e}")
        return {"i": i, "start": start, "end": end,
                "log": log_lines, "elapsed_ms": 0, "ocr": None,
                "gemma": None, "qwen": None, "llama4": None, "gemini": None}
    ts_text = transcript_slice(transcript, start, end)

    # ── v3 (Fix 1): OCR pre-pass with adaptive 60-frame @1fps for broadcasts ──
    # Strategy:
    #   1. OCR the initial 8 frames (cheap detection pass).
    #   2. If broadcast_mode detected AND chunk is long enough, upsample to
    #      60 frames at 1fps, OCR in batches of 10 (memory-safe), MERGE all
    #      OCR text, then SUBSET to ~20 most-distinct frames for the VLM
    #      (preserves VLM cost while massively widening OCR coverage).
    #   3. Non-broadcast scenes keep the cheap 8-frame path — no regression.
    ocr_result: Optional[dict] = None
    ocr_text = ""
    frame_sampling_rate = len(frames)  # how many frames we OCR'd total
    if OCR_AVAILABLE and _ocr is not None:
        try:
            ts_per_frame = [
                start + j * ((end - start) / max(1, len(frames)))
                for j in range(len(frames))
            ]
            ocr_result = _ocr.extract_text_from_frames(frames, ts_per_frame)
            chunk_dur = end - start
            # 60-frame @ 1fps upsample requires a chunk long enough to host
            # at least 16 1-second slots; otherwise the 8-frame path covers it.
            if ocr_result.get("broadcast_mode_detected") and chunk_dur >= 16 and len(frames) < 60:
                try:
                    target_60 = min(60, max(20, int(chunk_dur)))  # 1fps, capped at 60
                    # Sample target_60 frames evenly across the chunk
                    dense_frames = sample_frames_window(video_path, start, end, target_60)
                    dense_ts = [
                        start + (j + 0.5) * (chunk_dur / max(1, len(dense_frames)))
                        for j in range(len(dense_frames))
                    ]
                    # Batch OCR in groups of 10 for memory safety.
                    batch_size = 10
                    batch_results: list[dict] = []
                    total_batch_latency = 0.0
                    for b_start in range(0, len(dense_frames), batch_size):
                        b_frames = dense_frames[b_start:b_start + batch_size]
                        b_ts = dense_ts[b_start:b_start + batch_size]
                        b_res = _ocr.extract_text_from_frames(b_frames, b_ts)
                        batch_results.append(b_res)
                        total_batch_latency += b_res.get("ocr_latency_sec", 0.0)
                    # Merge per_frame entries + text dump (dedup by string)
                    merged_per_frame: list[dict] = []
                    for bi, br in enumerate(batch_results):
                        offset = bi * batch_size
                        for pf in br.get("per_frame", []):
                            pf2 = dict(pf)
                            pf2["frame_idx"] = offset + pf2.get("frame_idx", 0)
                            merged_per_frame.append(pf2)
                    # Build merged text with dedupe + 500-item cap so the
                    # injected prompt doesn't balloon.
                    seen_text: set[str] = set()
                    merged_text: list[str] = []
                    any_broadcast = False
                    for br in batch_results:
                        if br.get("broadcast_mode_detected"):
                            any_broadcast = True
                        for line in br.get("ocr_full_text", "").split("\n"):
                            ln = line.strip()
                            if ln and ln not in seen_text:
                                seen_text.add(ln)
                                merged_text.append(ln)
                                if len(merged_text) >= 500:
                                    break
                        if len(merged_text) >= 500:
                            break
                    # Replace the initial 8-frame ocr_result with the dense one.
                    ocr_result = {
                        "ocr_full_text": "\n".join(merged_text),
                        "per_frame": merged_per_frame,
                        "broadcast_mode_detected": any_broadcast,
                        "total_unique_text_items": len(merged_text),
                        "ocr_latency_sec": round(total_batch_latency, 3),
                        "ocr_mode": getattr(_ocr, "_OCR_MODE", "unknown"),
                    }
                    frame_sampling_rate = len(dense_frames)
                    # Subset the dense frames for VLM input (~20 most distinct).
                    vlm_target = 20
                    try:
                        keep_idx = _ocr.pick_distinct_frames_phash(dense_frames, vlm_target)
                        vlm_frames = [dense_frames[k] for k in keep_idx]
                    except Exception as e:
                        # Fallback: even-spaced subset
                        log_lines.append(f"    [ocr-vlm-subset] phash picker failed ({type(e).__name__}); even-spaced fallback")
                        step = max(1, len(dense_frames) // vlm_target)
                        vlm_frames = dense_frames[::step][:vlm_target]
                    frames = vlm_frames  # the VLM now sees the distinct subset
                except Exception as e:
                    log_lines.append(f"    [ocr-upsample] failed: {type(e).__name__}: {e}")
            ocr_text = ocr_result.get("ocr_full_text", "")
            n_items = ocr_result.get("total_unique_text_items", 0)
            bc = ocr_result.get("broadcast_mode_detected", False)
            ocr_sec = ocr_result.get("ocr_latency_sec", 0)
            log_lines.append(
                f"    [ocr] {n_items} text items, broadcast={bc}, "
                f"sampling_rate={frame_sampling_rate}, vlm_frames={len(frames)}, {ocr_sec:.1f}s"
            )
        except Exception as e:
            log_lines.append(f"    [ocr] FAILED: {type(e).__name__}: {str(e)[:160]}")

    # ── Fix 3: cross-frame value-change detection ──
    # When the same metric (e.g. "SK하이닉스") shows different values across
    # frames in this chunk, surface as value_updates so the VLM (and the DB)
    # can present it as a change rather than a duplicate.
    value_updates: list[dict] = []
    if ocr_result and ocr_result.get("per_frame") and OCR_AVAILABLE and _ocr is not None:
        try:
            value_updates = _ocr.detect_value_changes(ocr_result["per_frame"])
            if value_updates:
                log_lines.append(f"    [val-changes] {len(value_updates)} metric(s) changed value")
        except Exception as e:
            log_lines.append(f"    [val-changes] failed: {type(e).__name__}: {str(e)[:120]}")

    # ── Fix 4: temporal sub-chunking (60s → 4×15s windows in prompt) ──
    # Group OCR results into ~15s sub-windows so the VLM can produce a
    # window-by-window timeline. Only structure when we have a dense
    # broadcast OCR pass (otherwise the single window with 8 frames is
    # equivalent to the legacy single dump).
    ocr_by_window: list[dict] = []
    chunk_dur = end - start
    if ocr_result and ocr_result.get("per_frame") and chunk_dur >= 30 and frame_sampling_rate >= 20:
        try:
            win_count = 4
            win_dur = chunk_dur / win_count
            buckets: list[list[dict]] = [[] for _ in range(win_count)]
            for pf in ocr_result["per_frame"]:
                ts = float(pf.get("timestamp_sec", 0)) - start
                w = min(win_count - 1, max(0, int(ts // win_dur)))
                buckets[w].append(pf)
            for w_idx, pfs in enumerate(buckets):
                seen: set[str] = set()
                items: list[str] = []
                panels = 0
                for pf in pfs:
                    panels = max(panels, len(pf.get("panels_detected", []) or []))
                    for b in pf.get("text_boxes", []):
                        t = (b.get("text") or "").strip()
                        if t and t not in seen:
                            seen.add(t)
                            items.append(t)
                ocr_by_window.append({
                    "window_sec": f"{int(w_idx * win_dur)}-{int((w_idx + 1) * win_dur)}",
                    "frame_count": len(pfs),
                    "panels_detected": panels,
                    "items": items[:100],  # spec cap: 100 per window
                    "sparse": len(pfs) == 0,
                })
            log_lines.append(
                f"    [sub-chunks] {len(ocr_by_window)} windows "
                f"(items: {','.join(str(len(w['items'])) for w in ocr_by_window)})"
            )
        except Exception as e:
            log_lines.append(f"    [sub-chunks] failed: {type(e).__name__}: {str(e)[:120]}")
            ocr_by_window = []

    # Pipeline-built timeline from the sub-windows. gemma often DROPS
    # combined_analysis.timeline on dense chunks; this guarantees a
    # window-by-window timeline grounded in the OCR (key_items quality-filtered).
    pipeline_timeline: list[dict] = []
    try:
        from ocr_quality_filter import is_meaningful_ocr_item as _is_meaningful
    except Exception:
        _is_meaningful = lambda t, c=1.0: len((t or "").strip()) >= 4
    for w in ocr_by_window:
        key_items = [it for it in (w.get("items") or []) if _is_meaningful(it)][:8]
        pipeline_timeline.append({
            "window_sec": w.get("window_sec", "?"),
            "summary": "",
            "key_items": key_items,
        })

    log_lines.append(f"  chunk {i+1}  t={start:.0f}-{end:.0f}s  "
                     f"{len(frames)} vlm-frames  transcript={len(ts_text)} chars  "
                     f"ocr={len(ocr_text)} chars")

    # Build the set of model calls to run for this chunk.
    model_calls = []
    if gemma:
        model_calls.append(("gemma", call_gemma_lifelog))
    if compare:
        model_calls.append(("qwen", call_qwen_lifelog))
    if llama4:
        model_calls.append(("llama4", call_llama4_lifelog))
    if gemini:
        model_calls.append(("gemini", call_gemini_lifelog))

    # Each arm gets the same (frames, transcript_text, ocr_text, value_updates, ocr_by_window).
    def _invoke(fn):
        return fn(frames, ts_text, ocr_text=ocr_text,
                  value_updates=value_updates, ocr_by_window=ocr_by_window)

    results: dict[str, tuple[Optional[dict], int, Optional[str]]] = {}
    if parallel_models and len(model_calls) > 1:
        with ThreadPoolExecutor(max_workers=len(model_calls),
                                 thread_name_prefix=f"chunk{i}-model") as ex:
            futs = {ex.submit(_invoke, fn): name
                     for name, fn in model_calls}
            for fut in as_completed(futs):
                name = futs[fut]
                try:
                    results[name] = fut.result()
                except Exception as e:
                    results[name] = (None, 0, f"{type(e).__name__}: {e}")
    else:
        for name, fn in model_calls:
            results[name] = _invoke(fn)

    chunk_elapsed_ms = int((time.perf_counter() - chunk_t0) * 1000)

    out: dict = {"i": i, "start": start, "end": end,
                 "elapsed_ms": chunk_elapsed_ms, "log": log_lines,
                 "ocr": ocr_result,
                 "gemma": None, "qwen": None, "llama4": None, "gemini": None}

    for name in ("gemma", "qwen", "llama4", "gemini"):
        if name not in results:
            continue
        parsed, ms, err = results[name]
        # Hard failures (no parsed dict) — log and skip. Soft notes
        # (e.g. "json_recovered:regex_fix") still have a parsed dict
        # and should be treated as success with a marker.
        if parsed is None:
            log_lines.append(f"    [{name:<7}] ERROR ({ms}ms): {err}")
            continue
        events = parsed.get("events", []) if isinstance(parsed, dict) else []
        marker = f"  ({err})" if err else ""
        log_lines.append(f"    [{name:<7}] {ms:>6}ms → {len(events)} events"
                         f"{marker}  "
                         f"| {parsed.get('segment_summary', '')[:80]}")
        # v3 — clip-level extraction blocks emitted by THIS arm. Attached to
        # each event so write_events_to_supabase can populate the v3 columns
        # without losing per-arm distinctions (each arm may interpret the
        # screen/audio slightly differently).
        v3_video    = parsed.get("video_extraction")    if isinstance(parsed, dict) else None
        v3_audio    = parsed.get("audio_extraction")    if isinstance(parsed, dict) else None
        v3_combined = parsed.get("combined_analysis")   if isinstance(parsed, dict) else None
        # v3.2: detailed enumeration (defensive — coerce non-list to []).
        v3_enumerated = parsed.get("enumerated_observations") if isinstance(parsed, dict) else None
        if not isinstance(v3_enumerated, list):
            v3_enumerated = []
        # Fix 1: override frame_sampling_rate with the actual value we used
        # for OCR (truth, not what the VLM guessed). Stored both inside the
        # video_extraction JSONB and as a top-level row column.
        if isinstance(v3_video, dict):
            v3_video["frame_sampling_rate"] = frame_sampling_rate
        else:
            v3_video = {"frame_sampling_rate": frame_sampling_rate}
        # Fix 2: panels_detected count (aggregate across all OCR'd frames)
        all_panels = []
        if ocr_result and ocr_result.get("per_frame"):
            for pf in ocr_result["per_frame"]:
                all_panels.extend(pf.get("panels_detected", []) or [])
        if all_panels:
            v3_video["panels_detected"] = all_panels[:50]  # cap for JSONB sanity
        # Fix 3/4: ensure value_updates + timeline exist in combined_analysis
        # (prefer VLM's own emission; fall back to our computed value_updates).
        if not isinstance(v3_combined, dict):
            v3_combined = {}
        if value_updates and not v3_combined.get("value_updates"):
            v3_combined["value_updates"] = value_updates
        # Timeline: gemma frequently drops combined_analysis.timeline on dense
        # chunks. When the VLM's timeline is missing or has fewer windows than
        # the pipeline sub-windows, rebuild it from pipeline_timeline (grafting
        # any VLM-written per-window summaries by window key).
        if pipeline_timeline:
            vlm_tl = v3_combined.get("timeline")
            if not isinstance(vlm_tl, list) or len(vlm_tl) < len(pipeline_timeline):
                vlm_by_win = {}
                if isinstance(vlm_tl, list):
                    for w in vlm_tl:
                        if isinstance(w, dict) and w.get("window_sec"):
                            vlm_by_win[str(w["window_sec"])] = w
                v3_combined["timeline"] = [
                    {
                        "window_sec": w["window_sec"],
                        "summary": (vlm_by_win.get(w["window_sec"], {}).get("summary") or "").strip(),
                        "key_items": w["key_items"],
                    }
                    for w in pipeline_timeline
                ]
        # Audio: inject the actual Whisper transcript as GROUND TRUTH. The
        # prompt asks the VLM to echo it, but local arms routinely drop or
        # summarize it (and with no transcript they hallucinate
        # "silence_dominant"). This is the audio analogue of injecting OCR
        # text — override only when Whisper produced text for this chunk.
        if not isinstance(v3_audio, dict):
            v3_audio = {}
        if ts_text and ts_text.strip():
            v3_audio["transcript_full"] = ts_text
            if transcript and transcript.get("language"):
                v3_audio["language_detected"] = transcript["language"]
            # A real transcript means it wasn't silence — correct the VLM's
            # contradictory sole "silence_dominant" guess.
            if v3_audio.get("audio_events") in (None, [], ["silence_dominant"]):
                v3_audio["audio_events"] = ["speech"]
        # OCR fields are PER-CHUNK (same across arms for the same chunk).
        ocr_full = (ocr_result or {}).get("ocr_full_text", "") or None
        ocr_bcast = bool((ocr_result or {}).get("broadcast_mode_detected", False))

        chunk_events = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            ev["t_sec_abs"] = start + (ev.get("t_sec", 0) or 0)
            ev["_chunk_idx"] = i
            # Stash v3 + OCR side-channel under underscore-prefixed keys so
            # they don't collide with VLM-emitted fields. write_events_to_supabase
            # reads them when building the DB row.
            ev["_video_extraction"]    = v3_video
            ev["_audio_extraction"]    = v3_audio
            ev["_combined_analysis"]   = v3_combined
            ev["_enumerated_observations"] = v3_enumerated
            ev["_ocr_text_full"]       = ocr_full
            ev["_broadcast_mode"]      = ocr_bcast
            ev["_frame_sampling_rate"] = frame_sampling_rate
            chunk_events.append(ev)
        out[name] = {
            "events": chunk_events,
            "ms": ms,
            "summary": {
                "chunk_idx": i, "start_sec": start, "end_sec": end,
                "summary": parsed.get("segment_summary", ""),
                "dominant_activity": parsed.get("dominant_activity", ""),
                "processing_ms": ms,
            },
        }

    mode = "parallel" if parallel_models and len(model_calls) > 1 else "serial"
    log_lines.append(f"    [chunk_total] {chunk_elapsed_ms}ms  ({mode} models)")
    return out


def run(video_path: Path, compare: bool, chunk_sec: int = 60,
        frames_per_chunk: int = 8, write_supabase: bool = True,
        user_id: int = 1, llama4: bool = False, gemini: bool = False,
        chunk_workers: int = 3, parallel_models: bool = True,
        gemma: bool = True):
    print(f"\n=== Lifelog test: {video_path.name} ===")
    arms = []
    if gemma:   arms.append("Gemma 4")
    if compare: arms.append("Qwen 3.5 VLM")
    if llama4:  arms.append("Llama 4 Maverick")
    if gemini:
        _, _gem_model = _gemini_config()
        arms.append(f"Gemini ({_gem_model})")
    if not arms:
        raise ValueError("run(): at least one of gemma/compare/llama4/gemini must be enabled")
    print(f"  arms: {' + '.join(arms)}")
    duration = get_video_duration_sec(video_path)
    print(f"  duration: {duration:.1f}s")

    # Step 1: Whisper transcript (optional but valuable)
    print(f"  [1/3] extracting audio + Whisper transcript...")
    audio_path = extract_audio(video_path)
    transcript = None
    if audio_path and audio_path.exists():
        t0 = time.time()
        transcript = whisper_transcribe(audio_path)
        if transcript:
            print(f"        Whisper done ({time.time()-t0:.1f}s, "
                  f"lang={transcript['language']}, "
                  f"{len(transcript['segments'])} segments, "
                  f"{len(transcript['text'])} chars)")
        try:
            audio_path.unlink()
        except Exception:
            pass

    # Free Whisper's GPU memory before the chunk loop. Gemma 4 26B Q8 needs
    # ~30GB of the 32GB card; leaving Whisper's ctranslate2 model (~4GB) +
    # PaddleOCR resident makes Ollama unable to fit Gemma -> it spills to CPU
    # and blows the read timeout (observed after the Whisper WinError-127 fix
    # started actually loading the model). Whisper isn't needed past this point.
    global _WHISPER_MODEL
    if _WHISPER_MODEL is not None:
        _WHISPER_MODEL = None
        try:
            import gc
            gc.collect()
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        print("  [vram] released Whisper model to free GPU for Gemma")

    # Step 2: process chunks (in parallel)
    n_chunks = max(1, int(duration / chunk_sec) + (1 if duration % chunk_sec else 0))
    n_arms = (1 if gemma else 0) + (1 if compare else 0) + (1 if llama4 else 0) + (1 if gemini else 0)
    eff_chunk_workers = max(1, min(chunk_workers, n_chunks))
    mode_models = "parallel" if (parallel_models and n_arms > 1) else "serial"
    mode_chunks = (f"{eff_chunk_workers}-way parallel"
                   if eff_chunk_workers > 1 else "serial")
    print(f"  [2/3] processing {n_chunks} chunks of ~{chunk_sec}s each  "
          f"(chunks: {mode_chunks}, models per chunk: {mode_models})")

    gemma_events: list = []
    gemma_summaries: list = []
    qwen_events: list = []
    qwen_summaries: list = []
    llama4_events: list = []
    llama4_summaries: list = []
    gemini_events: list = []
    gemini_summaries: list = []

    total_t0 = time.perf_counter()
    chunk_results: list[Optional[dict]] = [None] * n_chunks

    if eff_chunk_workers > 1 and n_chunks > 1:
        with ThreadPoolExecutor(max_workers=eff_chunk_workers,
                                 thread_name_prefix="chunk") as ex:
            futs = {
                ex.submit(_process_chunk, i, video_path, chunk_sec, duration,
                          transcript, frames_per_chunk, compare, llama4, gemini,
                          parallel_models, gemma): i
                for i in range(n_chunks)
            }
            for fut in as_completed(futs):
                i = futs[fut]
                try:
                    chunk_results[i] = fut.result()
                except Exception as e:
                    chunk_results[i] = {
                        "i": i, "log": [f"  chunk {i+1} FAILED: {type(e).__name__}: {e}"],
                        "elapsed_ms": 0,
                        "gemma": None, "qwen": None, "llama4": None, "gemini": None,
                    }
                # Print this chunk's buffered output atomically.
                for line in chunk_results[i]["log"]:
                    print(line)
    else:
        for i in range(n_chunks):
            chunk_results[i] = _process_chunk(
                i, video_path, chunk_sec, duration, transcript,
                frames_per_chunk, compare, llama4, gemini, parallel_models, gemma,
            )
            for line in chunk_results[i]["log"]:
                print(line)

    total_chunks_elapsed = time.perf_counter() - total_t0

    # Aggregate in original chunk order
    for r in chunk_results:
        if r is None:
            continue
        if r.get("gemma"):
            gemma_events.extend(r["gemma"]["events"])
            gemma_summaries.append(r["gemma"]["summary"])
        if r.get("qwen"):
            qwen_events.extend(r["qwen"]["events"])
            qwen_summaries.append(r["qwen"]["summary"])
        if r.get("llama4"):
            llama4_events.extend(r["llama4"]["events"])
            llama4_summaries.append(r["llama4"]["summary"])
        if r.get("gemini"):
            gemini_events.extend(r["gemini"]["events"])
            gemini_summaries.append(r["gemini"]["summary"])

    # Speed summary: wall-clock vs sum-of-arms (= what serial would have cost).
    sum_arm_ms = 0
    per_chunk_max_ms = 0
    for r in chunk_results:
        if r is None:
            continue
        chunk_arm_sum = 0
        chunk_arm_max = 0
        for name in ("gemma", "qwen", "llama4", "gemini"):
            arm = r.get(name)
            if arm:
                chunk_arm_sum += arm["ms"]
                chunk_arm_max = max(chunk_arm_max, arm["ms"])
        sum_arm_ms += chunk_arm_sum
        per_chunk_max_ms = max(per_chunk_max_ms, chunk_arm_max)
    serial_baseline_s = sum_arm_ms / 1000.0
    if total_chunks_elapsed > 0 and serial_baseline_s > 0:
        speedup = serial_baseline_s / total_chunks_elapsed
        print(f"  [speed] wall-clock {total_chunks_elapsed:.1f}s  "
              f"vs serial-baseline {serial_baseline_s:.1f}s  "
              f"→ {speedup:.2f}× speedup  "
              f"(slowest single arm: {per_chunk_max_ms/1000:.1f}s)")

    # Step 2.5: write to Supabase lifelog_event (one row per event)
    if write_supabase:
        # Derive video_start (= recording start, wall clock) preferring the
        # AIMB filename which embeds YYYYMMDDhhmmssXXX. With the 2026-05-22
        # CRC-16/Modbus TIME SYNC fix the filename stamp is now correct, so
        # this is more accurate than file mtime (mtime = when Syncthing
        # wrote the file on PC, which can be many minutes after recording).
        video_start = None
        try:
            import re as _re
            stem = video_path.stem  # e.g. "20260522141334817" or
                                    # "20260522_14-13-34" after rename
            m = _re.match(r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{3})?$", stem)
            if not m:
                # Tolerate the human-readable renamed form 2026-05-22_14-13-34
                m = _re.match(r"^(\d{4})-?(\d{2})-?(\d{2})[_-](\d{2})-(\d{2})-(\d{2})$", stem)
            if m:
                yr, mo, dy, hh, mm, ss = (int(m.group(i)) for i in range(1, 7))
                ms = int(m.group(7)) if m.lastindex and m.lastindex >= 7 and m.group(7) else 0
                video_start = datetime(yr, mo, dy, hh, mm, ss, ms * 1000, tzinfo=KST).astimezone(timezone.utc)
        except Exception:
            video_start = None

        # Sanity-check the filename stamp against the file's mtime. The AIMB-G1
        # glasses clock can be wrong (observed 2026-06: stuck days behind,
        # stamping June clips as "20260528..."). mtime is when Syncthing wrote
        # the clip to this PC — at most a short sync delay after recording — so
        # (mtime - duration) ~ recording start. If the filename time disagrees
        # by more than 12h, trust mtime (12h >> any real sync delay, << the
        # multi-day glasses drift, so legit slightly-late syncs still keep the
        # more precise filename stamp).
        if video_start is not None:
            try:
                mtime_start = (datetime.fromtimestamp(video_path.stat().st_mtime, tz=timezone.utc)
                               - timedelta(seconds=duration))
                drift_h = abs((video_start - mtime_start).total_seconds()) / 3600.0
                if drift_h > 12:
                    print(f"  [time] filename stamp ({video_start.date()}) disagrees with file "
                          f"mtime by {drift_h:.1f}h - glasses clock suspect; using mtime "
                          f"-> {mtime_start.date()}")
                    video_start = mtime_start
            except Exception:
                pass

        if video_start is None:
            # Fallback: mtime − duration, so observed_at lands at recording start.
            try:
                video_start = datetime.fromtimestamp(video_path.stat().st_mtime, tz=KST).astimezone(timezone.utc)
                video_start = video_start - timedelta(seconds=duration)
            except Exception:
                video_start = datetime.now(timezone.utc) - timedelta(seconds=duration)

        print(f"  [3/3] writing events to Supabase (user_id={user_id})...")
        _, _gemini_model_active = _gemini_config()
        if gemma and gemma_events:
            g_inserted = write_events_to_supabase(
                gemma_events, _model_to_source_tag(GEMMA_MODEL), video_path.name, video_start, user_id,
            )
            print(f"        Gemma  : {g_inserted} rows inserted into lifelog_event")
        if compare and qwen_events:
            q_inserted = write_events_to_supabase(
                qwen_events, _model_to_source_tag(QWEN_MODEL), video_path.name, video_start, user_id,
            )
            print(f"        Qwen   : {q_inserted} rows inserted into lifelog_event")
        if llama4 and llama4_events:
            l_inserted = write_events_to_supabase(
                llama4_events, _model_to_source_tag(LLAMA4_MODEL), video_path.name, video_start, user_id,
            )
            print(f"        Llama4 : {l_inserted} rows inserted into lifelog_event")
        if gemini and gemini_events:
            gem_inserted = write_events_to_supabase(
                gemini_events, _model_to_source_tag(_gemini_model_active), video_path.name, video_start, user_id,
            )
            print(f"        Gemini : {gem_inserted} rows inserted into lifelog_event")

    # Step 3: save JSON dump
    out = {
        "video": str(video_path),
        "duration_sec": duration,
        "n_chunks": n_chunks,
        "whisper_transcript": (transcript or {}).get("text", ""),
        "whisper_language": (transcript or {}).get("language", ""),
    }
    if gemma:
        out["gemma"] = {
            "total_events": len(gemma_events),
            "events": gemma_events,
            "chunk_summaries": gemma_summaries,
        }
    if compare:
        out["qwen"] = {
            "total_events": len(qwen_events),
            "events": qwen_events,
            "chunk_summaries": qwen_summaries,
        }
    if llama4:
        out["llama4"] = {
            "total_events": len(llama4_events),
            "events": llama4_events,
            "chunk_summaries": llama4_summaries,
        }
    if gemini:
        out["gemini"] = {
            "total_events": len(gemini_events),
            "events": gemini_events,
            "chunk_summaries": gemini_summaries,
        }
    multi_arm = (1 if gemma else 0) + (1 if compare else 0) + (1 if llama4 else 0) + (1 if gemini else 0) > 1
    suffix = ".compare.json" if multi_arm else ".lifelog.json"
    output_path = video_path.with_suffix(suffix)
    output_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  [OK] wrote {output_path}")
    if gemma:
        print(f"  Gemma  : {len(gemma_events)} events")
    if compare:
        print(f"  Qwen   : {len(qwen_events)} events")
    if llama4:
        print(f"  Llama4 : {len(llama4_events)} events")
    if gemini:
        print(f"  Gemini : {len(gemini_events)} events")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lifelog extraction test")
    parser.add_argument("video", type=Path, help="path to video file")
    parser.add_argument("--compare", action="store_true",
                        help="also run Qwen 3.5 VLM 397B via NVIDIA NIM and compare")
    parser.add_argument("--llama4", action="store_true",
                        help="also run Llama 4 Maverick via NVIDIA NIM and compare")
    parser.add_argument("--gemini", action="store_true",
                        help="also run Gemini (Google AI Studio) and compare")
    parser.add_argument("--chunk-sec", type=int, default=60,
                        help="chunk duration in seconds (default 60)")
    parser.add_argument("--frames", type=int, default=8,
                        help="frames per chunk (default 8)")
    parser.add_argument("--user-id", type=int, default=1,
                        help="user_id to tag events with (default 1)")
    parser.add_argument("--no-supabase", action="store_true",
                        help="skip Supabase writes (JSON file only)")
    parser.add_argument("--chunk-workers", type=int, default=3,
                        help="how many chunks to process concurrently "
                             "(default 3; set 1 to disable chunk parallelism)")
    parser.add_argument("--no-parallel-models", action="store_true",
                        help="run Gemma/Qwen/Llama4 serially within each chunk "
                             "(default: parallel)")
    parser.add_argument("--pipeline", action="store_true",
                        help="multi-chunk pipelining: overlap OCR of chunk N+1 "
                             "with LLM of chunk N. Enforces >=2 chunk workers. "
                             "Matters for multi-chunk (5-min) clips; a no-op "
                             "speed-wise on a single-chunk video.")
    parser.add_argument("--no-gemma", action="store_true",
                        help="skip the always-on local Gemma arm (e.g. to "
                             "iterate on a cloud arm only). Requires at least "
                             "one of --gemini/--llama4/--compare.")
    args = parser.parse_args()

    if not args.video.exists():
        print(f"video not found: {args.video}")
        sys.exit(1)

    # Multi-chunk pipelining is implemented by the chunk-level ThreadPoolExecutor
    # in run() (chunk_workers): because LLM calls (cloud/Ollama) release the GIL
    # on network I/O and PaddleOCR releases it during C++ inference, OCR of the
    # next chunk overlaps the LLM of the current one. --pipeline simply enforces
    # a >=2 worker floor so that overlap is guaranteed for multi-chunk clips.
    chunk_workers = args.chunk_workers
    if args.pipeline:
        chunk_workers = max(2, chunk_workers)

    run(args.video, compare=args.compare,
        chunk_sec=args.chunk_sec, frames_per_chunk=args.frames,
        write_supabase=(not args.no_supabase), user_id=args.user_id,
        llama4=args.llama4, gemini=args.gemini,
        chunk_workers=chunk_workers,
        parallel_models=(not args.no_parallel_models),
        gemma=(not args.no_gemma))
