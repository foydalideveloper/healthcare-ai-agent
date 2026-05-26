"""Nemotron 3 Nano Omni extractor — NVIDIA NIM API.

Adds two arms to the dual-extraction comparison:
    arm_nemotron_text       — transcript-only via NIM
    arm_nemotron_multimodal — 8 sampled video frames + transcript via NIM

API endpoint:  https://integrate.api.nvidia.com/v1  (OpenAI-compatible)
Model:         nvidia/nemotron-3-nano-omni-30b-a3b-reasoning
Key:           set NVIDIA_API_KEY env var
               Free credits at https://build.nvidia.com

Language note:
    Nemotron 3 Nano Omni is trained primarily in English. Korean transcripts
    partially work (Llama 3.1 base has limited Korean) but accuracy is lower
    than Gemma 4 E4B. This arm is included to give the boss an English-baseline
    comparison; Korean support is tracked for a future fine-tune.

Reasoning model note:
    The model emits <think>...</think> reasoning tokens before the JSON answer.
    _strip_thinking() removes them automatically. If reasoning consumes max_tokens
    and the JSON is truncated, the error field will say "json_parse".

Local GGUF alternative (blocked for now):
    bartowski/nvidia_Nemotron-3-Nano-30B-A3B-GGUF exists and runs on 12 GB VRAM
    (~25 t/s at Q4_K_M) but llama.cpp issue #20570 (mamba-base.cpp:173 assert)
    causes crashes. Revisit when that bug is patched.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Optional, Tuple

import httpx

# ── Config ──
# Priority: environment variable → backend/.env file → default
def _load_env_key(key: str, default: str = "") -> str:
    if os.environ.get(key):
        return os.environ[key]
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    return default

NVIDIA_BASE_URL      = _load_env_key("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_API_KEY       = _load_env_key("NVIDIA_API_KEY", "")
NEMOTRON_MODEL       = _load_env_key("NEMOTRON_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")
NEMOTRON_TIMEOUT_SEC = 120  # reasoning model + 12 frames + NIM congestion → bumped from 60 s
NEMOTRON_MAX_RETRIES = 2    # retry on ReadTimeout / 5xx — covers transient NIM API hiccups

# Same JSON schema as Gemma arms — outputs are directly comparable.
# /no_think attempts to suppress reasoning; model may still think briefly.
PROMPT_TEMPLATE = (
    "/no_think\n"
    "{frame_intro}"
    "{transcript_block}"
    "Extract every DISTINCT food, drink, exercise, and medication shown in the image(s) "
    "OR mentioned in the transcript. Output ONLY valid JSON — no explanations.\n\n"
    "Schema: {{\"foods\": [{{\"name\": \"...\", \"quantity\": int}}], "
    "\"exercise\": {{\"minutes\": int}} or null, "
    "\"medications\": [{{\"drug_name\": \"...\"}}]}}\n\n"
    "Rules:\n"
    "- Each DISTINCT food/drink is a SEPARATE object. Multiple frames are different "
    "views of the SAME scene — if the same item appears in 5 frames, count it ONCE.\n"
    "- Quantity = how many were eaten/drunk if EXPLICITLY stated. Default to 1.\n"
    "- Preserve names exactly. Korean stays Korean. English stays English.\n"
    "- Identify branded snacks by name only if the wrapper/label is clearly readable.\n"
    "- If unsure of identity, OMIT rather than guess.\n"
    "- SNACK TYPES: be specific — 'chips' not 'snack', 'cookies' not 'biscuit', 'chocolate bar' not 'candy'. Use generic type if brand is unreadable.\n"
    "- EXERCISE — two independent sources, report BOTH if present:\n"
    "  1. Transcript exercise: if transcript mentions duration, record it.\n"
    "  2. Visual exercise: if ANY frame shows physical activity (squat, push-up, stretch, jump, any deliberate body movement), add it with minutes=1 if duration is unknown.\n"
    "  DO NOT skip visual exercise just because the transcript already has exercise.\n"
    "- SHORT CLIPS: a single frame showing someone holding food, or doing one rep of exercise, is a valid event. Extract it.\n"
    "Output ONLY the JSON object."
)


def _strip_thinking(text: str) -> str:
    """Remove <think>...</think> block from reasoning model output."""
    if not text:
        return ""
    if "<think>" in text:
        end = text.rfind("</think>")
        if end != -1:
            text = text[end + len("</think>"):].strip()
    text = re.sub(r"</?think>", "", text).strip()
    return text


def _extract_json(text: str) -> str:
    """Pull the first complete {...} JSON object out of text."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def _repair_loose_json(text: str) -> str:
    """Best-effort repair for non-strict JSON Nemotron sometimes emits.

    Handles failure modes seen in real Nemotron native-video output:
      1. Unquoted property names:        {name: "x"}        → {"name": "x"}
      2. Single-quoted strings:          {'name': 'x'}      → {"name": "x"}
      3. Trailing commas:                [1, 2, ]           → [1, 2 ]
      4. Missing colon after key:        {"foods" [...]}    → {"foods": [...]}
      5. Missing comma between fields:   "name":"x" "qty":1 → "name":"x", "qty":1
      6. Python-style booleans/None:     True/False/None    → true/false/null

    Heuristic only — won't recover from severely truncated output.
    """
    # 1. Quote bare identifier keys
    text = re.sub(
        r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:',
        r'\1"\2":',
        text,
    )
    # 2. Convert single-quoted strings to double-quoted
    text = re.sub(r"'([^'\\]*)'", r'"\1"', text)
    # 3. Remove trailing commas before } or ]
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    # 4. Insert missing colon between a quoted key and the following value
    #    Pattern: "key" [  or  "key" {  or  "key" "value"  or  "key" 123
    text = re.sub(
        r'("[^"]+")\s+(?=[\[{"\d-])',
        r'\1: ',
        text,
    )
    # 5. Insert missing commas between adjacent key-value pairs at the same level
    #    "v1" "k2": → "v1", "k2":
    text = re.sub(r'("\s*)\s+("\w[^"]*"\s*:)', r'\1, \2', text)
    text = re.sub(r'(\d\s*)\s+("\w[^"]*"\s*:)', r'\1, \2', text)
    text = re.sub(r'(}\s*)\s+(?={)', r'\1, ', text)
    text = re.sub(r'(\]\s*)\s+(?=[{"])', r'\1, ', text)
    # 6. Python literals
    text = re.sub(r'\bTrue\b',  'true',  text)
    text = re.sub(r'\bFalse\b', 'false', text)
    text = re.sub(r'\bNone\b',  'null',  text)
    return text


