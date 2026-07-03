"""Unit test for ocr_preprocessor against the 12 ground-truth KBS screenshots.

Asserts:
  * Module imports cleanly + reports a mode.
  * At least 30 unique text items are detected across the 12 frames.
  * Broadcast mode is True for at least one frame (KOSPI/KOSDAQ visible).
  * Latency reported, OCR mode reported.

Run from project root:
    .venv\\Scripts\\python.exe -m backend.glasses_watcher.tests.test_ocr_preprocessor

(or with pytest if installed:)
    .venv\\Scripts\\python.exe -m pytest backend\\glasses_watcher\\tests\\test_ocr_preprocessor.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a script: add backend/ to sys.path so we can import the
# sibling module without the `backend.glasses_watcher.` package prefix.
HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from glasses_watcher import ocr_preprocessor as op  # noqa: E402

SCREENSHOT_DIR = Path(r"C:\Users\A\projects\healthcare-ai-agent\test_data\kbs_clip\screenshots")


def _load_screenshots() -> tuple[list, list[float]]:
    """Load the 12 KBS screenshots as PIL Images + synthetic timestamps."""
    from PIL import Image
    files = sorted(SCREENSHOT_DIR.glob("*.png"))
    if not files:
        raise FileNotFoundError(f"No screenshots at {SCREENSHOT_DIR}")
    frames = [Image.open(p).convert("RGB") for p in files]
    timestamps = [i * 5.0 for i in range(len(frames))]  # synthetic 5s spacing
    return frames, timestamps


def test_ocr_on_kbs_screenshots() -> dict:
    assert op.OCR_AVAILABLE, "PaddleOCR / imagehash not importable - install failed"
    frames, ts = _load_screenshots()
    assert len(frames) == 12, f"Expected 12 ground-truth screenshots, got {len(frames)}"

    op.reset_phash_cache()
    result = op.extract_text_from_frames(frames, ts)

    print()
    print("=" * 60)
    print(f"OCR mode:                 {result.get('ocr_mode')}")
    print(f"Frames processed:         {len(result['per_frame'])}")
    print(f"Total unique text items:  {result['total_unique_text_items']}")
    print(f"Broadcast mode detected:  {result['broadcast_mode_detected']}")
    print(f"OCR latency:              {result['ocr_latency_sec']:.2f}s "
          f"({result['ocr_latency_sec'] / max(1, len(frames)):.2f}s/frame)")
    print("=" * 60)
    print("\nFirst 30 unique text items detected:")
    for line in result["ocr_full_text"].split("\n")[:30]:
        print(f"  - {line}")
    print()

    # Schema sanity
    assert "ocr_full_text" in result
    assert "per_frame" in result
    assert "broadcast_mode_detected" in result
    assert "total_unique_text_items" in result
    assert "ocr_latency_sec" in result
    for f in result["per_frame"]:
        assert {"frame_idx", "timestamp_sec", "text_boxes",
                "broadcast_mode", "text_density"} <= set(f.keys())

    # Recall floor — spec says assert >=30 unique text items.
    assert result["total_unique_text_items"] >= 30, (
        f"FAIL: only {result['total_unique_text_items']} unique items "
        f"(expected >=30 across 12 KBS screenshots)"
    )

    # At least one broadcast-mode frame (KOSPI/KOSDAQ are clearly visible).
    assert result["broadcast_mode_detected"], (
        "FAIL: no frame flagged broadcast_mode despite KBS news content"
    )

    print("[OK] test_ocr_on_kbs_screenshots PASSED")
    return result


if __name__ == "__main__":
    try:
        test_ocr_on_kbs_screenshots()
        sys.exit(0)
    except AssertionError as e:
        print(f"\n[ERR] assertion failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERR] {type(e).__name__}: {e}")
        sys.exit(2)
