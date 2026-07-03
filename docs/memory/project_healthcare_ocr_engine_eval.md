---
name: project-healthcare-ocr-engine-eval
description: "Healthcare AI Agent (Triple-H lifelog) — OCR engine evaluation (2026-06-05). Free-engine bake-off vs PaddleOCR baseline (73%) on the 2 failure frames. EasyOCR(ko+en) REJECTED (50%, loses both). PaddleStructure(en) wins Latin f08 only (90%). Korean ceiling = CASE δ → escalate to Naver Clova (paid) or Mentra Live hardware. Evaluation-only, production untouched, eval uncommitted under backend/ocr_eval/."
metadata:
  node_type: memory
  type: project
  originSessionId: ca30b8c8-372d-44be-97df-a9e0250935d2
---

# Healthcare AI Agent — OCR Engine Evaluation (2026-06-05, COMPLETE)

Repo: `C:\Users\A\projects\healthcare-ai-agent`. Resume via `handoff_ocr_eval_2026-06-05.md` (§15 = final results) → `handoff.md` §9. Full decision matrix: `backend/ocr_eval/RECOMMENDATION.md`. Resolves the long-deferred "different tooling, not tuning" question from [[project-healthcare-postprocessing-limits]] at the engine level — it's NOT free tooling either (4th instance of the capture-layer ceiling pattern).

## What this session was (evaluation-only; NO production change)
A side-by-side free-OCR-engine bake-off under NEW `backend/ocr_eval/` (harness.py + engines/ + metrics.py + report.py + test_data/ + results/). All UNCOMMITTED (commit pending user OK as `ocr-engine-evaluation-results`; open question = whether to include the 3 ~2MB frame PNGs given the repo keeps test_data binaries out). Production files (`ocr_preprocessor.py`, `_lifelog_test.py`, etc.) verified untouched before AND after.

## Results (22 scored tokens: f07 KRX Korean board 12 + f08 Hana Latin currency board 10)
| Engine | f07 Korean | f08 Latin | Overall | p50 | $/1k |
|---|---|---|---|---|---|
| PaddleOCR (baseline) | 9/12 (75%) | 7/10 (70%) | **16/22 (73%)** | 599ms | $0 |
| PaddleStructure (en) | 5/12 (42%) | **9/10 (90%)** | 14/22 (64%) | 512ms | $0 |
| EasyOCR (ko+en) | 7/12 (58%) | 4/10 (40%) | 11/22 (50%) | 721ms | $0 |

## Verdict & recommendation
- **EasyOCR REJECTED** — the `['ko','en']` single-model hope. Worse on BOTH frames, slower; recovered **0/4** flagged ceiling tokens (현대차/681,000/삼성전기/SK스퀘어) baseline missed, and even LOST 삼성전기 + 1,630,000 that baseline gets. On Latin f08 it collapses to 40% (reads only big top values, misses the whole small currency row). No swap.
- **Korean KRX board = CASE δ:** no free engine beats PaddleOCR's 75%. PaddleStructure can't read Hangul (en/ch only; `lang='korean'` hard `sys.exit`). → escalate to **Naver Clova OCR (paid, Korean-specialized)** [Phase D skipped — no `CLOVA_OCR_API_KEY` in backend/.env] OR **Mentra Live** higher-res hardware (capture-layer fix).
- **Latin currency board = CASE β:** PaddleStructure(en) wins f08 (90% vs 70%, faster) — optional FREE content-routed hybrid (route Latin-currency-table frames → PaddleStructure en; keep PaddleOCR for Korean). Trade-off: routing + 2nd engine load for ~2-3 tokens on one board type. Integration session decides build-vs-defer.

## ⚠️ Environment lessons (reusable, non-obvious)
- **`pip install easyocr` MUST pin numpy:** plain install upgrades numpy 1.26.4→2.4.6 → breaks the paddle/torch/ctranslate2 DLL stack. Use `.venv\Scripts\python.exe -m pip install easyocr "numpy==1.26.4"` (pin forces opencv-python-headless to backtrack to 4.11.0.86, numpy-1.x-compatible). torch stayed 2.11.0+cu128 (NO downgrade — verified via `--dry-run` first). New packages: easyocr 1.7.2, ninja, opencv-python-headless 4.11.0.86, python-bidi.
- **EasyOCR `Reader` crashes the cp949 Windows console** — its download/progress hook prints U+2588 (block char) → `UnicodeEncodeError`. Fix: `Reader(['ko','en'], gpu=True, verbose=False)` + run with `PYTHONIOENCODING=utf-8`.
- **torch-FIRST import order in any multi-engine script:** the harness loads paddle (via baseline's `ocr_preprocessor` import) before EasyOCR's torch → `WinError 127` on `torch/lib/shm.dll`. Fix = `import torch` at the very top of `harness.py` (before any paddle import), mirroring production `_lifelog_test.py:51`. NOT an EasyOCR bug (works standalone torch-first).

## Constraints honored
Evaluation-only — all work in `backend/ocr_eval/` + doc files. NO production code modified, NO engine integrated. DLL stack health verified before/after install. Always `.venv\Scripts\python.exe`; no emoji in print(); v3.4 features intact (production untouched).
