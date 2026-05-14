"""Lifelog watcher — auto-runs Gemma 4 + Qwen 3.5 VLM (+ optional Llama 4 Maverick) on every new video.

Sibling to watcher.py. Watches the same OneDrive Camera Roll folders for new
videos and runs the lifelog extraction pipeline (Gemma 4 E4B on Mac mini +
Qwen 3.5 VLM 397B via NVIDIA NIM, and optionally Llama 4 Maverick 17B/128E
via NVIDIA NIM) on each one. Each model's events are written to the
`lifelog_event` table tagged with source_model so you can filter / compare
them in the /lifelog dashboard.

Llama 4 is opt-in (--llama4) because it consumes NVIDIA NIM credits on top
of Qwen — keeps existing watcher cost unchanged unless you ask for it.

Independent of watcher.py:
  - separate processed-file cache (lifelog_processed.json) so the two watchers
    don't fight over the same seen-list
  - videos only (lifelog only makes sense over a time window)
  - safe to run side-by-side with watcher.py

Usage:
  cd C:\\Users\\tripleh\\projects\\healthcare-ai-agent\\backend
  python glasses_watcher\\lifelog_watcher.py
  python glasses_watcher\\lifelog_watcher.py --no-compare     # Gemma only
  python glasses_watcher\\lifelog_watcher.py --llama4         # + Llama 4 Maverick
  python glasses_watcher\\lifelog_watcher.py --user-id 2
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

import builtins
_orig_print = builtins.print
def print(*args, **kwargs):
    kwargs.setdefault("flush", True)
    _orig_print(*args, **kwargs)

sys.path.insert(0, str(Path(__file__).parent))
from _lifelog_test import run as run_lifelog

PROJECT_ROOT = Path(__file__).parent.parent.parent
KST = timezone(timedelta(hours=9))

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv"}
RECENT_FILE_LOOKBACK_SECONDS = 48 * 3600

PROCESSED_FILE = PROJECT_ROOT / "backend" / "glasses_watcher" / "lifelog_processed.json"


def _camera_roll_folders() -> list:
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
        Path.home() / "AIMB-Bridge",
        PROJECT_ROOT / "backend" / "glasses_watcher" / "inbox",
    ]
)


class LifelogWatcher:

    def __init__(self, compare: bool, user_id: int, chunk_sec: int, frames: int,
                 llama4: bool = False):
        self.compare = compare
        self.llama4 = llama4
        self.user_id = user_id
        self.chunk_sec = chunk_sec
        self.frames = frames
        self.processed = self._load_processed()
        self._size_history: dict[Path, tuple[int, float]] = {}

    def _load_processed(self) -> set:
        if PROCESSED_FILE.exists():
            try:
                return set(json.loads(PROCESSED_FILE.read_text()).get("files", []))
            except Exception:
                return set()
        return set()

    def _save_processed(self):
        PROCESSED_FILE.parent.mkdir(parents=True, exist_ok=True)
        PROCESSED_FILE.write_text(json.dumps({"files": list(self.processed)}))

    def _file_hash(self, path: Path) -> str:
        return hashlib.md5(
            f"{path.name}_{path.stat().st_size}_{path.stat().st_mtime}".encode()
        ).hexdigest()

    def _process_video(self, path: Path):
        try:
            run_lifelog(
                video_path=path,
                compare=self.compare,
                chunk_sec=self.chunk_sec,
                frames_per_chunk=self.frames,
                write_supabase=True,
                user_id=self.user_id,
                llama4=self.llama4,
            )
            self.processed.add(self._file_hash(path))
            self._save_processed()
        except Exception as e:
            print(f"  [lifelog] failed on {path.name}: {type(e).__name__}: {str(e)[:200]}")
            self.processed.add(self._file_hash(path))
            self._save_processed()

    def run(self):
        active = [f for f in WATCH_FOLDERS if f.exists()]
        arms = ["Gemma 4"]
        if self.compare: arms.append("Qwen 3.5 VLM")
        if self.llama4:  arms.append("Llama 4 Maverick")
        print("=" * 60)
        print(f"Lifelog Watcher — {' + '.join(arms)}")
        print(f"User ID: {self.user_id}")
        print(f"Chunk size: {self.chunk_sec}s, frames/chunk: {self.frames}")
        print(f"Lookback: {RECENT_FILE_LOOKBACK_SECONDS // 3600}h")
        print(f"Already processed: {len(self.processed)} videos")
        print("\nWatching folders:")
        for f in active:
            print(f"  - {f}")
        print("\nWaiting for new videos... (Ctrl+C to stop)")
        print("-" * 60)

        try:
            while True:
                for folder in active:
                    for f in sorted(folder.rglob("*"), key=lambda x: x.stat().st_mtime):
                        if not f.is_file():
                            continue
                        if f.suffix.lower() not in VIDEO_EXTS:
                            continue
                        _st = f.stat()
                        _age = min(time.time() - _st.st_mtime, time.time() - _st.st_ctime)
                        if _age > RECENT_FILE_LOOKBACK_SECONDS:
                            continue
                        if self._file_hash(f) in self.processed:
                            continue

                        # Wait for file to finish syncing (size stable for 2s)
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
                        print(f"NEW VIDEO: {f.name} ({current_size / 1024 / 1024:.1f} MB)")
                        self._process_video(f)

                time.sleep(3)
        except KeyboardInterrupt:
            print(f"\nStopped. Total processed: {len(self.processed)}")
            self._save_processed()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lifelog watcher — auto-extract from new videos")
    parser.add_argument("--no-compare", action="store_true",
                        help="run Gemma only (skip Qwen 3.5 VLM)")
    parser.add_argument("--llama4", action="store_true",
                        help="also run Llama 4 Maverick via NVIDIA NIM")
    parser.add_argument("--user-id", type=int, default=1,
                        help="user_id to tag events with (default 1)")
    parser.add_argument("--chunk-sec", type=int, default=60,
                        help="chunk duration in seconds (default 60)")
    parser.add_argument("--frames", type=int, default=8,
                        help="frames per chunk (default 8)")
    args = parser.parse_args()

    LifelogWatcher(
        compare=(not args.no_compare),
        llama4=args.llama4,
        user_id=args.user_id,
        chunk_sec=args.chunk_sec,
        frames=args.frames,
    ).run()
