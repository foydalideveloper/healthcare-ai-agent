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
import sys
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
observable event, interaction, object, location, activity, and conversation
topic. Be thorough but factual — only extract what you actually see or hear.
Do NOT invent. Do NOT skip mundane events (sitting at desk counts).

Output ONLY valid JSON. Schema:
{
  "events": [
    {
      "t_sec": int,                  // seconds from clip start
      "duration_sec": int,           // estimate, default 5 if unsure
      "category": "activity" | "interaction" | "conversation" | "food" |
                  "drink" | "exercise" | "medication" | "task_received" |
                  "commitment_made" | "purchase" | "location_change" |
                  "object_use" | "screen_content" | "observation",
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
                      "stretching" | null
    }
  ],
  "segment_summary": "<one sentence describing this whole clip>",
  "dominant_activity": "<the main thing the user was doing>"
}

Rules:
- Each DISTINCT event is a SEPARATE object. Don't lump multiple events together.
- Use ROLES for people (boss/colleague/stranger), not names — you don't know names.
- Sitting at a desk for 5 min = ONE event (don't repeat per second).
- If conversation: extract topic + any decisions/commitments separately.
- If food/drink: estimate kcal based on visible portion.
- Korean speech → keep in Korean. English speech → keep in English. Do NOT translate.
- If genuinely nothing observable, return {"events": [], ...}.
- DO NOT invent events that aren't visible/audible in the clip.
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

def call_gemma_lifelog(frames: list, transcript_text: str = "",
                       max_tokens: int = 1500) -> tuple[Optional[dict], int, Optional[str]]:
    """Send frames + transcript + LIFELOG_PROMPT to Gemma 4 E4B."""
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
        with httpx.Client(timeout=GEMMA_TIMEOUT_SEC * 2) as client:
            resp = client.post(f"{GEMMA_BASE_URL}/v1/chat/completions", json=body)
            resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        parsed = json.loads(text)
        ms = int((time.perf_counter() - t0) * 1000)
        return parsed, ms, None
    except Exception as e:
        ms = int((time.perf_counter() - t0) * 1000)
        return None, ms, f"{type(e).__name__}: {str(e)[:160]}"


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
                      max_tokens: int = 1500) -> tuple[Optional[dict], int, Optional[str]]:
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
            # Strip any markdown JSON fences Qwen might add
            text = text.strip()
            if text.startswith("```"):
                text = text.split("```", 2)[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            parsed = json.loads(text)
            ms = int((time.perf_counter() - t0) * 1000)
            return parsed, ms, None
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
                        max_tokens: int = 1500) -> tuple[Optional[dict], int, Optional[str]]:
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
            # Strip any markdown JSON fences Llama 4 might add.
            text = text.strip()
            if text.startswith("```"):
                text = text.split("```", 2)[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            parsed = json.loads(text)
            ms = int((time.perf_counter() - t0) * 1000)
            return parsed, ms, None
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
                   compare: bool, llama4: bool,
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
                "gemma": None, "qwen": None, "llama4": None}
    ts_text = transcript_slice(transcript, start, end)
    log_lines.append(f"  chunk {i+1}  t={start:.0f}-{end:.0f}s  "
                     f"{len(frames)} frames  transcript={len(ts_text)} chars")

    # Build the set of model calls to run for this chunk.
    model_calls = [("gemma", call_gemma_lifelog)]
    if compare:
        model_calls.append(("qwen", call_qwen_lifelog))
    if llama4:
        model_calls.append(("llama4", call_llama4_lifelog))

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
                 "gemma": None, "qwen": None, "llama4": None}

    for name in ("gemma", "qwen", "llama4"):
        if name not in results:
            continue
        parsed, ms, err = results[name]
        if err:
            log_lines.append(f"    [{name:<7}] ERROR ({ms}ms): {err}")
            continue
        events = parsed.get("events", []) if isinstance(parsed, dict) else []
        log_lines.append(f"    [{name:<7}] {ms:>6}ms → {len(events)} events  "
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
        user_id: int = 1, llama4: bool = False,
        chunk_workers: int = 3, parallel_models: bool = True):
    print(f"\n=== Lifelog test: {video_path.name} ===")
    arms = ["Gemma 4"]
    if compare: arms.append("Qwen 3.5 VLM")
    if llama4:  arms.append("Llama 4 Maverick")
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
    n_arms = 1 + (1 if compare else 0) + (1 if llama4 else 0)
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

    total_t0 = time.perf_counter()
    chunk_results: list[Optional[dict]] = [None] * n_chunks

    if eff_chunk_workers > 1 and n_chunks > 1:
        with ThreadPoolExecutor(max_workers=eff_chunk_workers,
                                 thread_name_prefix="chunk") as ex:
            futs = {
                ex.submit(_process_chunk, i, video_path, chunk_sec, duration,
                          transcript, frames_per_chunk, compare, llama4,
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
                        "gemma": None, "qwen": None, "llama4": None,
                    }
                # Print this chunk's buffered output atomically.
                for line in chunk_results[i]["log"]:
                    print(line)
    else:
        for i in range(n_chunks):
            chunk_results[i] = _process_chunk(
                i, video_path, chunk_sec, duration, transcript,
                frames_per_chunk, compare, llama4, parallel_models,
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

    # Speed summary: wall-clock vs sum-of-arms (= what serial would have cost).
    sum_arm_ms = 0
    per_chunk_max_ms = 0
    for r in chunk_results:
        if r is None:
            continue
        chunk_arm_sum = 0
        chunk_arm_max = 0
        for name in ("gemma", "qwen", "llama4"):
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
        # Use video file's mtime as the "video start" wall-clock time so
        # event timestamps reflect when the recording actually happened.
        try:
            video_start = datetime.fromtimestamp(video_path.stat().st_mtime, tz=KST).astimezone(timezone.utc)
        except Exception:
            video_start = datetime.now(timezone.utc) - timedelta(seconds=duration)
        # Subtract video duration so observed_at = video_start + t_sec_abs
        # lands at the actual moment the event happened (mtime = end of recording).
        video_start = video_start - timedelta(seconds=duration)

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
    suffix = ".compare.json" if (compare or llama4) else ".lifelog.json"
    output_path = video_path.with_suffix(suffix)
    output_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  ✓ wrote {output_path}")
    print(f"  Gemma  : {len(gemma_events)} events")
    if compare:
        print(f"  Qwen   : {len(qwen_events)} events")
    if llama4:
        print(f"  Llama4 : {len(llama4_events)} events")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lifelog extraction test")
    parser.add_argument("video", type=Path, help="path to video file")
    parser.add_argument("--compare", action="store_true",
                        help="also run Qwen 3.5 VLM 397B via NVIDIA NIM and compare")
    parser.add_argument("--llama4", action="store_true",
                        help="also run Llama 4 Maverick via NVIDIA NIM and compare")
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
        llama4=args.llama4,
        chunk_workers=args.chunk_workers,
        parallel_models=(not args.no_parallel_models))
