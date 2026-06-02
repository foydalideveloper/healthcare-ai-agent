"""Shared helpers for per-arm watchers (gemma4_watcher.py etc.).

Each per-arm watcher script is a thin CLI wrapper around `run_single_arm()`
below, which delegates to `_lifelog_test.run()` with the appropriate arm
enabled and the others disabled. That keeps chunking, Whisper, parallel
dispatch, Supabase writes, and JSON-dump output all identical to the
canonical 4-arm pipeline — only the arm selection differs.

`--watch` mode polls a target folder for new .mp4 files and processes
each through the chosen arm. Per-arm dedup uses its own state file so
running `gemma4_watcher.py --watch` and `qwen_watcher.py --watch`
simultaneously won't deduplicate each other.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import _lifelog_test as t

# ── Per-arm flag mapping ───────────────────────────────────────────────
# Map a friendly arm name to (gemma, compare, llama4, gemini) flags for
# _lifelog_test.run(). compare == enable Qwen.
ARM_FLAGS: dict[str, dict[str, bool]] = {
    "gemma":  {"gemma": True,  "compare": False, "llama4": False, "gemini": False},
    "qwen":   {"gemma": False, "compare": True,  "llama4": False, "gemini": False},
    "llama4": {"gemma": False, "compare": False, "llama4": True,  "gemini": False},
    "gemini": {"gemma": False, "compare": False, "llama4": False, "gemini": True},
    # NEW gemini arms (env-override). They reuse the gemini code path; only the
    # GEMINI_MODEL differs (set via ARM_GEMINI_MODEL below). source_model is
    # auto-derived from that model string by _lifelog_test._model_to_source_tag.
    "gemini_3_1_pro_preview": {"gemma": False, "compare": False, "llama4": False, "gemini": True},
    "gemini_3_5_flash":       {"gemma": False, "compare": False, "llama4": False, "gemini": True},
}

ARM_LABELS = {
    "gemma":  "Gemma 4",
    "qwen":   "Qwen 3.5 VLM",
    "llama4": "Llama 4 Maverick",
    "gemini": "Gemini",
    "gemini_3_1_pro_preview": "Gemini 3.1 Pro Preview",
    "gemini_3_5_flash":       "Gemini 3.5 Flash",
}

# Per-arm GEMINI_MODEL override. When an arm is in this map, run_single_arm sets
# os.environ["GEMINI_MODEL"] before delegating to _lifelog_test.run(), so the
# gemini REST caller (_gemini_config) targets that model and the write path tags
# the right source_model. The plain "gemini" arm is intentionally ABSENT here so
# it keeps using GEMINI_MODEL from backend/.env (gemini-2.5-pro) — untouched.
ARM_GEMINI_MODEL = {
    "gemini_3_1_pro_preview": "gemini-3.1-pro-preview",
    "gemini_3_5_flash":       "gemini-3.5-flash",
}

DEFAULT_WATCH_DIR = Path.home() / "AIMB-Bridge"
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv"}


def _state_path(arm: str) -> Path:
    """Per-arm processed-files dedup state."""
    return Path(__file__).parent / f"processed_{arm}.json"


def _file_hash(p: Path) -> str:
    """Same algo as watcher.py:_file_hash for cross-compatibility."""
    st = p.stat()
    return hashlib.md5(f"{p.name}_{st.st_size}_{st.st_mtime}".encode()).hexdigest()


def _load_state(arm: str) -> set[str]:
    sp = _state_path(arm)
    if sp.exists():
        try:
            return set(json.loads(sp.read_text()).get("files", []))
        except Exception:
            return set()
    return set()


def _save_state(arm: str, hashes: set[str]) -> None:
    sp = _state_path(arm)
    sp.write_text(json.dumps({"files": sorted(hashes)}))


def run_single_arm(video_path: Path, arm: str, user_id: int = 1,
                   write_supabase: bool = True) -> None:
    if arm not in ARM_FLAGS:
        raise ValueError(f"unknown arm {arm!r}; expected one of {list(ARM_FLAGS)}")
    flags = ARM_FLAGS[arm]
    # Env-override gemini arms: point the REST caller at this arm's model. Each
    # watcher is its own process, so mutating os.environ here is isolated.
    if arm in ARM_GEMINI_MODEL:
        os.environ["GEMINI_MODEL"] = ARM_GEMINI_MODEL[arm]
        print(f"[{ARM_LABELS[arm]}] GEMINI_MODEL={ARM_GEMINI_MODEL[arm]}")
    t0 = time.perf_counter()
    t.run(
        video_path=video_path,
        write_supabase=write_supabase,
        user_id=user_id,
        **flags,
    )
    elapsed = time.perf_counter() - t0
    print(f"\n[{ARM_LABELS[arm]}] total wall-clock: {elapsed:.1f}s")


def watch_loop(arm: str, watch_dir: Path = DEFAULT_WATCH_DIR,
               user_id: int = 1, poll_sec: float = 3.0) -> None:
    """Poll watch_dir for new .mp4 files and process each through `arm`.

    Files present at startup are added to the dedup set without being
    processed (matches the user's spec — skip historical clips).
    """
    print(f"=== {ARM_LABELS[arm]} watcher started on {watch_dir} ===")
    if not watch_dir.exists():
        print(f"[error] watch_dir does not exist: {watch_dir}")
        return

    state = _load_state(arm)
    print(f"  loaded state: {len(state)} files previously processed by this arm")

    # Seed every existing file as already-processed so we only handle NEW arrivals.
    seeded = 0
    for f in watch_dir.iterdir():
        if not f.is_file() or f.suffix.lower() not in VIDEO_EXTS:
            continue
        h = _file_hash(f)
        if h not in state:
            state.add(h)
            seeded += 1
    if seeded:
        _save_state(arm, state)
        print(f"  seeded {seeded} pre-existing videos as already-processed")
    print(f"  watching for new .mp4 files (poll every {poll_sec:.1f}s, Ctrl+C to stop)")
    print("-" * 60)

    size_history: dict[Path, tuple[int, float]] = {}
    try:
        while True:
            time.sleep(poll_sec)
            now = time.time()
            for f in watch_dir.iterdir():
                if not f.is_file() or f.suffix.lower() not in VIDEO_EXTS:
                    continue
                h = _file_hash(f)
                if h in state:
                    continue
                # Debounce: wait until size stops growing for 2s (Syncthing copy in progress)
                size = f.stat().st_size
                last = size_history.get(f)
                if last is None or last[0] != size:
                    size_history[f] = (size, now)
                    continue
                if now - last[1] < 2.0:
                    continue
                print(f"\n[NEW] {f.name} ({size // 1024} KB)")
                try:
                    run_single_arm(f, arm, user_id=user_id, write_supabase=True)
                except Exception as e:
                    print(f"[error] processing failed: {type(e).__name__}: {e}")
                state.add(h)
                _save_state(arm, state)
                size_history.pop(f, None)
    except KeyboardInterrupt:
        print("\n[stopped]")


def make_parser(arm: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=f"{ARM_LABELS[arm]} single-arm watcher.",
    )
    p.add_argument("video", type=Path, nargs="?",
                   help="path to one video to process (omit when --watch is used)")
    p.add_argument("--watch", action="store_true",
                   help=f"poll {DEFAULT_WATCH_DIR} for new .mp4 files instead of processing one")
    p.add_argument("--watch-dir", type=Path, default=DEFAULT_WATCH_DIR,
                   help=f"watch directory (default: {DEFAULT_WATCH_DIR})")
    p.add_argument("--user-id", type=int, default=1)
    p.add_argument("--no-supabase", action="store_true",
                   help="skip writing events to Supabase (smoke-test mode)")
    return p


def main(arm: str) -> None:
    args = make_parser(arm).parse_args()
    if args.watch:
        watch_loop(arm, watch_dir=args.watch_dir, user_id=args.user_id)
    else:
        if not args.video:
            raise SystemExit("error: a video path is required unless --watch is given")
        if not args.video.exists():
            raise SystemExit(f"error: video does not exist: {args.video}")
        run_single_arm(args.video, arm, user_id=args.user_id,
                       write_supabase=not args.no_supabase)
