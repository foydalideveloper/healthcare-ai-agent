"""Unit tests for audio_preprocessor (soundfile-only, no librosa).

Run: {venv} -m pytest backend/glasses_watcher/tests/test_audio_preprocessor.py -v
"""
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]  # .../backend
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from glasses_watcher.audio_preprocessor import (  # noqa: E402
    preprocess_audio_for_whisper,
    is_preprocessing_available,
)


def test_availability_is_bool():
    assert is_preprocessing_available() in (True, False)


def test_nonexistent_input_returns_unchanged():
    # Graceful fallback: a missing file must return the path unchanged, not raise.
    p = "/nonexistent/does_not_exist.wav"
    assert preprocess_audio_for_whisper(p) == p


def test_roundtrip_denoise_when_available(tmp_path):
    """If libs are installed, a real 16kHz mono WAV is denoised to a new file of
    the same length; otherwise it degrades to returning the input unchanged."""
    if not is_preprocessing_available():
        import pytest
        pytest.skip("audio libs not installed")
    import numpy as np
    import soundfile as sf

    sr = 16000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    tone = 0.2 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    noise = (0.01 * np.random.RandomState(0).randn(sr)).astype(np.float32)
    src = tmp_path / "in.wav"
    sf.write(str(src), tone + noise, sr, subtype="PCM_16")

    out = preprocess_audio_for_whisper(str(src), output_dir=str(tmp_path))
    assert out != str(src)            # a cleaned file was produced
    assert Path(out).exists()
    cleaned, csr = sf.read(out)
    assert csr == sr
    assert abs(len(cleaned) - sr) <= sr * 0.05  # length preserved (~1s)


def test_wrong_sample_rate_skips(tmp_path):
    """Non-16kHz input must fall back to the original (no librosa resample)."""
    if not is_preprocessing_available():
        import pytest
        pytest.skip("audio libs not installed")
    import numpy as np
    import soundfile as sf

    sr = 44100
    data = (0.1 * np.random.RandomState(1).randn(sr)).astype(np.float32)
    src = tmp_path / "hi.wav"
    sf.write(str(src), data, sr, subtype="PCM_16")

    assert preprocess_audio_for_whisper(str(src)) == str(src)  # unchanged
