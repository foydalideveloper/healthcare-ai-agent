# OCR eval — test data

This directory holds the ground truth for the OCR-engine evaluation. The raw frame
PNGs are **intentionally not committed** (repo convention keeps `test_data/` binaries
out of git — see `../.gitignore`). They are fully regenerable from the source clip.

## Files
- `ground_truth.json` — the scored frames and their `must_contain` tokens (committed).
- `frame_provenance.json` — exact source / timestamp / dimensions / sha256 for each
  frame, so a regenerated PNG can be checksum-verified (committed).
- `frames/*.png` — the extracted frames (NOT committed; regenerate as below).

## How to regenerate the frames

Source clip: `C:\Users\A\AIMB-Bridge\20260528144922838.mp4`
(61.6 s, 1849 frames, 1600x1200; the standard KBS-clip lifelog test video).

From a shell with FFmpeg on PATH:

```bash
SRC="C:/Users/A/AIMB-Bridge/20260528144922838.mp4"
OUT="backend/ocr_eval/test_data/frames"

# -ss <seconds> seeks to the frame timestamp encoded in each filename (t10s/t17s/t20s).
ffmpeg -y -ss 10 -i "$SRC" -frames:v 1 "$OUT/f04_t10s.png"
ffmpeg -y -ss 17 -i "$SRC" -frames:v 1 "$OUT/f07_t17s.png"
ffmpeg -y -ss 20 -i "$SRC" -frames:v 1 "$OUT/f08_t20s.png"
```

> Note: re-encode/seek differences across FFmpeg builds can shift the decoded frame by
> a few ms, so a regenerated PNG may not byte-match the original sha256 in
> `frame_provenance.json`. The OCR content (the `must_contain` tokens in
> `ground_truth.json`) is what the evaluation actually scores — verify against that, not
> the checksum, if the hashes differ.

## How to re-run the evaluation

From `backend/`:

```bash
PYTHONIOENCODING=utf-8 ../.venv/Scripts/python.exe -m ocr_eval.harness \
  --engines paddle_baseline,paddle_structure,easy_ocr \
  --out ocr_eval/results/phase_c_easyocr.json
```

Render the side-by-side report: `... -m ocr_eval.report ocr_eval/results/phase_c_easyocr.json`.
Decision matrix + recommendation: `../RECOMMENDATION.md` (one level up, in `ocr_eval/`).
