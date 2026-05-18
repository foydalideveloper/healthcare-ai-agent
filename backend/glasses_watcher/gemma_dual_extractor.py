"""Phase 2 dual-extraction logger — runs Gemma 4 + Nemotron alongside today's pipeline.

For every AIMB-G1 video event, this module makes extra calls to comparison models
and logs all 5 arms side-by-side to a JSONL file for offline analysis:

    arm_today               — today's pipeline (regex + YOLO + Whisper + Claude Haiku)
    arm_gemma_text          — Gemma 4 E4B Q8 on Whisper transcript only
    arm_gemma_multimodal    — Gemma 4 E4B Q8 on 8 video frames + transcript
    arm_nemotron_text       — Nemotron 3 Nano Omni via NVIDIA NIM, transcript only
    arm_nemotron_multimodal — Nemotron 3 Nano Omni via NVIDIA NIM, 8 frames + transcript

Arms 4 & 5 require NVIDIA_API_KEY env var. If missing, they record "no_api_key" and skip.
Arms 4 & 5 are English-primary; Korean transcripts partially work (Llama 3.1 base).

Design rules:
  • Additive only — never modifies, blocks, or replaces today's pipeline
  • Fail-safe — every path catches exceptions; can never raise into watcher.py
  • Side-effect-free w.r.t. Supabase — only writes to the local JSONL log file
  • If any server is unreachable, that arm records the error and we move on

Reference: ~/.claude/projects/.../memory/project_healthcare_gemma_llamacpp_request_format.md
"""

import base64
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

import httpx


GEMMA_BASE_URL = "http://100.69.125.64:8080"  # Mac mini Tailscale IP
GEMMA_TIMEOUT_SEC = 30
GEMMA_FRAMES_PER_VIDEO = 6   # Lowered from 12 — fewer vision tokens reduces JSON parse failures on the small Gemma 4 E4B model.

PROJECT_ROOT = Path(__file__).parent.parent.parent
LOG_DIR = PROJECT_ROOT / "backend" / "glasses_watcher" / "logs"
KST = timezone(timedelta(hours=9))

log = logging.getLogger("gemma_dual")

# Nemotron arms (optional — only active when NVIDIA_API_KEY is set in environment).
# Fail-safe import: if nemotron_extractor.py is missing, arms 4 & 5 skip silently.
try:
    from nemotron_extractor import nemotron_extract_text, nemotron_extract_multimodal
    _NEMOTRON_AVAILABLE = True
except Exception as _nem_import_err:
    nemotron_extract_text = None      # type: ignore[assignment]
    nemotron_extract_multimodal = None  # type: ignore[assignment]
    _NEMOTRON_AVAILABLE = False


