"""
watcher_gemma.py — Gemma 4 multimodal pipeline, Supabase-writing.

Drop-in companion to watcher.py. Watches the same folders; for every new video,
runs Gemma 4 E4B multimodal extraction (8 frames + Whisper transcript) and writes
results directly to Supabase: user_food_log, user_medication_intake, user_lifestyle.

Runs independently — does NOT modify watcher.py. Uses processed_gemma.json so
the two watchers track files separately and don't block each other.

Tags all rows: data_source='gemma_multimodal' — easy to filter on dashboard.
98% of dashboard data is mock → hallucinations are acceptable (decision 2026-04-30).

Usage:
  cd C:\\Users\\tripleh\\projects\\healthcare-ai-agent
  C:\\Users\\tripleh\\AppData\\Local\\Python\\pythoncore-3.11-64\\python.exe backend/glasses_watcher/watcher_gemma.py
"""

import io
import json
import os
import subprocess
import sys
import time
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

import builtins
_orig_print = builtins.print
def print(*args, **kwargs):
    kwargs.setdefault("flush", True)
    _orig_print(*args, **kwargs)

import httpx

# ── Config ──

PROJECT_ROOT = Path(__file__).parent.parent.parent
KST = timezone(timedelta(hours=9))

SUPABASE_URL = ""
SUPABASE_KEY = ""
env_path = PROJECT_ROOT / "backend" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("SUPABASE_URL="):
            SUPABASE_URL = line.split("=", 1)[1].strip()
        elif line.startswith("SUPABASE_SERVICE_ROLE_KEY="):
            SUPABASE_KEY = line.split("=", 1)[1].strip()

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

WATCH_FOLDERS = [
    Path.home() / "OneDrive" / "Pictures" / "Camera Roll",
    Path.home() / "OneDrive" / "Pictures",
    PROJECT_ROOT / "backend" / "glasses_watcher" / "inbox",
]

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv"}
RECENT_FILE_LOOKBACK_SECONDS = 48 * 3600
PROCESSED_FILE = PROJECT_ROOT / "backend" / "glasses_watcher" / "processed_gemma.json"
TEST_USER_ID = 1

# Calorie fallback table for items Gemma identifies that aren't in the food DB.
# Prioritises known branded snacks we've seen in testing.
CALORIE_FALLBACK = {
    "snickers": {"kcal": 250, "protein_g": 4, "fat_g": 12, "carb_g": 33, "serving_g": 52},
    "twix":     {"kcal": 250, "protein_g": 3, "fat_g": 12, "carb_g": 33, "serving_g": 50},
    "oreo":     {"kcal": 160, "protein_g": 1, "fat_g":  7, "carb_g": 25, "serving_g": 34},
    "kitkat":   {"kcal": 210, "protein_g": 3, "fat_g": 11, "carb_g": 28, "serving_g": 41},
    "lays":     {"kcal": 160, "protein_g": 2, "fat_g": 10, "carb_g": 15, "serving_g": 28},
    "beverage": {"kcal":   0, "protein_g": 0, "fat_g":  0, "carb_g":  0, "serving_g": 250},
    "water":    {"kcal":   0, "protein_g": 0, "fat_g":  0, "carb_g":  0, "serving_g": 250},
    "coffee":   {"kcal":   5, "protein_g": 0, "fat_g":  0, "carb_g":  0, "serving_g": 250},
    "tea":      {"kcal":   2, "protein_g": 0, "fat_g":  0, "carb_g":  0, "serving_g": 250},
    "juice":    {"kcal": 110, "protein_g": 1, "fat_g":  0, "carb_g": 26, "serving_g": 250},
    "milk":     {"kcal": 150, "protein_g": 8, "fat_g":  8, "carb_g": 12, "serving_g": 250},
    "soda":     {"kcal": 140, "protein_g": 0, "fat_g":  0, "carb_g": 39, "serving_g": 355},
    "beer":     {"kcal": 150, "protein_g": 1, "fat_g":  0, "carb_g": 13, "serving_g": 355},
}
_DEFAULT_KCAL = 150   # conservative unknown snack estimate
_DEFAULT_SERVING_G = 100


# ── Nutrition lookup ──

