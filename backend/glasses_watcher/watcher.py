"""
AI Glasses Data Collection Pipeline - Smart Health Event Watcher
Watches a folder for new photos/videos/audio from AIMB-G1 AI glasses.
Transforms raw detections into MEANINGFUL health events before uploading to Supabase.

Output format (smart health events, not raw YOLO):
  "At 12:30pm, user ate a meal (bowl+spoon detected, confidence 84%)"
  "At 3:15pm, user drank from cup (estimated 250ml)"
  "At 5:00pm, user voice report: feeling tired today"

Usage:
  cd C:\\Users\\tripleh\\projects\\healthcare-ai-agent
  C:\\Users\\tripleh\\AppData\\Local\\Python\\pythoncore-3.11-64\\python.exe backend/glasses_watcher/watcher.py
"""

import io
import json
import os
import re
import sys
import time
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

# Force flush on every print
import builtins
_original_print = builtins.print
def print(*args, **kwargs):
    kwargs.setdefault("flush", True)
    _original_print(*args, **kwargs)

import httpx
import numpy as np
from PIL import Image, ExifTags
import cv2

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_SUPPORT = True
except ImportError:
    HEIC_SUPPORT = False

# Phase 2 — Gemma 4 dual-extraction logger (additive; never breaks the watcher).
# If import fails for any reason (missing av, network module, etc.), watcher
# proceeds normally and skips the comparison logging.
try:
    import sys as _phase2_sys
    _phase2_sys.path.insert(0, str(Path(__file__).parent))
    from gemma_dual_extractor import process_event_for_dual_log as _gemma_dual_log
    _PHASE2_ENABLED = True
except Exception as _phase2_err:
    _gemma_dual_log = None
    _PHASE2_ENABLED = False
    print(f"  [phase2] dual-extraction disabled: {_phase2_err}")

# Production-write gate for Nemotron multimodal output. Per user decision
# (May 8): Nemotron 30B is noisy in production — repeats names as quantity,
# returns partial Korean transliterations ("스퀴즈 오렌지" missing "에이드"),
# hallucinates exercise minutes from non-exercise scenes. Drop it from
# Supabase writes; keep it in the comparison JSONL for benchmarking. To
# re-enable later, flip this to True (or read from env var).
NEMOTRON_WRITES_ENABLED = False

# Tier 0/1 CNN cascade — Korean food (88.41% TTA) + Food-101 (88.15% TTA).
# Runs BEFORE the Phase 2 multimodal supplements so confident CNN hits land
# in user_food_log without an LLM call. Both ONNX models are CPU-only and
# load lazily on first inference (~200 ms cold + ~100 ms/image steady).
try:
    sys.path.insert(0, str(Path(__file__).parent))
    import food_cnn_cascade as _food_cnn
    _CNN_ENABLED = _food_cnn.is_available()
    if not _CNN_ENABLED:
        print(f"  [cnn-cascade] disabled: {_food_cnn.load_failure_reason()}")
except Exception as _cnn_err:
    _food_cnn = None
    _CNN_ENABLED = False
    print(f"  [cnn-cascade] import failed: {_cnn_err}")

# ── Configuration ──
PROJECT_ROOT = Path(__file__).parent.parent.parent
KST = timezone(timedelta(hours=9))

def _camera_roll_folders() -> list:
    """Return Camera Roll root + current month subfolder.

    OneDrive puts new videos in Camera Roll/YYYY/MM/. Only watch the current
    month. Also add previous month only if today is day 1-3 (videos recorded
    in the last 2-3 days of last month may still be syncing).
    """
    base = Path.home() / "OneDrive" / "Pictures" / "Camera Roll"
    folders = [base]
    now = datetime.now()
    candidates = [(now.year, now.month)]
    if now.day <= 3:
        prev = (now.year - 1, 12) if now.month == 1 else (now.year, now.month - 1)
        candidates.append(prev)
    for year, month in candidates:
        sub = base / str(year) / f"{month:02d}"
        if sub.exists():
            folders.append(sub)
    return folders

WATCH_FOLDERS = (
    _camera_roll_folders()
    + [
        Path.home() / "OneDrive" / "Pictures",
        PROJECT_ROOT / "backend" / "glasses_watcher" / "inbox",
        # AIMB-Bridge phone-side sync folder (Syncthing target).
        # Clips arrive here as YYYYMMDDhhmmssXXX.mp4 — the rename helper
        # at humanize_aimb_filename converts them to YYYY-MM-DD_HH-MM-SS.mp4
        # before processing.
        Path.home() / "AIMB-Bridge",
    ]
)

# Supabase
SUPABASE_URL = ""
SUPABASE_KEY = ""
env_path = PROJECT_ROOT / "backend" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("SUPABASE_URL="):
            SUPABASE_URL = line.split("=", 1)[1].strip()
        elif line.startswith("SUPABASE_SERVICE_ROLE_KEY="):
            SUPABASE_KEY = line.split("=", 1)[1].strip()

# Mac mini Tailscale IP — whisper.cpp large-v3 server (port 8082, separate from Gemma 8081)
WHISPER_REMOTE_URL = "http://100.69.125.64:8082/inference"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv"}
AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".aac", ".ogg"}
TEST_USER_ID = 1

# Mtime window for picking up recent files. Filename parsing is unreliable
# because iOS names photos with UTC capture time — a shot taken at 08:00 KST
# becomes YYYYMMDD_23XXXX_iOS.* with YESTERDAY's UTC date in the name.
RECENT_FILE_LOOKBACK_SECONDS = 48 * 3600

PROCESSED_FILE = PROJECT_ROOT / "backend" / "glasses_watcher" / "processed.json"

# ── Health Event Inference Rules ──
# YOLOv8 detects objects → we infer health-meaningful activities

DRINK_OBJECTS = {"bottle", "cup", "wine glass"}
EAT_OBJECTS = {"bowl", "fork", "knife", "spoon", "sandwich", "pizza", "cake",
               "apple", "banana", "orange", "donut", "hot dog", "broccoli", "carrot"}
EXERCISE_OBJECTS = {"sports ball", "tennis racket", "skateboard", "surfboard",
                    "frisbee", "skis", "snowboard", "bicycle"}

# Health-related keywords (Korean + English). Used to gate the CNN cascade
# + Phase 2 multimodal supplement: when YOLO sees nothing health-related
# AND the audio transcript has no health keywords, the photo/video is
# treated as NON-HEALTH and food/exercise extraction is skipped. Without
# this gate the multimodal models would hallucinate food/exercise from
# random scenes (e.g. tech expo footage → "orange bag" → 도토리묵 false
# positives, or "exercise 1min" rows from speeches).
_HEALTH_KEYWORDS = (
    # Korean
    "먹", "마시", "음식", "음료", "식사", "밥", "운동", "약", "수면",
    "잠", "비타민", "체중", "몸무게", "혈압", "혈당",
    # English
    "eat", "ate", "food", "drink", "drank", "lunch", "dinner",
    "breakfast", "snack", "meal", "exercise", "walk", "run",
    "gym", "workout", "medicine", "pill", "vitamin", "supplement",
    "sleep", "slept", "woke", "weight", "kg", "water", "coffee",
    "tea", "juice", "calorie", "kcal", "protein",
)


def _has_health_keyword(text: Optional[str]) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(kw in t for kw in _HEALTH_KEYWORDS)

DRINK_ESTIMATES = {
    "bottle": {"name": "bottle", "ml": 500, "description": "drank from bottle"},
    "cup": {"name": "cup", "ml": 250, "description": "drank from cup"},
    "wine glass": {"name": "glass", "ml": 150, "description": "drank from glass"},
}

MEAL_INDICATORS = {
    "bowl": "eating from bowl (soup/rice/noodles likely)",
    "fork": "eating with fork",
    "knife": "cutting food",
    "spoon": "eating with spoon (soup/stew likely)",
    "sandwich": "eating sandwich",
    "pizza": "eating pizza",
    "cake": "eating cake/dessert",
    "apple": "eating apple",
    "banana": "eating banana",
    "orange": "eating orange",
}

# Whisper prompts — language-matched to reduce hallucination.
# Korean prompt used when audio is detected as Korean or Korean-accent mixed speech.
_WHISPER_PROMPT_KO = (
    "건강 기록 음성입니다. 한국어와 영어를 섞어서 말합니다. "
    "들리는 그대로 정확히 받아쓰세요. 영어 단어와 브랜드명은 영어로 유지하세요. "
    "예시: 고등어구이, 김치찌개, 비빔밥, 삼겹살, Snickers, Vitamin D."
)
_WHISPER_PROMPT_EN = (
    "Health log audio. English speech with some Korean food names. "
    "Transcribe exactly as spoken. "
    "Korean food names: 고등어구이, 김치찌개, 비빔밥, 삼겹살."
)

# Known Korean-mode hallucination phrases.
# When Whisper is locked to Korean but encounters English speech it can't
# decode, it outputs these instead of the actual words.
_KO_HALLUCINATION_PHRASES = [
    "영어 단어",   # "English word" — Whisper's Korean-mode response to English phonemes
    "자막 제공",   # "Subtitles provided" — common Korean broadcast hallucination
    "번역",        # "Translation" — another loop filler Whisper uses
]


