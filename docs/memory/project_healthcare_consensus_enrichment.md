---
name: project-healthcare-consensus-enrichment
description: "Healthcare AI Agent (Triple-H lifelog) — Self-Improvement Job 1: cross-arm consensus enrichment (2026-06-05, SHIPPED, 4 commits, schema v3.5). Aggregator-level; compares per-arm observed_facts, surfaces facts >=~67% of arms agree on with a confidence score. Foundation for Job 2 (auto-labeled dataset) + Job 3 (LoRA fine-tune local Gemma 4). First post-processing feature to ship cleanly since the capture-layer-ceiling pattern emerged."
metadata:
  node_type: memory
  type: project
  originSessionId: ca30b8c8-372d-44be-97df-a9e0250935d2
---

# Healthcare AI Agent — Cross-Arm Consensus Enrichment (Self-Improvement Job 1, 2026-06-05, SHIPPED)

Repo: `C:\Users\A\projects\healthcare-ai-agent`. Resume via `handoff.md` §9 (top entry) + §12. Final commit `3e6b8a1`. The first of a 3-job self-improvement flywheel. Related: [[project-healthcare-gemini-fact-expansion]] (the 6-arm setup), [[project-healthcare-postprocessing-limits]] (the pattern this updates).

## What shipped (4 commits, per-part discipline)
- `1dffd4d` — Part A (`backend/app/services/consensus_enricher.py` + 16 unit tests) **+** Part B (aggregator integration), committed together.
- `b2fe80a` — Part C: Word doc "Cross-Arm Consensus Findings" section (`word_exporter.py`).
- `3e6b8a1` — Part D: frontend modal section + TS types (`frontend/hrt-dashboard/app/lifelog/page.tsx`).

## Architecture (KEY)
- **Purely aggregator-level, ADDITIVE.** NO extraction-pipeline / LLM-prompt / watcher changes; single-arm reports unchanged. Schema **v3.4 → v3.5** (`SCHEMA_VERSION` in `full_report_aggregator.py`). Adds `consensus_observed_facts` + 6 `metrics.consensus_*` fields.
- NEW `consensus_enricher.py` = **pure stdlib** (`re`, `difflib` only). `compute_consensus_facts(arm_inputs, min_agreement_count=None, min_agreement_fraction=0.67, similarity_threshold=0.75)`. Clusters per-arm facts by `SequenceMatcher` ratio; a cluster reaching the threshold becomes a `ConsensusFact` (canonical = longest variant; confidence = agreeing_arms / total_arms over DISTINCT arms).
- Integration point: `full_report_aggregator.py`, AFTER the Option A backfill, BEFORE `return report`. Reads **flattened** `e.get("observed_facts")` / `e.get("source_model")` (events are flattened by the endpoint — NOT nested under `raw_event`). Helpers `_can_compute_consensus` (≥2 arms with facts) + `_build_arm_inputs_from_events`.

## Threshold choices (empirical, from unit-test calibration)
- **Similarity 0.75** — conservative; prefers false-negatives (distinct facts) over false-positives (collapsing different facts), so a consensus claim is never an over-merge artifact. "KOSPI is at 8228.70" vs "The KOSPI index is at 8,228.70" cluster (~0.8+); a fact with a long extra tail ("...up 8,000 won (+2.68%)") drops below 0.75 and stays separate (this caught a bad TEST in dev — fix the test, not the module).
- **Adaptive count 0.67 fraction** — `min_agreement_count = max(2, round(arms × 0.67))` (floor 2). 4 arms→3 (75%); 6 arms→4 (67%). Reads as "more than two-thirds of our LLMs agreed" and scales to any arm count. Override with explicit `min_agreement_count`.
- Badge bands: High `≥0.83`, Medium `0.67–0.83`, below not rendered (filtered at compute).

## ⭐ Determinism property (the most important catch of the session)
Greedy single-link clustering is order-sensitive — pre-fix the SAME data gave 6 facts one run, 9 another (DB row-order tie-breaks). Fixed by canonicalizing input order INSIDE the pure module: process arms by `sorted(arm_id)`, seed clusters longest-fact-first. Result is now a function of the input **SET**, not order — verified 9/9/9 under shuffled input. **Future Job 2/3 sessions MUST preserve this** — it's the stability the labeled-dataset generation depends on.

## Visual hierarchy (consistent Word + frontend — keep these exact)
- High ≥83%: green `#1A7F37` / Tailwind `bg-green-100 text-green-700`.
- Medium 67–83%: amber `#B8860B` / Tailwind `bg-amber-100 text-amber-700`.
- Word: `[High]`/`[Med]` text badges + 9pt gray arm-attribution subtitle. Frontend: `%` pills + 11px gray attribution. Korean uses existing Malgun Gothic eastAsia font (Hangul renders, no mojibake).

## Test-clip result + the "4 arms now, scales to 6+ later" property
KBS clip `20260528144922838.mp4` has only **4 arms** with events (gemma4 + gemini 2.5/3.1/3.5; **qwen3_vl + llama_4_maverick absent** — the flaky local/NIM pair). Built on the 4 present: **9 consensus facts (2 high 4/4, 7 medium 3/4)** — SK Hynix +9.31%, Samsung +2.68%, KRX/Micron headlines, sign-language interpreter, etc. `arms_compared` is a RUNTIME metric, so when qwen+llama4 populate future clips, consensus uses 6 arms with NO code change. **Decision (boss): override Phase-0-step-2 "run missing arms" with the harder "operate on existing DB data only / no re-extract" DON'T** — re-populating the flaky arms wasn't worth the GPU/cloud cost just to demo the architecture.

## Verification (all automatable gates passed)
16/16 consensus unit tests; 46/46 services suite; `all_observed_facts` 131 UNCHANGED (additive proof); KOSPI/KOSDAQ/USD-KRW multi-value + audio_only_terms=4 + Option A backfill all intact; single-arm → consensus `[]`; schema v3.5; Word doc 51KB with 2 green + 7 amber badges (python-docx-inspected, not assumed); tsc 0 new errors in page.tsx; `/lifelog` compiles + serves 200. **Deferred:** browser interactive click/resize smoke test (needs human eyes; data contract guarantees render).

## Pattern update — post-processing CAN ship when architectural fit matches
[[project-healthcare-postprocessing-limits]] documented 4 cases where post-processing/tuning could NOT manufacture data the capture layer never produced. Consensus enrichment is DIFFERENT and ships cleanly: it does NOT try to recover un-captured data — it operates on data the arms DID produce (their observed_facts), cross-referencing for agreement. So the ceiling pattern is about *manufacturing missing capture*; aggregator features that reorganize/cross-reference EXISTING multi-arm output are fair game and high-value.

## Foundation for the flywheel
- **Job 2 (deferred, ~6–8h):** auto-labeled dataset — `consensus_observed_facts` become ground-truth labels for (frames+transcript) chunks; tag content type / language / scene complexity.
- **Job 3 (deferred, ~12–16h after Job 2):** LoRA fine-tune local Gemma 4 26B A4B on Job 2's data → Korean-financial/lifelog specialization; production switch to fine-tuned local primary arm ≈80% cloud-cost cut.

## Constraints honored
No change to `ocr_preprocessor.py` / `audio_fact_extractor.py` / `audio_preprocessor.py` / `_lifelog_test.py` / LLM prompts / callers / watchers / `ocr_quality_filter.py`; no migrations; no new packages (stdlib only); per-part commits; `test_data/` artifacts left uncommitted; no emoji in `print()`.
