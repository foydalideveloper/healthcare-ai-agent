"""Lifelog chat — text-RAG over the `lifelog_event` table.

User asks a natural-language question ("what did I eat yesterday?",
"who did I meet on Saturday at 10am?"). We pull recent events for that
user, stuff them into the prompt, and call one of three LLMs:

  - gemma_4_e4b      → Mac mini llama.cpp @ 100.69.125.64:8081 (local, fast, free)
  - qwen_3_5_vlm     → NVIDIA NIM qwen/qwen3.5-397b-a17b
  - llama_4_maverick → NVIDIA NIM meta/llama-4-maverick-17b-128e-instruct

Auto-escalation: when the chat answer indicates the structured events
do not cover the question (e.g. "I don't have that information"), the
endpoint automatically calls `reanalyze_clip` on the candidate clip
(picked by time hint in the question, or most-recent fallback) so the
user gets a multimodal answer in ONE request.
"""

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import get_db_admin
from app.api.lifelog_reanalyze import reanalyze_clip

router = APIRouter(prefix="/lifelog", tags=["lifelog"])

# Refusal-detection: case-insensitive substrings that signal the chat
# model couldn't answer from the structured events. Conservative on purpose
# — better to occasionally over-escalate (cost: one extra reanalyze call)
# than to under-escalate (cost: user gets "I don't know" when we could
# have looked at the actual clip).
_REFUSAL_PATTERNS = (
    "i don't have that information",
    "i do not have that information",
    "i don't have information",
    "i do not have information",
    "no record of",
    "no information about",
    "no information on",
    "i cannot determine",
    "i can't determine",
    "i don't see",
    "i do not see",
    "not in the events",
    "the events do not",
    "the events don't",
    "no events",
    "not enough information",
    "cannot answer",
    "can't answer",
)


def _is_refusal(answer: str) -> bool:
    a = (answer or "").strip().lower()
    if not a:
        return False
    return any(p in a for p in _REFUSAL_PATTERNS)


def _pick_clip_candidate(events: list[dict], user_message: str) -> Optional[dict]:
    """Heuristic: pick the most-likely-relevant event whose source_video
    is non-null, given the user's question. v1 strategy: take the most
    recent event with a source_video. If the message contains common
    time hints we can later upgrade this. Returns the event dict or None.
    """
    if not events:
        return None
    # Reverse to start from most recent
    for ev in reversed(events):
        if ev.get("source_video"):
            return ev
    return None

_KST = timezone(timedelta(hours=9))

GEMMA_URL = "http://100.69.125.64:8081/v1/chat/completions"
GEMMA_MODEL = "gemma-4-E4B-it"
NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
QWEN_MODEL = "qwen/qwen3.5-397b-a17b"
LLAMA4_MODEL = "meta/llama-4-maverick-17b-128e-instruct"

ALLOWED_MODELS = {"gemma_4_e4b", "qwen_3_5_vlm", "llama_4_maverick"}
DEFAULT_LOOKBACK_DAYS = 7
MAX_EVENTS_IN_CONTEXT = 200
MAX_HISTORY_TURNS = 10


