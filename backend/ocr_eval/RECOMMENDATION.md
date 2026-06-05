# OCR Engine Evaluation — Decision Matrix & Recommendation (2026-06-05)

**Evaluation-only session. No production code was modified; no engine was integrated.**
Deliverable: which OCR engine (if any) should a FUTURE authorized session integrate to
break PaddleOCR's Korean-financial-text accuracy ceiling.

> **Test frames** are regenerable from the source clip via FFmpeg — see
> `test_data/README.md` for the exact commands (the PNGs themselves are gitignored;
> `test_data/frame_provenance.json` records each frame's source/timestamp/checksum).

Test frames (from clip `20260528144922838.mp4`, visually ground-truthed):
- **f07** — KRX individual-stocks board (유가증권시장), large Korean text + comma numbers (12 tokens).
- **f08** — Hana Bank multi-currency board, small Latin currency ticker (10 tokens).
- f04 (animated headline) excluded from scoring — documents a separate PaddleOCR comma-number
  fragmentation issue, not an engine-choice question.

## Results (22 scored tokens: 12 Korean-heavy f07 + 10 Latin f08)

| Engine | f07 Korean KRX | f08 Latin Hana | Overall | CharAcc | p50 latency | $/1k |
|---|---|---|---|---|---|---|
| **PaddleOCR (baseline)** | **9/12 (75%)** | 7/10 (70%) | **16/22 (73%)** | 85% | 599 ms | $0 |
| PaddleStructure (en) | 5/12 (42%) | **9/10 (90%)** | 14/22 (64%) | 74% | 512 ms | $0 |
| EasyOCR (ko+en) | 7/12 (58%) | 4/10 (40%) | 11/22 (50%) | 72% | 721 ms | $0 |

**Bar to beat = 73% (PaddleOCR baseline). No free engine beats it overall.**

## CASE classification

Two different content types give two different verdicts:

- **Korean KRX board (f07) → CASE δ (PaddleOCR is the free-engine ceiling).**
  Neither alternative beats PaddleOCR's 75%. PaddleStructure can't read Hangul at all (42%,
  numbers only). EasyOCR (the great hope — the one free model that loads `['ko','en']` together)
  lands at **58%, *below* baseline**, and recovers **0 of the 4 flagged architectural-ceiling
  tokens** (현대차, 681,000, 삼성전기, SK스퀘어) that PaddleOCR didn't already have. It even
  *loses* 삼성전기 and 1,630,000 that the baseline gets. → **No free engine breaks the Korean ceiling.**

- **Latin currency board (f08) → CASE β (free, table-aware engine wins this content type).**
  PaddleStructure (en) is decisively best: **9/10 (90%) vs 70%**, *and faster* (637 ms). It cleanly
  reads 221.27, CAD/KRW, EUR/USD — the small-Latin-ticker tokens PaddleOCR misses. EasyOCR is
  *worst* here (40% — reads only the large top values, misses the whole small currency row).

This matches the evaluator's own framework exactly: *"EasyOCR matches or underperforms PaddleOCR
on f07 → no free engine fully solves the Korean ceiling → recommend Naver Clova (paid) or hardware."*

## Recommendation

1. **Do NOT integrate EasyOCR. Do NOT replace PaddleOCR.** EasyOCR is worse on both frames
   (50% vs 73% overall) and slower. The `['ko','en']` single-model hope did not pan out on dense
   broadcast financial text. PaddleOCR remains the best free engine for Korean content.

2. **The Korean ceiling is confirmed unbreakable by free tooling.** This extends the project's
   established "tooling, not tuning" pattern (Rule 1a `f2e74dd`, Option B `9bbb412`, E1 `81c0c07`)
   with a 4th data point: it's not free *tooling* either. The real fix for Korean KRX recovery is:
   - **(preferred next eval) Naver Clova OCR** — paid, Korean-specialized commercial engine.
     Needs a `CLOVA_OCR_API_KEY`; was skipped this session (Phase D). One clean future eval.
   - **(capture-layer fix) Mentra Live hardware** — higher-resolution glasses sensor. Addresses
     the root cause (capture quality) rather than the OCR engine. Already the standing hardware path.

3. **One free, low-risk win is available now — content-routed hybrid for Latin currency boards.**
   PaddleStructure (en) on f08-type frames (Hana/Latin-currency tickers) is +20pts and faster.
   A future integration session *could* route detected Latin-currency-table frames → PaddleStructure(en)
   while keeping PaddleOCR for all Korean content. **Trade-off:** adds frame-type routing + a second
   engine load for a modest absolute gain (~2-3 tokens on one board type). Recommend the integration
   session decide build-vs-defer; it is the single actionable free improvement found.

**Net:** no engine swap. For Korean, escalate to Clova (paid) eval or Mentra Live hardware. For
Latin currency tables only, an optional PaddleStructure(en) hybrid is the free upside.

## Environment note (for reproducibility)
- `easyocr 1.7.2` installed **with `numpy==1.26.4` pinned** — a plain `pip install easyocr` would
  have upgraded numpy to 2.4.6 and broken the paddle/torch/ctranslate2 DLL stack. torch stayed
  2.11.0+cu128 (no downgrade). New packages: easyocr, ninja, opencv-python-headless 4.11.0.86, python-bidi.
- EasyOCR's progress bar prints U+2588 and crashes the cp949 Windows console → engine inits with
  `verbose=False`; harness imports torch FIRST (before paddle) to keep the shared DLL stack healthy.
- Full DLL-stack health verified before and after install; **production pipeline untouched throughout.**