def _salvage_names(text: str) -> Optional[dict]:
    """Last-resort salvage when strict + repair both fail.
    Pulls food names and exercise minutes via regex even if the surrounding
    JSON structure is broken. Loses kcal/quantity but rescues the core info.
    """
    name_matches = re.findall(r'"name"\s*:\s*"([^"]+)"', text)
    drug_matches = re.findall(r'"drug_name"\s*:\s*"([^"]+)"', text)
    minutes_match = re.search(r'"minutes"\s*:\s*(\d+)', text)
    if not (name_matches or drug_matches or minutes_match):
        return None
    foods = [{"name": n, "quantity": 1} for n in name_matches]
    meds = [{"drug_name": d} for d in drug_matches]
    exercise = {"minutes": int(minutes_match.group(1))} if minutes_match else None
    return {"foods": foods, "exercise": exercise, "medications": meds}


def _safe_json_loads(text: str):
    """Three-tier parser: strict → permissive repair → regex salvage.
    Raises json.JSONDecodeError only if all three fail."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(_repair_loose_json(text))
    except json.JSONDecodeError as e:
        salvaged = _salvage_names(text)
        if salvaged is not None:
            return salvaged
        raise e


def _post_to_nemotron(
    content_blocks: list,
    max_tokens: int = 2048,
    multimodal: bool = False,
) -> Tuple[Optional[dict], int, Optional[str]]:
    if not NVIDIA_API_KEY:
        return None, 0, "no_api_key: set NVIDIA_API_KEY env var (get free credits at build.nvidia.com)"

    body = {
        "model": NEMOTRON_MODEL,
        "messages": [{"role": "user", "content": content_blocks}],
        "temperature": 1.0,  # NVIDIA docs require 1.0; 0 causes issues
        "top_p": 1.0,
        "max_tokens": max_tokens,
        # response_format: json_object removed — reasoning model uses thinking tokens
        # that count toward max_tokens, causing JSON truncation. _extract_json handles
        # both text and multimodal outputs reliably without this constraint.
    }
    t0 = time.perf_counter()
    last_transient_err: Optional[str] = None
    resp = None
    for attempt in range(NEMOTRON_MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=NEMOTRON_TIMEOUT_SEC) as client:
                resp = client.post(
                    f"{NVIDIA_BASE_URL}/chat/completions",
                    json=body,
                    headers={
                        "Authorization": f"Bearer {NVIDIA_API_KEY}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
            break  # success
        except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            last_transient_err = f"timeout (attempt {attempt + 1}/{NEMOTRON_MAX_RETRIES + 1}): {type(e).__name__}"
            if attempt == NEMOTRON_MAX_RETRIES:
                return None, int((time.perf_counter() - t0) * 1000), f"http: {last_transient_err}"
            time.sleep(2 * (attempt + 1))  # 2s, 4s backoff
        except httpx.HTTPStatusError as e:
            # Retry only on 5xx (transient server errors); 4xx is permanent
            if 500 <= e.response.status_code < 600 and attempt < NEMOTRON_MAX_RETRIES:
                last_transient_err = f"http_{e.response.status_code} (attempt {attempt + 1})"
                time.sleep(2 * (attempt + 1))
                continue
            body_snippet = ""
            try:
                body_snippet = f" body={e.response.text[:200]}"
            except Exception:
                pass
            return None, int((time.perf_counter() - t0) * 1000), f"http_{e.response.status_code}: {str(e)[:200]}{body_snippet}"
    try:
        data = resp.json()
        msg = data["choices"][0]["message"]
        raw_text = msg.get("content") or msg.get("reasoning_content") or ""
        if not raw_text:
            return None, int((time.perf_counter() - t0) * 1000), f"empty_content: full={json.dumps(data)[:300]}"
        clean_text = _extract_json(_strip_thinking(raw_text))
        if not clean_text:
            return None, int((time.perf_counter() - t0) * 1000), "empty_after_strip_thinking"
        parsed = _safe_json_loads(clean_text)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return parsed, elapsed_ms, None
    except json.JSONDecodeError as e:
        return None, int((time.perf_counter() - t0) * 1000), f"json_parse: {str(e)[:200]}"
    except Exception as e:
        return None, int((time.perf_counter() - t0) * 1000), f"other: {type(e).__name__}: {str(e)[:200]}"


def nemotron_extract_text(transcript: str) -> Tuple[Optional[dict], int, Optional[str]]:
    """Text-only arm: Whisper transcript → Nemotron NIM → JSON."""
    if not transcript:
        return None, 0, "empty_transcript"
    prompt = PROMPT_TEMPLATE.format(
        frame_intro="",
        transcript_block=f'Spoken transcript: "{transcript}"\n\n',
    )
    # 4096 tokens: reasoning model may still think despite /no_think, consuming
    # 1000-2000 tokens before generating JSON. 2048 (old default) truncates mid-key.
    return _post_to_nemotron([{"type": "text", "text": prompt}], max_tokens=4096)


def nemotron_extract_multimodal(
    video_path: Path,
    transcript: str = "",
) -> Tuple[Optional[dict], int, Optional[str]]:
    """Multimodal arm: 8 sampled video frames + transcript → Nemotron NIM → JSON."""
    if not video_path or not Path(video_path).exists():
        return None, 0, "no_video"

    # Reuse frame sampling + JPEG encoding from gemma_dual_extractor
    try:
        from gemma_dual_extractor import _sample_frames, _img_to_data_url
    except ImportError as e:
        return None, 0, f"import_error: {e}"

    # NVIDIA NIM has stricter request-size limits than the local Mac mini server.
    # 6 frames keeps the payload well under the limit while still covering the video.
    frames = _sample_frames(Path(video_path), num_frames=6)
    if not frames:
        return None, 0, "no_frames"

    content = [
        {"type": "image_url", "image_url": {"url": _img_to_data_url(img)}}
        for img in frames
    ]
    transcript_block = f'Spoken transcript: "{transcript}"\n\n' if transcript else ""
    prompt = PROMPT_TEMPLATE.format(
        frame_intro="These 6 frames are sampled across a short video (front-weighted: more frames in first 40%). ",
        transcript_block=transcript_block,
    )
    content.append({"type": "text", "text": prompt})
    return _post_to_nemotron(content, max_tokens=4096, multimodal=True)


def nemotron_extract_image(image_path: Path) -> Tuple[Optional[dict], int, Optional[str]]:
    """Single-photo arm: Nemotron multimodal on one still image (HEIC/JPG/PNG)."""
    if not image_path or not Path(image_path).exists():
        return None, 0, "no_image"
    try:
        from gemma_dual_extractor import _img_to_data_url
        from PIL import Image as _PIL
        img = _PIL.open(image_path).convert("RGB")
    except Exception as e:
        return None, 0, f"image_load: {type(e).__name__}: {str(e)[:120]}"
    content = [
        {"type": "image_url", "image_url": {"url": _img_to_data_url(img)}},
        {"type": "text", "text": PROMPT_TEMPLATE.format(
            frame_intro="This is a single photo from AI glasses. Identify every food, drink, exercise, or medication visible. ",
            transcript_block="",
        )},
    ]
    return _post_to_nemotron(content, max_tokens=4096, multimodal=True)


# ─── Stage 1: NATIVE audio + NATIVE video arms ───
# These bypass Whisper and frame-sampling entirely. NVIDIA NIM accepts raw
# audio (wav/mp3 up to 1h) and raw video (mp4 up to 2 min) via the audio_url
# and video_url content types. Sent as base64 data URIs.

import base64 as _b64


def _file_to_data_uri(path: Path, mime: str) -> Optional[str]:
    """Read a file and return a base64 data URI suitable for NVIDIA NIM."""
    try:
        raw = Path(path).read_bytes()
    except Exception:
        return None
    return f"data:{mime};base64,{_b64.b64encode(raw).decode()}"


def nemotron_extract_native_audio(audio_path: Path) -> Tuple[Optional[dict], int, Optional[str]]:
    """Send raw WAV audio to Nemotron's Parakeet encoder. NO Whisper involved.
    Tests Nemotron's native ASR + extraction in one shot."""
    if not audio_path or not Path(audio_path).exists():
        return None, 0, "no_audio"
    size_mb = Path(audio_path).stat().st_size / 1e6
    if size_mb > 25:  # NIM payload limit safety
        return None, 0, f"audio_too_large: {size_mb:.1f} MB"

    data_uri = _file_to_data_uri(audio_path, "audio/wav")
    if not data_uri:
        return None, 0, "audio_read_failed"

    prompt = (
        "/no_think\n"
        "Listen to this audio recording from AI glasses worn by a user. "
        "Extract every food, drink, exercise, and medication the user mentions. "
        "Output ONLY valid JSON.\n\n"
        "Schema: {\"foods\": [{\"name\": \"...\", \"quantity\": int}], "
        "\"exercise\": {\"minutes\": int} or null, "
        "\"medications\": [{\"drug_name\": \"...\"}]}\n\n"
        "- Preserve exact words. Korean stays Korean, English stays English.\n"
        "- If user says 'I had three of this' it counts as quantity=3 of the previously named item.\n"
        "- Do not invent items. Output only the JSON object."
    )

    content = [
        {"type": "audio_url", "audio_url": {"url": data_uri}},
        {"type": "text", "text": prompt},
    ]
    return _post_to_nemotron(content, max_tokens=4096, multimodal=True)


