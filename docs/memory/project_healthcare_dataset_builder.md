---
name: project-healthcare-dataset-builder
description: "Healthcare AI Agent (Triple-H lifelog) — Self-Improvement Job 2: auto-labeled dataset builder (2026-06-05, SHIPPED 3edf2b6). Read-only backend/training/ turns Job 1 per-CHUNK consensus into versioned JSONL training data (foundation for Job 3 LoRA fine-tune of local Gemma 4). NO production change; PyAV+PIL already in venv. Determinism byte-identical across rebuild. v1.0.0 = thin_start 2 examples, auto-grows."
metadata:
  node_type: memory
  type: project
  originSessionId: ca30b8c8-372d-44be-97df-a9e0250935d2
---

# Healthcare AI Agent — Job 2 Auto-Labeled Dataset Builder (2026-06-05, SHIPPED)

Repo: `C:\Users\A\projects\healthcare-ai-agent`. Resume via `handoff.md` §9 (top) + §12. Commit `3edf2b6`. Second job of the 3-job self-improvement flywheel. Builds on [[project-healthcare-consensus-enrichment]] (Job 1 — its consensus is Job 2's ground-truth labels). Job 3 (LoRA fine-tune) is the next session.

## What it is
Read-only builder under NEW `backend/training/` (6 modules + 4 test files, 28 tests) that pairs each video chunk's INPUTS (frames + transcript + OCR) with LABELS (Job 1 consensus facts) → versioned JSONL training dataset. NO production code touched; no new packages (PyAV 17.0.1 + PIL already in venv; stdlib otherwise). Output `backend/training_data/<version>/` is **gitignored** (large regenerable binaries).

Modules: `event_query.py` (flatten + multi-arm census + per-chunk consensus), `frame_extractor.py` (PyAV even-split sampling), `label_filter.py` (high/medium tiers), `dataset_writer.py` (JSONL + SHA256 split + manifest), `dataset_builder.py` (async orchestrator) + `cli.py`.

## ⚠️ INVOCATION (non-obvious — the #1 gotcha)
Run **from `backend/`**: `..\.venv\Scripts\python.exe -m training.cli --version v1.0.0`. Running `-m backend.training.cli` from repo root FAILS — `from app.database` won't resolve. If you see `ImportError: app.database`, you're in the wrong cwd. Output lands in `backend/training_data/` (relative to cwd).

## Per-CHUNK consensus (not per-video)
Job 1 computes consensus over the whole video's events; Job 2 needs per-`chunk_idx` granularity to make one training example per chunk. `event_query.compute_per_chunk_consensus` groups facts by arm within a chunk, sorts arms, and calls Job 1's `compute_consensus_facts(min_agreement_count=None)` (adaptive 67%). Per-chunk totals sum to Job 1's per-video count (test clip: chunk0 6 + chunk1 3 = 9).

## Phase-0 reality corrections (verified vs live DB — the spec was wrong)
- `observed_facts` / `video_extraction` / `audio_extraction` are **NOT columns** — they live in the `raw_event` JSONB and need the endpoint's flatten-first-wins (`if k not in row`). Selecting `observed_facts` as a column **400s**. `get_db_admin` is in `app.database` (not `app.db.supabase_client`). All DB fns are `async def`.
- Group by **`chunk_idx`** (0,1,…); `start_sec`/`end_sec` are NULL in this DB.
- Frame windows by **even-split**: `start=(idx/n_chunks)*duration`, `end=((idx+1)/n_chunks)*duration` (61.6s/2 → chunk0 0–30.8, chunk1 30.8–61.6). Helper `compute_chunk_window` is separately unit-tested.
- The 109 raw "multi-arm" clips are mostly OLD food/activity events (arms `gemma_4_e4b`/`llama_4_maverick`/`qwen_3_5_vlm`) with no `observed_facts`; `fetch_multi_arm_events` filters to ≥2 arms WITH facts → 6 VLM clips, only the test clip has a present video.

## ⭐ Determinism (byte-identical rebuild — Job 3 reproducibility)
Verified: rebuild v1.0.0→v1.0.1 produced **SHA256-identical** `train.jsonl` + `val.jsonl`. Guarantees: arms sorted before clustering (Job 1 property); OCR/transcript aggregation `set → SORTED list` (a raw set→list order was a latent non-determinism bug — the 2nd such bug caught this flywheel, after Job 1's clustering order-sensitivity); train/val split by `SHA256(seed:example_id)` (same id → same split regardless of order). The builder must keep this property.

## v1.0.0 dataset (thin_start, auto-grows)
2 examples (test clip's 2 chunks: chunk0 = 0 high + 6 med, chunk1 = 2 high + 1 med), 1 train / 1 val, 32 frames (16/chunk, 1600×1200 PNG), 46 MB. Manifest tagged `first_build` + `dataset_size_category=thin_start` + `expected_growth_pattern`. Skips tracked in `manifest.generation_metadata` (no_video 3 / no_consensus 1 / insufficient_labels 3). **Auto-grows** as new multi-arm v3.4+ clips WITH videos accumulate — just re-run `training.cli`, no code change.

## Example schema (for Job 3)
`{dataset_schema_version, example_id, source_video, chunk_start_sec, chunk_end_sec, inputs:{frame_paths(relative), audio_transcript, ocr_text}, labels:{high_confidence_facts, medium_confidence_facts, fact_count_*}, metadata}`. Tiers: high ≥0.83, medium 0.67–0.83 (disjoint).

## Foundation for Job 3 (deferred, ~12–16h)
LoRA fine-tune local Gemma 4 26B A4B on this dataset → Korean-financial/lifelog specialization; production switch ≈80% Gemini cost cut. **Gate:** do NOT start real training until the dataset grows to **≥20 examples** (current 2 only support an "overfit on 1" sanity-check). Needs a PEFT install (clear the DLL-safety bar). See handoff §9 deferred for full prereqs/criteria.

## Constraints honored
No change to any production/extraction/aggregator/consensus/word/frontend file; no migrations; no new packages; `test_data/` + `training_data/` kept out of git; per-part build with tests; no emoji in `print()` ([OK]/[SKIP]/[WARN]/[ERR]). 28 training + 46 services tests pass; all v3.5 gates intact.