def _load_nvidia_key() -> Optional[str]:
    key = os.environ.get("NVIDIA_API_KEY")
    if key:
        return key
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("NVIDIA_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    user_id: int
    model: str = Field(..., description="gemma_4_e4b | qwen_3_5_vlm | llama_4_maverick")
    message: str
    history: list[ChatTurn] = Field(default_factory=list)
    lookback_days: int = DEFAULT_LOOKBACK_DAYS
    auto_escalate: bool = Field(
        default=True,
        description="If the chat answer can't be grounded in the events, "
                    "automatically re-analyze the most-recent clip with the "
                    "same model and return the multimodal answer.",
    )


def _format_event_line(ev: dict) -> str:
    try:
        obs = datetime.fromisoformat(ev["observed_at"].replace("Z", "+00:00"))
        ts = obs.astimezone(_KST).strftime("%a %m-%d %H:%M")
    except Exception:
        ts = (ev.get("observed_at") or "")[:16]

    parts = [f"[{ts}]"]
    if ev.get("category"):
        parts.append(f"({ev['category']})")
    if ev.get("location"):
        parts.append(f"@{ev['location']}")
    parts.append(ev.get("description") or "(no description)")

    extras = []
    if ev.get("people"):            extras.append(f"people={ev['people']}")
    if ev.get("objects"):           extras.append(f"objects={ev['objects']}")
    if ev.get("topic"):             extras.append(f"topic={ev['topic']}")
    if ev.get("decision"):          extras.append(f"decision={ev['decision']}")
    if ev.get("mood"):              extras.append(f"mood={ev['mood']}")
    if ev.get("kcal"):              extras.append(f"{ev['kcal']}kcal")
    if ev.get("amount_ml"):         extras.append(f"{ev['amount_ml']}ml")
    if ev.get("audio_heard"):       extras.append(f"audio={ev['audio_heard']}")
    if ev.get("numbers_mentioned"): extras.append(f"nums={ev['numbers_mentioned']}")
    if ev.get("screen"):            extras.append(f"screen={ev['screen']}")
    if extras:
        parts.append("| " + " ".join(extras))
    return " ".join(parts)


async def _fetch_user_events(user_id: int, lookback_days: int) -> list[dict]:
    db = get_db_admin()
    now = datetime.now(_KST)
    since = now - timedelta(days=lookback_days)
    params = [
        ("select", "observed_at,duration_sec,category,description,people,"
                   "people_count,location,indoor_outdoor,posture,mood,"
                   "objects,screen,topic,decision,audio_heard,"
                   "numbers_mentioned,kcal,amount_ml,source_model,source_video"),
        ("user_id",     f"eq.{user_id}"),
        ("observed_at", f"gte.{since.astimezone(timezone.utc).isoformat()}"),
        ("order",       "observed_at.asc"),
        ("limit",       str(MAX_EVENTS_IN_CONTEXT)),
    ]
    resp = await db._client.get("/lifelog_event", params=params)
    resp.raise_for_status()
    rows = resp.json()
    return rows if isinstance(rows, list) else []


def _build_messages(events: list[dict], history: list[ChatTurn],
                    user_message: str, lookback_days: int) -> list[dict]:
    now_kst = datetime.now(_KST).strftime("%A %Y-%m-%d %H:%M")
    events_block = (
        "\n".join(_format_event_line(e) for e in events)
        if events else "(no events recorded in this time window)"
    )

    system = (
        "You are an AI assistant that helps the user remember their day. "
        "The user wears AI glasses that record their activities; the data "
        "below is a chronological log of events extracted from those "
        "recordings, with absolute timestamps.\n\n"
        f"Current time (KST): {now_kst}\n"
        "Timezone: KST (UTC+9)\n\n"
        "Rules:\n"
        "- Answer ONLY from the events below. Do NOT invent facts.\n"
        "- If the user asks about something the events do not cover, say "
        "\"I don't have that information.\"\n"
        "- Be concise. Quote timestamps and locations when relevant.\n"
        "- Korean text in events stays in Korean unless the user asks for "
        "translation.\n"
        "- The user's time references (\"yesterday morning\", \"Saturday at "
        "10am\") are in KST.\n\n"
        f"=== Events for the past {lookback_days} day(s) ===\n"
        f"{events_block}\n"
        "=== End events ==="
    )

    msgs: list[dict] = [{"role": "system", "content": system}]
    for t in history[-MAX_HISTORY_TURNS:]:
        if t.role in ("user", "assistant"):
            msgs.append({"role": t.role, "content": t.content})
    msgs.append({"role": "user", "content": user_message})
    return msgs


async def _call_gemma(messages: list[dict]) -> tuple[str, int]:
    body = {
        "model": GEMMA_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1024,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(GEMMA_URL, json=body)
        resp.raise_for_status()
    data = resp.json()
    answer = data["choices"][0]["message"]["content"].strip()
    return answer, int((time.perf_counter() - t0) * 1000)


async def _call_nim(messages: list[dict], model: str) -> tuple[str, int]:
    key = _load_nvidia_key()
    if not key:
        raise HTTPException(status_code=500, detail="NVIDIA_API_KEY not configured")
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1024,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(NIM_URL, json=body, headers=headers)
        resp.raise_for_status()
    data = resp.json()
    answer = data["choices"][0]["message"]["content"].strip()
    return answer, int((time.perf_counter() - t0) * 1000)


@router.post("/chat")
async def lifelog_chat(req: ChatRequest):
    if req.model not in ALLOWED_MODELS:
        raise HTTPException(status_code=400,
                            detail=f"model must be one of {sorted(ALLOWED_MODELS)}")
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    events = await _fetch_user_events(req.user_id, max(1, req.lookback_days))
    messages = _build_messages(events, req.history, req.message, req.lookback_days)

    try:
        if req.model == "gemma_4_e4b":
            answer, latency_ms = await _call_gemma(messages)
        elif req.model == "qwen_3_5_vlm":
            answer, latency_ms = await _call_nim(messages, QWEN_MODEL)
        else:  # llama_4_maverick
            answer, latency_ms = await _call_nim(messages, LLAMA4_MODEL)
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"{req.model} returned {e.response.status_code}: {e.response.text[:200]}",
        )
    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"{type(e).__name__}: {str(e)[:200]}")

    response = {
        "answer": answer,
        "model": req.model,
        "latency_ms": latency_ms,
        "events_in_context": len(events),
        "lookback_days": req.lookback_days,
        "escalated": False,
    }

    # ── Auto-escalation ──────────────────────────────────────────────
    # If the structured-RAG answer is a refusal, fall back to a multimodal
    # look at the most-recent clip with the same model. User gets ONE
    # combined response with both passes visible.
    if req.auto_escalate and _is_refusal(answer):
        candidate = _pick_clip_candidate(events, req.message)
        if candidate and candidate.get("source_video"):
            response["first_pass_answer"] = answer
            response["escalation_reason"] = (
                "chat could not answer from structured events; re-analysing "
                f"clip '{candidate['source_video']}' with {req.model}"
            )
            try:
                deep = await reanalyze_clip(
                    user_id=req.user_id,
                    model=req.model,
                    source_video=candidate["source_video"],
                    question=req.message,
                    frames=8,
                )
                response["answer"] = deep["answer"]
                response["escalated"] = True
                response["reanalyze_source_video"] = deep["source_video"]
                response["reanalyze_frames_used"] = deep["frames_used"]
                response["reanalyze_latency_ms"] = deep["latency_ms"]
                response["reanalyze_transcript_excerpt"] = deep["transcript_excerpt"]
            except HTTPException as e:
                response["escalation_error"] = f"{e.status_code}: {e.detail}"
            except Exception as e:
                response["escalation_error"] = f"{type(e).__name__}: {str(e)[:200]}"

    return response
