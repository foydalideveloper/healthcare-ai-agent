---
name: project-healthcare-gemini-fact-expansion
description: "Healthcare AI Agent (Triple-H lifelog) — gemini-fact-expansion (2026-06-04). Gemini-only prompt addendum raises Gemini observed_facts to 41-66 (match Gemma's volume) while preserving multi-value tracking + quality bar. Gemma/Qwen/Llama prompts untouched. ALSO: rejected 'Rule 1a' absolute-value prompt fix (KOSPI base 0/3 across 3 runs — use a deterministic aggregator backfill, NOT a prompt rule)."
metadata: 
  node_type: memory
  type: project
  originSessionId: ca30b8c8-372d-44be-97df-a9e0250935d2
---

# Healthcare AI Agent — Gemini Fact Expansion (2026-06-04, COMPLETE)

Repo: `C:\Users\A\projects\healthcare-ai-agent`. Resume via `handoff.md` (⭐ LATEST at top). Builds on [[project-healthcare-6arm-gemini3]] and [[project-healthcare-v34-audio-xref]].

## Problem & fix
With the shared v3.3 prompt, Gemini arms produced too few `observed_facts` (3.1 Pro=19, Flash=18) vs Gemma's 49 — high quality, low volume. Fix: a Gemini-ONLY prompt addendum that instructs DECOMPOSITION of what the model already sees (no padding, no quality drop). Commit `5e69597` (gemini-fact-expansion).

## Architecture (KEY — differs from the mission template)
The v3.3 prompt is `LIFELOG_PROMPT` (line 105), embedded in the SHARED `_build_user_prompt()` used by all 4 base arms — NOT a variable named `LIFELOG_PROMPT_V33`, and the Gemini caller is SYNC raw-httpx REST (not the genai SDK). To isolate a Gemini-only variant without touching shared code:
- New constant **`GEMINI_FACT_EXPANSION_ADDENDUM`** (~line 1146, Gemini section).
- Appended to the prompt **inside `call_gemini_lifelog` ONLY** (~line 1275), AFTER `_build_user_prompt()` returns.
- Diff = **100 insertions, 0 deletions**. `LIFELOG_PROMPT`, `_build_user_prompt`, `_GEMMA_SYSTEM_INSTRUCTION`, and the gemma/qwen/llama callers are byte-identical.
- All 3 Gemini arms share `call_gemini_lifelog`, so the addendum applies to all 3 automatically.

The 8 decomposition rules: (1) multi-value panels→one fact/value, (2) multi-stock boards→one fact/stock, (3) each headline/overlay→own fact (verbatim quoted), (4) named entities→identity split from each claim, (5) each UI element→own fact w/ location, (6) audio↔video cross-refs, (7) scene/environment→each detail, (8) temporal/progression. Quality bar UNCHANGED; explicitly reinforces "KEEP value_updates multi-value behavior."

## Per-arm fact counts (UPDATED, test clip 20260528144922838.mp4)
- Gemma 4: ~49 (UNCHANGED — v3.3 prompt untouched; verbose, ambient-inclusive)
- Qwen / Llama 4: baseline (UNCHANGED; not re-run)
- Gemini 2.5 Pro: ~46 · Gemini 3.5 Flash: ~41 · Gemini 3.1 Pro Preview: ~66 (highest)

The ~25-fact spread (Flash 41 vs 3.1 Pro 66) is each model's natural verbosity at the same quality bar. 3.1 Pro overshot the 40-60 target to 66 — deliberately ACCEPTED (0 near-dupes, ~3% filler; a hard cap would make the model drop genuine facts + risk multi-value tracking).

## Multi-value value_updates tracking (cross-frame, e.g. KOSPI 8,228.70→8,428.84)
- Gemini 2.5 Pro: 3 entries (KOSPI, KOSDAQ, USD/KRW). Gemini 3.1 Pro Preview: 3 entries (same). Gemini 3.5 Flash: **0** (model-capability limitation, NOT a bug). Gemma/Qwen/Llama: not implementing it.