def _lookup_nutrition(food_name: str) -> dict:
    """
    Return nutrition dict for food_name.
    Priority: CALORIE_FALLBACK by partial match → MFDS/USDA SQLite → generic defaults.
    """
    name_lower = food_name.lower()

    # 1. Exact or partial match in branded fallback table
    for key, info in CALORIE_FALLBACK.items():
        if key in name_lower:
            return {**info, "source": "fallback_table"}

    # 2. MFDS / USDA SQLite (289K foods)
    mfds_path = PROJECT_ROOT / "backend" / "data" / "food_db" / "food_nutrition.db"
    usda_path = PROJECT_ROOT / "backend" / "data" / "food_db" / "usda_food_nutrition.db"
    try:
        import sqlite3
        if mfds_path.exists():
            conn = sqlite3.connect(str(mfds_path))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT energy_kcal, protein_g, fat_g, carbohydrate_g, serving_size "
                "FROM foods WHERE food_name_kr LIKE ? ORDER BY LENGTH(food_name_kr) ASC LIMIT 1",
                (f"%{food_name}%",)
            ).fetchone()
            conn.close()
            if row:
                return {
                    "kcal": row["energy_kcal"] or 0,
                    "protein_g": row["protein_g"] or 0,
                    "fat_g": row["fat_g"] or 0,
                    "carb_g": row["carbohydrate_g"] or 0,
                    "serving_g": row["serving_size"] or _DEFAULT_SERVING_G,
                    "source": "MFDS",
                }
        if usda_path.exists():
            conn = sqlite3.connect(str(usda_path))
            conn.row_factory = sqlite3.Row
            food_row = conn.execute(
                "SELECT fdc_id FROM foods WHERE description LIKE ? "
                "ORDER BY LENGTH(description) ASC LIMIT 1",
                (f"%{food_name}%",)
            ).fetchone()
            if food_row:
                nutrients = {
                    r["nutrient_name"]: r["amount"]
                    for r in conn.execute(
                        "SELECT nutrient_name, amount FROM nutrients WHERE fdc_id = ? "
                        "AND nutrient_name IN ('Energy','Protein','Total lipid (fat)','Carbohydrate, by difference')",
                        (food_row["fdc_id"],)
                    ).fetchall()
                }
                conn.close()
                return {
                    "kcal": nutrients.get("Energy", 0),
                    "protein_g": nutrients.get("Protein", 0),
                    "fat_g": nutrients.get("Total lipid (fat)", 0),
                    "carb_g": nutrients.get("Carbohydrate, by difference", 0),
                    "serving_g": _DEFAULT_SERVING_G,
                    "source": "USDA",
                }
    except Exception:
        pass

    return {
        "kcal": _DEFAULT_KCAL,
        "protein_g": 3,
        "fat_g": 6,
        "carb_g": 20,
        "serving_g": _DEFAULT_SERVING_G,
        "source": "default",
    }


# ── Supabase helpers ──

def _supabase_insert(table: str, data: dict) -> dict | None:
    if not SUPABASE_KEY:
        print(f"    [gemma] no Supabase key — skipping {table} insert")
        return None
    try:
        resp = httpx.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            json=data,
            headers=SUPABASE_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json()
        return result[0] if isinstance(result, list) else result
    except Exception as e:
        print(f"    [gemma] {table} insert failed: {e}")
        return None


def _write_food_log(user_id: int, food_name: str, quantity: int):
    """Insert one row per distinct food item into user_food_log."""
    nutrition = _lookup_nutrition(food_name)
    portion_g = nutrition["serving_g"] * quantity
    now = datetime.now(KST)
    row = {
        "user_id": user_id,
        "consumed_at": now.isoformat(),
        "food_name": food_name,
        "portion_g": portion_g,
        "nutrients_json": {
            "energy_kcal": nutrition["kcal"] * quantity,
            "protein_g": nutrition["protein_g"] * quantity,
            "fat_g": nutrition["fat_g"] * quantity,
            "carbohydrate_g": nutrition["carb_g"] * quantity,
            "quantity": quantity,
            "portion_source": nutrition["source"],
            "portion_confidence": 0.65,
            "extractor": "gemma_multimodal",
        },
        "recognition_confidence": 0.75,
        "data_source": "gemma_multimodal",
    }
    result = _supabase_insert("user_food_log", row)
    if result:
        fid = result.get("food_id", "?")
        kcal = nutrition["kcal"] * quantity
        print(f"    [gemma] -> user_food_log food_id={fid} | {food_name} x{quantity} ({kcal} kcal)")


def _write_medication_intake(user_id: int, drug_name: str):
    """Insert one row into user_medication_intake."""
    now = datetime.now(timezone.utc)
    row = {
        "user_id": user_id,
        "drug_name": drug_name,
        "drug_code": "",
        "dose": 1,
        "unit": "tablet",
        "taken_at": now.isoformat(),
        "source": "gemma_multimodal",
        "confidence": 0.70,
    }
    result = _supabase_insert("user_medication_intake", row)
    if result:
        iid = result.get("intake_id", "?")
        print(f"    [gemma] -> user_medication_intake intake_id={iid} | {drug_name}")