def _compress_video_for_nim(video_path: Path, target_mb: int = 25) -> Tuple[Optional[Path], Optional[str]]:
    """Compress video to fit under NIM payload limits (target ~25 MB raw → ~33 MB base64).
    Returns (compressed_path, None) on success or (None, error_msg) on failure.
    Caller is responsible for deleting the compressed file when done.
    """
    import subprocess
    src = Path(video_path)
    dst = src.parent / f".{src.stem}_compressed_for_nim.mp4"
    try:
        # H.264 at 720p, CRF 30 (visually OK for analysis), 64 kbps mono audio.
        # -preset veryfast keeps compression time under ~10s for a 60s 1080p clip.
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(src),
                "-vf", "scale='min(1280,iw)':-2",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
                "-c:a", "aac", "-b:a", "64k", "-ac", "1",
                "-movflags", "+faststart",
                str(dst),
            ],
            capture_output=True,
            timeout=180,
        )
        if result.returncode != 0:
            return None, f"ffmpeg_failed: rc={result.returncode}"
        if not dst.exists() or dst.stat().st_size < 10000:
            return None, "ffmpeg_no_output"
        out_mb = dst.stat().st_size / 1e6
        if out_mb > target_mb * 2:
            return None, f"compress_insufficient: {out_mb:.1f} MB (wanted ~{target_mb} MB)"
        return dst, None
    except FileNotFoundError:
        return None, "ffmpeg_not_installed"
    except subprocess.TimeoutExpired:
        return None, "ffmpeg_timeout"
    except Exception as e:
        return None, f"compress_error: {type(e).__name__}: {str(e)[:120]}"