## Critical preservation (must-not-break list — all verified)
Gemma still 49; 3.1 Pro KOSPI 8,228.70→8,428.84 + KOSDAQ 1,133.13→1,148.16 + USD/KRW 1,501.80→1,500.40 all PRESENT; audio_only_terms=4 on all 3 Gemini arms; value_updates source tagging (7 audio-tagged each); schema v3.4; no latency regression (Flash ~65s/chunk, 3.1 Pro ~113s, 2.5 Pro ~86s). Quality: 0 dupes, ~3% filler.

## ❌ REJECTED EXPERIMENT (2026-06-04): "Rule 1a" absolute-value prompt fix — DO NOT REPEAT
Tried a 1-sentence sub-rule in `GEMINI_FACT_EXPANSION_ADDENDUM` ("Rule 1a") telling Gemini to emit base + delta as TWO separate observed_facts (goal: get KOSPI 8,228.70 base into observed_facts, not just the +181.19 change). Commit-and-test discipline; **never committed; rolled back**.
- **Result over 3 runs of 3.1 Pro:** KOSPI absolute standalone **0/3** (rule ineffective for primary target); SK Hynix abs 2/3 (noise); controls KOSDAQ 1/3 / Samsung 3/3 (model variance, NOT rule damage); critical preserve gates (multi-value tracking + audio_only_terms) held in ALL 3 runs; totals 49/48/39.
- **Conclusion:** a 1-sentence prompt rule cannot reliably force model attention onto a specific absolute value. Strengthening to "MUST" would just add noise. The earlier single-run "control regression" alarm was variance. ~25 min cost — don't repeat without new evidence.
- **Root cause — not really a gap:** KOSPI's base IS in the report, in **Value Updates** as `8,228.70 → 8,428.84` (survived all 3 runs). Cross-frame tracking does the job, just in a different section than observed_facts.
- **Correct future path:** deterministic aggregator-side backfill in `full_report_aggregator.py` — promote each `source='video'` value_updates entry into 1-2 observed_facts at AGGREGATION time (not via prompt). 100% reliable, model-agnostic, all 6 arms at once, no API cost; needs dedup vs model-emitted facts; ~45-60 min. (Listed in handoff §9.)

## ✅ FOLLOW-UP SHIPPED: Aggregator-side absolute-value backfill (2026-06-04, commit b7a5946)
Implements the "correct future path" above (replaces the rejected Rule 1a prompt). One file: `full_report_aggregator.py` (+80/−1). 4 helpers (`_normalize_for_fact_dedup`, `_generate_facts_from_value_update`, `_is_fact_already_present`, `backfill_absolute_value_facts`) + call at line 561 AFTER the v3.4 audio-xref source tagging (so `source='video'` exists). **Base-value-only (Option 1)** — second-value "also shown at" branch dropped as redundant with the Value Updates "Y → Z" arrow. Two regex bugs caught+fixed in test: sentence-final period in number match (`8,228.70.` ≠ `8228.70`), and label robustness (`USD/KRW` ≡ `USD-KRW`). Result: Gemini 3.1 Pro +1 (KOSPI base added, 100% deterministic vs Rule 1a 0/3), Gemma +0 (dedup skips natural facts), edge +0. Cross-arm, no API cost; multi-value tracking / audio_only_terms=4 / schema v3.4 preserved. The ❌ Rule 1a negative-result note above stays as the "why not a prompt" record.

## Deferred (added this session)
- Apply decomposition addendum to Gemma path IF more Gemma facts ever wanted (currently 49 is the target; prompt deliberately untouched).
- Investigate why 3.5 Flash does 0 multi-value tracking with the same addendum (likely weaker cross-frame state).
- Qwen/Llama not re-run post-expansion (provably unaffected; empirical confirmation deferred).
- Aggregator-side absolute-value backfill (replaces rejected Rule 1a; see above).

## Constraints honored
No change to `ocr_preprocessor.py` / `audio_fact_extractor.py` / `LIFELOG_PROMPT` / `_build_user_prompt` / gemma-qwen-llama callers / migrations / packages. Deliberate single-file commit (`_lifelog_test.py`). Test artifacts saved as untracked test_data JSON.
