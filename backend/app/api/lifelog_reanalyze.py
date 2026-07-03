"""Lifelog re-analysis — ask the LLM about a SPECIFIC clip, on demand.

Users sometimes ask things the original extractor didn't capture:
  "What was that book on the table?"
  "What brand was the coffee cup?"
  "Who walked past in the background?"

This endpoint takes a clip filename + a question, re-samples frames,
re-runs Whisper on the audio, and sends both to the chosen multimodal
model with the user's question (NOT the LIFELOG_PROMPT schema).

POST /api/v1/lifelog/reanalyze
body:
  {
    "user_id": 1,
    "model": "gemma_4_e4b" | "qwen_3_5_vlm" | "llama_4_maverick",
    "source_video": "20260513_iOS.MOV",          # required
    "question": "What was the book on the desk?",
    "frames": 8                                   # optional, default 8
  }

returns:
  {
    "answer": "...",
    "model": "...",
    "latency_ms": int,
    "source_video": "...",
    "video_path": "...",
    "transcript_excerpt": "...",
    "frames_used": int
  }
"""

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/lifelog", tags=["lifelog"])

_KST = timezone(timedelta(hours=9))

# Endpoints — three local arms via Ollama (port 11434), Llama4 via NIM cloud,
# Gemini via Google AI Studio. Whisper is local faster-whisper, not the old
# Mac mini whisper-server.
OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
GEMMA_MODEL = "gemma4:26b-a4b-it-q8_0"
QWEN_MODEL = "qwen3-vl:30b-a3b-instruct-q4_K_M"
NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
LLAMA4_MODEL = "meta/llama-4-maverick-17b-128e-instruct"
GEMINI_MODEL_DEFAULT = "gemini-2.5-pro"

# Frontend can send either the new dynamic source tags (preferred — match what
# _lifelog_test writes to Supabase) or the legacy hard-coded tags (kept so old
# bookmarks still resolve). Each acceptable tag dispatches to one of 4 canonical
# handlers below.
MODEL_DISPATCH: dict[str, str] = {
    # Gemma → local Ollama
    "gemma4_26b_a4b_it_q8_0": "gemma",
    "gemma_4_e4b":            "gemma",   # legacy
    # Qwen → local Ollama
    "qwen3_vl_30b_a3b_instruct_q4_k_m": "qwen",
    "qwen3_5_397b_a17b":                "qwen",
    "qwen_3_5_vlm":                     "qwen",  # legacy
    # Llama 4 Maverick → NVIDIA NIM
    "llama_4_maverick_17b_128e_inst": "llama4",
    "llama_4_maverick":               "llama4",  # legacy
    # Gemini 2.5 Pro → Google AI Studio
    "gemini_2_5_pro": "gemini",
}
ALLOWED_MODELS = set(MODEL_DISPATCH)
GEMMA_MAX_FRAMES = 8   # local Ollama Gemma 26B A4B handles 8 frames fine
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv"}

# Where to look for the source clip. Mirrors lifelog_watcher.py's folders.
def _watch_folders() -> list[Path]:
    base = Path.home() / "OneDrive" / "Pictures" / "Camera Roll"
    out = [base, Path.home() / "OneDrive" / "Pictures", Path.home() / "AIMB-Bridge"]
    now = datetime.now()
    out.append(base / str(now.year) / f"{now.month:02d}")
    if now.month > 1:
        out.append(base / str(now.year) / f"{now.month - 1:02d}")
    out.append(Path(__file__).resolve().parents[2] / "backend" / "glasses_watcher" / "inbox")
    return [p for p in out if p.exists()]


def _find_clip(source_video: str) -> Optional[Path]:
    name = Path(source_video).name
    # Direct hit first
    for folder in _watch_folders():
        direct = folder / name
        if direct.is_file():
            return direct
    # Recursive fallback
    for folder in _watch_folders():
        for p in folder.rglob(name):
            if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
                return p
    return None


