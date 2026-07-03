---
name: project-healthcare-6arm-gemini3
description: Healthcare AI Agent (Triple-H lifelog) — 6-arm pipeline (2026-06-02). Added gemini_3_1_pro_preview + gemini_3_5_flash via env-override watchers; zero changes to _lifelog_test.py; gemini_2_5_pro intact.
metadata: 
  node_type: memory
  type: project
  originSessionId: ca30b8c8-372d-44be-97df-a9e0250935d2
---

# Healthcare AI Agent — 6-Arm Pipeline: Gemini 3 Watchers (2026-06-02, COMPLETE)

Repo: `C:\Users\A\projects\healthcare-ai-agent`. Resume via `handoff.md` (⭐ LATEST section at top). Builds on [[project-healthcare-v34-audio-xref]].

## What shipped
Two new LLM arms: `gemini_3_1_pro_preview` (model `gemini-3.1-pro-preview`) + `gemini_3_5_flash` (model `gemini-3.5-flash`). Total arms **4 → 6**. Commit `649c2b2` (gemini-3-arms) + `<session-close>` docs.

## Design: Option A — env-override watchers (KEY DECISION)
Phase 0 found the mission's template assumed an architecture the repo doesn't have. The reality:
- Gemini calls are **raw httpx REST** to `generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` — NOT the `google.generativeai` SDK (which isn't even installed).
- No `ARMS` dict; arms are a **hard-coded 4-key boolean dispatch** (gemma/qwen=compare/llama4/gemini) threaded through fixed `out` dict + result tuple + write block in `_lifelog_test.py`.
- **One global gemini model per process**, read from `GEMINI_MODEL` env via `_gemini_config()`.

So instead of SDK/dispatch surgery, each new watcher sets `GEMINI_MODEL=<model>` (via `ARM_GEMINI_MODEL` map in `_arm_helpers.run_single_arm`) and reuses the existing gemini REST path. **`_lifelog_test.py` was NOT modified** — that's why `gemini_2_5_pro` stayed intact. `source_model` auto-derives via `_model_to_source_tag(model)` → exactly `gemini_3_1_pro_preview` / `gemini_3_5_flash`.

## Files
- `_arm_helpers.py`: +2 ARM_FLAGS/ARM_LABELS, +`ARM_GEMINI_MODEL` map, +env-override in `run_single_arm`.
- NEW `gemini_3_1_pro_watcher.py`, `gemini_3_5_flash_watcher.py` (4-line stubs, pattern: `from _arm_helpers import main; main("<arm>")`).
- `frontend/.../lifelog/page.tsx`: +2 `SELECTABLE_SOURCES` + `SOURCE_BADGE` (3.1 Pro=orange, 3.5 Flash=cyan).
- Option B commit choice: **adopted the previously-untracked watcher system into git** (gemma4/qwen/llama/gemini watchers — secret-scanned clean, 10-line stubs).

## Live-verified
Both models return HTTP 200. Wrote to Supabase: gemini_3_1_pro_preview=2 rows, gemini_3_5_flash=2 rows, dated 2026-06-01 (glasses-clock mtime fallback). gemini_2_5_pro INTACT (44 rows, 5 clips). v3.4 audio-xref auto-active on new arms (value_updates source tags + audio_only_terms).

## Latency + variance
Flash ~40–53s/chunk (faster); 3.1 Pro Preview ~220s/chunk (markedly slower). Pro Preview produced fewer events (2) than Flash (5 smoke/2 DB) — event count varies between runs even at temp 0. A/B comparison deferred.

## How to run a new arm
From `backend/glasses_watcher`: `python gemini_3_5_flash_watcher.py "<clip>"` (add `--no-supabase` to smoke, `--watch` to poll). One GPU processor at a time — stop other watchers first. Always `.venv\Scripts\python.exe`.

## Deferred (added this session)
- Gemini arm A/B comparison (Pro Preview vs Flash vs 2.5 Pro) before picking a default.
- Dead default `GEMINI_MODEL_DEFAULT="gemini-3.1-pro"` (`_lifelog_test.py:1131`) — that ID doesn't exist on the API; harmless (overridden by .env=gemini-2.5-pro) but should be a real ID.
- 3 untracked non-watcher files in glasses_watcher (`_v2_audit.py`, `tests/__init__.py`, `tests/test_ocr_preprocessor.py`) — track or .gitignore.

## Constraints honored
No change to `ocr_preprocessor.py` / `audio_fact_extractor.py` / `_lifelog_test.py` / LIFELOG_PROMPT; no migrations; no new packages (REST path; SDK not needed); deliberate commits (left pre-existing WIP + the `/lifelog/ask` page's uncommitted edits alone).
