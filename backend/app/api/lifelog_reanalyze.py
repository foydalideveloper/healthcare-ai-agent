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

# Endpoints (same as lifelog_chat.py — duplicated here so this module is
# self-contained and doesn't import from a sibling that could change).
GEMMA_URL = "http://100.69.125.64:8081/v1/chat/completions"
GEMMA_MODEL = "gemma-4-E4B-it"
WHISPER_REMOTE_URL = "http://100.69.125.64:8082/inference"
NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
QWEN_MODEL = "qwen/qwen3.5-397b-a17b"
LLAMA4_MODEL = "meta/llama-4-maverick-17b-128e-instruct"

ALLOWED_MODELS = {"gemma_4_e4b", "qwen_3_5_vlm", "llama_4_maverick"}
GEMMA_MAX_FRAMES = 6   # Mac mini Gemma OOMs on 8 real frames; same cap used in _lifelog_test.py
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


def _whisper(video_path: Path) -> str:
    """Extract audio + transcribe via Mac mini Whisper. Returns plain text."""
    import subprocess
    audio_path = video_path.with_suffix(".reanalyze_audio.wav")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path),
             "-ac", "1", "-ar", "16000", "-f", "wav", str(audio_path)],
            capture_output=True, check=True, timeout=300,
        )
        with open(audio_path, "rb") as f:
            resp = httpx.post(
                WHISPER_REMOTE_URL,
                files={"file": ("audio.wav", f, "audio/wav")},
                data={"language": "auto", "response_format": "verbose_json",
                      "max_len": "0", "temperature": "0"},
                timeout=300,
            )
        resp.raise_for_status()
        return (resp.json().get("text") or "").strip()
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


async def _call_gemma(content: list[dict]) -> tuple[str, int]:
    body = {
        "model": GEMMA_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": content},
        ],
        "temperature": 0.2,
        "max_tokens": 512,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(GEMMA_URL, json=body)
        resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip(), int((time.perf_counter() - t0) * 1000)


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
    model: str = Field(..., description="gemma_4_e4b | qwen_3_5_vlm | llama_4_maverick")
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

    max_frames_for_model = GEMMA_MAX_FRAMES if model == "gemma_4_e4b" else len(sampled)
    content = _build_content(sampled, transcript, question, max_frames_for_model)

    try:
        if model == "gemma_4_e4b":
            answer, latency_ms = await _call_gemma(content)
        elif model == "qwen_3_5_vlm":
            answer, latency_ms = await _call_nim(content, QWEN_MODEL)
        else:
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