def _write_lifestyle_exercise(user_id: int, minutes: int):
    """Upsert today's user_lifestyle row with exercise minutes (MAX merge)."""
    today_kst = datetime.now(KST).date().isoformat()
    headers = SUPABASE_HEADERS.copy()
    if not SUPABASE_KEY:
        return
    try:
        existing = httpx.get(
            f"{SUPABASE_URL}/rest/v1/user_lifestyle",
            params={
                "user_id": f"eq.{user_id}",
                "recorded_date": f"eq.{today_kst}",
                "data_source": "eq.gemma_multimodal",
                "select": "ls_id,exercise_min",
                "limit": "1",
            },
            headers=headers,
            timeout=15,
        )
        existing.raise_for_status()
        rows = existing.json()

        if rows:
            ls_id = rows[0]["ls_id"]
            merged = max(rows[0].get("exercise_min") or 0, minutes)
            httpx.patch(
                f"{SUPABASE_URL}/rest/v1/user_lifestyle",
                params={"ls_id": f"eq.{ls_id}"},
                json={"exercise_min": merged},
                headers=headers,
                timeout=15,
            ).raise_for_status()
            print(f"    [gemma] -> user_lifestyle ls_id={ls_id} | exercise_min merged to {merged}min")
        else:
            row = {
                "user_id": user_id,
                "recorded_date": today_kst,
                "exercise_min": minutes,
                "data_source": "gemma_multimodal",
            }
            result = _supabase_insert("user_lifestyle", row)
            if result:
                lid = result.get("ls_id", "?")
                print(f"    [gemma] -> user_lifestyle ls_id={lid} | exercise {minutes}min")
    except Exception as e:
        print(f"    [gemma] user_lifestyle upsert failed: {e}")


# ── Gemma extraction (reuse gemma_dual_extractor) ──

sys.path.insert(0, str(Path(__file__).parent))
try:
    from gemma_dual_extractor import gemma_extract_multimodal, gemma_extract_text
    _GEMMA_AVAILABLE = True
except Exception as e:
    print(f"[gemma_watcher] gemma_dual_extractor import failed: {e}")
    _GEMMA_AVAILABLE = False


# ── Whisper transcription ──

def _transcribe(video_path: Path) -> str:
    """Extract audio and transcribe with Whisper. Returns empty string on failure."""
    temp_dir = PROJECT_ROOT / "backend" / "glasses_watcher" / "temp_frames"
    temp_dir.mkdir(parents=True, exist_ok=True)
    audio_path = temp_dir / f"{video_path.stem}_gemma_audio.wav"
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", str(video_path), "-vn", "-acodec", "pcm_s16le",
             "-ar", "16000", "-ac", "1", "-y", str(audio_path)],
            capture_output=True, timeout=60,
        )
        if not (audio_path.exists() and audio_path.stat().st_size > 1000):
            return ""
        import whisper
        model = whisper.load_model("medium")
        wresult = model.transcribe(
            str(audio_path),
            initial_prompt="한국어와 영어를 섞어서 말하는 건강 일지 음성입니다. "
                           "Mixed Korean-English health log audio.",
            task="transcribe",
        )
        transcript = wresult["text"].strip()
        return transcript
    except Exception as e:
        print(f"    [gemma] transcription failed (non-fatal): {e}")
        return ""
    finally:
        try:
            if audio_path.exists():
                audio_path.unlink()
        except Exception:
            pass


# ── Process one video ──

