"""Extract video frames for the Job 2 training dataset (read-only).

PyAV-based uniform frame sampling within a time window. Chunks in this DB have no
start_sec/end_sec, so windows are derived by EVEN-SPLITTING the video duration across
the chunks present (`compute_chunk_window`) — kept as a separate helper so it's
testable without decoding video.

Defensive by design: a missing file raises (loud, not silent); a short video or a
decode error returns the frames gathered so far so one bad clip can't crash a build.
PyAV is already in the venv (Whisper path) — read-only usage, no DLL-stack impact.
"""
from __future__ import annotations

import os
from pathlib import Path

import av
from PIL import Image

TARGET_SIZE = (1600, 1200)  # source resolution — no up/down-scale, just normalize


def compute_chunk_window(video_duration: float, chunk_idx: int, total_chunks: int) -> tuple[float, float]:
    """Even-split window for a chunk: the video is divided into `total_chunks` equal
    spans and chunk `chunk_idx` gets its span. e.g. 61.6s / 2 chunks → chunk 0 (0, 30.8),
    chunk 1 (30.8, 61.6). Degenerate total_chunks (<=0) → the whole video."""
    dur = float(video_duration)
    if total_chunks <= 0:
        return (0.0, dur)
    start = (chunk_idx / total_chunks) * dur
    end = ((chunk_idx + 1) / total_chunks) * dur
    return (float(start), float(end))


def get_video_duration(video_path: str) -> float:
    """Video duration in seconds (stream duration preferred, container as fallback)."""
    if not Path(video_path).exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    container = av.open(video_path)
    try:
        stream = container.streams.video[0]
        if stream.duration is not None and stream.time_base is not None:
            return float(stream.duration * stream.time_base)
        if container.duration is not None:
            return float(container.duration) / av.time_base
        return 0.0
    finally:
        container.close()


def extract_frames_uniform(
    video_path: str,
    output_dir: str,
    num_frames: int = 16,
    start_sec: float = 0.0,
    end_sec: float = 60.0,
    prefix: str = "frame",
) -> list[str]:
    """Extract `num_frames` uniformly across [start_sec, end_sec], saved as
    `<prefix>_NNN.png` (zero-padded 3-digit). Returns absolute paths actually written.

    - Missing file → FileNotFoundError (loud).
    - end_sec beyond the video → clamped to the real duration (partial list, warned).
    - Decode/seek error mid-way → log + return what was gathered (no crash).
    """
    if not Path(video_path).exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    os.makedirs(output_dir, exist_ok=True)
    if num_frames <= 0 or end_sec <= start_sec:
        return []

    # Clamp the window to the real duration so out-of-range targets don't duplicate the tail.
    duration = get_video_duration(video_path)
    eff_end = min(end_sec, duration) if duration > 0 else end_sec
    if eff_end <= start_sec:
        print(f"[INFO] frame_extractor: window [{start_sec:.1f},{end_sec:.1f}] beyond "
              f"duration {duration:.1f}s -> nothing to extract")
        return []
    if eff_end < end_sec:
        print(f"[INFO] frame_extractor: clamped end {end_sec:.1f}->{eff_end:.1f}s (video duration)")

    span = eff_end - start_sec
    timestamps = [start_sec + (i + 0.5) * span / num_frames for i in range(num_frames)]

    saved: list[str] = []
    container = av.open(video_path)
    try:
        stream = container.streams.video[0]
        for i, target in enumerate(timestamps):
            try:
                # Seek to the keyframe at/just before target (container time_base = av.time_base µs),
                # then decode forward to the first frame whose presentation time >= target.
                container.seek(int(target * av.time_base), backward=True, any_frame=False)
                picked = None
                for frame in container.decode(stream):
                    picked = frame  # keep last as fallback (e.g. near the very end)
                    if frame.time is not None and frame.time >= target:
                        break
                if picked is None:
                    continue
                img = picked.to_image()
                if img.size != TARGET_SIZE:
                    img = img.resize(TARGET_SIZE)
                out_path = Path(output_dir) / f"{prefix}_{i:03d}.png"
                img.save(out_path, "PNG")
                saved.append(str(out_path))
            except Exception as e:  # per-frame seek/decode failure → skip that frame
                print(f"[ERR] frame_extractor: frame {i} @ {target:.1f}s failed: "
                      f"{type(e).__name__}: {str(e)[:120]}")
                continue
    except Exception as e:
        print(f"[ERR] frame_extractor: extraction aborted after {len(saved)} frames: "
              f"{type(e).__name__}: {str(e)[:120]}")
    finally:
        container.close()
    return saved