PROMPT_TEMPLATE = (
    "/no_think\n"
    "{frame_intro}"
    "{transcript_block}"
    "Extract every DISTINCT food, drink, exercise, and medication shown in the image(s) OR mentioned in the transcript. "
    "Output ONLY valid JSON.\n\n"
    "Schema: {{\"foods\": [{{\"name\": \"...\", \"quantity\": int, \"evidence\": \"visual+pronoun\" or \"visual_only\" or \"transcript_explicit\" or \"transcript_inferred\"}}], "
    "\"exercise\": {{\"minutes\": int}} or null, \"medications\": [{{\"drug_name\": \"...\"}}]}}\n\n"
    "EVIDENCE field rules (set this for EVERY food/drink):\n"
    "  - \"visual+pronoun\": item is clearly visible in frames AND transcript references it via 'this/these/that/those'\n"
    "  - \"visual_only\":    item visible in frames but transcript doesn't mention it\n"
    "  - \"transcript_explicit\": user named the item by name (e.g. 'I drank coffee'); may or may not be visible\n"
    "  - \"transcript_inferred\": item not visible AND not explicitly named — you guessed it from context (LOW CONFIDENCE)\n\n"
    "Rules:\n"
    "- If NO food or drink items are clearly visible AND the transcript does not mention any, return {{\"foods\": [], \"exercise\": null, \"medications\": []}}. DO NOT invent food.\n"
    "- NEVER output vague placeholder names: 'tasty item', 'tasty food', 'delicious item', 'snack item', 'food item', 'thing'. If you cannot identify what specific food/drink it is, OMIT it from the list rather than using a placeholder.\n"
    "- Use specific names: 'cookie' (not 'tasty item'), 'orange juice' or 'orange ade' (not 'tasty drink'), 'chips' (not 'crunchy thing'), 'samgyeopsal' / '삼겹살' (not 'meat'). If genuinely uncertain about TYPE, use a broad category like 'cookie', 'chips', 'beverage' — but still be a real food name.\n"
    "- Computers, phones, keyboards, desks, chairs, hands, and people are NOT food items. Ignore them entirely.\n"
    "- Each DISTINCT food/drink is a SEPARATE object. Multiple sampled frames are different views of the SAME scene — count each distinct physical item only once.\n"
    "- QUANTITY RULES (read carefully):\n"
    "    * If the user says 'X of this/these/them' (e.g. 'four of these', 'three of this', 'I had 4 of these') AND a food/drink is visible in the frames, that X IS the quantity for that visible item.\n"
    "    * If the user says a number directly with a food name ('three coffees', 'two cookies'), that number IS the quantity.\n"
    "    * If you only hear sequential counting like '1, 2, 3, 4, 5, 6, 7, 8, 9, 10' on its own (without 'of this' or a food word), it's exercise reps — DO NOT use as quantity. Default to quantity=1.\n"
    "    * The same food/drink shown in multiple frames is ONE physical item — count it once, not per frame, unless quantity was explicitly stated.\n"
    "- Preserve names exactly. Korean stays Korean. English stays English. Do NOT translate.\n"
    "- For BRANDED items: use the brand name only if the wrapper/label text is clearly readable. If the brand is unclear, use the generic food type instead (e.g. 'chips', 'chocolate bar', 'cracker').\n"
    "- SNACK TYPES: be specific — 'chips' not 'snack', 'cookies' not 'snack', 'chocolate bar' not 'candy'. If you can see the snack type clearly, name it. Only use 'snack' when the item is truly unidentifiable.\n"
    "- If a drink container is visible but contents are unnamed, use 'beverage' as the name.\n"
    "- EXERCISE — two independent sources, report BOTH if present:\n"
    "  1. Transcript exercise: if the transcript mentions duration (e.g. '47 minutes'), record that.\n"
    "  2. Visual exercise: if ANY frame shows physical activity (squat, push-up, stretch, jump, any deliberate body movement), add it as a SEPARATE exercise entry with minutes=1 if no duration is visible.\n"
    "  DO NOT skip visual exercise just because the transcript already has exercise.\n"
    "- SHORT CLIPS: even a single frame showing someone holding food, or doing one rep of exercise, is a valid event. Extract it.\n"
    "- Only invent nothing — if you see it or hear it, extract it; if you don't, omit it."
)


def _sample_frames(video_path: Path, num_frames: int = GEMMA_FRAMES_PER_VIDEO):
    try:
        import av
        container = av.open(str(video_path))
        if not container.streams.video:
            container.close()
            return []
        stream = container.streams.video[0]
        total = stream.frames or 0
        if total == 0:
            container.close()
            container = av.open(str(video_path))
            total = sum(1 for _ in container.decode(video=0))
            container.close()
            container = av.open(str(video_path))
        if total == 0:
            return []
        # Front-weighted sampling: first 40% of video gets 60% of frames.
        # Users typically present items in the first few seconds; even coverage
        # misses them when 8 frames span a 30s video (one frame every 3.75s).
        front_count = int(num_frames * 0.6)
        back_count = num_frames - front_count
        front_end = int(total * 0.4)
        front_pts = [int(i * front_end / front_count) for i in range(front_count)]
        back_pts = [front_end + int(i * (total - front_end) / back_count) for i in range(back_count)]
        targets = sorted(set(front_pts + back_pts))
        frames = []
        for i, frame in enumerate(container.decode(video=0)):
            if i in targets:
                frames.append(frame.to_image())
                if len(frames) >= num_frames:
                    break
        container.close()
        return frames
    except Exception as e:
        log.warning("frame sampling failed for %s: %s", video_path, e)
        return []