class SmartGlassesWatcher:

    def __init__(self):
        self.processed = self._load_processed()
        self.yolo = None
        self._size_history: dict[Path, tuple[int, float]] = {}

    def _load_processed(self) -> set:
        if PROCESSED_FILE.exists():
            return set(json.loads(PROCESSED_FILE.read_text()).get("files", []))
        return set()

    def _save_processed(self):
        PROCESSED_FILE.parent.mkdir(parents=True, exist_ok=True)
        PROCESSED_FILE.write_text(json.dumps({"files": list(self.processed)}))

    def _file_hash(self, path: Path) -> str:
        return hashlib.md5(f"{path.name}_{path.stat().st_size}_{path.stat().st_mtime}".encode()).hexdigest()

    def _get_yolo(self):
        if self.yolo is None:
            from ultralytics import YOLO
            print("  Loading YOLOv8n...")
            self.yolo = YOLO("yolov8n.pt")
            print("  YOLOv8n ready")
        return self.yolo

    # ── EXIF ──

    def extract_exif(self, image_path: Path) -> dict:
        try:
            img = Image.open(image_path)
            exif = img._getexif() or {}
            result = {"width": img.width, "height": img.height}
            for tag_id, value in exif.items():
                tag = ExifTags.TAGS.get(tag_id, "")
                if tag == "DateTimeOriginal":
                    result["taken_at"] = str(value)
                elif tag == "GPSInfo":
                    try:
                        gps = {ExifTags.GPSTAGS.get(k, ""): v for k, v in value.items()}
                        if "GPSLatitude" in gps and "GPSLongitude" in gps:
                            lat = sum(float(x) / 60**i for i, x in enumerate(gps["GPSLatitude"]))
                            lng = sum(float(x) / 60**i for i, x in enumerate(gps["GPSLongitude"]))
                            if gps.get("GPSLatitudeRef") == "S": lat = -lat
                            if gps.get("GPSLongitudeRef") == "W": lng = -lng
                            result["location"] = {"lat": round(lat, 6), "lng": round(lng, 6)}
                    except Exception:
                        pass
            return result
        except Exception:
            return {}

    # ── Smart Health Event from YOLO ──

    def detect_and_interpret(self, image_path: Path) -> dict:
        """Run YOLOv8 and convert to health-meaningful event."""
        yolo = self._get_yolo()
        results = yolo(str(image_path), verbose=False, conf=0.3)

        objects = []
        for r in results:
            for box in r.boxes:
                objects.append({
                    "name": yolo.names[int(box.cls[0])],
                    "confidence": round(float(box.conf[0]), 3),
                })

        # ── Infer health event ──
        detected_names = {o["name"] for o in objects}
        drink_items = detected_names & DRINK_OBJECTS
        eat_items = detected_names & EAT_OBJECTS
        exercise_items = detected_names & EXERCISE_OBJECTS

        now = datetime.now(KST)
        time_str = now.strftime("%I:%M %p")
        hour = now.hour

        # Determine meal type by time
        if 6 <= hour < 10:
            meal_type = "breakfast"
        elif 11 <= hour < 14:
            meal_type = "lunch"
        elif 17 <= hour < 21:
            meal_type = "dinner"
        else:
            meal_type = "snack"

        if drink_items:
            item = list(drink_items)[0]
            est = DRINK_ESTIMATES.get(item, {"ml": 250, "description": "drank"})
            best_conf = max(o["confidence"] for o in objects if o["name"] == item)
            return {
                "event_type": "drink",
                "description": f"At {time_str}, user {est['description']} (estimated {est['ml']}ml)",
                "health_data": {
                    "hydration_ml": est["ml"],
                    "container": item,
                    "time": now.isoformat(),
                },
                "confidence": best_conf,
                "objects_detected": [o["name"] for o in objects],
            }

        elif eat_items:
            indicators = [MEAL_INDICATORS[i] for i in eat_items if i in MEAL_INDICATORS]
            best_conf = max(o["confidence"] for o in objects if o["name"] in eat_items)
            return {
                "event_type": "meal",
                "description": f"At {time_str}, user eating {meal_type} ({', '.join(indicators[:2])})",
                "health_data": {
                    "meal_type": meal_type,
                    "indicators": indicators,
                    "time": now.isoformat(),
                },
                "confidence": best_conf,
                "objects_detected": [o["name"] for o in objects],
            }

        elif exercise_items:
            item = list(exercise_items)[0]
            best_conf = max(o["confidence"] for o in objects if o["name"] in exercise_items)
            return {
                "event_type": "exercise",
                "description": f"At {time_str}, user exercising ({item} detected)",
                "health_data": {
                    "equipment": item,
                    "time": now.isoformat(),
                },
                "confidence": best_conf,
                "objects_detected": [o["name"] for o in objects],
            }

        else:
            return {
                "event_type": "photo_capture",
                "description": f"At {time_str}, photo captured (no health activity detected)",
                "health_data": {
                    "time": now.isoformat(),
                    "objects": [o["name"] for o in objects[:5]],
                },
                "confidence": max((o["confidence"] for o in objects), default=0),
                "objects_detected": [o["name"] for o in objects],
            }

    # ── Supabase Upload ──

    def upload_event(self, event: dict, source_file: str) -> int | None:
        if not SUPABASE_KEY:
            print("    No Supabase key - logged locally only")
            return None

        row = {
            "user_id": TEST_USER_ID,
            "event_type": event["event_type"],
            "source_device": "AIMB-G1_glasses",
            "confidence_score": event.get("confidence", 0),
            # Pass as dict, NOT json.dumps() — httpx JSON-encodes the outer body.
            # Double-encoding would store a JSON string in the JSONB column,
            # breaking any `structured_data -> 'description'` queries.
            "structured_data": {
                "description": event["description"],
                "health_data": event["health_data"],
                "objects_detected": event.get("objects_detected", []),
                "source_file": source_file,
            },
            "edge_model_version": "yolov8n_v1",
            "verified": False,
            "processing_status": "edge_only",
        }

        try:
            resp = httpx.post(
                f"{SUPABASE_URL}/rest/v1/user_activity_event",
                json=row,
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=representation",
                },
                timeout=15,
            )
            resp.raise_for_status()
            result = resp.json()
            eid = result[0]["event_id"] if isinstance(result, list) else result.get("event_id")
            return eid
        except Exception as e:
            print(f"    Upload failed: {e}")
            return None

    # ── Process Image ──

    def process_image(self, path: Path):
        print(f"\n  [PHOTO] {path.name}")

        exif = self.extract_exif(path)
        if exif.get("taken_at"):
            print(f"    Taken: {exif['taken_at']}")
        if exif.get("location"):
            print(f"    Location: {exif['location']}")
        print(f"    Resolution: {exif.get('width', '?')}x{exif.get('height', '?')}")

        event = self.detect_and_interpret(path)
        print(f"    >> {event['description']}")

        # Step 1: raw audit row in user_activity_event (always — independent
        # of food_log writes).
        eid = self.upload_event(event, path.name)
        if eid:
            print(f"    Supabase event_id={eid}")

        # Non-health gate: if YOLO didn't detect any food/drink/exercise
        # indicator, this photo is NOT health-related (e.g. screenshot,
        # selfie, tech expo footage). Skip CNN cascade + Phase 2 to avoid
        # the multimodal models hallucinating food from random scenes.
        # User can still override by voice-narrating ("I ate sushi") on
        # video clips — that path goes through process_video.
        if event["event_type"] not in ("drink", "meal", "exercise"):
            print(f"    [non-health-photo] YOLO event_type={event['event_type']!r} — "
                  f"skipping CNN cascade + Phase 2 multimodal (no food row will be written)")
            self._log_event(event, path.name)
            return

        # Step 2: Tier 0/1 CNN cascade — confident hits land directly in
        # user_food_log via MFDS / Food-101 nutrition lookup, no LLM call.
        # Returns dedup-name set + per-class-group counts (MAX-count rule
        # in Phase 2 below).
        cnn_written_names: set[str] = set()
        cnn_class_counts: dict = {}
        if _CNN_ENABLED:
            try:
                cnn_written_names, cnn_class_counts = self._run_photo_cnn_cascade(path)
            except Exception as e:
                print(f"    [cnn-cascade] failed (non-fatal): {e}")

        # Step 3: Phase 2 multimodal supplement — fills gaps the CNN missed.
        # Photos lack a transcript, so YOLO+Gemini-text are insufficient.
        # Cross-model dedup: per class group, MAX(CNN_count, Phase2_count)
        # determines how many rows total — Phase 2 writes only the difference.
        # Returns (wrote_any_food, wrote_specific_drink).
        phase2_wrote_food = False
        phase2_wrote_specific_drink = False
        if _PHASE2_ENABLED:
            try:
                phase2_wrote_food, phase2_wrote_specific_drink = self._run_photo_multimodal(
                    path, event,
                    cnn_written_names=cnn_written_names,
                    cnn_class_counts=cnn_class_counts,
                )
            except Exception as e:
                print(f"    [phase2-photo] failed (non-fatal): {e}")

        # Step 4: distribute generic auto-rows (drink/meal/exercise). Suppress
        # the meal placeholder when CNN/Phase 2 already wrote specific dishes;
        # suppress the drink placeholder when CNN/Phase 2 already wrote a
        # specific drink — otherwise the dashboard double-counts.
        sys.path.insert(0, str(Path(__file__).parent))
        from food_class_groups import is_drink_class as _is_drink_class
        cnn_wrote_drink = any(_is_drink_class(cid) for cid in cnn_class_counts.keys())
        specific_dishes_found = bool(cnn_written_names) or phase2_wrote_food
        specific_drink_found = cnn_wrote_drink or phase2_wrote_specific_drink
        if event["event_type"] in ("voice_report", "drink", "meal", "exercise"):
            print(f"    --- Auto-distributing to tables ---")
            self.distribute_to_tables(
                event,
                skip_meal_placeholder=specific_dishes_found,
                skip_drink_placeholder=specific_drink_found,
            )

        self._log_event(event, path.name)

    # Hardcoded kcal/macros for common dishes — used when the multimodal model
    # gives only a name. Pure lookup, no LLM. Names are matched substring-wise
    # so "grilled fish" matches "fish" entry. Add new entries as needed.
    _DISH_KCAL: dict[str, dict] = {
        # ── Korean main dishes ──
        "고등어구이":  {"kcal": 260, "protein_g": 32, "fat_g": 14, "carb_g": 0,  "serving_g": 150},
        "grilled fish": {"kcal": 250, "protein_g": 30, "fat_g": 12, "carb_g": 0,  "serving_g": 150},
        "갈치구이":   {"kcal": 240, "protein_g": 28, "fat_g": 12, "carb_g": 0,  "serving_g": 150},
        "삼겹살":    {"kcal": 500, "protein_g": 30, "fat_g": 40, "carb_g": 0,  "serving_g": 200},
        "닭갈비":    {"kcal": 400, "protein_g": 30, "fat_g": 18, "carb_g": 15, "serving_g": 200},
        "fried chicken": {"kcal": 300, "protein_g": 22, "fat_g": 18, "carb_g": 8, "serving_g": 150},
        "chicken":   {"kcal": 200, "protein_g": 22, "fat_g": 10, "carb_g": 0,  "serving_g": 100},
        # ── Rice / grains ──
        "밥":        {"kcal": 300, "protein_g": 6,  "fat_g": 1,  "carb_g": 65, "serving_g": 200},
        "rice":      {"kcal": 300, "protein_g": 6,  "fat_g": 1,  "carb_g": 65, "serving_g": 200},
        "현미밥":     {"kcal": 270, "protein_g": 7,  "fat_g": 2,  "carb_g": 56, "serving_g": 200},
        # ── Tofu ──
        "두부":      {"kcal": 80,  "protein_g": 8,  "fat_g": 5,  "carb_g": 2,  "serving_g": 100},
        "tofu":      {"kcal": 80,  "protein_g": 8,  "fat_g": 5,  "carb_g": 2,  "serving_g": 100},
        # ── Side dishes (banchan) ──
        "김치":      {"kcal": 30,  "protein_g": 1,  "fat_g": 0,  "carb_g": 5,  "serving_g": 50},
        "kimchi":    {"kcal": 30,  "protein_g": 1,  "fat_g": 0,  "carb_g": 5,  "serving_g": 50},
        "banchan":   {"kcal": 30,  "protein_g": 1,  "fat_g": 1,  "carb_g": 5,  "serving_g": 40},
        "spicy side": {"kcal": 30, "protein_g": 1,  "fat_g": 1,  "carb_g": 5,  "serving_g": 40},
        "콩나물":     {"kcal": 50,  "protein_g": 5,  "fat_g": 2,  "carb_g": 4,  "serving_g": 80},
        "bean sprouts": {"kcal": 50, "protein_g": 5, "fat_g": 2, "carb_g": 4,  "serving_g": 80},
        "나물":      {"kcal": 80,  "protein_g": 3,  "fat_g": 5,  "carb_g": 8,  "serving_g": 80},
        "stir-fried vegetables": {"kcal": 100, "protein_g": 3, "fat_g": 5, "carb_g": 12, "serving_g": 100},
        "vegetables": {"kcal": 80, "protein_g": 3,  "fat_g": 3,  "carb_g": 10, "serving_g": 100},
        # ── Soups / stews ──
        "국":        {"kcal": 80,  "protein_g": 4,  "fat_g": 3,  "carb_g": 8,  "serving_g": 250},
        "soup":      {"kcal": 80,  "protein_g": 4,  "fat_g": 3,  "carb_g": 8,  "serving_g": 250},
        "찌개":      {"kcal": 200, "protein_g": 12, "fat_g": 8,  "carb_g": 15, "serving_g": 300},
        "stew":      {"kcal": 200, "protein_g": 12, "fat_g": 8,  "carb_g": 15, "serving_g": 300},
        "doenjang":  {"kcal": 150, "protein_g": 10, "fat_g": 5,  "carb_g": 12, "serving_g": 250},
        "된장":      {"kcal": 150, "protein_g": 10, "fat_g": 5,  "carb_g": 12, "serving_g": 250},
        # ── Other ──
        "garlic":    {"kcal": 5,   "protein_g": 0,  "fat_g": 0,  "carb_g": 1,  "serving_g": 5},
        "soybean paste": {"kcal": 50, "protein_g": 4, "fat_g": 2, "carb_g": 5, "serving_g": 30},
        "fish":      {"kcal": 200, "protein_g": 25, "fat_g": 10, "carb_g": 0,  "serving_g": 120},
        # Fallback for ambiguous "fried/roasted pieces"
        "fried":     {"kcal": 250, "protein_g": 18, "fat_g": 15, "carb_g": 8,  "serving_g": 100},
        "roasted":   {"kcal": 220, "protein_g": 22, "fat_g": 12, "carb_g": 2,  "serving_g": 100},
    }

    def _estimate_kcal(self, name: str) -> dict:
        """Substring-match the dish name against the hardcoded table.
        Returns nutrition dict (kcal, protein, fat, carb, serving_g) or
        a generic fallback if no match. No LLM call — pure dict lookup."""
        n = (name or "").lower().strip()
        # Try longest-key match first so "grilled fish" beats "fish"
        for key in sorted(self._DISH_KCAL, key=len, reverse=True):
            if key.lower() in n:
                return dict(self._DISH_KCAL[key])
        # Generic dish fallback — better than 0
        return {"kcal": 150, "protein_g": 8, "fat_g": 6, "carb_g": 12, "serving_g": 150}

    # Bilingual equivalents — used in BOTH the CNN cascade dedup and the
    # Phase 2 supplement dedup, so duplicate writes are blocked across paths.
    _CNN_BILINGUAL_EQUIV = {
        "rice": "밥",   "밥": "rice",
        "tofu": "두부",  "두부": "tofu",
        "kimchi": "김치", "김치": "kimchi",
    }

    def _dedup_cnn_results_by_class(self, results: list) -> list:
        """Cross-tier dedup: when Tier 0 (Korean) and Tier 1 (Food-101) both
        fire for names that map to the same class group (e.g. 양념치킨 + chicken_wings),
        keep only Tier 0 — it has MFDS-grade nutrition. Distinct class_kr
        names within Tier 0 are kept (양념치킨 + 후라이드치킨 = 2 boxes)."""
        sys.path.insert(0, str(Path(__file__).parent))
        from food_class_groups import food_class
        by_class: dict = {}
        unmapped: list = []
        for r in results:
            cid = food_class(r.class_kr)
            if cid is None:
                unmapped.append(r)
            else:
                by_class.setdefault(cid, []).append(r)
        kept: list = []
        for cid, items in by_class.items():
            if any(r.tier == "korean" for r in items):
                # T0 wins → drop T1 entries in this group
                kept.extend(r for r in items if r.tier == "korean")
            else:
                kept.extend(items)
        kept.extend(unmapped)
        return kept

    def _cnn_class_counts(self, results: list) -> dict:
        """Count distinct class_kr names per class group across CNN results.
        양념치킨 ×1 + 후라이드치킨 ×1 = chicken-class count 2.
        Used to seed the MAX-count rule in Phase 2."""
        sys.path.insert(0, str(Path(__file__).parent))
        from food_class_groups import food_class
        counts: dict = {}
        seen_names_per_class: dict = {}
        for r in results:
            cid = food_class(r.class_kr)
            if not cid:
                continue
            seen = seen_names_per_class.setdefault(cid, set())
            if r.class_kr.lower() not in seen:
                seen.add(r.class_kr.lower())
                counts[cid] = counts.get(cid, 0) + 1
        return counts

    def _run_photo_cnn_cascade(self, path: Path) -> tuple[set[str], dict]:
        """Tier 0 (Korean) + Tier 1 (Food-101) CNN cascade with multi-crop
        sliding window. Writes ONE row per confident dish (after class-group
        dedup) and returns (written_names_set, class_counts_dict) so Phase 2
        can apply the MAX-count rule across models."""
        if not _CNN_ENABLED or _food_cnn is None:
            return set(), {}

        try:
            img = Image.open(path).convert("RGB")
        except Exception as e:
            print(f"    [cnn-cascade] open failed: {e}")
            return set(), {}

        results = _food_cnn.classify_image_multi(img)
        if not results:
            try:
                dbg = _food_cnn.debug_top1_across_crops(img)
            except Exception:
                dbg = None
            if dbg:
                print(f"    [cnn-cascade] no confident hit ({dbg[0]} top-1: {dbg[1]} {dbg[2]:.2f}) — falling through to Phase 2")
            else:
                print(f"    [cnn-cascade] no confident hit — falling through to Phase 2")
            return set(), {}

        kept = self._dedup_cnn_results_by_class(results)
        if len(kept) < len(results):
            print(f"    [cnn-cascade] {len(results)} hit(s) -> {len(kept)} after class-group dedup")
        else:
            print(f"    [cnn-cascade] {len(results)} confident hit(s) across multi-crop")
        written: set[str] = set()
        for result in kept:
            written |= self._write_cnn_result(result)
        class_counts = self._cnn_class_counts(kept)
        return written, class_counts

    def _run_video_cnn_cascade(self, path: Path) -> tuple[set[str], dict]:
        """Sample 6 frames from the video, multi-crop each, dedup by class
        group, write one row per kept dish. Returns (names, class_counts)."""
        if not _CNN_ENABLED or _food_cnn is None:
            return set(), {}
        try:
            results = _food_cnn.classify_video_multi(path, num_frames=6)
        except Exception as e:
            print(f"    [cnn-cascade] video sampling failed: {e}")
            return set(), {}
        if not results:
            print(f"    [cnn-cascade] no confident hit across 6 frames x multi-crop — falling through to Phase 2")
            return set(), {}
        kept = self._dedup_cnn_results_by_class(results)
        if len(kept) < len(results):
            print(f"    [cnn-cascade] {len(results)} hit(s) -> {len(kept)} after class-group dedup")
        else:
            print(f"    [cnn-cascade] {len(results)} confident hit(s) across video frames + multi-crop")
        written: set[str] = set()
        for result in kept:
            written |= self._write_cnn_result(result)
        class_counts = self._cnn_class_counts(kept)
        return written, class_counts

    def _write_cnn_result(self, result) -> set[str]:
        """Resolve nutrition for a CascadeResult and write a row to
        user_food_log. Returns dedup name set (lower-cased + bilingual)."""
        sys.path.insert(0, str(Path(__file__).parent))
        from event_processor import EventProcessor as _EP
        from food101_nutrition import lookup as _food101_lookup
        proc = _EP()

        name = result.class_kr
        nutrition: Optional[dict] = None
        nut_source = "fallback"

        if result.tier == "korean":
            # MFDS lookup first per the project plan: 275K Korean foods is
            # the canonical source. _DISH_KCAL is the fallback.
            # MFDS values are normalized per ~100 g; pass portion_g=150 so
            # the lookup scales to a typical Korean main-dish portion.
            mfds = proc.lookup_food_nutrition(name, portion_g=150)
            if mfds and mfds.get("kcal"):
                nutrition = {
                    "kcal":      mfds.get("kcal", 0),
                    "protein_g": mfds.get("protein_g", 0),
                    "fat_g":     mfds.get("fat_g", 0),
                    "carb_g":    mfds.get("carb_g", 0),
                    "serving_g": mfds.get("portion_g", 150),
                }
                nut_source = f"mfds(serving={mfds.get('serving_size_g'):.0f}g)"
            else:
                nutrition = self._estimate_kcal(name)
                nut_source = "_DISH_KCAL"
        elif result.tier == "food101":
            row = _food101_lookup(name)
            if row:
                nutrition = row
                nut_source = "food101_table"
            else:
                nutrition = self._estimate_kcal(result.class_en or name)
                nut_source = "_DISH_KCAL"
        else:
            return set()

        write_name = name if result.tier == "korean" else (result.class_en or name)
        proc.write_food_log(TEST_USER_ID, {"name": write_name, **nutrition})
        print(f"    [cnn-cascade] tier={result.tier} -> user_food_log: {write_name} "
              f"(conf={result.confidence:.2f} margin={result.margin:.2f} kcal={nutrition['kcal']} src={nut_source})")

        # Build the dedup set (lower-cased + bilingual equivalent if any)
        written = {write_name.lower().strip()}
        if result.tier == "korean":
            # Korean dish — also block English equivalent if listed
            written.add(name.lower().strip())
            eq = self._CNN_BILINGUAL_EQUIV.get(name.lower().strip())
            if eq:
                written.add(eq.lower().strip())
            if result.class_en:
                written.add(result.class_en.lower().strip())
        else:
            # Food-101 — block both raw class ("french_fries") and humanized ("french fries")
            written.add(name.lower().strip())
            if result.class_en:
                written.add(result.class_en.lower().strip())
        return written

    # SQL hydration regex tokens (migration 006). If a Phase 2 drink name
    # contains NONE of these, the dashboard's SQL classifier will route it
    # to Food & Nutrition by mistake. _canonicalize_drink_name_for_sql
    # appends "drink" so the regex picks it up.
    _SQL_DRINK_TOKENS = (
        "drink", "water", "coffee", "tea", "juice", "milk",
        "물", "커피", "차", "주스", "우유", "홍차", "녹차", "아이스티", "라떼",
    )

    def _canonicalize_drink_name_for_sql(self, name: str) -> str:
        if any(tok.lower() in name.lower() for tok in self._SQL_DRINK_TOKENS):
            return name
        return f"{name} drink"

    def _phase2_nutrition_lookup(self, name: str, portion_g: int = 150) -> tuple[dict, str]:
        """Nutrition for a Phase 2 detection. Lookup priority:
          1. If name has a Korean canonical class id (e.g. "kimchi" → "김치"),
             query MFDS with that — much more precise than English-name
             substring matches that fall through to USDA.
          2. lookup_food_nutrition(name, portion_g) — MFDS then USDA.
          3. _DISH_KCAL substring match (always returns something).

        Pass portion_g=250 for drinks so kcal is scaled for the 250ml
        Hydration serving convention (not the 150g default for solid food).

        Sanity cap at 900 kcal/100g — pure butter/oil is ~900 kcal/100g,
        nothing edible exceeds that. USDA's `Energy` rows can include
        kJ values mis-labeled as kcal for certain foods, producing
        absurd numbers like 'fried chicken @ 2,716 kcal/150g'. When the
        lookup returns an implausible value, fall through to _DISH_KCAL.
        """
        sys.path.insert(0, str(Path(__file__).parent))
        from event_processor import EventProcessor as _EP
        from food_class_groups import food_class
        proc = _EP()

        def _accept(looked: dict | None) -> tuple[dict, str] | None:
            if not looked or not looked.get("kcal"):
                return None
            kcal = looked.get("kcal", 0) or 0
            portion_g = looked.get("portion_g", 150) or 150
            kcal_per_100g = (kcal / portion_g * 100) if portion_g > 0 else kcal
            if kcal_per_100g > 900:
                print(f"    [phase2-lookup] '{name}' via {looked.get('source')} returned "
                      f"{kcal:.0f}kcal/{portion_g:.0f}g (={kcal_per_100g:.0f}/100g) — "
                      f"implausible, ignored")
                return None
            return ({
                "kcal":      kcal,
                "protein_g": looked.get("protein_g", 0),
                "fat_g":     looked.get("fat_g", 0),
                "carb_g":    looked.get("carb_g", 0),
                "serving_g": portion_g,
            }, f"{looked.get('source','MFDS')}(serving={looked.get('serving_size_g',100):.0f}g)")

        # Step 1: try MFDS via the Korean canonical of the class group.
        canon = food_class(name)
        if canon and any('가' <= ch <= '힣' for ch in canon):
            res = _accept(proc.lookup_food_nutrition(canon, portion_g=portion_g))
            if res:
                return res

        # Step 2: original lookup chain (MFDS by raw name → USDA fallback).
        res = _accept(proc.lookup_food_nutrition(name, portion_g=portion_g))
        if res:
            return res

        # Step 3: _DISH_KCAL substring match (always returns something).
        return self._estimate_kcal(name), "_DISH_KCAL"

    def _run_photo_multimodal(self, path: Path, yolo_event: dict,
                              cnn_written_names: Optional[set] = None,
                              cnn_class_counts: Optional[dict] = None) -> tuple[bool, bool]:
        """Run Gemma + Nemotron multimodal on a single photo, write specific
        items to Supabase, and log to the comparison JSONL.

        Returns (wrote_any_food, wrote_specific_drink) — the caller uses
        these to suppress the generic meal/drink placeholders that would
        otherwise double-count nutrition or hydration.

        Cross-model dedup rule (per class group from food_class_groups.py):
          rows_total = MAX(cnn_class_counts[class], phase2_count_for_class)
          phase2_extra = rows_total - cnn_class_counts[class]
          → Phase 2 writes only `phase2_extra` rows for each class. Names are
            taken from Gemma → Nemotron (in that priority) so each row gets a
            distinct label when multiple distinct names exist for one class.

        Nutrition for every Phase 2 row uses lookup_food_nutrition() (MFDS
        first, USDA fallback) instead of trusting LLM-returned kcal — the
        LLM kcal numbers from Gemma 4 E4B / Nemotron 30B were unreliable.
        """
        wrote_food = False
        wrote_specific_drink = False
        sys.path.insert(0, str(Path(__file__).parent))
        from gemma_dual_extractor import (
            gemma_extract_image, log_dual_extraction, _format_arm_one_line,
        )
        from nemotron_extractor import nemotron_extract_image

        print("    --- Phase 2: photo multimodal extraction ---")
        gemma_result, gemma_ms, gemma_err = gemma_extract_image(path)
        nem_result, nem_ms, nem_err = nemotron_extract_image(path)

        print(_format_arm_one_line("gemma photo", gemma_result, gemma_ms, gemma_err))
        print(_format_arm_one_line("nemotron photo", nem_result, nem_ms, nem_err))

        # Production write — prefer Gemma's output (general object recognition),
        # fall back to Nemotron's if Gemma returned nothing useful.
        # Generic placeholders ("snack", "food", etc.) are filtered out so we
        # only persist specific identifications.
        _GENERIC = {
            "snack", "food", "meal", "item", "drink", "beverage",
            "thing", "object", "container", "package",
            "간식", "음식", "식사",
        }
        primary = gemma_result if isinstance(gemma_result, dict) else None
        if (not primary or not primary.get("foods")) and isinstance(nem_result, dict):
            primary = nem_result

        cnn_written_names = cnn_written_names or set()
        cnn_class_counts = cnn_class_counts or {}

        # Aggregate Phase 2 detections by class group (using gemma's foods
        # list as primary; Nemotron supplies extra distinct names when
        # available). Items not in the food_class_groups map fall to the
        # legacy name-only dedup path.
        sys.path.insert(0, str(Path(__file__).parent))
        from food_class_groups import food_class, is_drink_class
        from event_processor import EventProcessor as _EP

        # Collect candidates from BOTH Gemma and Nemotron. We no longer treat
        # Gemma as primary — instead we score every candidate and pick the
        # best name per class group (with optional Gemma tiebreak when scores
        # are close). This lets Nemotron's specific Korean brand names (e.g.
        # "스퀴이즈 오렌지 에이드") win over Gemma's generic English ("Orangeade")
        # when the heuristic agrees.
        gemma_foods = (gemma_result or {}).get("foods") if isinstance(gemma_result, dict) else None
        nem_foods   = (nem_result   or {}).get("foods") if isinstance(nem_result,   dict) else None

        def _clean_name(food: dict) -> str:
            return (food.get("name") or "").strip() if isinstance(food, dict) else ""

        # Per-source counts: per-NAME repetitions, then MAX across distinct
        # names within a class. Logic:
        #   - same name twice (Gemma "fried chicken, fried chicken") = 2
        #     boxes → class_count = 2
        #   - distinct synonyms (Nemotron "스퀴즈 오렌지 에이드, SQUEEZE ADE
        #     ORANGE") = 1 drink with naming variation → class_count = 1
        # Trade-off: if a model uses different sub-type names for two physical
        # dishes (e.g. "양념치킨" + "후라이드치킨"), this gives 1, undercounting.
        # User can voice-correct or take separate photos in that case.
        def _count_per_class(foods, source: str) -> tuple[dict[str, int], dict[str, list[str]], list[str]]:
            class_names: dict[str, list[str]] = {}
            unmapped: list[str] = []
            name_counts: dict[str, int] = {}
            for f in foods or []:
                name = _clean_name(f)
                if not name or name.lower() in _GENERIC:
                    continue
                name_counts[name] = name_counts.get(name, 0) + 1
                cid = food_class(name)
                if cid is None:
                    if name not in unmapped:
                        unmapped.append(name)
                    continue
                if name not in class_names.setdefault(cid, []):
                    class_names[cid].append(name)
            class_count: dict[str, int] = {}
            for cid, names in class_names.items():
                class_count[cid] = max((name_counts.get(n, 1) for n in names), default=0)
            return class_count, class_names, unmapped

        gemma_class_count, gemma_class_names, gemma_unmapped = _count_per_class(gemma_foods, "gemma")
        if NEMOTRON_WRITES_ENABLED:
            nem_class_count, nem_class_names, nem_unmapped = _count_per_class(nem_foods, "nemotron")
        else:
            # Nemotron contributes to the JSONL benchmark log below, but its
            # foods are excluded from production writes (too noisy).
            nem_class_count, nem_class_names, nem_unmapped = {}, {}, []

        proc_ep = _EP()

        # Heuristic scorer: prefer names that hit MFDS, are Korean, are longer.
        def _score(name: str) -> tuple[int, str]:
            score = 0
            tags = []
            looked = proc_ep.lookup_food_nutrition(name, portion_g=150)
            if looked and looked.get("kcal"):
                kcal_per_100 = looked["kcal"] / max(1, looked.get("portion_g", 100)) * 100
                if kcal_per_100 <= 900:
                    score += 10
                    tags.append("mfds")
            if any('가' <= ch <= '힣' for ch in name):
                score += 5
                tags.append("kr")
            length_bonus = max(0, len(name) - 5)
            score += length_bonus
            if length_bonus > 0:
                tags.append(f"len+{length_bonus}")
            return score, ",".join(tags) or "no-signal"

        def _pick_name(candidates: list[str], context: str) -> str:
            """Pick the best name from candidates: heuristic top-1, with Gemma
            arbitration when top-2 scores are within 5 points."""
            if not candidates:
                return ""
            if len(candidates) == 1:
                return candidates[0]
            scored = [(name, *_score(name)) for name in candidates]
            scored.sort(key=lambda x: x[1], reverse=True)
            top_name, top_score, top_tags = scored[0]
            if len(scored) == 1 or (scored[0][1] - scored[1][1] >= 5):
                print(f"    [phase2-pick] {context}: {top_name!r} score={top_score} ({top_tags}) — clear winner")
                return top_name
            # Close call → Gemma arbitration
            shortlist = [n for n, *_ in scored[:3]]
            try:
                from gemma_dual_extractor import gemma_arbitrate_image_candidates
                chosen, ms, err = gemma_arbitrate_image_candidates(path, shortlist)
            except Exception as e:
                chosen, ms, err = None, 0, str(e)
            if chosen:
                print(f"    [phase2-pick] {context}: {chosen!r} (gemma arbitrated {ms}ms over {shortlist})")
                return chosen
            print(f"    [phase2-pick] {context}: {top_name!r} score={top_score} (gemma arbitrate failed: {err}) — fallback to top-score")
            return top_name

        # Per-class write decisions: Gemma-priority count rule.
        # Gemma's count is more reliable than Nemotron's (Nemotron commonly
        # repeats the same item in its foods list as noise, not as a real
        # quantity). So: if Gemma saw the class, trust Gemma's count;
        # otherwise fall back to Nemotron's count. Combined with CNN via
        # MAX to allow CNN to set the floor when Gemma also missed it.
        all_classes = set(gemma_class_count.keys()) | set(nem_class_count.keys()) | set(cnn_class_counts.keys())
        for cid in all_classes:
            cnn_n = cnn_class_counts.get(cid, 0)
            gem_n = gemma_class_count.get(cid, 0)
            nem_n = nem_class_count.get(cid, 0)
            phase2_n = gem_n if gem_n > 0 else nem_n
            target = max(cnn_n, phase2_n)
            extra = target - cnn_n
            if extra <= 0:
                if phase2_n > 0:
                    print(f"    [photo-multimodal] skip class={cid} (CNN={cnn_n}, Gemma={gem_n}, Nemotron={nem_n})")
                continue
            # Build candidate pool from BOTH Phase 2 sources for this class
            candidates = []
            for n in gemma_class_names.get(cid, []):
                if n not in candidates:
                    candidates.append(n)
            for n in nem_class_names.get(cid, []):
                if n not in candidates:
                    candidates.append(n)
            best_name = _pick_name(candidates, f"class={cid}")
            # Drink routing: if class is a drink, canonicalize the name so
            # the dashboard SQL hydration regex (migration 006) classifies
            # it correctly, and treat serving_g as ml (250 default).
            drink = is_drink_class(cid)
            if drink:
                write_name = self._canonicalize_drink_name_for_sql(best_name)
            else:
                write_name = best_name
            target_portion = 250 if drink else 150
            for _ in range(extra):
                nutrition, src = self._phase2_nutrition_lookup(best_name, portion_g=target_portion)
                proc_ep.write_food_log(TEST_USER_ID, {"name": write_name, **nutrition})
                wrote_food = True
                if drink:
                    wrote_specific_drink = True
                category = "drink" if drink else "food"
                print(f"    [photo-multimodal] -> user_food_log ({category}): {write_name} ({nutrition['kcal']} kcal/{nutrition['serving_g']}{('ml' if drink else 'g')}, src={src}, class={cid})")

        # Unmapped foods (no class_groups entry). When BOTH sources offer
        # distinct unmapped names, ask Gemma to arbitrate (likely the same
        # dish but neither is in our class map yet). Single-source unmapped
        # names go through with name-only dedup against CNN.
        unmapped_combined = []
        for n in gemma_unmapped + nem_unmapped:
            if n.lower().strip() in cnn_written_names:
                continue
            if n not in unmapped_combined:
                unmapped_combined.append(n)

        if len(unmapped_combined) > 1 and gemma_unmapped and nem_unmapped:
            # Cross-source disagreement → arbitrate
            best = _pick_name(unmapped_combined, "unmapped multi-source")
            unmapped_to_write = [best]
        else:
            unmapped_to_write = unmapped_combined

        for name in unmapped_to_write:
            nutrition, src = self._phase2_nutrition_lookup(name)
            proc_ep.write_food_log(TEST_USER_ID, {"name": name, **nutrition})
            wrote_food = True
            print(f"    [photo-multimodal] -> user_food_log: {name} ({nutrition['kcal']} kcal, src={src}, unmapped)")

        # Comparison log (reuses the same JSONL as videos; transcript is null).
        log_dual_extraction(
            event_id=path.name,
            video_path=path,
            transcript=None,
            today_result={
                "event_type": "photo",
                "yolo_description": yolo_event.get("description"),
            },
            gemma_text_result=None,
            gemma_text_ms=0,
            gemma_text_error="photo_no_transcript",
            gemma_mm_result=gemma_result,
            gemma_mm_ms=gemma_ms,
            gemma_mm_error=gemma_err,
            nemotron_text_result=None,
            nemotron_text_ms=0,
            nemotron_text_error="photo_no_transcript",
            nemotron_mm_result=nem_result,
            nemotron_mm_ms=nem_ms,
            nemotron_mm_error=nem_err,
        )
        print("    [phase2-photo] dual-extraction logged")
        return wrote_food, wrote_specific_drink

    # ── Extract Audio from Video ──

    def extract_audio_from_video(self, video_path: Path) -> Path | None:
        """Extract audio track from video file using ffmpeg."""
        temp_dir = PROJECT_ROOT / "backend" / "glasses_watcher" / "temp_frames"
        temp_dir.mkdir(parents=True, exist_ok=True)
        audio_path = temp_dir / f"{video_path.stem}_audio.wav"
        try:
            import subprocess
            result = subprocess.run(
                ["ffmpeg", "-i", str(video_path), "-vn", "-acodec", "pcm_s16le",
                 "-ar", "16000", "-ac", "1", "-y", str(audio_path)],
                capture_output=True, timeout=60,
            )
            if audio_path.exists() and audio_path.stat().st_size > 1000:
                return audio_path
        except FileNotFoundError:
            # ffmpeg not installed - try moviepy or opencv
            try:
                import subprocess
                result = subprocess.run(
                    ["python", "-c", f"""
import cv2
cap = cv2.VideoCapture(r'{video_path}')
cap.release()
"""], capture_output=True, timeout=10)
            except Exception:
                pass
        except Exception:
            pass
        return None

    def _call_whisper_server(self, audio_path: Path) -> dict | None:
        """Call the Mac mini whisper.cpp large-v3 server over Tailscale.

        large-v3 handles Korean/English mixed speech natively without hallucinating.
        Returns None if the server is unreachable — caller falls back to local medium.

        For long audio, whisper.cpp processes in 30s windows. We assemble all
        segments returned in verbose_json so we get the FULL transcript, not
        just the first window's `text` field.
        """
        try:
            with open(audio_path, "rb") as f:
                resp = httpx.post(
                    WHISPER_REMOTE_URL,
                    files={"file": ("audio.wav", f, "audio/wav")},
                    data={
                        "language": "auto",
                        "response_format": "verbose_json",  # underscore, not hyphen
                        "max_len": "0",                      # 0 = no per-segment length limit
                        "temperature": "0",
                    },
                    timeout=180,  # longer videos need more time
                )
            resp.raise_for_status()
            data = resp.json()
            # Some whisper.cpp versions return everything in `text`, others split into `segments`.
            # If `segments` exists and is non-empty, concatenate ALL of them — that's the full
            # transcript. If only `text` is set, use that.
            segments = data.get("segments") or []
            if segments:
                text = " ".join(
                    (seg.get("text") or "").strip()
                    for seg in segments
                    if isinstance(seg, dict) and seg.get("text")
                ).strip()
            else:
                text = (data.get("text") or "").strip()
            lang = data.get("language", "auto")
            duration = data.get("duration", 0)
            if not text:
                print(f"    [whisper-remote] empty response — falling back to local")
                return None
            seg_info = f"{len(segments)}seg" if segments else "1block"
            print(f"    [whisper-remote] large-v3 | lang={lang} | {duration:.1f}s | {seg_info} | {len(text)} chars")
            return {"transcript": text, "language": lang, "duration": duration}
        except Exception as e:
            print(f"    [whisper-remote] unreachable ({e.__class__.__name__}) — falling back to local medium")
            return None

    def _detect_language_for_production(self, model, audio_path: Path) -> str:
        """
        Two-pass language detection tuned for Korean production users.

        Korean-accent speakers register as 'ko' even when speaking mostly English.
        Rather than fighting that, we embrace it: route any Korean-detected audio to
        Korean mode where Whisper transcribes faithfully instead of hallucinating.

        Only use English mode when the audio is unambiguously English (prob >= 0.75
        AND Korean prob < 0.20). Default fallback is Korean since production is Korean.
        """
        import whisper
        try:
            audio = whisper.load_audio(str(audio_path))
            mel = whisper.log_mel_spectrogram(whisper.pad_or_trim(audio)).to(model.device)
            _, probs = model.detect_language(mel)
            ko_prob = probs.get("ko", 0)
            en_prob = probs.get("en", 0)
            print(f"    Lang detection: ko={ko_prob:.2f}  en={en_prob:.2f}")
            if ko_prob >= 0.20:
                return "ko"
            if en_prob >= 0.75:
                return "en"
            return "ko"  # production default
        except Exception:
            return "ko"

    def _is_hallucinating(self, text: str) -> bool:
        """Detect Whisper hallucination or prompt bleed-through.

        Three signals:
          1. A known Korean-mode hallucination phrase appears ≥2 times.
          2. The text is highly repetitive (unique 3-grams < 35% of total).
          3. The text is a substring of one of our prompts (prompt bleed-through:
             Whisper echoes the initial_prompt when it can't decode the audio).
        """
        if not text or len(text.strip()) < 5:
            return True
        for phrase in _KO_HALLUCINATION_PHRASES:
            if text.count(phrase) >= 2:
                return True
        # Prompt bleed-through: output is contained in one of our prompts
        for prompt in (_WHISPER_PROMPT_KO, _WHISPER_PROMPT_EN):
            if text.strip().rstrip(".").strip() in prompt:
                return True
        words = text.split()
        if len(words) >= 8:
            unique_3grams = set(
                (words[i], words[i + 1], words[i + 2])
                for i in range(len(words) - 2)
            )
            if len(unique_3grams) / max(len(words) - 2, 1) < 0.35:
                return True
        return False

    def transcribe_audio(self, audio_path: Path) -> dict | None:
        """Transcribe audio — tries Mac mini large-v3 first, falls back to local medium.

        large-v3 on Mac mini (Metal) handles Korean/English mixed speech natively.
        Local medium fallback uses two-pass language detection + hallucination retry.
        """
        # Primary: remote large-v3 on Mac mini (no hallucination on mixed speech)
        remote = self._call_whisper_server(audio_path)
        if remote:
            return remote

        # Fallback: local Whisper medium on CPU
        try:
            import whisper
            print("    Loading Whisper (medium, multilingual)...")
            model = whisper.load_model("medium")

            lang = self._detect_language_for_production(model, audio_path)
            print(f"    Transcribing as: {lang}")
            result = model.transcribe(
                str(audio_path),
                language=lang,
                initial_prompt=_WHISPER_PROMPT_KO if lang == "ko" else _WHISPER_PROMPT_EN,
                task="transcribe",
                condition_on_previous_text=False,
                temperature=0,
            )
            text = result["text"].strip()

            # Hallucination check: Korean decoder loops on filler phrases when
            # it encounters English phonemes it cannot decode.
            # Retry with task="translate" so Whisper translates Korean words
            # to English text — this preserves the MEANING of mixed-language
            # speech (Korean words appear as their English equivalents rather
            # than being silently dropped by the English-only decoder).
            if lang == "ko" and self._is_hallucinating(text):
                print(f"    [retry] Korean hallucination detected — retrying with translate task")
                result_en = model.transcribe(
                    str(audio_path),
                    task="translate",
                    initial_prompt=None,
                    condition_on_previous_text=False,
                    temperature=0,
                )
                text_en = result_en["text"].strip()
                if not self._is_hallucinating(text_en):
                    print(f"    [retry] Translation succeeded")
                    return {"transcript": text_en, "language": "en"}
                print(f"    [retry] Both hallucinated, using translation result as fallback")
                return {"transcript": text_en or text, "language": "en"}

            return {
                "transcript": text,
                "language": result.get("language", lang),
            }
        except Exception as e:
            print(f"    Whisper error: {e}")
            return None

    # ── Process Video (visual + audio) ──

    def process_video(self, path: Path):
        print(f"\n  [VIDEO] {path.name}")
        transcript: str = ""  # Phase 2: captured if Whisper transcribes; passed to dual-extraction logger

        cap = cv2.VideoCapture(str(path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total / fps if fps > 0 else 0
        print(f"    Duration: {duration:.1f}s | {total} frames")

        # ── Part A: Visual detection (YOLOv8 on frames) ──
        print(f"    --- Visual Analysis ---")
        temp_dir = PROJECT_ROOT / "backend" / "glasses_watcher" / "temp_frames"
        temp_dir.mkdir(parents=True, exist_ok=True)

        interval = max(int(fps * 3), 1)
        frame_num = 0
        events = []

        while cap.isOpened() and len(events) < 10:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_num % interval == 0:
                fp = temp_dir / f"f_{len(events)}.jpg"
                cv2.imwrite(str(fp), frame)
                event = self.detect_and_interpret(fp)
                t_sec = round(frame_num / fps, 1)
                event["time_in_video"] = t_sec
                events.append(event)
                print(f"    t={t_sec}s: {event['description']}")
                fp.unlink()
            frame_num += 1
        cap.release()

        # Find visual health events
        health_events = [e for e in events if e["event_type"] in ("meal", "drink", "exercise")]
        if health_events:
            best_visual = max(health_events, key=lambda e: e["confidence"])
            print(f"    >> Visual: {best_visual['description']}")
        else:
            best_visual = {
                "event_type": "video_capture",
                "description": f"Video {duration:.0f}s - no visual health activity",
                "health_data": {"duration_sec": round(duration, 1)},
                "confidence": 0,
                "objects_detected": [],
            }

        # Upload visual event (raw audit log goes to user_activity_event now;
        # distribution to domain tables is DEFERRED until we see the audio
        # result — see two-phase logic below).
        best_visual["health_data"]["video_duration_sec"] = round(duration, 1)
        best_visual["health_data"]["frames_analyzed"] = len(events)
        best_visual["health_data"]["all_activities"] = list({e["event_type"] for e in events})

        visual_eid = self.upload_event(best_visual, path.name)
        if visual_eid:
            print(f"    Supabase event_id={visual_eid} (visual raw)")

        # ── Part B: Audio extraction + Whisper STT ──
        print(f"    --- Audio Analysis ---")
        audio_path = self.extract_audio_from_video(path)
        audio_summary: dict = {}

        if audio_path and audio_path.exists():
            transcription = self.transcribe_audio(audio_path)

            if transcription and transcription["transcript"]:
                transcript = transcription["transcript"]
                lang = transcription["language"]
                print(f"    Language: {lang}")
                # Show full transcript (no truncation) so we can verify Whisper
                # returned the complete audio — truncation here was masking
                # whether the issue was Whisper or our display.
                print(f"    Transcript ({len(transcript)} chars): {transcript}")

                now = datetime.now(KST)
                audio_event = {
                    "event_type": "voice_report",
                    "description": f"At {now.strftime('%I:%M %p')}, voice from video: \"{transcript[:100]}\"",
                    "health_data": {
                        "transcript": transcript,
                        "language": lang,
                        "source": "video_audio_track",
                        "time": now.isoformat(),
                    },
                    "confidence": 0.8,
                    "objects_detected": [],
                }

                audio_eid = self.upload_event(audio_event, path.name)
                if audio_eid:
                    print(f"    Supabase event_id={audio_eid} (audio raw)")
                print(f"    --- Auto-distributing audio extraction ---")
                audio_summary = self.distribute_to_tables(audio_event)

                # If user stated the exercise happened at a past time (e.g. "at 9am"),
                # backfill user_activity_event.detected_at so the dashboard shows the
                # correct time instead of the current processing time.
                ex_time = audio_summary.get("exercise_time")
                if ex_time and audio_eid:
                    try:
                        today_kst = datetime.now(KST).date().isoformat()
                        stated_at = f"{today_kst}T{ex_time}:00+09:00"
                        httpx.patch(
                            f"{SUPABASE_URL}/rest/v1/user_activity_event",
                            params={"event_id": f"eq.{audio_eid}"},
                            json={"detected_at": stated_at},
                            headers={
                                "apikey": SUPABASE_KEY,
                                "Authorization": f"Bearer {SUPABASE_KEY}",
                                "Content-Type": "application/json",
                            },
                            timeout=10,
                        ).raise_for_status()
                        print(f"    -> backfilled detected_at to {stated_at} (user stated {ex_time})")
                    except Exception as _e:
                        print(f"    detected_at backfill failed: {_e}")
            else:
                print(f"    No speech detected in video audio")

            # NOTE: temp WAV cleanup deferred until AFTER Phase 2 dual-extraction
            # so Nemotron native-audio arm can read the same WAV. See cleanup
            # block after the Phase 2 try/except.
        else:
            print(f"    Could not extract audio (ffmpeg may not be installed)")
            print(f"    Install: winget install FFmpeg")

        visual_type = best_visual.get("event_type")
        audio_already_named_drink = (
            audio_summary.get("audio_drink") and visual_type == "drink"
        )

        # Non-health gate: skip CNN cascade + Phase 2 multimodal entirely if
        # NEITHER YOLO NOR the audio transcript shows any health signal. The
        # multimodal models will hallucinate food/exercise from random
        # scenes (e.g. tech expo footage → "orange bag" written as food,
        # or "exercise 1min" rows from a generic speech). Audio override
        # works: if the user voice-narrates a meal ("I'm eating sushi"),
        # the transcript health keywords pass the gate even when YOLO
        # missed the food.
        is_health_video = bool(health_events) or _has_health_keyword(transcript)
        if not is_health_video:
            print(f"    [non-health-video] no YOLO health frames + no transcript "
                  f"health keywords — skipping CNN cascade + Phase 2 multimodal "
                  f"(no food/exercise rows will be written)")
            # Cleanup temp WAV (Phase 2 normally does this; we exit early).
            if isinstance(audio_path, Path) and audio_path.exists():
                try:
                    audio_path.unlink()
                except Exception:
                    pass
            self._log_event(best_visual, path.name)
            return

        # Tier 0/1 CNN cascade on video frames — runs BEFORE Phase 2 so
        # confident hits land in user_food_log first and the supplement loops
        # below dedup against these names via expanded_audio. Also runs
        # BEFORE the visual distribute (deferred to end of this block) so the
        # generic meal placeholder is suppressed when CNN found specific dishes.
        cnn_video_names_lower: set[str] = set()
        cnn_video_class_counts: dict = {}
        if _CNN_ENABLED:
            try:
                print(f"    --- CNN cascade: 6-frame video sample ---")
                cnn_video_names_lower, cnn_video_class_counts = self._run_video_cnn_cascade(path)
            except Exception as e:
                print(f"    [cnn-cascade] failed (non-fatal): {e}")

        # Tracks whether Phase 2 supplements wrote any specific dish row.
        # Drives the meal-placeholder suppression in the visual-distribute
        # step below.
        phase2_wrote_food = False

        if _PHASE2_ENABLED:
            try:
                print(f"    --- Phase 2: Gemma dual-extraction ---")
                gemma_mm = _gemma_dual_log(
                    event_id=path.name,
                    video_path=path,
                    transcript=transcript,
                    today_extraction={
                        "audio_summary": audio_summary,
                        "best_visual_type": best_visual.get("event_type"),
                        "best_visual_description": best_visual.get("description"),
                        "best_visual_health_data": best_visual.get("health_data"),
                    },
                    audio_path=audio_path if isinstance(audio_path, Path) and audio_path.exists() else None,
                )
                print(f"    [phase2] dual-extraction logged")

                # Supplement production DB with multimodal detections that the
                # text-only production arm missed. Reads from FOUR sources:
                # gemma_mm, nemotron_mm, nemotron_native_audio, nemotron_native_video.
                # Filters applied in order:
                #   - generic placeholders ("snack", "food", "meal")
                #   - bilingual duplicates (coffee≡커피, tea≡차)
                #   - transcript homophone filter (skip "tea" if transcript says "tea of this")
                #   - obvious Nemotron hallucinations + garbage tokens
                #   - cross-arm dedup (same name written only once)
                gemma_mm_dict       = gemma_mm.get("gemma_mm")              if isinstance(gemma_mm, dict) else None
                nemotron_mm_dict    = gemma_mm.get("nemotron_mm")           if isinstance(gemma_mm, dict) else None
                nemotron_audio_dict = gemma_mm.get("nemotron_native_audio") if isinstance(gemma_mm, dict) else None
                nemotron_video_dict = gemma_mm.get("nemotron_native_video") if isinstance(gemma_mm, dict) else None

                # Generic / vague tokens — block from Supabase writes.
                # "snack" / "간식" are ALLOWED through (user wants visibility
                # when models detect a snack but can't identify the brand).
                # The truly meaningless tokens below ("food", "meal", "thing")
                # add zero information and stay blocked.
                _GENERIC = {
                    "food", "meal", "item", "drink", "beverage",
                    "thing", "object", "container", "package",
                    "음식", "식사",
                }
                # Pronouns / stopwords / fillers / adjectives that ASR models
                # occasionally extract as "food names" because they appear in
                # the audio. Adjectives like "tasty" / "delicious" describe
                # food but ARE NOT food themselves.
                _STOPWORDS = {
                    # Pronouns / fillers
                    "this", "that", "these", "those", "it", "them",
                    "the", "a", "an", "and", "or", "but",
                    "i", "you", "we", "they", "he", "she", "his", "her",
                    "yes", "no", "ok", "okay", "well", "um", "uh",
                    "today", "yesterday", "tomorrow", "morning", "evening",
                    "이거", "그거", "저거", "이것", "그것", "저것",
                    # Adjectives that describe food but are not food
                    "tasty", "delicious", "yummy", "good", "great", "nice",
                    "amazing", "wonderful", "fantastic", "spicy", "sweet",
                    "salty", "savory", "fresh", "warm", "cold", "hot",
                    "맛있는", "맛있어", "맛있다", "맛있어요",
                    # Tasty-item / generic-item phrasings
                    "tasty item", "tasty food", "delicious item",
                    # Exercise reps incorrectly extracted as items
                    "warm-up", "warm-ups", "rep", "reps", "set", "sets",
                }
                # Beverage keywords — if the supplemented name contains any,
                # we route it as hydration (serving_g = ml ≈ 250) so it lands
                # in the Hydration dashboard category, not Food & Nutrition.
                _DRINK_KEYWORDS = {
                    # English
                    "juice", "ade", "coffee", "tea", "water", "milk",
                    "soda", "cola", "beer", "wine", "smoothie",
                    "latte", "americano", "cappuccino", "espresso",
                    "lemonade", "drink", "beverage", "shake",
                    # Korean (incl. ASR spelling variants)
                    "주스", "쥬스", "에이드", "메이드", "커피", "차", "물", "우유",
                    "탄산", "음료", "라떼", "라테", "맥주", "와인",
                    "오렌지",  # very commonly in drink names: 오렌지주스, 오렌지에이드
                }
                # The hrt_drilldown SQL regex only recognizes a fixed set of
                # drink keywords. Whisper sometimes outputs spelling variants
                # (쥬스 vs 주스) that bypass the SQL classifier, putting drinks
                # into Food & Nutrition. Normalize variants → canonical form
                # the SQL regex actually matches.
                _DRINK_NAME_NORMALIZATION = [
                    ("쥬스", "주스"),   # ASR variant of 주스 (juice)
                    ("메이드", "에이드"),  # ASR variant of 에이드 (ade) — but '에이드' itself isn't in SQL regex (see below)
                ]
                # SQL regex tokens (must match what's in migration 006). If the
                # supplemented drink name contains NONE of these, we append
                # the English word "drink" so the SQL classifier picks it up
                # for Hydration aggregation.
                _SQL_DRINK_TOKENS = (
                    "drink", "water", "coffee", "tea", "juice", "milk",
                    "물", "커피", "차", "주스", "우유", "홍차", "녹차", "아이스티", "라떼",
                )

                def _canonicalize_drink_name(name: str) -> str:
                    """Apply ASR-variant normalization, and ensure the result
                    contains at least one keyword the SQL hydration classifier
                    recognizes — otherwise append a tag."""
                    canon = name
                    for src, dst in _DRINK_NAME_NORMALIZATION:
                        canon = canon.replace(src, dst)
                    if not any(tok.lower() in canon.lower() for tok in _SQL_DRINK_TOKENS):
                        canon = f"{canon} drink"  # English token forces SQL match
                    return canon
                # Korean ↔ English equivalents — used for cross-language dedup.
                # If production wrote "커피", visual saying "coffee" is the same item.
                _BILINGUAL_EQUIV = {
                    "coffee": "커피",  "커피": "coffee",
                    "tea":    "차",   "차":    "tea",
                    "water":  "물",   "물":    "water",
                    "juice":  "주스",  "주스":  "juice",
                    "milk":   "우유",  "우유":  "milk",
                    "soda":   "탄산",  "탄산":  "soda",
                    "rice":   "밥",   "밥":    "rice",
                    "tofu":   "두부",  "두부":  "tofu",
                    "kimchi": "김치",  "김치":  "kimchi",
                }
                # Detect Whisper homophone patterns in the transcript itself.
                # When the transcript contains "tea of this/these" it actually means
                # "three of this" — the user wasn't drinking tea. Same for to=two, for=four.
                _homophone_skip: set[str] = set()
                if transcript:
                    t_lower = transcript.lower()
                    if " tea of this" in t_lower or " tea of these" in t_lower:
                        _homophone_skip.update({"tea", "차"})
                    if " to of this" in t_lower or " to of these" in t_lower:
                        _homophone_skip.add("to")
                    if " for of this" in t_lower or " for of these" in t_lower:
                        _homophone_skip.add("for")

                # Items Nemotron has hallucinated in past tests + obvious garbage
                # tokens (long phrases with "time", weird strings, items not
                # actually in our test videos).
                _NEMOTRON_HALLUCINATIONS = {
                    "noodles", "spring stew", "soybean paste",
                    "massive oat drink time",
                    "chocolate bar", "pepper sauce",
                    "biscuit",  # Nemotron's confused name for "cookie"
                    "맥주 라인치",
                }

                def _looks_like_garbage(name_lower: str) -> bool:
                    """Filter outputs that clearly aren't a single food item."""
                    if len(name_lower) < 2:
                        return True
                    if len(name_lower.split()) > 5:
                        return True  # "massive oat drink time" — too many words for a dish name
                    if any(token in name_lower for token in (" time", "drink time", "  ")):
                        return True
                    return False

                # Names the production arm already wrote this turn.
                audio_names_lower = {
                    n.lower().strip()
                    for n in (audio_summary.get("audio_food_names") or [])
                }
                # Expand audio_names with bilingual equivalents so "커피"
                # production write blocks both "커피" and "coffee" supplement.
                expanded_audio = set(audio_names_lower)
                for n in list(audio_names_lower):
                    eq = _BILINGUAL_EQUIV.get(n)
                    if eq:
                        expanded_audio.add(eq.lower())

                # Also block items the Tier 0/1 CNN cascade already wrote on
                # this video. Same set semantics as expanded_audio so the
                # supplement filter loops below catch them automatically.
                expanded_audio |= cnn_video_names_lower

                sys.path.insert(0, str(Path(__file__).parent))
                from event_processor import EventProcessor as _EP
                _proc = _EP()
                already_written_lower: set[str] = set()

                # Pre-compute the set of English/Latin tokens in the name so
                # word-boundary matching ("cola" must be a separate word, NOT
                # a substring of "chocolate"). Korean keywords are still
                # substring-matched because Korean isn't whitespace-tokenized.
                import re as _re
                _LATIN_DRINK_KW = {
                    kw for kw in _DRINK_KEYWORDS
                    if _re.match(r'^[a-z]+$', kw)
                }
                _NON_LATIN_DRINK_KW = _DRINK_KEYWORDS - _LATIN_DRINK_KW

                def _is_drink(name_lower: str) -> bool:
                    # English: word-boundary regex match — prevents "cola"
                    # matching "chocolate", "tea" matching "steak", etc.
                    words = set(_re.findall(r'\b[a-z]+\b', name_lower))
                    if words & _LATIN_DRINK_KW:
                        return True
                    # Korean / non-Latin: substring is fine because there are
                    # no whitespace word boundaries between hangul characters.
                    if any(kw in name_lower for kw in _NON_LATIN_DRINK_KW):
                        return True
                    return False

                # Evidence values that indicate the model GUESSED rather than
                # actually saw or heard the item. Drop these — they're the
                # main hallucination source ("chocolate bar" / "맥주 라인치"
                # arise when models infer items from word context like
                # "tasty"/"good" rather than evidence).
                _EVIDENCE_BLOCK = {"transcript_inferred", "guessed", "inferred", ""}

                # Class-group dedup: when CNN cascade already wrote rows for
                # a class (e.g. chicken-class), don't let Phase 2 supplements
                # double-count by writing the same dish under a different
                # synonym. Conservative rule for video: if CNN covered the
                # class, skip ALL Phase 2 supplement writes in that class.
                from food_class_groups import food_class as _food_class

                def _supplement_from(source_label: str, mm: Optional[dict], strict: bool):
                    """strict=True applies Nemotron hallucination + stopword filter
                    aggressively. strict=False is used for Gemma (cleaner output)."""
                    if not isinstance(mm, dict):
                        return
                    for food in mm.get("foods") or []:
                        if not isinstance(food, dict):
                            continue
                        name = (food.get("name") or "").strip()
                        name_lower = name.lower().strip()
                        if not name_lower:
                            continue
                        # Evidence-based hallucination filter (#5 from plan).
                        # If the model populated the new `evidence` field and
                        # said it INFERRED the item without seeing/hearing it,
                        # drop it — those are exactly the hallucinations we
                        # don't want hitting Supabase.
                        evidence = (food.get("evidence") or "").lower().strip()
                        if evidence and evidence in _EVIDENCE_BLOCK:
                            continue
                        if name_lower in _GENERIC:
                            continue
                        if name_lower in _STOPWORDS:
                            continue  # "this", "that", "the" — never a real food
                        if name_lower in _homophone_skip:
                            continue  # transcript shows it's a homophone
                        if _looks_like_garbage(name_lower):
                            continue
                        if strict and name_lower in _NEMOTRON_HALLUCINATIONS:
                            continue
                        if name_lower in expanded_audio:
                            continue  # production already wrote this (bilingual-aware)
                        # Cross-arm dedup with bilingual awareness
                        if name_lower in already_written_lower:
                            continue
                        eq = _BILINGUAL_EQUIV.get(name_lower)
                        if eq and eq.lower() in already_written_lower:
                            continue
                        # Class-group dedup against CNN: conservative for video.
                        cid = _food_class(name)
                        if cid and cnn_video_class_counts.get(cid, 0) > 0:
                            print(f"    [{source_label}] skip '{name}' (class={cid} already covered by CNN cascade)")
                            continue
                        already_written_lower.add(name_lower)
                        if eq:
                            already_written_lower.add(eq.lower())

                        qty = food.get("quantity", 1) or 1
                        try:
                            qty = int(qty)
                        except (TypeError, ValueError):
                            qty = 1
                        qty = max(1, min(qty, 20))  # sanity-cap at 20 to avoid spam
                        is_drink = _is_drink(name_lower)
                        # Drinks: serving_g treated as ml (typical 250 ml) →
                        #   dashboard SQL categorizes as Hydration.
                        # Foods: portion in grams (typical 200 g) →
                        #   dashboard SQL categorizes as Food & Nutrition.
                        serving_g = food.get("portion_g") or food.get("ml")
                        if not serving_g:
                            serving_g = 250 if is_drink else 200
                        # For drinks, normalize the name so the SQL hydration
                        # classifier (migration 006 regex) actually matches it.
                        write_name = _canonicalize_drink_name(name) if is_drink else name
                        # Authoritative nutrition: MFDS / USDA via lookup_food_nutrition
                        # (scaled to portion=150g), else _DISH_KCAL substring match.
                        # Replaces the previous "trust LLM-returned kcal" path which
                        # used Gemma's / Nemotron's hallucinated calorie numbers.
                        nutrition_dict, _src = self._phase2_nutrition_lookup(name)
                        kcal = nutrition_dict["kcal"]
                        # Write `qty` separate rows so the timeline reflects N
                        # individual events (e.g. 4 cookies = 4 rows), each at
                        # slightly different consumed_at timestamps for ordering.
                        for _ in range(qty):
                            _proc.write_food_log(TEST_USER_ID, {
                                "name": write_name,
                                "kcal":      kcal,
                                "protein_g": nutrition_dict["protein_g"],
                                "fat_g":     nutrition_dict["fat_g"],
                                "carb_g":    nutrition_dict["carb_g"],
                                "serving_g": serving_g,
                            })
                        category = "drink" if is_drink else "food"
                        unit = "ml" if is_drink else "g"
                        total_kcal = kcal * qty
                        total_serving = serving_g * qty
                        rows_msg = f"{qty} rows" if qty > 1 else "1 row"
                        if write_name != name:
                            print(f"    [{source_label}] -> user_food_log ({category}, {rows_msg}): {write_name} (orig: {name}, qty {qty}, total {total_kcal} kcal, {total_serving}{unit})")
                        else:
                            print(f"    [{source_label}] -> user_food_log ({category}, {rows_msg}): {name} (qty {qty}, total {total_kcal} kcal, {total_serving}{unit})")

                # ──────────────────────────────────────────────────────
                # Phase 2 supplements — RESTORED to "always run + filters".
                # The conditional trigger and cross-arm agreement we tried
                # were too strict and blocked legitimate writes. Filters
                # below handle the noise:
                #
                #   - _GENERIC blocks "food", "meal", "thing"
                #   - _STOPWORDS blocks "tasty item", "this", adjectives
                #   - _NEMOTRON_HALLUCINATIONS blocks known phantom items
                #   - evidence="transcript_inferred" filter drops guesses
                #   - drink keywords + canonicalization route to Hydration
                #
                # Both Gemma mm AND Nemotron mm supplement Supabase. Native
                # audio/video stay JSONL-only (too noisy for production).
                # ──────────────────────────────────────────────────────
                _supplement_from("gemma-visual", gemma_mm_dict, strict=False)
                if NEMOTRON_WRITES_ENABLED:
                    _supplement_from("nemotron-visual", nemotron_mm_dict, strict=True)
                # If supplements wrote anything, mark so visual distribute
                # below suppresses the generic meal placeholder.
                phase2_wrote_food = len(already_written_lower) > 0

                # Write visual exercise only when audio found none. Prefer
                # Gemma's reading; Nemotron is gated by NEMOTRON_WRITES_ENABLED
                # (it has hallucinated "exercise 1min" on non-exercise scenes).
                # Sanity-cap minutes: a 110s video can't contain >480 min of
                # exercise (one workday).
                if not audio_summary.get("exercise"):
                    gex = (gemma_mm_dict or {}).get("exercise")
                    if not gex and NEMOTRON_WRITES_ENABLED:
                        gex = (nemotron_mm_dict or {}).get("exercise")
                    if isinstance(gex, dict):
                        try:
                            mins = int(gex.get("minutes") or 0)
                        except (TypeError, ValueError):
                            mins = 0
                        if 1 <= mins <= 480:
                            self._write_lifestyle_row(TEST_USER_ID, {
                                "exercise_min": mins,
                                "exercise_type": "general",
                            })
                            print(f"    [phase2-visual] -> user_lifestyle: visual exercise {mins}min")
                        elif mins > 480:
                            print(f"    [phase2-visual] hallucinated exercise duration {mins}min — rejected (cap 480)")
            except Exception as e:
                print(f"    [phase2] dual-extraction failed (non-fatal): {e}")

        # Visual distribute — runs AFTER CNN cascade + Phase 2 supplements so
        # we know whether any specific dish was already written. This is the
        # generic 'lunch'/'snack'/'meal' fallback row; suppress it when CNN
        # or Phase 2 already wrote real dishes (otherwise kcal double-counts).
        # Two-phase dedup: if audio transcript already named a specific drink
        # (e.g. "black tea" → 홍차), skip the generic visual "drink (cup)" row.
        # Use audio_drink (not food_or_drink) for the cup-skip check — a
        # hallucinated solid food must NOT suppress a real visual cup signal.
        if visual_type in ("drink", "meal", "exercise"):
            if audio_already_named_drink:
                print(f"    (skipping visual 'drink' distribution — audio already named the beverage)")
            else:
                specific_dishes_found = bool(cnn_video_names_lower) or phase2_wrote_food
                print(f"    --- Auto-distributing visual detection ---")
                self.distribute_to_tables(best_visual, skip_meal_placeholder=specific_dishes_found)

        # Deferred temp-WAV cleanup — kept alive for Nemotron native-audio arm
        # in Phase 2. Now Phase 2 has finished; safe to delete.
        if isinstance(audio_path, Path) and audio_path.exists():
            try:
                audio_path.unlink()
            except Exception:
                pass

        self._log_event(best_visual, path.name)

    # ── Process Audio ──

    def process_audio(self, path: Path):
        print(f"\n  [AUDIO] {path.name}")
        try:
            # Primary: remote large-v3 on Mac mini
            remote = self._call_whisper_server(path)
            if remote:
                transcript = remote["transcript"]
                lang = remote["language"]
                duration = remote.get("duration", 0)
            else:
                # Fallback: local Whisper medium
                import whisper
                print("    Loading Whisper (medium, multilingual)...")
                model = whisper.load_model("medium")
                lang = self._detect_language_for_production(model, path)
                print(f"    Transcribing as: {lang}")
                result = model.transcribe(
                    str(path),
                    language=lang,
                    initial_prompt=_WHISPER_PROMPT_KO if lang == "ko" else _WHISPER_PROMPT_EN,
                    task="transcribe",
                    condition_on_previous_text=False,
                    temperature=0,
                )
                transcript = result["text"].strip()
                duration = result.get("duration", 0)

            # Hallucination retry — only for local medium fallback path.
            # large-v3 remote handles mixed speech natively; no retry needed there.
            if not remote and lang == "ko" and self._is_hallucinating(transcript):
                print(f"    [retry] Korean hallucination detected — retrying with translate task")
                result_en = model.transcribe(
                    str(path),
                    task="translate",
                    initial_prompt=None,
                    condition_on_previous_text=False,
                    temperature=0,
                )
                text_en = result_en["text"].strip()
                if not self._is_hallucinating(text_en):
                    print(f"    [retry] Translation succeeded")
                    transcript = text_en
                    lang = "en"
                    duration = result_en.get("duration", duration)
                else:
                    print(f"    [retry] Both hallucinated, using translation result as fallback")
                    transcript = text_en or transcript
                    lang = "en"

            print(f"    Duration: {duration:.1f}s")
            print(f"    Transcript: {transcript[:150]}{'...' if len(transcript) > 150 else ''}")
            print(f"    Language: {lang}")

            now = datetime.now(KST)
            event = {
                "event_type": "voice_report",
                "description": f"At {now.strftime('%I:%M %p')}, user voice report: \"{transcript[:100]}\"",
                "health_data": {
                    "transcript": transcript,
                    "language": lang,
                    "duration_sec": round(duration, 1),
                    "time": now.isoformat(),
                },
                "confidence": 0.8,
                "objects_detected": [],
            }

            print(f"    >> {event['description']}")

            eid = self.upload_event(event, path.name)
            if eid:
                print(f"    Supabase: event_id={eid}")

            self._log_event(event, path.name)

        except Exception as e:
            print(f"    Audio error: {e}")

    # ── Local Log ──

    def _log_event(self, event: dict, source: str):
        log_dir = PROJECT_ROOT / "backend" / "glasses_watcher" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"source": source, **event}, ensure_ascii=False, default=str) + "\n")

    # ── File Router ──

    # ── Step 2: Auto-distribute to proper tables ──

    def _write_biometric_row(self, user_id: int, fields: dict):
        """Insert biometric measurement (heart rate, BP, glucose, etc.) from voice."""
        row = {"user_id": user_id, "measured_at": datetime.now(KST).isoformat(),
               "device_type": "voice_report"}
        if fields.get("heart_rate") is not None:  row["heart_rate"] = int(fields["heart_rate"])
        if fields.get("glucose_mgdl") is not None: row["glucose_mgdl"] = float(fields["glucose_mgdl"])
        # sbp/dbp not in schema — skip until BP columns added
        try:
            httpx.post(f"{SUPABASE_URL}/rest/v1/user_biometric", json=row,
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                         "Content-Type": "application/json", "Prefer": "return=representation"},
                timeout=15).raise_for_status()
        except Exception as e:
            print(f"    user_biometric insert failed: {e}")

    def _write_health_level_row(self, user_id: int, fields: dict):
        """Insert mental-health snapshot (stress, mood, energy) from voice."""
        row = {"user_id": user_id, "measured_at": datetime.now(KST).isoformat(),
               "period_type": "voice"}
        if fields.get("stress_level") is not None:
            row["stress_level"] = int(fields["stress_level"])
        try:
            httpx.post(f"{SUPABASE_URL}/rest/v1/user_health_level", json=row,
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                         "Content-Type": "application/json", "Prefer": "return=representation"},
                timeout=15).raise_for_status()
        except Exception as e:
            print(f"    user_health_level insert failed: {e}")

    def _write_lifestyle_row(self, user_id: int, fields: dict):
        """Upsert today's user_lifestyle row.

        Exercise merge logic:
          - SAME exercise_type as existing: MAX(existing, new) — prevents
            double-counting when the user mentions the same workout twice.
          - DIFFERENT exercise_type: SUM(existing, new) — accumulates a
            morning run (30 min "running") + evening warm-ups (5 min) into
            the daily total (35 min "running, warm-ups").
        Sleep: latest wins.
        """
        today_kst = datetime.now(KST).date().isoformat()
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        try:
            existing = httpx.get(
                f"{SUPABASE_URL}/rest/v1/user_lifestyle",
                params={
                    "user_id": f"eq.{user_id}",
                    "recorded_date": f"eq.{today_kst}",
                    "data_source": "eq.ai_glasses_voice",
                    "select": "ls_id,exercise_min,exercise_type,sleep_hours",
                    "order": "ls_id.asc",
                    "limit": "1",
                },
                headers=headers,
                timeout=15,
            )
            existing.raise_for_status()
            rows = existing.json()

            if rows:
                ls_id = rows[0]["ls_id"]
                patch = {}
                if fields.get("exercise_min") is not None:
                    existing_min  = rows[0].get("exercise_min") or 0
                    existing_type = (rows[0].get("exercise_type") or "").strip()
                    new_min       = fields["exercise_min"]
                    new_type      = (fields.get("exercise_type") or "").strip()
                    same_type = (
                        existing_type and new_type
                        and existing_type.lower() == new_type.lower()
                    )
                    if same_type:
                        # Same exercise mentioned twice — dedupe with MAX.
                        patch["exercise_min"] = max(existing_min, new_min)
                        patch["exercise_type"] = new_type
                    else:
                        # Different exercise types or one missing — accumulate.
                        patch["exercise_min"] = existing_min + new_min
                        if existing_type and new_type:
                            # Append new type if not already in the list
                            if new_type.lower() not in existing_type.lower():
                                patch["exercise_type"] = f"{existing_type}, {new_type}"
                            else:
                                patch["exercise_type"] = existing_type
                        else:
                            patch["exercise_type"] = new_type or existing_type
                for k in ("sleep_start", "sleep_end", "sleep_hours", "wake_count"):
                    if fields.get(k) is not None:
                        patch[k] = fields[k]
                if patch:
                    httpx.patch(
                        f"{SUPABASE_URL}/rest/v1/user_lifestyle",
                        params={"ls_id": f"eq.{ls_id}"},
                        json=patch,
                        headers=headers,
                        timeout=15,
                    ).raise_for_status()
            else:
                row = {"user_id": user_id, "recorded_date": today_kst,
                       "data_source": "ai_glasses_voice"}
                row.update({k: v for k, v in fields.items() if v is not None})
                httpx.post(
                    f"{SUPABASE_URL}/rest/v1/user_lifestyle",
                    json=row,
                    headers=headers,
                    timeout=15,
                ).raise_for_status()
        except Exception as e:
            print(f"    user_lifestyle upsert failed: {e}")

    def distribute_to_tables(self, event_data: dict, user_id: int = TEST_USER_ID,
                             skip_meal_placeholder: bool = False,
                             skip_drink_placeholder: bool = False) -> dict:
        """Automatically extract health facts and save to proper tables.

        Returns a summary dict with flags indicating which categories produced
        writes. Callers can use this to dedupe visual + audio from the same
        video (e.g. skip visual's generic 'drink (cup)' if audio transcript
        already wrote a named beverage like '홍차').

        `skip_meal_placeholder=True` suppresses the generic 400-kcal "lunch"/
        "snack"/"meal" food_log row that fires for `event_type=="meal"`. Set
        this when CNN cascade or Phase 2 multimodal has already written
        specific dishes for this image/video — otherwise the dashboard
        double-counts kcal (placeholder + specific dishes).

        `skip_drink_placeholder=True` does the same for the generic 0-kcal
        "drink (cup)" hydration row that fires for `event_type=="drink"`.
        Set this when Phase 2 already wrote a specific drink (e.g.
        "스퀴즈 오렌지 에이드 drink") — otherwise Hydration tab shows two
        rows for one physical drink (specific name + cup placeholder).
        """
        # audio_drink: True only when audio identified a drink/beverage (not solid food).
        # Used by process_video() to decide whether to skip visual cup detection.
        # Keeping it separate from food_or_drink prevents hallucinated solid-food
        # extractions from suppressing a real visual drink signal.
        summary = {"food_or_drink": False, "audio_drink": False, "biometric": False,
                   "mental": False, "exercise": False, "sleep": False,
                   "exercise_time": None,  # "HH:MM" if user stated a specific time
                   "audio_food_names": []}  # names of foods/drinks written by audio arm — used by Phase 2 supplement to dedup

        sys.path.insert(0, str(Path(__file__).parent))
        from event_processor import EventProcessor
        processor = EventProcessor()

        event_type = event_data.get("event_type", "")
        health_data = event_data.get("health_data", {})

        if event_type == "voice_report":
            transcript = health_data.get("transcript", "")
            if transcript:
                # Guard: if the transcript contains no health-related keywords,
                # neither the LLM nor the regex extractor can produce meaningful
                # health data. Skipping avoids Haiku hallucinating food names
                # from demo/test videos that have no health content at all.
                _HEALTH_KW = [
                    # Korean
                    "먹", "마시", "음식", "음료", "식사", "밥", "운동", "약", "수면",
                    "잠", "비타민", "체중", "몸무게", "혈압", "혈당",
                    # English
                    "eat", "ate", "food", "drink", "drank", "lunch", "dinner",
                    "breakfast", "snack", "meal", "exercise", "walk", "run",
                    "gym", "workout", "medicine", "pill", "vitamin", "supplement",
                    "sleep", "slept", "woke", "weight", "kg", "water", "coffee",
                    "tea", "juice", "calorie", "kcal", "protein",
                ]
                t_lower = transcript.lower()
                has_health_content = any(kw in t_lower for kw in _HEALTH_KW)
                if not has_health_content:
                    print(f"    No health keywords in transcript — skipping extraction")
                    return summary

                # Try LLM-based extraction first (handles any phrasing).
                # Falls back to regex-based extraction if API key missing or call fails.
                extracted = None
                try:
                    from llm_extractor import extract_health_facts, to_legacy_format
                    llm_result = extract_health_facts(transcript)
                    if llm_result:
                        extracted = to_legacy_format(llm_result)
                        print(f"    LLM extraction: {len(extracted['foods'])} foods, "
                              f"{len(extracted['drinks'])} drinks, "
                              f"{len(extracted['medications'])} meds")
                        # Write biometrics + mental health from LLM (regex can't)
                        bio = extracted.get("biometrics") or {}
                        if any(bio.values()):
                            self._write_biometric_row(user_id, bio)
                            print(f"    -> user_biometric: {bio}")
                        mental = extracted.get("mental") or {}
                        if mental.get("stress_level") is not None:
                            self._write_health_level_row(user_id, mental)
                            print(f"    -> user_health_level: stress={mental.get('stress_level')}")
                except Exception as e:
                    print(f"    LLM extractor unavailable ({e}), using regex fallback")

                if extracted is None:
                    extracted = processor.extract_from_transcript(transcript)
                    # Write biometrics + mental from regex path too
                    bio = extracted.get("biometrics") or {}
                    if any(bio.values()):
                        self._write_biometric_row(user_id, bio)
                        print(f"    -> user_biometric: {bio}")
                    mental = extracted.get("mental") or {}
                    if mental.get("stress_level") is not None:
                        self._write_health_level_row(user_id, mental)
                        print(f"    -> user_health_level: stress={mental.get('stress_level')}")

                # LLM may produce a "drinks" list separate from "foods".
                # Write each as a named food_log row (0 kcal, portion_g = ml).
                for drink in extracted.get("drinks", []):
                    processor.write_food_log(user_id, drink)
                    summary["food_or_drink"] = True
                    summary["audio_drink"] = True
                    _name = (drink.get("name") or "").strip()
                    if _name:
                        summary["audio_food_names"].append(_name)

                _BEVERAGE_KW = {
                    "커피", "coffee", "차", "tea", "물", "water", "주스", "juice",
                    "우유", "milk", "음료", "latte", "라떼", "americano", "아메리카노",
                    "soda", "탄산", "녹차", "홍차", "아이스티", "drink", "beverage",
                }
                for food in extracted["foods"]:
                    processor.write_food_log(user_id, food)
                    summary["food_or_drink"] = True
                    _name = (food.get("name") or "").strip()
                    if _name:
                        summary["audio_food_names"].append(_name)
                    # Regex path puts drinks in foods[] — flag them so process_video
                    # skips the generic visual "drink (cup)" dedup check correctly.
                    if any(kw in food.get("name", "").lower() for kw in _BEVERAGE_KW):
                        summary["audio_drink"] = True
                for med in extracted["medications"]:
                    processor.write_medication(user_id, med)

                # Exercise → write to user_lifestyle
                if extracted["exercise"]:
                    ex = extracted["exercise"]
                    self._write_lifestyle_row(user_id, {
                        "exercise_min":  ex["minutes"],
                        "exercise_type": ex.get("type"),
                    })
                    ex_time = ex.get("event_time")
                    time_note = f" at {ex_time}" if ex_time else ""
                    print(f"    -> user_lifestyle: exercise {ex['minutes']}min ({ex.get('type')}){time_note}")
                    summary["exercise"] = True
                    summary["exercise_time"] = ex_time  # pass back to process_video for detected_at patch

                # Sleep → write to user_lifestyle
                if extracted["sleep"]:
                    sleep = extracted["sleep"]
                    self._write_lifestyle_row(user_id, {
                        "sleep_hours": sleep.get("hours"),
                        "wake_count":  None,
                    })
                    print(f"    -> user_lifestyle: wake_time {sleep.get('wake_time')}")
                    summary["sleep"] = True

                # Hydration from voice → log as named drink in user_food_log.
                # Regex-path fallback only — if the LLM path already wrote drinks
                # individually above, skip this to avoid double-logging the same beverage.
                if extracted["hydration"] and not extracted.get("foods") and not extracted.get("drinks"):
                    hyd = extracted["hydration"]
                    processor.write_food_log(user_id, {
                        "name":       hyd.get("type", "water"),
                        "serving_g":  hyd.get("ml", 250),
                        "kcal":       0,
                        "protein_g":  0,
                        "fat_g":      0,
                        "carb_g":     0,
                    })
                    print(f"    -> user_food_log: {hyd.get('type')} ({hyd.get('ml')}ml)")
                    summary["food_or_drink"] = True
                    summary["audio_drink"] = True

        elif event_type == "drink":
            ml = health_data.get("hydration_ml", 250)
            container = health_data.get("container", "cup")
            if skip_drink_placeholder:
                # Phase 2 / CNN already wrote a specific drink row — the
                # generic "drink (cup)" placeholder would double-count
                # hydration in the dashboard.
                print(f"    (skipping generic drink placeholder — specific drink already written)")
            else:
                processor.write_food_log(user_id, {
                    "name": f"drink ({container})",
                    "kcal": 0, "protein_g": 0, "fat_g": 0, "carb_g": 0,
                })
                print(f"    -> Hydration: {ml}ml ({container})")
                summary["food_or_drink"] = True

        elif event_type == "meal":
            if skip_meal_placeholder:
                # CNN cascade / Phase 2 already wrote specific dishes — the
                # generic 400-kcal placeholder would double-count.
                print(f"    (skipping generic meal placeholder — specific dishes already written)")
            else:
                processor.write_food_log(user_id, {
                    "name": health_data.get("meal_type", "meal"),
                    "kcal": 400, "protein_g": 15, "fat_g": 15, "carb_g": 50,
                })
                summary["food_or_drink"] = True

        return summary

    def _rename_aimb_to_human(self, path: Path) -> Path:
        """Rename AIMB-Bridge clips from `YYYYMMDDhhmmssXXX.mp4` to
        `YYYYMMDD_hh-mm-ss.mp4` so the wall-clock time is readable at a glance.

        Returns the (possibly new) Path. Silently no-op if the filename
        doesn't match the 17-digit AIMB pattern. Safe to re-run; collisions
        are avoided by appending `_<ms>` when the target already exists.
        """
        import re as _re
        stem = path.stem
        m = _re.match(r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{3})$", stem)
        if not m:
            return path  # not an AIMB-format filename, leave it
        yr, mo, dy, hh, mm, ss, ms = m.groups()
        new_name = f"{yr}{mo}{dy}_{hh}-{mm}-{ss}{path.suffix}"
        new_path = path.with_name(new_name)
        if new_path.exists():
            # Collision (e.g. two clips with same hh-mm-ss). Disambiguate
            # with the millisecond portion.
            new_name = f"{yr}{mo}{dy}_{hh}-{mm}-{ss}_{ms}{path.suffix}"
            new_path = path.with_name(new_name)
            if new_path.exists():
                return path  # give up; keep original
        try:
            path.rename(new_path)
            print(f"    [rename] {path.name} → {new_path.name}")
            return new_path
        except Exception as e:
            print(f"    [rename] failed for {path.name}: {e}")
            return path

    def process_file(self, path: Path):
        # Pre-step: humanize AIMB filenames before any processing.
        path = self._rename_aimb_to_human(path)
        ext = path.suffix.lower()
        try:
            if ext == ".heic" and not HEIC_SUPPORT:
                print(f"    Skipping .heic — install pillow-heif to enable: pip install pillow-heif")
                self.processed.add(self._file_hash(path))
                self._save_processed()
                return
            if ext in IMAGE_EXTS:
                self.process_image(path)
            elif ext in VIDEO_EXTS:
                self.process_video(path)
            elif ext in AUDIO_EXTS:
                self.process_audio(path)
        except Exception as e:
            print(f"    ERROR processing {path.name}: {e}")
        self.processed.add(self._file_hash(path))
        self._save_processed()

    # ── Upload + Distribute (combined Step 1 + Step 2) ──

    def upload_and_distribute(self, event: dict, source_file: str) -> int | None:
        """Upload to user_activity_event AND distribute to proper tables automatically."""
        # Step 1: Upload raw event
        eid = self.upload_event(event, source_file)
        if eid:
            print(f"    Supabase event_id={eid}")

        # Step 2: Auto-distribute to proper tables
        if event["event_type"] in ("voice_report", "drink", "meal", "exercise"):
            print(f"    --- Auto-distributing to tables ---")
            self.distribute_to_tables(event)

        return eid

    # ── Watch Loop ──

    def run(self):
        print("=" * 60)
        print("AI GLASSES HEALTH EVENT PIPELINE")
        print("AIMB-G1 -> Smart Health Events -> Supabase")
        print("Step 1 (detect) + Step 2 (distribute) = FULLY AUTOMATIC")
        print("=" * 60)
        print(f"\nSupabase: {SUPABASE_URL}")

        active = []
        for f in WATCH_FOLDERS:
            if f.exists():
                active.append(f)
                print(f"  [WATCHING] {f}")
            else:
                print(f"  [--skip--] {f}")

        inbox = PROJECT_ROOT / "backend" / "glasses_watcher" / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        if inbox not in active:
            active.append(inbox)
            print(f"  [WATCHING] {inbox}")

        # First-scan summary — so silent skips (wrong date filter, HEIC, etc.)
        # can never again masquerade as "nothing happening".
        total = 0
        recent = 0
        heic_total = 0
        heic_recent = 0
        lookback_h = RECENT_FILE_LOOKBACK_SECONDS // 3600
        now_ts = time.time()
        for folder in active:
            for f in folder.rglob("*"):
                if not f.is_file():
                    continue
                if f.suffix.lower() not in IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS:
                    continue
                total += 1
                is_recent = now_ts - f.stat().st_mtime <= RECENT_FILE_LOOKBACK_SECONDS
                if is_recent:
                    recent += 1
                if f.suffix.lower() == ".heic":
                    heic_total += 1
                    if is_recent:
                        heic_recent += 1
        heic_note = "enabled" if HEIC_SUPPORT else "DISABLED — run: pip install pillow-heif"
        print(f"\nScan: {total} media files total, {recent} within last {lookback_h}h")
        print(f"HEIC support: {heic_note} ({heic_recent} recent HEIC / {heic_total} total)")
        print(f"Already processed: {len(self.processed)}")

        print(f"\nDrop photos/videos/audio into inbox folder to test.")
        print(f"Or set up OneDrive Camera Upload for automatic flow.")
        print(f"\nWaiting for files... (Ctrl+C to stop)")
        print("-" * 60)

        try:
            while True:
                for folder in active:
                    for f in sorted(folder.rglob("*"), key=lambda x: x.stat().st_mtime):
                        if not f.is_file():
                            continue
                        if f.suffix.lower() not in IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS:
                            continue
                        # Use min(mtime_age, ctime_age): Windows `copy` preserves source
                        # mtime but sets ctime=now, so recently-copied old videos are found.
                        _st = f.stat()
                        _file_age = min(time.time() - _st.st_mtime, time.time() - _st.st_ctime)
                        if _file_age > RECENT_FILE_LOOKBACK_SECONDS:
                            continue
                        if self._file_hash(f) in self.processed:
                            continue

                        current_size = f.stat().st_size
                        last = self._size_history.get(f)
                        now = time.time()
                        if last is None or last[0] != current_size:
                            self._size_history[f] = (current_size, now)
                            continue
                        if now - last[1] < 2.0:
                            continue

                        self._size_history.pop(f, None)
                        print(f"\n{'=' * 60}")
                        print(f"NEW: {f.name} ({current_size / 1024:.0f} KB)")
                        self.process_file(f)
                time.sleep(3)
        except KeyboardInterrupt:
            print(f"\nStopped. Total processed: {len(self.processed)}")
            self._save_processed()


if __name__ == "__main__":
    SmartGlassesWatcher().run()