def _load_nvidia_key() -> Optional[str]:
    key = os.environ.get("NVIDIA_API_KEY")
    if key:
        return key
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("NVIDIA_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


# ──────────────────────────────────────────────────────────────────────
# Frame sampling + Whisper transcript — sync, run inside asyncio.to_thread
# ──────────────────────────────────────────────────────────────────────

def _sample_frames(video_path: Path, n_frames: int) -> list:
    """Sample n_frames evenly from the video. Returns PIL Images."""
    import av  # type: ignore
    container = av.open(str(video_path))
    stream = container.streams.video[0]
    fps = float(stream.average_rate or 30)
    n_total = stream.frames or 0
    if n_total == 0:
        # Re-decode to count
        n_total = sum(1 for _ in container.decode(video=0))
        container.close()
        container = av.open(str(video_path))
    targets = sorted({int(i * n_total / n_frames) for i in range(n_frames)})
    frames = []
    for i, frame in enumerate(container.decode(video=0)):
        if i in targets:
            frames.append(frame.to_image())
            if len(frames) >= n_frames:
                break
    container.close()
    return frames


def _img_to_data_url(img, max_edge: int = 1024) -> str:
    import base64
    from io import BytesIO
    if max(img.size) > max_edge:
        img = img.copy()
        img.thumbnail((max_edge, max_edge))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"


# Local faster-whisper model, lazy-loaded once per process.
_FW_MODEL = None


def _get_fw_model():
    global _FW_MODEL
    if _FW_MODEL is None:
        from faster_whisper import WhisperModel
        _FW_MODEL = WhisperModel("large-v3", device="cuda", compute_type="float16")
    return _FW_MODEL


def _whisper(video_path: Path) -> str:
    """Extract audio with ffmpeg, transcribe with local faster-whisper on GPU.

    Returns the concatenated transcript text, or a "(whisper failed: ...)"
    string on error (callers display it as the transcript excerpt verbatim).
    """
    import subprocess
    audio_path = video_path.with_suffix(".reanalyze_audio.wav")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path),
             "-ac", "1", "-ar", "16000", "-f", "wav", str(audio_path)],
            capture_output=True, check=True, timeout=300,
        )
        model = _get_fw_model()
        segments_iter, _info = model.transcribe(
            str(audio_path), language=None, temperature=0, vad_filter=True,
        )
        parts: list[str] = []
        for s in segments_iter:
            t = (s.text or "").strip()
            if t:
                parts.append(t)
        return " ".join(parts).strip()
    except Exception as e:
        return f"(whisper failed: {type(e).__name__}: {str(e)[:120]})"
    finally:
        try:
            audio_path.unlink(missing_ok=True)
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────
# Model calls
# ──────────────────────────────────────────────────────────────────────

_SYSTEM = (
    "You are answering a specific question about what was happening in a "
    "short video clip from the user's AI glasses. Look at the frames "
    "carefully and use the audio transcript when relevant. "
    "Answer in 1-3 short sentences, grounded ONLY in what you can see or "
    "hear. If the answer is not in the clip, say \"I cannot determine "
    "this from the clip.\" Korean stays in Korean; English stays in English."
)


def _build_content(frames: list, transcript: str, question: str, max_frames: int) -> list[dict]:
    if len(frames) > max_frames:
        step = len(frames) / max_frames
        frames = [frames[int(i * step)] for i in range(max_frames)]
    content: list[dict] = [
        {"type": "image_url", "image_url": {"url": _img_to_data_url(f)}}
        for f in frames
    ]
    text = ""
    if transcript and not transcript.startswith("(whisper"):
        text += f'Audio transcript: "{transcript}"\n\n'
    text += f"Question: {question}"
    content.append({"type": "text", "text": text})
    return content


async def _call_ollama(content: list[dict], model: str) -> tuple[str, int]:
    """Call local Ollama (OpenAI-compat). Used for both Gemma and Qwen."""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": content},
        ],
        "temperature": 0.2,
        "max_tokens": 512,
    }
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(OLLAMA_URL, json=body)
        resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip(), int((time.perf_counter() - t0) * 1000)


def _load_gemini_config() -> tuple[Optional[str], str]:
    """Return (api_key, model_id) for Gemini, reading env first then .env."""
    api_key = os.environ.get("GEMINI_API_KEY")
    model = os.environ.get("GEMINI_MODEL") or GEMINI_MODEL_DEFAULT
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if not api_key and line.startswith("GEMINI_API_KEY="):
                api_key = line.split("=", 1)[1].strip()
            elif not os.environ.get("GEMINI_MODEL") and line.startswith("GEMINI_MODEL="):
                v = line.split("=", 1)[1].strip()
                if v:
                    model = v
    return api_key, model


