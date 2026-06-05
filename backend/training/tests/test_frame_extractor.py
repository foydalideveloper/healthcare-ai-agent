"""Unit + integration tests for Job 2 frame_extractor.

Pure-function tests (compute_chunk_window, filename format) always run. PyAV
integration tests use the real test clip and skip if it isn't present.

Run: {venv} -m pytest backend/training/tests/test_frame_extractor.py -v
"""
import sys
import tempfile
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[3]  # .../backend
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from training.frame_extractor import (  # noqa: E402
    compute_chunk_window,
    get_video_duration,
    extract_frames_uniform,
)

TEST_CLIP = r"C:\Users\A\AIMB-Bridge\20260528144922838.mp4"
_have_clip = Path(TEST_CLIP).exists()
needs_clip = pytest.mark.skipif(not _have_clip, reason="test clip not present")


# --- pure helper tests (no video) ---

def test_compute_chunk_window_two_chunks():
    assert compute_chunk_window(61.6, 0, 2) == pytest.approx((0.0, 30.8))
    assert compute_chunk_window(61.6, 1, 2) == pytest.approx((30.8, 61.6))


def test_compute_chunk_window_single_chunk():
    assert compute_chunk_window(61.6, 0, 1) == pytest.approx((0.0, 61.6))


def test_extract_handles_missing_video():
    with pytest.raises(FileNotFoundError):
        extract_frames_uniform("C:/nope/missing.mp4", tempfile.mkdtemp(), num_frames=4)


# --- PyAV integration tests (real clip) ---

@needs_clip
def test_get_video_duration():
    d = get_video_duration(TEST_CLIP)
    assert 50.0 < d < 75.0  # ~61.6s


@needs_clip
def test_extract_correct_number_of_frames():
    with tempfile.TemporaryDirectory() as td:
        paths = extract_frames_uniform(TEST_CLIP, td, num_frames=16, start_sec=0.0, end_sec=30.8)
        assert len(paths) == 16
        assert all(Path(p).exists() for p in paths)


@needs_clip
def test_extract_creates_output_dir():
    with tempfile.TemporaryDirectory() as td:
        nested = Path(td) / "a" / "b" / "c"
        assert not nested.exists()
        paths = extract_frames_uniform(TEST_CLIP, str(nested), num_frames=2, start_sec=0.0, end_sec=10.0)
        assert nested.exists() and len(paths) == 2


@needs_clip
def test_extract_time_window():
    # chunk 1 window of the 2-chunk clip produces the requested count, normalized size,
    # and a DISTINCT frame set from chunk 0 (proves the window actually shifts).
    from PIL import Image
    with tempfile.TemporaryDirectory() as td:
        c0 = extract_frames_uniform(TEST_CLIP, str(Path(td) / "c0"), num_frames=4, start_sec=0.0, end_sec=30.8)
        c1 = extract_frames_uniform(TEST_CLIP, str(Path(td) / "c1"), num_frames=4, start_sec=30.8, end_sec=61.6)
        assert len(c0) == 4 and len(c1) == 4
        assert Image.open(c1[0]).size == (1600, 1200)
        # first frame of chunk 0 and chunk 1 must differ (different time windows).
        assert Path(c0[0]).read_bytes() != Path(c1[0]).read_bytes()


@needs_clip
def test_filename_format_zero_padded():
    with tempfile.TemporaryDirectory() as td:
        paths = extract_frames_uniform(TEST_CLIP, td, num_frames=3, start_sec=0.0, end_sec=10.0)
        names = sorted(Path(p).name for p in paths)
        assert names[0] == "frame_000.png"
        assert "frame_001.png" in names  # zero-padded, not frame_1.png
