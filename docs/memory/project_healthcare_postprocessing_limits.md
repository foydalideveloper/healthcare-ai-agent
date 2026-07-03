---
name: project-healthcare-postprocessing-limits
description: "Healthcare AI Agent (Triple-H lifelog) — architectural lesson: post-processing (prompt tweaks, aggregator scans) CANNOT manufacture data the extraction layer never captured. THREE proven negative findings: Rule 1a (f2e74dd, prompt), Option B (9bbb412, aggregator scan), and E1 OCR-pipeline tuning (2026-06-04, C1 kept / C2-C3 reverted — surfaced the Hana board but bundled with non-separable latency+noise+gate-break costs). Real fix = different OCR tooling, not tuning."
metadata: 
  node_type: memory
  type: project
  originSessionId: ca30b8c8-372d-44be-97df-a9e0250935d2
---

# Healthcare AI Agent — Architectural Limit: Post-Processing Can't Fix Extraction Gaps

Repo: `C:\Users\A\projects\healthcare-ai-agent`. Two independent attempts proved the same lesson — write it down so future sessions don't burn time re-discovering it. Related: [[project-healthcare-gemini-fact-expansion]] (holds the Rule 1a detail), [[project-healthcare-v34-audio-xref]].

## The pattern (now THREE instances)
**If the extraction layer (LLM, OCR, Whisper) didn't capture/produce the data, no downstream post-processing can recover it — AND when tuning the current capture stack DOES surface the data, it often comes bundled with costs that the same stack can't separate.** The fix for a true capture gap is usually DIFFERENT TOOLING, not more tuning.
- #1 [[Rule 1a]] (`f2e74dd`): prompt rule can't force LLM attention (KOSPI base 0/3).
- #2 Option B (`9bbb412`): aggregator scan can't read OCR text that was never emitted (6/8 targets absent).
- #3 E1 (2026-06-04, below): OCR-pipeline TUNING can surface the data but bundled with prohibitive, inseparable costs.

## Negative finding #1 — "Rule 1a" prompt fix (commit f2e74dd, rolled back)
Tried a one-sentence addendum rule to force Gemini to emit a metric's absolute value as its own observed_fact. Over 3 runs of 3.1 Pro: KOSPI absolute appeared **0/3**. A prompt rule cannot reliably force model attention onto a specific value. Superseded by a DETERMINISTIC aggregator backfill (b7a5946) — which works ONLY because the value WAS already captured (in value_updates), just not surfaced as a fact. Key distinction: backfill re-surfaces captured data; it does not manufacture new data.

## Negative finding #2 — Option B aggregator-side OCR entity recovery (2026-06-04, abandoned at design, NO commit)
Goal: scan `ocr_appendix_full`/`all_ocr_text` for missed visual entities (SK스퀘어, 삼성전자우, 현대차, 삼성전기, EUR/USD, CNH/KRW, CAD/KRW, S&P 500, SK하이닉스 2,328,000) and promote label+value pairs into value_updates → observed_facts (via Option A's backfill). **Phase 0 killed it before any edit:**
- **6 of 8 targets were never OCR-captured** — not in the appendix at all. The appendix is mojibake-dominated ("EXAHANUGE", "!II1", "15…27ZKOSP!"): PaddleOCR couldn't read the dense small-text financial boards.
- The **2 present** (SK스퀘어, 삼성전자우) appear only as comma-LESS, garbled, **value-before-label** tokens (`…"1276000", "SK스퀴어"…`) inside a noisy interleaved cluster (95000/1276000/스486/192000).
- The mission's own design was also broken (value regex required commas the OCR lacked; scanned forward when the value preceded the label).
- A 2/8 recovery would be clip-specific overfit with real false-positive risk.

**The real fix is OCR-quality work in the OFF-LIMITS `ocr_preprocessor.py`** (higher-DPI / 3-4× upscale for dense panels, DBSCAN-eps tuning, possibly PaddleStructure table OCR). Deferred to a future session explicitly authorized to touch the OCR pipeline (handoff §9). Do NOT retry an aggregator/post-processing scan.

## Negative finding #3 — E1 authorized OCR-pipeline tuning (2026-06-04, C1 kept, C2/C3 reverted)
ONE-SESSION authorized exception to the `ocr_preprocessor.py` off-limits rule (now CLOSED, off-limits restored). Goal: recover the OCR-missed Hana Bank multi-currency board + KRX stocks.
- **C1 density-aware upscale — SHIPPED `81c0c07`** (kept as harmless infra; +1s, no standalone gain because the 4000px width cap clamps wide boards to ~2x).
- **C2 DBSCAN fragmentation (eps 0.12→0.07/0.085, min_samples 4→3) — REVERTED.** It WORKED — surfaced 3/3 Hana entities (EUR/USD, CAD/KRW, S&P 500 7,519.12) into observed_facts, all gates pass — but coupled to: +33s OCR latency (over budget, NOT tunable — 0.07 and 0.085 both +33s) AND observed_facts inflated 44→95 (garbled-OCR noise: 현→허, 1,630,000→630000, .→/). The only mitigation (top-N densest panel cap) at N=3 cut latency to +16s + noise to 51 BUT broke KOSPI/KOSDAQ/USD-KRW multi-value tracking (dropped the Hana panel with the 2nd KOSPI value) and lost 2/3 entities. No N gives recovery + budget + preserve-gates together.
- **Lesson:** even WITH capture-layer access, tuning the current PaddleOCR stack couldn't separate the Hana-board win from its costs. KRX stocks never cleanly recovered (font too small/garbled). Real fix = different tooling (PaddleStructure/table OCR, commercial Korean OCR API) or better capture (Mentra Live / higher-res sensor). Needs fresh authorization. Boss-demo state restored to clean C1-only (all gates pass, ~36-51 facts, no noise/latency regression).

## What DID work (the contrast — re-surfacing captured data is fine)
- Aggregator backfill (b7a5946): promotes already-captured value_updates into observed_facts. Deterministic, cross-arm. Works because the data exists.
- Audio preprocessing (85bf21f): improves capture AT the Whisper input (noisereduce before transcription) — a capture-layer fix, not post-processing. Fixed 2/4 known errors.