async def _call_gemini(content: list[dict]) -> tuple[str, int]:
    """Call Gemini (Google AI Studio). Converts OpenAI-shape content blocks
    (text + image_url data URLs) to Gemini's parts shape."""
    import base64
    api_key, model = _load_gemini_config()
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")
    parts: list[dict] = []
    for block in content:
        if block.get("type") == "text":
            parts.append({"text": block.get("text", "")})
        elif block.get("type") == "image_url":
            url = (block.get("image_url") or {}).get("url", "")
            # Expect data:image/jpeg;base64,XXXX
            if url.startswith("data:") and "," in url:
                header, b64 = url.split(",", 1)
                mime = header[5:].split(";", 1)[0] or "image/jpeg"
                parts.append({"inline_data": {"mime_type": mime, "data": b64}})
    body = {
        "system_instruction": {"parts": [{"text": _SYSTEM}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 512},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(url, json=body, headers=headers)
        resp.raise_for_status()
    data = resp.json()
    text = (
        data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
    ).strip()
    return text, int((time.perf_counter() - t0) * 1000)


async def _call_nim(content: list[dict], model: str) -> tuple[str, int]:
    key = _load_nvidia_key()
    if not key:
        raise HTTPException(status_code=500, detail="NVIDIA_API_KEY not configured")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": content},
        ],
        "temperature": 0.2,
        "max_tokens": 512,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    t0 = time.perf_counter()
    # 240s — Qwen 3.5 VLM 397B on multimodal can take 90-180s, occasional
    # spikes to ~220s. Llama 4 Maverick is consistently <5s but we keep
    # the shared cap loose for the slower arm.
    async with httpx.AsyncClient(timeout=240.0) as client:
        resp = await client.post(NIM_URL, json=body, headers=headers)
        resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip(), int((time.perf_counter() - t0) * 1000)


# ──────────────────────────────────────────────────────────────────────
# Endpoint
# ──────────────────────────────────────────────────────────────────────

class ReanalyzeRequest(BaseModel):
    user_id: int
    model: str = Field(..., description="any tag from MODEL_DISPATCH (gemma4_26b_a4b_it_q8_0 | qwen3_vl_30b_a3b_instruct_q4_k_m | llama_4_maverick_17b_128e_inst | gemini_2_5_pro). Legacy tags also accepted.")
    source_video: str = Field(..., description="filename only, e.g. '20260513_iOS.MOV'")
    question: str
    frames: int = 8


async def reanalyze_clip(user_id: int, model: str, source_video: str,
                         question: str, frames: int = 8) -> dict:
    """Core reanalyze logic — importable so chat auto-escalation can call it
    directly without an extra HTTP hop. Raises HTTPException on failure so
    both the endpoint and the chat wrapper see the same error shape."""
    if model not in ALLOWED_MODELS:
        raise HTTPException(status_code=400,
                            detail=f"model must be one of {sorted(ALLOWED_MODELS)}")
    if not question.strip():
        raise HTTPException(status_code=400, detail="question is required")

    clip_path = _find_clip(source_video)
    if clip_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"source_video '{source_video}' not found in OneDrive Camera Roll, ~/AIMB-Bridge, or inbox",
        )

    n_frames = max(1, min(16, frames))
    try:
        frames_task = asyncio.to_thread(_sample_frames, clip_path, n_frames)
        transcript_task = asyncio.to_thread(_whisper, clip_path)
        sampled, transcript = await asyncio.gather(frames_task, transcript_task)
    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"clip prep failed: {type(e).__name__}: {str(e)[:200]}")
    if not sampled:
        raise HTTPException(status_code=500, detail="no frames could be sampled from clip")

    handler = MODEL_DISPATCH[model]
    max_frames_for_model = GEMMA_MAX_FRAMES if handler == "gemma" else len(sampled)
    content = _build_content(sampled, transcript, question, max_frames_for_model)

    try:
        if handler == "gemma":
            answer, latency_ms = await _call_ollama(content, GEMMA_MODEL)
        elif handler == "qwen":
            answer, latency_ms = await _call_ollama(content, QWEN_MODEL)
        elif handler == "gemini":
            answer, latency_ms = await _call_gemini(content)
        else:  # llama4
            answer, latency_ms = await _call_nim(content, LLAMA4_MODEL)
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"{model} returned {e.response.status_code}: {e.response.text[:200]}",
        )
    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"{type(e).__name__}: {str(e)[:200]}")

    return {
        "answer": answer,
        "model": model,
        "latency_ms": latency_ms,
        "source_video": source_video,
        "video_path": str(clip_path),
        "transcript_excerpt": transcript[:500] if transcript else "",
        "frames_used": min(len(sampled), max_frames_for_model),
    }


@router.post("/reanalyze")
async def lifelog_reanalyze(req: ReanalyzeRequest):
    return await reanalyze_clip(
        user_id=req.user_id,
        model=req.model,
        source_video=req.source_video,
        question=req.question,
        frames=req.frames,
    )