def nemotron_extract_native_video(video_path: Path) -> Tuple[Optional[dict], int, Optional[str]]:
    """Send raw MP4 video to Nemotron's 3D-conv video encoder. NO frame sampling, NO Whisper.
    Tests Nemotron's native multimodal in one shot.

    If the source video exceeds ~25 MB, it is transparently compressed via ffmpeg
    (H.264 720p CRF30) to fit under the NIM API's payload limit. The compressed
    file is deleted after the API call completes.
    """
    if not video_path or not Path(video_path).exists():
        return None, 0, "no_video"

    src = Path(video_path)
    src_mb = src.stat().st_size / 1e6
    upload_path = src
    cleanup_path: Optional[Path] = None

    if src_mb > 25:
        compressed, comp_err = _compress_video_for_nim(src, target_mb=25)
        if compressed is None:
            return None, 0, f"compress_failed: {comp_err} (source {src_mb:.1f} MB)"
        upload_path = compressed
        cleanup_path = compressed

    try:
        upload_mb = upload_path.stat().st_size / 1e6
        if upload_mb > 70:
            return None, 0, f"still_too_large: {upload_mb:.1f} MB after compression"

        data_uri = _file_to_data_uri(upload_path, "video/mp4")
        if not data_uri:
            return None, 0, "video_read_failed"

        prompt = (
            "/no_think\n"
            "This is a video clip from AI glasses worn by a user. Watch the video AND listen to the audio. "
            "Extract every food, drink, exercise, and medication visible in the frames or mentioned in the audio. "
            "Output ONLY valid JSON.\n\n"
            "Schema: {\"foods\": [{\"name\": \"...\", \"quantity\": int}], "
            "\"exercise\": {\"minutes\": int} or null, "
            "\"medications\": [{\"drug_name\": \"...\"}]}\n\n"
            "- Even brief physical activity (a short stretch, a few jumping jacks) counts as exercise; "
            "use minutes=1 if duration is unclear.\n"
            "- Korean stays Korean, English stays English. Do not translate.\n"
            "- If you see a labeled product, use the brand text from the label.\n"
            "- Output only the JSON object."
        )

        content = [
            {"type": "video_url", "video_url": {"url": data_uri}},
            {"type": "text", "text": prompt},
        ]
        return _post_to_nemotron(content, max_tokens=4096, multimodal=True)
    finally:
        if cleanup_path is not None and cleanup_path.exists():
            try:
                cleanup_path.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    # Standalone smoke test
    import sys
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if not NVIDIA_API_KEY:
        print("ERROR: NVIDIA_API_KEY not set.")
        print("  Get free credits at https://build.nvidia.com")
        print("  Then: set NVIDIA_API_KEY=nvapi-xxxx")
        sys.exit(1)

    print(f"Model : {NEMOTRON_MODEL}")
    print(f"API   : {NVIDIA_BASE_URL}")
    print()

    # Text test
    test_transcript = "Right now I ate three Snickers and today morning I had 42 minutes of exercise."
    print(f"Text test transcript: {test_transcript}")
    result, ms, err = nemotron_extract_text(test_transcript)
    if err:
        print(f"  ERROR: {err}")
    else:
        print(f"  Result ({ms}ms): {json.dumps(result, ensure_ascii=False)}")

    # Multimodal test (if video path provided)
    if len(sys.argv) > 1:
        video = Path(sys.argv[1])
        print(f"\nMultimodal test: {video}")
        result, ms, err = nemotron_extract_multimodal(video, test_transcript)
        if err:
            print(f"  ERROR: {err}")
        else:
            print(f"  Result ({ms}ms): {json.dumps(result, ensure_ascii=False)}")
