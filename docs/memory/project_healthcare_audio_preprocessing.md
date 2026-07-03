---
name: project-healthcare-audio-preprocessing
description: "Healthcare AI Agent (Triple-H lifelog) — audio preprocessing for Whisper (2026-06-04, 85bf21f). noisereduce + soundfile (NOT librosa) denoise glasses audio before Whisper. ADDS 2 pip packages (noisereduce, soundfile) — required for a fresh .venv. Escape hatch SKIP_AUDIO_PREPROC."
metadata: 
  node_type: memory
  type: project
  originSessionId: ca30b8c8-372d-44be-97df-a9e0250935d2
---

# Healthcare AI Agent — Audio Preprocessing for Whisper (2026-06-04, commit 85bf21f)

Repo: `C:\Users\A\projects\healthcare-ai-agent`. Resume via `handoff.md` (see ⚠️ Environment Dependencies + §9 Completed). Related: [[project-healthcare-v34-audio-xref]], [[project-healthcare-gemini-fact-expansion]].

## ⚠️ UPDATE 2026-06-04 (`da20d0a`): FLIPPED TO DEFAULT-OFF — content preservation
Option C was found to **silently drop/substitute quieter legitimate speech**, not just denoise: the analyst-quote sentences `3년에서 5년` (supply contract) and `사이클 장기화` (prolonged cycle) vanished from the test clip's preprocessed transcript (443 chars) vs raw audio (492 chars, all present). User priority is **100% audio-content preservation, accepting Whisper errors**. So audio preprocessing is now **DEFAULT-OFF** (only the `whisper_transcribe` gate in `_lifelog_test.py` changed): enable via **`ENABLE_AUDIO_PREPROC=1`**; legacy `SKIP_AUDIO_PREPROC=1` still works and WINS over ENABLE. Module + deps untouched.
- **Verification lesson:** transcript LENGTH is NOT a valid STT-preprocessing quality metric — content loss was disguised by near-identical length. The original 85bf21f report under-weighted this (verified ~90% length without checking dropped segments). **Use content-presence gates, not length.**
- **Dual-constraint to ever re-enable default-ON (BOTH on the test clip):** (1) phrases `3년에서 5년` AND `사이클이 장기화` present (100% speech preserved); (2) ≥1 Korean error corrected. See handoff §9 deferred for tuning options (lower prop_decrease, VAD gate, DeepFilterNet/rnnoise). Related: [[project-healthcare-postprocessing-limits]].

## ⚠️ NEW DEPENDENCIES (prominent — fresh-venv reproducibility)
A fresh `.venv` MUST install **`noisereduce` (3.0.3) + `soundfile` (0.13.1)** or audio preprocessing silently disables (graceful: `AUDIO_PREPROC_AVAILABLE=False` → raw audio, no crash). Install: `.venv\Scripts\python.exe -m pip install noisereduce soundfile`.
- **librosa is deliberately NOT used** — `audio_preprocessor.py` uses `soundfile` I/O (audio is already 16kHz mono, no resample), avoiding numba/llvmlite so the torch/paddle/ctranslate2 DLL stack stays stable. numpy STAYS 1.26.4. Do NOT add librosa.
- There is **no requirements.txt** (deliberate; out of scope). Handoff "Environment Dependencies" section is the record.
- Pinned stack untouched: numpy 1.26.4 · torch 2.11.0+cu128 · ctranslate2 4.7.2 · faster_whisper 1.2.1 · paddle 2.6.2 · scipy 1.17.1.
- This was the FIRST task to install packages (the long-standing "no new packages" rule was waived with user sign-off after a pip dry-run confirmed the stack was safe).

## What shipped
- NEW `backend/glasses_watcher/audio_preprocessor.py`: noisereduce stationary spectral gating (`prop_decrease=0.85`) + ~6dB amplification on the 16kHz mono WAV from `extract_audio()`, written to a temp `*_preprocessed.wav`. soundfile-only I/O. Defensive: non-16kHz / missing libs / read error → returns original path unchanged.
- `_lifelog_test.py` (+32/−1): optional import (`from audio_preprocessor import preprocess_audio_for_whisper`, top-level like `ocr_preprocessor`), then preprocess inside `whisper_transcribe()` before `model.transcribe()`, with **`SKIP_AUDIO_PREPROC` env escape hatch** + temp-file cleanup in `finally`.
- 4 unit tests in `tests/test_audio_preprocessor.py`.

## Honest result (KBS clip, 3.1 Pro)
Eliminated **4/4** known Whisper error-forms (originals 승리/크룸/분풍/공독). **2/4 cleanly corrected** to the right word (심리, 흐름); the other 2 segments (훈풍, 공급) transcribe differently in the new pass — error gone but correct form not empirically confirmed. Noise reduction can't fix genuine model/phonetic-limit errors (only noise artifacts). Transcript 492→443 chars (90%). **Latency −22s** (302.7s vs ~325s). value_updates multi-value + audio_only_terms=4 + schema v3.4 preserved. DLL health proven by a single-process PaddleOCR + Whisper + Gemini run.

## Constraints honored
Only `audio_preprocessor.py` (new) + `_lifelog_test.py` (Whisper call site) + a new test touched. NOT touched: `ocr_preprocessor.py`, `audio_fact_extractor.py`, LLM prompts, the 4 callers, aggregator, exporter, frontend, watchers. No migrations. The hardware mic upgrade (Mentra Live) remains the real fix for the residual phonetic-limit errors.
