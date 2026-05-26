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

# Reuse Gemma helpers
sys.path.insert(0, str(Path(__file__).parent))
from gemma_dual_extractor import (
    GEMMA_BASE_URL,
    GEMMA_TIMEOUT_SEC,
    _img_to_data_url,
    _GEMMA_SYSTEM_INSTRUCTION,
)


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

      // ─── CONVERSATION (when speaking with someone) ───
      "conversation_detail": {
        "participants":   ["<roles, not names>"],
        "key_points":     ["<main points raised>"],
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
    * ALWAYS split into `observed_facts` (what you SAW/HEARD) and `inferred_context`
      (what you GUESSED). Don't blur the line. Reduces hallucination.
    * ALWAYS fill `importance` (1-10). Stock recommendation = 8-9; sip of water = 2.
    * ALWAYS fill `memory_relevance`. Random office sitting = "low"; financial advice = "high".
    * Fill `screen_analysis` whenever ANY screen is visible.
    * Fill `technical_analysis` whenever ANY chart is visible — including TA indicators
      if you can read them (RSI value, MA crossover, breakout pattern, etc.).
    * Fill `macro` block only when broader market regime / sector commentary appears.
    * Fill `conversation_detail` only for spoken interactions, not for screen-content events.
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

WHISPER_REMOTE_URL = "http://100.69.125.64:8082/inference"  # same Mac mini endpoint used in healthcare

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
        with open(audio_path, "rb") as f:
            resp = httpx.post(
                WHISPER_REMOTE_URL,
                files={"file": ("audio.wav", f, "audio/wav")},
                data={
                    "language": "auto",
                    "response_format": "verbose_json",
                    "max_len": "0",
                    "temperature": "0",
                },
                timeout=300,
            )
        resp.raise_for_status()
        data = resp.json()
        segs = data.get("segments") or []
        return {
            "text": data.get("text", "").strip(),
            "language": data.get("language", "auto"),
            "segments": [
                {"start": s.get("start", 0), "end": s.get("end", 0),
                 "text": (s.get("text") or "").strip()}
                for s in segs if isinstance(s, dict)
            ],
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


# ──────────────────────────────────────────────────────────────────────
# Gemma 4 E4B call (Mac mini)
# ──────────────────────────────────────────────────────────────────────

GEMMA_MAX_FRAMES = 6  # Mac mini Gemma 4 E4B 500s on 8 real frames (vision-
                      # encoder OOM in the mmproj forward pass). Healthcare
                      # watcher runs at 6 for the same reason. Qwen and Llama 4
                      # via NIM still see all 8 — NIM has the headroom.

# Mac mini's llama-server can host one Gemma inference at a time; two
# concurrent requests crash the server (500 / disconnect) due to vision-
# encoder contention. Serialize all Gemma calls process-wide. NIM-hosted
# Qwen/Llama4 stay fully concurrent — only Gemma is gated.
_GEMMA_LOCK = threading.Lock()

def call_gemma_lifelog(frames: list, transcript_text: str = "",
                       max_tokens: int = 2000) -> tuple[Optional[dict], int, Optional[str]]:
    """Send frames + transcript + LIFELOG_PROMPT to Gemma 4 E4B.

    Serialized via _GEMMA_LOCK so concurrent chunks don't crash the
    single-instance Mac mini llama-server.
    """
    if not frames:
        return None, 0, "no_frames"
    # Evenly subsample down to GEMMA_MAX_FRAMES.
    if len(frames) > GEMMA_MAX_FRAMES:
        step = len(frames) / GEMMA_MAX_FRAMES
        frames = [frames[int(i * step)] for i in range(GEMMA_MAX_FRAMES)]
    content = [{"type": "image_url", "image_url": {"url": _img_to_data_url(f)}}
               for f in frames]
    prompt = LIFELOG_PROMPT
    if transcript_text:
        prompt = f'Audio transcript for this clip: "{transcript_text}"\n\n' + prompt
    content.append({"type": "text", "text": prompt})

    body = {
        "model": "gemma-4-E4B-it",
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
        with _GEMMA_LOCK:
            with httpx.Client(timeout=GEMMA_TIMEOUT_SEC * 2) as client:
                resp = client.post(f"{GEMMA_BASE_URL}/v1/chat/completions", json=body)
                resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            parsed = json.loads(text)
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
        if end > 0:
            arr_text = text[start:end]
            arr_text = re.sub(r"\}(\s*)\{", r"},\1{", arr_text)
            try:
                events = json.loads(arr_text)
                if isinstance(events, list):
                    return ({"events": events, "segment_summary": "",
                             "dominant_activity": ""}, "events_only")
            except json.JSONDecodeError:
                pass

    return None, "failed"


# ──────────────────────────────────────────────────────────────────────
# Qwen2.5-VL via NVIDIA NIM API (only when --compare is set)
# ──────────────────────────────────────────────────────────────────────

NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
# Qwen 3.5 VLM (per NVIDIA Developer Blog, May 2026):
#   397B params (MoE, ~17B active), 256K context, free tier via build.nvidia.com.
# Much stronger than the older Qwen2.5-VL-72B; same OpenAI-compat request shape.
QWEN_MODEL = "qwen/qwen3.5-397b-a17b"
# Qwen 397B is much slower than Gemma 4 E4B — typical 30-60s, cold-start 90s+.
QWEN_TIMEOUT_SEC = 180
QWEN_RETRIES = 1

def call_qwen_lifelog(frames: list, transcript_text: str = "",
                      max_tokens: int = 8000) -> tuple[Optional[dict], int, Optional[str]]:
    """Send same payload to Qwen2.5-VL via NVIDIA NIM."""
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        # Try the .env in backend
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
    prompt = LIFELOG_PROMPT
    if transcript_text:
        prompt = f'Audio transcript for this clip: "{transcript_text}"\n\n' + prompt
    content.append({"type": "text", "text": prompt})

    body = {
        "model": QWEN_MODEL,
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
    for attempt in range(QWEN_RETRIES + 1):
        try:
            with httpx.Client(timeout=QWEN_TIMEOUT_SEC) as client:
                resp = client.post(NIM_URL, headers=headers, json=body)
                resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            parsed, mode = _try_parse_lifelog_json(text)
            if parsed is None:
                last_err = f"JSONDecodeError after cleanup ({len(text)} chars returned)"
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
LLAMA4_RETRIES = 1

def call_llama4_lifelog(frames: list, transcript_text: str = "",
                        max_tokens: int = 10000) -> tuple[Optional[dict], int, Optional[str]]:
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
    prompt = LIFELOG_PROMPT
    if transcript_text:
        prompt = f'Audio transcript for this clip: "{transcript_text}"\n\n' + prompt
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
                break
            ms = int((time.perf_counter() - t0) * 1000)
            note = None if mode == "clean" else f"json_recovered:{mode}"
            return parsed, ms, note
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
                        max_tokens: int = 10000) -> tuple[Optional[dict], int, Optional[str]]:
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

    prompt = LIFELOG_PROMPT
    if transcript_text:
        prompt = f'Audio transcript for this clip: "{transcript_text}"\n\n' + prompt

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
                   parallel_models: bool = True) -> dict:
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
                "log": log_lines, "elapsed_ms": 0,
                "gemma": None, "qwen": None, "llama4": None, "gemini": None}
    ts_text = transcript_slice(transcript, start, end)
    log_lines.append(f"  chunk {i+1}  t={start:.0f}-{end:.0f}s  "
                     f"{len(frames)} frames  transcript={len(ts_text)} chars")

    # Build the set of model calls to run for this chunk.
    model_calls = [("gemma", call_gemma_lifelog)]
    if compare:
        model_calls.append(("qwen", call_qwen_lifelog))
    if llama4:
        model_calls.append(("llama4", call_llama4_lifelog))
    if gemini:
        model_calls.append(("gemini", call_gemini_lifelog))

    results: dict[str, tuple[Optional[dict], int, Optional[str]]] = {}
    if parallel_models and len(model_calls) > 1:
        with ThreadPoolExecutor(max_workers=len(model_calls),
                                 thread_name_prefix=f"chunk{i}-model") as ex:
            futs = {ex.submit(fn, frames, ts_text): name
                     for name, fn in model_calls}
            for fut in as_completed(futs):
                name = futs[fut]
                try:
                    results[name] = fut.result()
                except Exception as e:
                    results[name] = (None, 0, f"{type(e).__name__}: {e}")
    else:
        for name, fn in model_calls:
            results[name] = fn(frames, ts_text)

    chunk_elapsed_ms = int((time.perf_counter() - chunk_t0) * 1000)

    out: dict = {"i": i, "start": start, "end": end,
                 "elapsed_ms": chunk_elapsed_ms, "log": log_lines,
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
        chunk_events = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            ev["t_sec_abs"] = start + (ev.get("t_sec", 0) or 0)
            ev["_chunk_idx"] = i
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
        chunk_workers: int = 3, parallel_models: bool = True):
    print(f"\n=== Lifelog test: {video_path.name} ===")
    arms = ["Gemma 4"]
    if compare: arms.append("Qwen 3.5 VLM")
    if llama4:  arms.append("Llama 4 Maverick")
    if gemini:
        _, _gem_model = _gemini_config()
        arms.append(f"Gemini ({_gem_model})")
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

    # Step 2: process chunks (in parallel)
    n_chunks = max(1, int(duration / chunk_sec) + (1 if duration % chunk_sec else 0))
    n_arms = 1 + (1 if compare else 0) + (1 if llama4 else 0) + (1 if gemini else 0)
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
                          parallel_models): i
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
                frames_per_chunk, compare, llama4, gemini, parallel_models,
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

        if video_start is None:
            # Fallback: mtime − duration, so observed_at lands at recording start.
            try:
                video_start = datetime.fromtimestamp(video_path.stat().st_mtime, tz=KST).astimezone(timezone.utc)
                video_start = video_start - timedelta(seconds=duration)
            except Exception:
                video_start = datetime.now(timezone.utc) - timedelta(seconds=duration)

        print(f"  [3/3] writing events to Supabase (user_id={user_id})...")
        g_inserted = write_events_to_supabase(
            gemma_events, "gemma_4_e4b", video_path.name, video_start, user_id,
        )
        print(f"        Gemma  : {g_inserted} rows inserted into lifelog_event")
        if compare and qwen_events:
            q_inserted = write_events_to_supabase(
                qwen_events, "qwen_3_5_vlm", video_path.name, video_start, user_id,
            )
            print(f"        Qwen   : {q_inserted} rows inserted into lifelog_event")
        if llama4 and llama4_events:
            l_inserted = write_events_to_supabase(
                llama4_events, "llama_4_maverick", video_path.name, video_start, user_id,
            )
            print(f"        Llama4 : {l_inserted} rows inserted into lifelog_event")
        if gemini and gemini_events:
            gem_inserted = write_events_to_supabase(
                gemini_events, "gemini_2_5_pro", video_path.name, video_start, user_id,
            )
            print(f"        Gemini : {gem_inserted} rows inserted into lifelog_event")

    # Step 3: save JSON dump
    out = {
        "video": str(video_path),
        "duration_sec": duration,
        "n_chunks": n_chunks,
        "whisper_transcript": (transcript or {}).get("text", ""),
        "whisper_language": (transcript or {}).get("language", ""),
        "gemma": {
            "total_events": len(gemma_events),
            "events": gemma_events,
            "chunk_summaries": gemma_summaries,
        },
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
    suffix = ".compare.json" if (compare or llama4 or gemini) else ".lifelog.json"
    output_path = video_path.with_suffix(suffix)
    output_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  ✓ wrote {output_path}")
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
    args = parser.parse_args()

    if not args.video.exists():
        print(f"video not found: {args.video}")
        sys.exit(1)
    run(args.video, compare=args.compare,
        chunk_sec=args.chunk_sec, frames_per_chunk=args.frames,
        write_supabase=(not args.no_supabase), user_id=args.user_id,
        llama4=args.llama4, gemini=args.gemini,
        chunk_workers=args.chunk_workers,
        parallel_models=(not args.no_parallel_models))