def process_video(path: Path):
    print(f"\n  [GEMMA VIDEO] {path.name}")

    if not _GEMMA_AVAILABLE:
        print("    [gemma] extractor not available — skip")
        return

    # Whisper transcript
    print("    [gemma] transcribing audio...")
    transcript = _transcribe(path)
    if transcript:
        snip = transcript[:90] + ("..." if len(transcript) > 90 else "")
        print(f"    [gemma] transcript: {snip}")
    else:
        print("    [gemma] no transcript (silent video or ffmpeg missing)")

    # Gemma multimodal extraction
    print("    [gemma] calling Gemma 4 multimodal...")
    t0 = time.perf_counter()
    result, elapsed_ms, error = gemma_extract_multimodal(path, transcript)
    elapsed_s = (time.perf_counter() - t0)
    print(f"    [gemma] extraction done in {elapsed_s:.1f}s")

    if error:
        print(f"    [gemma] extraction error: {error}")
        # If multimodal fails but we have transcript, try text-only fallback
        if transcript:
            print("    [gemma] falling back to text-only extraction...")
            result, elapsed_ms, error = gemma_extract_text(transcript)
            if error:
                print(f"    [gemma] text-only also failed: {error}")
                return
        else:
            return

    if not result:
        print("    [gemma] empty result — nothing to write")
        return

    print(f"    [gemma] extracted: {json.dumps(result, ensure_ascii=False)}")

    # ── Write to Supabase ──
    foods = result.get("foods") or []
    exercise = result.get("exercise")
    medications = result.get("medications") or []

    wrote_anything = False

    for food in foods:
        name = food.get("name", "").strip()
        qty = food.get("quantity", 1)
        if not name:
            continue
        try:
            qty = int(qty) if qty else 1
        except (TypeError, ValueError):
            qty = 1
        qty = max(1, min(qty, 20))  # sanity clamp
        _write_food_log(TEST_USER_ID, name, qty)
        wrote_anything = True

    if exercise and isinstance(exercise, dict):
        minutes = exercise.get("minutes")
        if minutes:
            try:
                minutes = int(minutes)
                if 1 <= minutes <= 300:
                    _write_lifestyle_exercise(TEST_USER_ID, minutes)
                    wrote_anything = True
            except (TypeError, ValueError):
                pass

    for med in medications:
        drug_name = med.get("drug_name", "").strip()
        if drug_name:
            _write_medication_intake(TEST_USER_ID, drug_name)
            wrote_anything = True

    if not wrote_anything:
        print("    [gemma] no health items found — no Supabase writes")

    # Local audit log
    _log_gemma_event(path.name, transcript, result)


# ── Local audit log ──

def _log_gemma_event(source_file: str, transcript: str, result: dict | None):
    log_dir = PROJECT_ROOT / "backend" / "glasses_watcher" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"gemma_writes_{datetime.now(KST).date().isoformat()}.jsonl"
    record = {
        "ts_kst": datetime.now(KST).isoformat(),
        "source_file": source_file,
        "transcript": transcript,
        "gemma_result": result,
        "user_id": TEST_USER_ID,
    }
    try:
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"    [gemma] audit log write failed: {e}")


# ── Watcher loop ──

class GemmaWatcher:

    def __init__(self):
        self.processed: set = self._load_processed()
        self._size_history: dict = {}

    def _load_processed(self) -> set:
        if PROCESSED_FILE.exists():
            return set(json.loads(PROCESSED_FILE.read_text()).get("files", []))
        return set()

    def _save_processed(self):
        PROCESSED_FILE.parent.mkdir(parents=True, exist_ok=True)
        PROCESSED_FILE.write_text(json.dumps({"files": list(self.processed)}))

    def _file_hash(self, path: Path) -> str:
        return hashlib.md5(
            f"{path.name}_{path.stat().st_size}_{path.stat().st_mtime}".encode()
        ).hexdigest()

    def process_file(self, path: Path):
        if path.suffix.lower() in VIDEO_EXTS:
            try:
                process_video(path)
            except Exception as e:
                print(f"    [gemma] ERROR processing {path.name}: {e}")
        else:
            # Images and audio: Gemma text-only if no video frames available
            # For now, skip non-video — add image support in future if needed
            print(f"    [gemma] skipping non-video file: {path.name}")

        self.processed.add(self._file_hash(path))
        self._save_processed()

    def run(self):
        print("=" * 60)
        print("GEMMA 4 MULTIMODAL PIPELINE — Supabase Writer")
        print("Gemma 4 E4B Q8 (Mac mini Tailscale) → user_food_log etc.")
        print("=" * 60)
        print(f"\nSupabase: {SUPABASE_URL}")
        print(f"Gemma available: {_GEMMA_AVAILABLE}")

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

        print(f"\nAlready processed: {len(self.processed)}")
        print(f"\nWaiting for videos... (Ctrl+C to stop)")
        print(f"Rows tagged data_source='gemma_multimodal' — filter on dashboard")
        print("-" * 60)

        try:
            while True:
                for folder in active:
                    for f in sorted(folder.rglob("*"), key=lambda x: x.stat().st_mtime):
                        if not f.is_file():
                            continue
                        if f.suffix.lower() not in VIDEO_EXTS:
                            continue
                        if time.time() - f.stat().st_mtime > RECENT_FILE_LOOKBACK_SECONDS:
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
                        print(f"NEW VIDEO: {f.name} ({f.stat().st_size / 1024:.0f} KB)")
                        self.process_file(f)

                time.sleep(3)
        except KeyboardInterrupt:
            print(f"\nStopped. Total processed: {len(self.processed)}")
            self._save_processed()


if __name__ == "__main__":
    GemmaWatcher().run()
