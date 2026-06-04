"""Audio preprocessing for Whisper.

Applies noise reduction + mild amplification to glasses-mic audio BEFORE Whisper
transcribes, to mitigate mic-quality artifacts (noise, low SNR) that degrade
accuracy. The Whisper model and its parameters are unchanged.

Pipeline: 16kHz mono WAV (from extract_audio) -> noisereduce spectral gating
-> +6dB amplification -> cleaned 16kHz mono WAV.

I/O uses `soundfile` (NOT librosa): extract_audio() already produces 16kHz mono,
so no resampling is needed, and we deliberately avoid librosa -> numba/llvmlite
(heavy native JIT) to stay DLL-safe next to the torch/paddle/ctranslate2 stack
(WinError-127 history). If the input is unexpectedly not 16kHz mono, the
preprocessor degrades gracefully and returns the ORIGINAL path unchanged rather
than pulling in librosa to resample.

Every failure mode returns `input_audio_path` unchanged (never raises), so a
missing lib / unreadable file / processing error simply falls back to raw audio.
"""
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

EXPECTED_SR = 16000  # extract_audio() emits 16kHz mono — Whisper's native rate

# numpy is part of the base stack; soundfile/noisereduce are lazy-loaded.
_SOUNDFILE = None
_NOISEREDUCE = None
_NUMPY = None

PREPROCESSING_AVAILABLE = True
try:
    import numpy as _np
    _NUMPY = _np
except ImportError:
    PREPROCESSING_AVAILABLE = False


def _lazy_load():
    """Load soundfile + noisereduce on first use (raises ImportError if absent)."""
    global _SOUNDFILE, _NOISEREDUCE
    if _SOUNDFILE is None:
        import soundfile
        _SOUNDFILE = soundfile
    if _NOISEREDUCE is None:
        import noisereduce
        _NOISEREDUCE = noisereduce


def preprocess_audio_for_whisper(
    input_audio_path: str,
    output_dir: Optional[str] = None,
    expected_sr: int = EXPECTED_SR,
    amplification_db: float = 6.0,
    noise_reduce_strength: float = 0.85,
) -> str:
    """Noise-reduce + amplify a 16kHz mono WAV for Whisper.

    Args:
        input_audio_path: path to a 16kHz mono WAV (from extract_audio).
        output_dir: where to write the cleaned WAV (default: input's dir).
        expected_sr: required sample rate; mismatches fall back to raw audio.
        amplification_db: gain in dB applied after denoise (default +6dB).
        noise_reduce_strength: 0..1 spectral-gate aggressiveness (default 0.85).

    Returns:
        Path to the cleaned WAV, or `input_audio_path` unchanged on any failure
        (libs missing / file unreadable / not 16kHz mono / processing error).
        The caller is responsible for deleting the cleaned file.
    """
    if not PREPROCESSING_AVAILABLE:
        logger.warning("[AUDIO PREPROC] numpy unavailable; skipping")
        return input_audio_path
    try:
        _lazy_load()
    except ImportError as e:
        logger.warning(f"[AUDIO PREPROC] library missing ({e}); skipping")
        return input_audio_path

    input_path = Path(input_audio_path)
    if not input_path.exists():
        logger.warning(f"[AUDIO PREPROC] input not found: {input_audio_path}")
        return input_audio_path

    try:
        audio, sr = _SOUNDFILE.read(str(input_path))
        # Caller guarantees 16kHz mono. If not, degrade gracefully (we don't pull
        # in librosa just to resample) — return the original untouched.
        if sr != expected_sr:
            logger.warning(f"[AUDIO PREPROC] sr={sr} != {expected_sr}; skipping (no resample)")
            return input_audio_path
        if getattr(audio, "ndim", 1) > 1:
            audio = audio.mean(axis=1)  # downmix to mono
        audio = audio.astype(_NUMPY.float32)

        denoised = _NOISEREDUCE.reduce_noise(
            y=audio, sr=sr, stationary=True, prop_decrease=noise_reduce_strength,
        )
        gain = 10 ** (amplification_db / 20.0)
        amplified = _NUMPY.clip(denoised * gain, -1.0, 1.0)

        out_dir = output_dir or str(input_path.parent)
        os.makedirs(out_dir, exist_ok=True)
        output_path = Path(out_dir) / f"{input_path.stem}_preprocessed.wav"
        _SOUNDFILE.write(str(output_path), amplified, sr, subtype="PCM_16")
        logger.info(f"[AUDIO PREPROC] wrote cleaned audio to {output_path}")
        return str(output_path)
    except Exception as e:  # noqa: BLE001 — any failure must fall back to raw
        logger.exception(f"[AUDIO PREPROC] failed: {e}")
        return input_audio_path


def is_preprocessing_available() -> bool:
    """True if soundfile + noisereduce are importable (numpy assumed present)."""
    if not PREPROCESSING_AVAILABLE:
        return False
    try:
        _lazy_load()
        return True
    except ImportError:
        return False