def _img_to_data_url(img, max_edge: int = 1024) -> str:
    # Downscale before encoding. Gemma 4's vision encoder operates at ~896px
    # internally, so anything larger is wasted bytes — and a Mac-mini-hosted
    # llama.cpp server 500s on 8 full-res iPhone frames (multimodal OOM /
    # context overflow). NIM servers auto-resize so it didn't show up there.
    if max(img.size) > max_edge:
        img = img.copy()
        img.thumbnail((max_edge, max_edge))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"


_GEMMA_SYSTEM_INSTRUCTION = (
    "You are a strict JSON extraction tool. You ALWAYS respond with a single "
    "valid JSON object matching the schema provided in the user message. "
    "Output JSON ONLY — no prose, no markdown fences, no explanation. "
    "If you cannot identify items, return empty arrays. Never invent items."
)


def _post_to_gemma(content_blocks: list, max_tokens: int = 384) -> Tuple[Optional[dict], int, Optional[str]]:
    # Split the schema/rules into a system message so the user message can
    # focus on the actual query (images + the task). This separation reduces
    # the small model's tendency to continue example JSON instead of
    # producing fresh output.
    body = {
        "model": "gemma-4-E4B-it",
        "messages": [
            {"role": "system", "content": _GEMMA_SYSTEM_INSTRUCTION},
            {"role": "user", "content": content_blocks},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=GEMMA_TIMEOUT_SEC) as client:
            resp = client.post(f"{GEMMA_BASE_URL}/v1/chat/completions", json=body)
            resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        parsed = json.loads(text)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return parsed, elapsed_ms, None
    except httpx.HTTPError as e:
        return None, int((time.perf_counter() - t0) * 1000), f"http: {type(e).__name__}: {str(e)[:200]}"
    except json.JSONDecodeError as e:
        return None, int((time.perf_counter() - t0) * 1000), f"json_parse: {str(e)[:200]}"
    except Exception as e:
        return None, int((time.perf_counter() - t0) * 1000), f"other: {type(e).__name__}: {str(e)[:200]}"


def gemma_extract_text(transcript: str) -> Tuple[Optional[dict], int, Optional[str]]:
    if not transcript:
        return None, 0, "empty_transcript"
    prompt = PROMPT_TEMPLATE.format(
        frame_intro="",
        transcript_block=f'Spoken transcript: "{transcript}"\n\n',
    )
    return _post_to_gemma([{"type": "text", "text": prompt}])


def gemma_extract_multimodal(video_path: Path, transcript: str = "") -> Tuple[Optional[dict], int, Optional[str]]:
    if not video_path or not Path(video_path).exists():
        return None, 0, "no_video"
    frames = _sample_frames(Path(video_path))
    if not frames:
        return None, 0, "no_frames"
    content = [{"type": "image_url", "image_url": {"url": _img_to_data_url(img)}} for img in frames]
    transcript_block = f'Spoken transcript: "{transcript}"\n\n' if transcript else ""
    prompt = PROMPT_TEMPLATE.format(
        frame_intro="These 6 frames are sampled across a short video (front-weighted: more frames in the first 40% where items are typically introduced). ",
        transcript_block=transcript_block,
    )
    content.append({"type": "text", "text": prompt})
    return _post_to_gemma(content, max_tokens=512)


PHOTO_PROMPT = (
    "/no_think\n"
    "This is a single photo from AI glasses. Identify every food, drink, exercise, "
    "or medication visible. Output ONLY valid JSON.\n\n"
    "Schema: {\"foods\": [{\"name\": \"string\", \"quantity\": int, "
    "\"kcal\": int, \"protein_g\": int, \"fat_g\": int, \"carb_g\": int, "
    "\"portion_g\": int}], "
    "\"exercise\": {\"minutes\": int} or null, "
    "\"medications\": [{\"drug_name\": \"string\"}]}\n\n"
    "Rules:\n"
    "- Identify each DISTINCT food/drink as a SEPARATE object.\n"
    "- Use Korean food names when the dish is clearly Korean (e.g. '고등어구이' "
    "for grilled mackerel, '김치' for kimchi, '두부' for tofu, '된장찌개' for "
    "doenjang stew). Use English for non-Korean items.\n"
    "- Estimate realistic kcal/protein/fat/carb per typical serving:\n"
    "    grilled fish ~250 kcal (35g protein, 12g fat, 0g carb)\n"
    "    cooked rice ~300 kcal (6g protein, 1g fat, 65g carb)\n"
    "    tofu ~80 kcal (8g protein, 5g fat, 2g carb)\n"
    "    kimchi/banchan ~30 kcal (1g protein, 1g fat, 5g carb)\n"
    "    stir-fried vegetables ~100 kcal (3g protein, 5g fat, 12g carb)\n"
    "    soup (broth+veg) ~80 kcal (4g protein, 3g fat, 8g carb)\n"
    "    chicken/meat piece ~200 kcal (20g protein, 12g fat, 2g carb)\n"
    "  Adjust if portion looks larger/smaller than typical.\n"
    "- portion_g = estimated grams on the plate (default ~150 if unsure).\n"
    "- If unsure of identity, OMIT rather than guess.\n"
    "- Computers, phones, keyboards, desks, hands are NOT food. Ignore them.\n"
    "Output ONLY the JSON object."
)


def gemma_extract_image(image_path: Path) -> Tuple[Optional[dict], int, Optional[str]]:
    """Single-photo arm: Gemma multimodal on one still image (HEIC/JPG/PNG).
    Uses a richer prompt than video frames so kcal/macros get estimated too."""
    if not image_path or not Path(image_path).exists():
        return None, 0, "no_image"
    try:
        from PIL import Image as _PIL
        img = _PIL.open(image_path).convert("RGB")
    except Exception as e:
        return None, 0, f"image_load: {type(e).__name__}: {str(e)[:120]}"
    content = [
        {"type": "image_url", "image_url": {"url": _img_to_data_url(img)}},
        {"type": "text", "text": PHOTO_PROMPT},
    ]
    return _post_to_gemma(content, max_tokens=1024)


_ARBITRATE_PROMPT_TEMPLATE = (
    "/no_think\n"
    "Look at the food/drink in this photo. From the candidate names below, "
    "pick the ONE that best identifies the item.\n\n"
    "Candidates:\n"
    "{candidates_block}"
    "\n"
    "Rules:\n"
    "- Pick the most specific brand/product name if multiple candidates "
    "refer to the same item (e.g. '스퀴즈 오렌지 에이드' beats 'Orangeade').\n"
    "- Prefer Korean names for Korean products (matching label text).\n"
    "- Output ONLY a JSON object: "
    '{{"chosen_index": <int 1-{n} or null>, "reason": "<short reason>"}}\n'
    "- chosen_index = null ONLY if every candidate is clearly wrong for "
    "what the photo actually shows.\n"
    "- Do NOT invent new names. Pick from the list, or null."
)


def gemma_arbitrate_image_candidates(
    image_path: Path,
    candidates: list,
) -> Tuple[Optional[str], int, Optional[str]]:
    """Ask Gemma 4 E4B vision to pick the best food/drink name from a small
    list of candidates produced by upstream models (CNN, Gemma extract,
    Nemotron). Returns (chosen_name_or_None, elapsed_ms, error_str_or_None).

    Designed to be called rarely — only on tiebreak in _run_photo_multimodal.
    """
    if not candidates:
        return None, 0, "no_candidates"
    if len(candidates) == 1:
        return candidates[0], 0, None
    if not image_path or not Path(image_path).exists():
        return None, 0, "no_image"
    try:
        from PIL import Image as _PIL
        img = _PIL.open(image_path).convert("RGB")
    except Exception as e:
        return None, 0, f"image_load: {type(e).__name__}: {str(e)[:120]}"

    block = "".join(f"  {i+1}. {c}\n" for i, c in enumerate(candidates))
    prompt = _ARBITRATE_PROMPT_TEMPLATE.format(candidates_block=block, n=len(candidates))
    content = [
        {"type": "image_url", "image_url": {"url": _img_to_data_url(img)}},
        {"type": "text", "text": prompt},
    ]
    parsed, ms, err = _post_to_gemma(content, max_tokens=128)
    if err or not isinstance(parsed, dict):
        return None, ms, err or "non_dict_response"
    idx = parsed.get("chosen_index")
    if idx is None:
        return None, ms, "model_chose_none"
    try:
        idx_int = int(idx)
    except (TypeError, ValueError):
        return None, ms, f"non_int_index: {idx!r}"
    if 1 <= idx_int <= len(candidates):
        return candidates[idx_int - 1], ms, None
    return None, ms, f"index_out_of_range: {idx_int}"


def log_dual_extraction(
    *,
    event_id: str,
    video_path: Optional[Path],
    transcript: Optional[str],
    today_result: Optional[dict],
    gemma_text_result: Optional[dict],
    gemma_text_ms: int,
    gemma_text_error: Optional[str],
    gemma_mm_result: Optional[dict],
    gemma_mm_ms: int,
    gemma_mm_error: Optional[str],
    nemotron_text_result: Optional[dict] = None,
    nemotron_text_ms: int = 0,
    nemotron_text_error: Optional[str] = None,
    nemotron_mm_result: Optional[dict] = None,
    nemotron_mm_ms: int = 0,
    nemotron_mm_error: Optional[str] = None,
    nemotron_native_audio_result: Optional[dict] = None,
    nemotron_native_audio_ms: int = 0,
    nemotron_native_audio_error: Optional[str] = None,
    nemotron_native_video_result: Optional[dict] = None,
    nemotron_native_video_ms: int = 0,
    nemotron_native_video_error: Optional[str] = None,
) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    today_kst = datetime.now(KST).date().isoformat()
    log_path = LOG_DIR / f"dual_extraction_{today_kst}.jsonl"

    size_mb = None
    if video_path:
        try:
            size_mb = round(Path(video_path).stat().st_size / 1e6, 2)
        except Exception:
            size_mb = None

    record = {
        "event_id": event_id,
        "ts_kst": datetime.now(KST).isoformat(),
        "data_path": "PC_to_PC_LAN_benchmark_only",
        "video_path": str(video_path) if video_path else None,
        "video_size_mb": size_mb,
        "transcript": transcript,
        "arm_today": today_result,
        "arm_gemma_text": {
            "result": gemma_text_result,
            "elapsed_ms": gemma_text_ms,
            "error": gemma_text_error,
        },
        "arm_gemma_multimodal": {
            "result": gemma_mm_result,
            "elapsed_ms": gemma_mm_ms,
            "error": gemma_mm_error,
        },
        "arm_nemotron_text": {
            "result": nemotron_text_result,
            "elapsed_ms": nemotron_text_ms,
            "error": nemotron_text_error,
        },
        "arm_nemotron_multimodal": {
            "result": nemotron_mm_result,
            "elapsed_ms": nemotron_mm_ms,
            "error": nemotron_mm_error,
        },
        "arm_nemotron_native_audio": {
            "result": nemotron_native_audio_result,
            "elapsed_ms": nemotron_native_audio_ms,
            "error": nemotron_native_audio_error,
        },
        "arm_nemotron_native_video": {
            "result": nemotron_native_video_result,
            "elapsed_ms": nemotron_native_video_ms,
            "error": nemotron_native_video_error,
        },
    }
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        log.warning("failed to append dual-extraction log: %s", e)


def _format_arm_one_line(label: str, result: Optional[dict], elapsed_ms: int, error: Optional[str]) -> str:
    """One short readable line summarizing an arm result for terminal display."""
    if error:
        snippet = error[:70].replace("\n", " ")
        return f"      {label:<20s} ERROR: {snippet}"
    if result is None:
        return f"      {label:<20s} (no result)"
    if not isinstance(result, dict):
        return f"      {label:<20s} ERROR: unexpected type {type(result).__name__}: {str(result)[:60]}"
    foods = result.get("foods") or []
    if foods:
        food_strs = []
        for f in foods:
            if isinstance(f, dict):
                name = f.get("name", "?")
                qty = f.get("quantity", 1)
                food_strs.append(f"{name} x{qty}" if qty != 1 else name)
            else:
                food_strs.append(str(f))
        food_str = ", ".join(food_strs)
    else:
        food_str = "(no foods)"
    ex = result.get("exercise")
    if isinstance(ex, dict):
        ex_str = f"exercise {ex.get('minutes')}min"
    elif isinstance(ex, (int, float)):
        ex_str = f"exercise {ex}min"
    else:
        ex_str = "no exercise"
    meds = result.get("medications") or []
    med_str = ""
    if meds:
        med_str = " | meds: " + ", ".join(
            (m.get("drug_name", "?") if isinstance(m, dict) else str(m))
            for m in meds
        )
    return f"      {label:<20s} ({elapsed_ms/1000:.1f}s) {food_str} | {ex_str}{med_str}"


def _print_comparison_summary(
    today_extraction: Optional[dict],
    transcript: Optional[str],
    text_result: Optional[dict],
    text_ms: int,
    text_err: Optional[str],
    mm_result: Optional[dict],
    mm_ms: int,
    mm_err: Optional[str],
    nem_text_result: Optional[dict] = None,
    nem_text_ms: int = 0,
    nem_text_err: Optional[str] = None,
    nem_mm_result: Optional[dict] = None,
    nem_mm_ms: int = 0,
    nem_mm_err: Optional[str] = None,
    nem_na_result: Optional[dict] = None,
    nem_na_ms: int = 0,
    nem_na_err: Optional[str] = None,
    nem_nv_result: Optional[dict] = None,
    nem_nv_ms: int = 0,
    nem_nv_err: Optional[str] = None,
) -> None:
    """Print a short, readable 7-arm comparison block to stdout."""
    print("    --- Phase 2 Comparison (7 arms) ---")
    if transcript:
        snip = transcript[:90] + ("..." if len(transcript) > 90 else "")
        print(f"      transcript: {snip}")

    if today_extraction and not today_extraction.get("_smoke_test"):
        visual = today_extraction.get("best_visual_description", "(no visual)")
        audio = today_extraction.get("audio_summary") or {}
        audio_flags = [k for k, v in audio.items() if v]
        audio_str = "audio: " + (", ".join(audio_flags) if audio_flags else "nothing")
        print(f"      {'today':<24s}     {visual} | {audio_str}")
    elif today_extraction and today_extraction.get("_smoke_test"):
        print(f"      {'today':<24s}     (smoke test placeholder)")

    print(_format_arm_one_line("gemma text-only",       text_result,     text_ms,     text_err))
    print(_format_arm_one_line("gemma multimodal",      mm_result,       mm_ms,       mm_err))
    print(_format_arm_one_line("nemotron text-only",    nem_text_result, nem_text_ms, nem_text_err))
    print(_format_arm_one_line("nemotron multimodal",   nem_mm_result,   nem_mm_ms,   nem_mm_err))
    print(_format_arm_one_line("nemotron NATIVE audio", nem_na_result,   nem_na_ms,   nem_na_err))
    print(_format_arm_one_line("nemotron NATIVE video", nem_nv_result,   nem_nv_ms,   nem_nv_err))
    print("    ------------------------------------")


def process_event_for_dual_log(
    *,
    event_id: str,
    video_path: Optional[Path],
    transcript: Optional[str],
    today_extraction: Optional[dict],
    audio_path: Optional[Path] = None,
) -> Optional[dict]:
    """Single entry point called from watcher.py.

    Catches all exceptions internally — guaranteed not to raise into caller.
    Returns dict with keys 'gemma_mm' and 'nemotron_mm' (each a dict or None)
    so watcher.py can supplement Supabase with visual detections that the
    production text-only arm missed.

    audio_path is optional — when supplied, enables Nemotron native-audio arm
    (raw WAV → Parakeet encoder, no Whisper). Pass the same WAV the watcher
    extracted for Whisper.
    """
    try:
        # ── Arms 2 & 3: Gemma ──
        if transcript:
            text_result, text_ms, text_err = gemma_extract_text(transcript)
        else:
            text_result, text_ms, text_err = None, 0, "no_transcript"

        if video_path:
            mm_result, mm_ms, mm_err = gemma_extract_multimodal(video_path, transcript or "")
        else:
            mm_result, mm_ms, mm_err = None, 0, "no_video"

        # ── Arms 4 & 5: Nemotron text + multimodal ──
        nem_text_result, nem_text_ms, nem_text_err = None, 0, "nemotron_unavailable"
        nem_mm_result,   nem_mm_ms,   nem_mm_err   = None, 0, "nemotron_unavailable"
        # ── Arms 6 & 7: Nemotron NATIVE audio + NATIVE video (new) ──
        nem_na_result,   nem_na_ms,   nem_na_err   = None, 0, "nemotron_unavailable"
        nem_nv_result,   nem_nv_ms,   nem_nv_err   = None, 0, "nemotron_unavailable"

        if _NEMOTRON_AVAILABLE:
            try:
                if transcript:
                    nem_text_result, nem_text_ms, nem_text_err = nemotron_extract_text(transcript)
                else:
                    nem_text_result, nem_text_ms, nem_text_err = None, 0, "no_transcript"
            except Exception as e:
                nem_text_err = f"exception: {e}"

            try:
                if video_path:
                    nem_mm_result, nem_mm_ms, nem_mm_err = nemotron_extract_multimodal(video_path, transcript or "")
                else:
                    nem_mm_result, nem_mm_ms, nem_mm_err = None, 0, "no_video"
            except Exception as e:
                nem_mm_err = f"exception: {e}"

            # Native audio — bypasses Whisper entirely. Sends raw WAV to Nemotron's Parakeet encoder.
            try:
                from nemotron_extractor import nemotron_extract_native_audio
                if audio_path and Path(audio_path).exists():
                    nem_na_result, nem_na_ms, nem_na_err = nemotron_extract_native_audio(audio_path)
                else:
                    nem_na_result, nem_na_ms, nem_na_err = None, 0, "no_audio_path"
            except Exception as e:
                nem_na_err = f"exception: {e}"

            # Native video — bypasses frame sampling. Sends raw MP4 to Nemotron's 3D-conv video encoder.
            try:
                from nemotron_extractor import nemotron_extract_native_video
                if video_path:
                    nem_nv_result, nem_nv_ms, nem_nv_err = nemotron_extract_native_video(video_path)
                else:
                    nem_nv_result, nem_nv_ms, nem_nv_err = None, 0, "no_video"
            except Exception as e:
                nem_nv_err = f"exception: {e}"

        log_dual_extraction(
            event_id=event_id,
            video_path=video_path,
            transcript=transcript,
            today_result=today_extraction,
            gemma_text_result=text_result,
            gemma_text_ms=text_ms,
            gemma_text_error=text_err,
            gemma_mm_result=mm_result,
            gemma_mm_ms=mm_ms,
            gemma_mm_error=mm_err,
            nemotron_text_result=nem_text_result,
            nemotron_text_ms=nem_text_ms,
            nemotron_text_error=nem_text_err,
            nemotron_mm_result=nem_mm_result,
            nemotron_mm_ms=nem_mm_ms,
            nemotron_mm_error=nem_mm_err,
            nemotron_native_audio_result=nem_na_result,
            nemotron_native_audio_ms=nem_na_ms,
            nemotron_native_audio_error=nem_na_err,
            nemotron_native_video_result=nem_nv_result,
            nemotron_native_video_ms=nem_nv_ms,
            nemotron_native_video_error=nem_nv_err,
        )

        # Pretty-print summary so the watcher terminal shows the comparison
        # immediately without needing to `type` the JSONL file separately.
        try:
            _print_comparison_summary(
                today_extraction=today_extraction,
                transcript=transcript,
                text_result=text_result,
                text_ms=text_ms,
                text_err=text_err,
                mm_result=mm_result,
                mm_ms=mm_ms,
                mm_err=mm_err,
                nem_text_result=nem_text_result,
                nem_text_ms=nem_text_ms,
                nem_text_err=nem_text_err,
                nem_mm_result=nem_mm_result,
                nem_mm_ms=nem_mm_ms,
                nem_mm_err=nem_mm_err,
                nem_na_result=nem_na_result,
                nem_na_ms=nem_na_ms,
                nem_na_err=nem_na_err,
                nem_nv_result=nem_nv_result,
                nem_nv_ms=nem_nv_ms,
                nem_nv_err=nem_nv_err,
            )
        except Exception as e:
            log.warning("comparison summary print failed: %s", e)

        # Return all multimodal arms back to watcher so it can supplement
        # Supabase with specific items detected that the text-only production
        # arm missed (orange juice held up to the camera, chips, etc.).
        return {
            "gemma_mm":              mm_result if isinstance(mm_result, dict) else None,
            "nemotron_mm":           nem_mm_result if isinstance(nem_mm_result, dict) else None,
            "nemotron_native_audio": nem_na_result if isinstance(nem_na_result, dict) else None,
            "nemotron_native_video": nem_nv_result if isinstance(nem_nv_result, dict) else None,
        }

    except Exception as e:
        log.warning("process_event_for_dual_log outer catch: %s", e)
        return None


if __name__ == "__main__":
    # Quick standalone smoke test — run this to verify the Mac mini server is reachable
    # and the module works end-to-end before hooking into watcher.py.
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if len(sys.argv) < 2:
        print("Usage: python gemma_dual_extractor.py <path_to_test_mp4>")
        sys.exit(1)

    test_video = Path(sys.argv[1])
    if not test_video.exists():
        print(f"Video not found: {test_video}")
        sys.exit(1)

    print(f"Smoke test on: {test_video}")
    print(f"Server: {GEMMA_BASE_URL}")
    print()

    process_event_for_dual_log(
        event_id="smoketest_local",
        video_path=test_video,
        transcript="Right now I ate three of these. It is delicious. This is what I drink right now. And today in the morning I had 42 minutes of exercise.",
        today_extraction={"_smoke_test": True, "note": "no real today-pipeline output for standalone test"},
    )

    today_kst = datetime.now(KST).date().isoformat()
    log_path = LOG_DIR / f"dual_extraction_{today_kst}.jsonl"
    print(f"\nLog written to: {log_path}")
    if log_path.exists():
        last_line = log_path.read_text(encoding="utf-8").strip().split("\n")[-1]
        print("\nLast log entry:")
        print(json.dumps(json.loads(last_line), indent=2, ensure_ascii=False))
