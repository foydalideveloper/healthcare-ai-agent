# Healthcare AI Agent — RESUME HERE (Session Handoff)

**Last updated:** 2026-06-04, end of **gemini-fact-expansion session** (Gemini arms now 41-66 facts).
**This is the FIRST file to read when resuming.** It is the umbrella + the current-state pointer.

> ## Read order on resume
> 1. **This file** (`handoff.md`) — current state, what to do next, where everything lives.
> 2. **`handoff_2026-06-02.md`** — full delta for the work done in the last two sessions (Full Report feature + v3.3 quality upgrade + production fixes). Detailed.
> 3. **`handoff_2026-05-29.md`** — prior session (paths, services, quick-start commands).
> 4. **`CLAUDE.md`** — architecture overview (LLM layers, DB, project structure).
> 5. Deep state of record: `~/.claude/projects/C--Users-tripleh/memory/project_healthcare_complete_handoff.md` (0-to-100% locked decisions). NOTE: this session ran under user `C--Users-A`; memory index is at `C:\Users\A\.claude\projects\C--Users-A\memory\MEMORY.md`.

---

## ⭐ LATEST: Gemini Fact Expansion (2026-06-04) — COMPLETE

**Problem:** with the shared v3.3 prompt, Gemini arms produced too few `observed_facts` (3.1 Pro=19, Flash=18) vs Gemma's 49 — high quality but low volume. **Fix:** a Gemini-ONLY prompt addendum that instructs DECOMPOSITION of what the model already sees (no padding, no quality drop). Purely additive.

**Architecture (key — differs from the original mission template):** the v3.3 prompt is `LIFELOG_PROMPT` (line 105), embedded in the SHARED `_build_user_prompt()` used by all 4 base arms. To isolate a Gemini-only variant WITHOUT touching shared code, a new constant **`GEMINI_FACT_EXPANSION_ADDENDUM`** (defined ~line 1146, in the Gemini section) is appended to the prompt **inside `call_gemini_lifelog` ONLY** (line ~1275), AFTER `_build_user_prompt()` returns. Diff = **100 insertions, 0 deletions** — `LIFELOG_PROMPT`, `_build_user_prompt`, `_GEMMA_SYSTEM_INSTRUCTION`, and the gemma/qwen/llama callers are byte-identical. All 3 Gemini arms share `call_gemini_lifelog`, so the addendum applies to all 3 automatically.

**The 8 decomposition rules in the addendum:** (1) multi-value panels → one fact per value, (2) multi-stock boards → one fact per stock, (3) each headline/overlay → own fact (verbatim quoted), (4) named entities → split identity from each claim, (5) each UI element → own fact w/ location, (6) audio↔video cross-references, (7) scene/environment → each detail, (8) temporal/progression. Quality bar UNCHANGED (subject+value/relationship, no filler, no padding, skip empty categories). Explicitly reinforces "KEEP value_updates multi-value behavior."

**Commit:** `5e69597` **gemini-fact-expansion**.

**Per-arm `observed_facts` expectations (UPDATED — measured on test clip `20260528144922838.mp4`):**
| Arm | Facts | Multi-value value_updates | Notes |
|---|---|---|---|
| Gemma 4 26B | **~49** | none (not implemented) | UNCHANGED — verbose, ambient-inclusive; v3.3 prompt untouched |
| Qwen 3.5 VL | baseline | none | UNCHANGED (prompt untouched; not re-run) |
| Llama 4 Maverick | baseline | none | UNCHANGED (prompt untouched; not re-run) |
| **Gemini 2.5 Pro** | **~46** | **3** (KOSPI, KOSDAQ, USD/KRW) | expanded |
| **Gemini 3.1 Pro Preview** | **~66** | **3** (KOSPI, KOSDAQ, USD/KRW) | highest/most thorough decomposition |
| **Gemini 3.5 Flash** | **~41** | **0** | expanded; doesn't do cross-frame multi-value (model limitation, not a bug) |

The ~25-fact spread between Flash (41) and 3.1 Pro (66) is each model's natural verbosity at the SAME quality bar — correct behavior. **3.1 Pro overshot the 40-60 target to 66; deliberately ACCEPTED** (0 near-dupes, ~3% filler — high-quality over-delivery; a hard count cap would make the model drop genuine facts and risk the multi-value tracking).

**Critical preservation verified (the must-not-break list):** Gemma still 49; Gemini 3.1 Pro KOSPI 8,228.70→8,428.84 + KOSDAQ 1,133.13→1,148.16 + USD/KRW 1,501.80→1,500.40 all PRESENT; audio_only_terms=4 on all 3 Gemini arms; value_updates source tagging (7 audio-tagged each); schema v3.4; no latency regression. Quality bar held (0 dupes, ~3% filler).

**Baselines + post-expansion artifacts** (untracked test_data): `baseline_gemini_{3_1_pro_preview,3_5_flash}_pre_expansion.json`, `expansion_test_gemini_{3_5_flash,3_1_pro_preview}.json`.

### ❌ REJECTED EXPERIMENT (2026-06-04): "Rule 1a" absolute-value prompt fix — DO NOT REPEAT

**What was tried:** a one-sentence sub-rule ("Rule 1a") added to `GEMINI_FACT_EXPANSION_ADDENDUM` telling Gemini that when a metric shows BOTH an absolute value AND a change, emit TWO separate `observed_facts` (base + delta). Goal: get KOSPI's base value (8,228.70) into observed_facts (it was only emitting the +181.19 change). **Commit-and-test discipline; NEVER committed.**

**Result over 3 runs of Gemini 3.1 Pro Preview (same KBS clip):**
| | run1 | run2 | run3 | |
|---|---|---|---|---|
| KOSPI absolute standalone (the target) | ✗ | ✗ | ✗ | **0/3 — rule ineffective** |
| SK Hynix absolute | ✓ | ✓ | ✗ | 2/3 (noise level) |
| KOSDAQ abs / Samsung abs (controls) | noisy | noisy | noisy | KOSDAQ 1/3, Samsung 3/3 — **model variance, not rule damage** |
| multi-value tracking + audio_only_terms | ✓ | ✓ | ✓ | **3/3 preserved** |
| total facts | 49 | 48 | 39 | all below the prior single 66-sample |

**Conclusion:** a 1-sentence prompt rule CANNOT reliably force model attention onto a specific absolute value (KOSPI base absent in 3/3). Strengthening to "MUST" would likely just add noise. The earlier single-run "control regression" alarm was model variance (KOSDAQ abs is only 1/3 even WITH the rule). Rolled back per a pre-agreed 3-run decision matrix (CASE B). **Cost of re-trying this prompt approach: ~25 min wasted. Don't repeat without new evidence.**

**Root-cause insight — the "gap" isn't really a gap:** KOSPI's base value IS in the report — captured in **Value Updates** as the multi-value entry `8,228.70 → 8,428.84` (survived all 3 runs). The cross-frame value tracking does the job; it just lives in the Value Updates section rather than being duplicated into `observed_facts`.

**Correct future path (if absolute values in `observed_facts` ever becomes a real demo requirement):** a DETERMINISTIC aggregator-side backfill in `full_report_aggregator.py` — for each `value_updates` entry with `source='video'`, synthesize 1-2 `observed_facts` ("Index X at value Y", "Index X changed from Y to Z") at AGGREGATION time, not via prompt. 100% reliable, model-agnostic, works on all 6 arms at once, no API cost. Risk: needs dedup vs facts the model already emitted. Est. ~45-60 min. See §9.

---

## 6-Arm Pipeline — Gemini 3 Watchers (2026-06-02) — COMPLETE

**Two new LLM arms added: `gemini_3_1_pro_preview` + `gemini_3_5_flash`. Total arms 4 → 6.** Purely additive; the existing 4 arms (gemma4, qwen, llama4, gemini_2_5_pro) are untouched.

**Design — Option A (env-override watchers).** Phase 0 found the repo does NOT use the `google.generativeai` SDK (it's raw httpx REST to `generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`), has NO `ARMS` dict (hard-coded 4-key boolean dispatch: gemma/qwen=compare/llama4/gemini), and reads ONE global gemini model from `GEMINI_MODEL` env per process. So instead of the mission's SDK/dispatch surgery, each new watcher sets `GEMINI_MODEL=<its model>` and reuses the existing gemini REST path. **`_lifelog_test.py` was NOT modified** — that's why `gemini_2_5_pro` stayed intact. `source_model` auto-derives via `_model_to_source_tag(model)`.

**Commits:**
- `649c2b2` **gemini-3-arms** — `_arm_helpers.py` (+ARM_FLAGS/ARM_LABELS/ARM_GEMINI_MODEL map + env-override in `run_single_arm`); NEW `gemini_3_1_pro_watcher.py` + `gemini_3_5_flash_watcher.py` (4-line stubs); `lifelog/page.tsx` (+2 SELECTABLE_SOURCES + SOURCE_BADGE: 3.1 Pro=orange, 3.5 Flash=cyan). Also **adopted the previously-untracked watcher system into git** (gemma4/qwen/llama/gemini watchers — secret-scanned clean).

**Live-verified (test clip `20260528144922838.mp4`, written to Supabase):**
- Both models exist on the API and return HTTP 200. `gemini_3_1_pro_preview`=2 rows, `gemini_3_5_flash`=2 rows, both dated **2026-06-01** (glasses-clock mtime fallback). `gemini_2_5_pro` INTACT (44 rows, 5 clips, untouched).
- **v3.4 audio-xref auto-active on the new arms** (gemini_3_5_flash report = schema v3.4, value_updates with source tags, audio_only_terms=4).

**Per-arm latency profile (5 cloud/local entries — was 4):**
| Arm | Model | Latency (per 60s chunk) | Notes |
|---|---|---|---|
| Gemma 4 26B (local) | gemma4:26b-a4b-it-q8_0 | ~50s full clip | primary local; GPU-locked w/ Qwen |
| Qwen 3.5 VL (local) | qwen3-vl:30b-a3b-q4 | varies | JSON-salvage; shares GPU lock |
| Llama 4 Maverick (NIM) | llama-4-maverick-17b-128e | ~cloud, flaky | NIM random 500s |
| Gemini 2.5 Pro (cloud) | gemini-2.5-pro | reliable | the dependable cloud arm |
| **Gemini 3.5 Flash (cloud)** | gemini-3.5-flash | **~40–53s/chunk** | NEW; faster |
| **Gemini 3.1 Pro Preview (cloud)** | gemini-3.1-pro-preview | **~220s/chunk** | NEW; markedly slower |

**Model-variance observation:** on this clip, Pro Preview produced FEWER events (2) than Flash (5 smoke / 2 DB) — even at temperature 0 the event/chunk count varies between runs. Pro Preview may be more conservative (fewer, denser events) vs Flash's higher recall. **Worth a proper A/B comparison next session** (event count, fact richness, Korean accuracy) before picking a default Gemini arm.

**Operational notes:** the new gemini arms run as SEPARATE watcher processes (the project's production pattern), not one `--pipeline` run — by design (one global gemini model per process). The `/lifelog/ask` standalone page still has pre-existing uncommitted edits + its own registry; left untouched (the inline per-event Ask picker already shows all 6 via SELECTABLE_SOURCES). The gemma4 watcher was stopped during testing — restart with `python gemma4_watcher.py --watch` from `backend/glasses_watcher`.

---

## v3.4 Audio-OCR Cross-Reference Layer (2026-06-02) — COMPLETE

**The architectural gap is fixed.** Previously the Whisper transcript was semi-isolated: structured sections (Value Updates, Key Terms) were OCR-only, so audio-spoken values like "SK하이닉스 시가총액 1,600조 원" or "마이크론 19% 급등" never reached the structured tables. v3.4 adds a **purely additive, aggregator-time** layer that parses the transcript for structured facts, cross-references them against OCR, and promotes them.

**What shipped (5 commits, all independently revertible):**
- `039638d` **audio-xref-extractor** — NEW `backend/app/services/audio_fact_extractor.py` (pure stdlib, no pipeline imports). Parses Korean trillion-currency / won / % / USD / year-range / multiplier; detects financial entity + claim_type from context; cross-references vs OCR; promotes. **30 unit tests** in `backend/app/services/tests/test_audio_fact_extractor.py` (all pass).
- `ea98809` **audio-xref-aggregator** — wired into `full_report_aggregator.py` after dedup+quality-filter, before return. Schema **v3.3 → v3.4**. New metrics: `audio_facts_extracted`, `audio_facts_cross_referenced`, `audio_only_facts`. New field `audio_only_terms`.
- `96e60c4` **audio-xref-tuning** — conservative full-token cross-ref (no bare-digit collision) + skip currency-unit/bare-multiplier label noise.
- `16ac9dc` **audio-xref-word** — `word_exporter.py`: Value Updates gains a **Source** column (Audio=blue / Video), claim_type subtitle, an **Audio-only Mentions** Key-Terms sub-section, +2 title-page metric rows.
- `8ad418f` **audio-xref-frontend** — `lifelog/page.tsx`: source badges + claim_type subtitles in the Full Report modal, Audio-only Mentions sub-section, **Esc-to-close**. Defensive vs old events lacking the new fields.

**Result on the KBS test clip (`20260528144922838.mp4`, gemma4):** value_updates **4 → 11** (4 video + 7 audio); **audio_only_terms = 4**; metrics extracted=10 / cross-referenced=5 / audio-only=5. Word doc 44 → **45.5 KB**.

**ZERO regressions** (every check byte-identical to `test_data/kbs_clip/baseline_pre_audio_xref.json`): observed_facts **49**, Key Terms **416**, OCR appendix **349**, timeline **4 windows**, headlines **3**, panels **213**, recall **0.95**, transcript text unchanged, Korean Malgun Gothic intact (34 CJK runs, 0 missing eastAsia), 0 mojibake.

**v3.4 caveats (new):**
- a. **Nearest-left entity match.** The extractor attaches the closest preceding entity to a value; it does NOT do multi-entity positional pairing. "각각 2.7%, 9.3% 급등한 삼성전자와 SK하이닉스" mislabels 9.3% to 삼성전자 (should be SK하이닉스). Cosmetic; deferred (§9).
- b. **Conservative cross-ref by design.** Matching uses the full normalized token (digits **+** unit), NOT the bare numeric core — a lone "1600" in the busy OCR dump must not mask the audio-only "1,600조 원" market-cap claim. This is deliberate; do not "loosen" it back to digit-substring matching.
- c. **Generic-label rows kept.** A real fact with a non-specific label (e.g. `time_range / 3년에서 5년`, supply-contract extension) is KEPT as a distinct audio Value-Updates row even though its label isn't an entity — the boss demo benefits from seeing it.

**Latest report artifact:** `test_data/kbs_clip/test_report_v34.docx` (45.5 KB). Baseline for regression diffing: `test_data/kbs_clip/baseline_pre_audio_xref.json`.

**Off-limits honored:** no touch to `ocr_preprocessor.py` / LIFELOG_PROMPT / `_lifelog_test.py` / watchers; no migrations; no new packages; no re-extraction. All work is post-processing at aggregator/exporter/frontend time.

---

## 1. What this project is

**Triple-H Co., Ltd. Healthcare AI Agent** — patent-protected (10-2025-0145274, Lee Chom-Sik, Oct 2, 2025).
A lifelong AI-assisted health timeline driven by **AI glasses (AIMB-G1)** + wearables, targeting 100,000 Korean users.

One sentence: *Korean users wear AI glasses; the system records what they eat / drink / take / do / see, runs it through a multi-tier extraction pipeline (CNN cascade → multimodal LLMs → nutrition DBs), persists to a 40+ table Supabase DB, and serves a Next.js dashboard with multi-dimensional drill-down + health forecasting.*

**Core product:** HRT (Health Record Timeline). The sub-area worked on this session is the **Lifelog pipeline** — glasses video → OCR (PaddleOCR) + audio (Whisper) + 4-arm multimodal LLM extraction → structured events → dashboard.

---

## 2. What we are trying to build (this session's scope)

The **"Full Report"** feature + **v3.3 data-quality upgrade**, both aimed at making a single 60-second glasses clip produce **one consolidated, demo-ready report** (on-screen modal + downloadable Word `.docx`) that a non-technical boss can show off tonight.

The clip under test is a **Korean KBS news broadcast** captured through the glasses (`test_data/kbs_clip/`).

---

## 3. The goal we are working toward

A `.docx` report from one clip that reads as **clean, distinct, professional findings** — not raw OCR noise, not reworded duplicates. The concrete current target: the `observed_facts` list should be **~42-45 truly distinct facts** (down from a raw 59), with no filler, no headline-fragment dupes, deduped visual objects, and a clean chronological timeline.

---

## 4. Current state of the project

**Demo-ready.** The Full Report feature + v3.3 quality upgrade are complete and committed. The latest report is `test_data/kbs_clip/test_report_v33_fixed_v4.docx` (44 KB).

- 4-arm LLM pipeline runs: **Gemma 4 26B (local Ollama)** and **Gemini 2.5 Pro (cloud)** are the dependable arms; Llama 4 Maverick (NVIDIA NIM) is flaky (provider 500s); Qwen3-VL 30B Q4 (local) writes rows via JSON-salvage.
- Whisper now runs **CPU int8** (frees GPU for Gemma 26B Q8 + Paddle on the 32GB RTX 5090).
- Dashboard (Next.js :3000) + FastAPI (:8888, `--reload`) both hot-reload.

---

## 5. Current state of code — what shipped

All of this is **committed** (see §8 for the exact last commit). Key files:

**Backend (new this session):**
- `backend/app/services/full_report_aggregator.py` — pure aggregator. Dedup OCR/facts/enumerations (exact + semantic), merge timeline by window, value_updates by label. Applies the v3.3 quality filter. `SCHEMA_VERSION="v3.3"`. Recent helpers: `_is_substantive_fact()`, `_semantic_dedup(thresh=0.7)`, `_dedup_objects(head_merge=)`, `_merge_timeline()`, `_is_headline_fragment()`. **(User has this file open in the IDE.)**
- `backend/app/services/word_exporter.py` — `generate_word_report()` → streaming `.docx`, 9 sections, Korean via **Malgun Gothic eastAsia font on every run** (python-docx `font.name` only sets ASCII — must set `w:eastAsia` explicitly).
- `backend/app/api/lifelog.py` — `GET /api/v1/lifelog/full-report` (JSON) + `/full-report.docx` (StreamingResponse). Uses the repo's httpx `SupabaseClient` (NOT supabase-py). Endpoint prefix = router `/api/v1` + `/lifelog`.
- `backend/glasses_watcher/ocr_quality_filter.py` — pure filter: keeps digits/currency/entities, drops particles/single-chars/garble/all-caps-non-entity/**mojibake**. 12 unit tests in `tests/test_ocr_quality_filter.py` — **all pass**.

**Frontend (new this session):**
- `frontend/hrt-dashboard/app/lifelog/page.tsx` — `📄 Full Report` 6th button (after 🧠 Combined) → `<FullReportModal>` with collapsible sections + 📥 Download as Word. Existing 5 buttons untouched. tsc-clean for this file.

**Prompt:** `backend/glasses_watcher/_lifelog_test.py` — `LIFELOG_PROMPT` v3.3 (observed_facts = 15-30 substantive subject+value statements; enumerated skip particles/garble). Also holds the production fixes (torch-before-paddle import, CPU Whisper, JSON salvage, GPU lock, timeline injection).

---

## 6. Files being actively edited / touched this session

- **Actively edited & open in IDE:** `backend/app/services/full_report_aggregator.py`
- **Created/edited this session:** the four backend files in §5 + the frontend `page.tsx` + `_lifelog_test.py` prompt + `tests/test_ocr_quality_filter.py`.
- **Generated artifacts:** `test_data/kbs_clip/test_report_v33_fixed_v4.docx` (latest) and earlier `_v1.._v3` + `quality_*.json` snapshots.
- **OFF-LIMITS (do not touch):** `backend/glasses_watcher/ocr_preprocessor.py` — the user explicitly forbade extraction-pipeline changes there.

---

## 7. What didn't work, why, and how we fixed it

| Symptom | Root cause | Fix | Commit |
|---|---|---|---|
| Dashboard panels "No data" | endpoint `select` omitted v3 columns | added them + graceful 42703 fallback | lifelog.py |
| Whisper **WinError 127** | PaddlePaddle imported before torch → ctranslate2 can't resolve cuDNN DLL | `import torch` BEFORE paddle in `_lifelog_test.py` | `1311138` |
| Wrong dates (May for June clips) | AIMB-G1 glasses clock stuck days behind; pipeline trusted filename | mtime sanity-fallback (>12h drift → mtime−duration) | `9ec7402` |
| Gemma timeout → 0 rows | Gemma 26B Q8 (~30GB) + Whisper-GPU + Paddle > 32GB VRAM | **Whisper → CPU** (int8) | `1c4a409` |
| Qwen 0 rows / Llama4 flaky | Q4 repetition truncates JSON; NIM random 500s | JSON truncation/bracket salvage + anti-repetition; NIM retry+backoff; **shared GPU lock** Gemma+Qwen | `5977e25`, `175f589` |
| Audio panel empty | transcript not injected as ground truth | inject Whisper transcript into `audio_extraction.transcript_full` | `0c3ac31` |
| Korean console garble | Windows cp949 mojibakes Korean/em-dash in print/grep | `PYTHONIOENCODING=utf-8`; write UTF-8 JSON & Read it; **never emoji in print() — use `[OK]/[ERR]/[INFO]`** | — |
| Word doc still had ~59 facts (filler, headline dupes, dup objects, overlapping timeline) | aggregator dedup too conservative | polish r2: filler+, headline-fragment drop, `_dedup_objects`, topic/timeline cleanup | `046a112` |

---

## 8. Where & why we stopped now

**Stopped because:** context window is running out → starting a fresh session.

**Last commit:** `046a112` — "full-report polish r2: filler+, headline-fragment drop, object dedup, topic/timeline cleanup".

**Last action:** generated `test_report_v33_fixed_v4.docx` and reported results to the user. The 7 polish items: **6 fully done** (stale metadata row removed, residual filler 0, headline fragments dropped, visual objects merged, weak topic dropped, timeline → 4 clean windows 0-15/15-30/30-45/45-60). **Item 4 (semantic dup clusters) is PARTIAL.**

**Result: 59 → 49 observed_facts** (target was ~42-45). The ~4-fact overage is **low-prominence ambient scene observations** (fan / monitor / studio) that share only an *entity*, not enough overlapping text to merge by lexical similarity without losing distinct spatial detail (same safety principle that deliberately kept the "top left corner" date fact). The financial facts at the top of the list are clean and distinct.

**Open decision — RESOLVED 2026-06-02: user chose (A). Ship v4 at 49 facts.**
- **(A) ✅ CHOSEN** — Ship v4 at 49 facts. Clean, safe; the ~4-fact overage is harmless end-of-list ambient scene clutter (fan/monitor/studio) that does not touch the boss-facing top-25 financial facts. Same over-merge-risk principle that deliberately kept the distinct date fact.
- **(B) rejected** — Force the fan/monitor/studio cluster merges (hits 42-45) — not worth the regression risk; would lose true spatial/scene nuance.

**Session CLOSED 2026-06-02.** v4 is the shipped report. Demo-ready tonight.

---

## 9. Next further plans

**✅ Completed in this session (2026-06-04):**
- **`b7a5946` — Aggregator-side absolute-value backfill.** Implements the deferred path below, superseding the rejected "Rule 1a" prompt experiment (whose ❌ negative-result note stays intact as the "why we didn't go that direction" record). One file: `full_report_aggregator.py` (+80/−1). Adds 4 helpers (`_normalize_for_fact_dedup`, `_generate_facts_from_value_update`, `_is_fact_already_present`, `backfill_absolute_value_facts`) + integration at line 561 (AFTER the v3.4 audio-xref source tagging). **Base-value-only emission (Option 1)** — the second-value branch was dropped as redundant with the Value Updates "Y → Z" arrow notation. Two regex bugs caught & fixed during testing: (1) sentence-final period swallowed by the number regex (`8,228.70.` ≠ `8228.70`), (2) label robustness (`USD/KRW` ≡ `USD-KRW`, slash/hyphen/space-insensitive). Result: **+1 fact on Gemini 3.1 Pro** (KOSPI base added, 100% deterministic vs Rule 1a's 0/3), **+0 on Gemma** (dedup skips its natural facts), +0 on the empty edge case. Cross-arm (all 6 arms), no API cost. Multi-value tracking / audio_only_terms=4 / schema v3.4 all preserved.
- **❌ Option B (aggregator-side OCR entity recovery) — ATTEMPTED & ABANDONED at design (2026-06-04, NO commit).** Goal was to scan `ocr_appendix_full`/`all_ocr_text` for missed entities (SK스퀘어, 삼성전자우, 현대차, 삼성전기, EUR/USD, CNH/KRW, CAD/KRW, S&P 500, SK하이닉스 2,328,000) and promote label+value pairs into `value_updates`→`observed_facts` (via Option A's chain). **Phase 0 killed it before any edit:** **6 of 8 targets were never OCR-captured** (not in the appendix at all — the appendix is mojibake-dominated, e.g. `"EXAHANUGE"`, `"!II1"`); the **2 present** (SK스퀘어, 삼성전자우) appear only as comma-LESS, OCR-garbled, **value-before-label** tokens (`…"1276000", "SK스퀴어"…`) interleaved in a noisy cluster (`95000/1276000/스486/192000`). Even the mission's own design wouldn't have worked (its value regex *required* commas; it scanned forward from the label). Building a 2/8 recovery would be clip-specific overfit with real false-positive risk. **This is the [[Rule 1a]] pattern (`f2e74dd`) repeating: post-processing cannot manufacture data the extraction layer never captured.** The real fix is OCR-quality work in the off-limits `ocr_preprocessor.py` (see deferred item below).
- **`85bf21f` — Audio preprocessing with noisereduce (Lighter scope).** NEW `backend/glasses_watcher/audio_preprocessor.py` (noisereduce spectral gating + ~6dB amplification on the 16kHz mono WAV from `extract_audio()`, before Whisper) + surgical integration inside `whisper_transcribe()` in `_lifelog_test.py` (+32/−1) with a **`SKIP_AUDIO_PREPROC` .env escape hatch** + temp-file cleanup + 4 unit tests. **soundfile-only I/O — librosa deliberately SKIPPED** (audio is already 16kHz mono, so no resample needed) to avoid numba/llvmlite and keep the torch/paddle/ctranslate2 DLL stack untouched (numpy stays 1.26.4). Degrades gracefully to raw audio on any failure / non-16kHz input. **Honest result:** eliminated **4/4** known Whisper error-forms (originals 승리/크룸/분풍/공독); **2/4 cleanly produce the correct word** (심리, 흐름); the other 2 segments (훈풍, 공급) transcribe differently in the new pass — error gone but correct form not empirically confirmed. Noise reduction can't fix errors that are genuine model/phonetic limits rather than noise artifacts. Latency **improved −22s** (302.7s vs ~325s baseline). DLL-stack health verified by a single-process PaddleOCR + Whisper + Gemini run. **Adds 2 packages — see "Environment Dependencies" below.**
- **🟡 E1 — Authorized one-session `ocr_preprocessor.py` exception (2026-06-04) — negative-leaning; off-limits RESTORED.** Goal: recover OCR-missed financial content (Hana Bank multi-currency board, KRX individual stocks). Outcome:
  - **C1 (density-aware upscale) — SHIPPED `81c0c07`.** `_upscale_factor_for` now promotes a LARGE panel 2×→3× when its box-density ≥ `_DENSE_PANEL_BOXES_PER_100KPX`. Harmless infrastructure (+1s, all gates pass) — **kept** even though it gives no standalone entity gain (the 4000px width cap clamps wide boards to ~2× regardless). May help a future OCR session if the cap is ever raised.
  - **C2 (DBSCAN row separation) — MEASURED in 3 configs, then REVERTED (uncommitted).** eps 0.12→0.07/0.085 + min_samples 4→3 fragments dense boards into smaller upscalable panels. *It worked* — surfaced **3/3 Hana Bank entities** (EUR/USD, CAD/KRW, **S&P 500 7,519.12**) into `observed_facts`, all v3.4 gates pass — **BUT** coupled to prohibitive costs: **+33s OCR latency** (over the +30s budget; **not tunable** — eps 0.07 and 0.085 both +33s) and **observed_facts inflated 44→95** (garbled-OCR noise; PaddleOCR misreads tiny fonts: 현→허, 1,630,000→630000, .→/). The only mitigation (a top-N densest **panel cap**, C3-repurposed) at N=3 dropped latency to +16s and noise to 51 facts **but BROKE the KOSPI/KOSDAQ/USD-KRW multi-value tracking** (the cap dropped the Hana panel carrying the 2nd KOSPI value 8,428.84) and lost 2/3 entities. **No N gives recovery + budget + preserve-gates together.** Reverted; KRX stocks (현대차/삼성전기) never cleanly recovered (garbled worst).
  - **C3 (original lower-ROI-threshold idea) — NOT implemented** (data showed the opposite lever was needed; pivoted to the panel cap, which also failed).
  - **Conclusion — third instance of the capture-layer-ceiling pattern** ([[Rule 1a]] `f2e74dd`, Option B `9bbb412`, now E1): the Hana board IS recoverable via aggressive fragmentation, but bundled with costs that tuning the current PaddleOCR stack can't separate. The real fix needs **different tooling** (PaddleStructure/table OCR, LayoutLM, or a commercial Korean OCR API) or **better capture** (Mentra Live / higher-res sensor) — not more tuning. Deferred (§9); requires fresh authorization to touch `ocr_preprocessor.py` again.

1. **Immediate:** ✅ DONE — user chose (A); v4 (49 facts) accepted as the shipped report. No further action on item 4.
2. **Deferred (from `handoff_2026-06-02.md` §5 — not active):**
   - Date-entity dedup (3 date facts → 1; cosmetic, regression risk, deliberately skipped).
   - Multi-arm comparison inside the Word doc (cross-arm JSON aggregation already works by omitting `source_model`).
   - Audio quality — external mic / Mentra Live migration to fix Korean transcript errors. **(Partially mitigated 2026-06-04 in `85bf21f`: noisereduce preprocessing eliminated the 4 known error-forms, 2/4 fully corrected — software side done; hardware mic upgrade still the real fix for the remaining phonetic-limit errors.)**
   - value_updates multi-value deltas on noisy OCR — needs `detect_value_changes` robustness in the **off-limits** `ocr_preprocessor.py`.
   - Glasses clock re-sync via AIMB bridge (mtime fallback is a safety net, not a cure).
   - AIMB-G1 BLE auto-wake (blocked — see `aimb-bridge-android/handoff.md`).
   - **Multi-entity positional pairing with 각각/respectively marker** — the audio-xref extractor (`audio_fact_extractor.py`) uses nearest-left entity match; it doesn't handle list-pair semantics where N values map to N entities by position. e.g. "각각 2.7%, 9.3% 급등한 삼성전자와 SK하이닉스" attaches 삼성전자 to BOTH percentages, when 9.3% should pair to SK하이닉스. Cosmetic mislabel on the audio Value-Updates rows; deferred (added 2026-06-02 audio-xref session).
   - **Source tagging on `observed_facts`** (audio / video / both) — would require a LIFELOG_PROMPT change + **re-extraction** of events; skipped this session to avoid regression risk. The v3.4 layer only tags `value_updates`, which is post-processing-safe.
   - **Audio-fact entity-coverage expansion** — `KOREAN_FINANCIAL_ENTITIES` currently covers EN/KO financial names (semiconductors, indices, banks). Could extend to more sectors (healthcare, energy, consumer) as the clip corpus broadens.
   - **Gemini arm A/B comparison** — Pro Preview (slower, fewer/denser events) vs 3.5 Flash (faster, higher recall) vs 2.5 Pro. Compare event count, fact richness, Korean accuracy before choosing a default Gemini arm. (added 2026-06-02 6-arm session.)
   - **Dead default `GEMINI_MODEL_DEFAULT="gemini-3.1-pro"`** in `_lifelog_test.py:1131` — that exact ID does NOT exist on the API (only `gemini-3.1-pro-preview` does). Harmless today because `backend/.env` pins `GEMINI_MODEL=gemini-2.5-pro`, but the fallback is dead. Update the default to a real ID someday. (cleanup; added 2026-06-02.)
   - **Git hygiene — 3 untracked non-watcher files** in `backend/glasses_watcher/`: `_v2_audit.py`, `tests/__init__.py`, `tests/test_ocr_preprocessor.py`. Left untracked when the watcher system was adopted (they're not watchers). Decide whether to track or .gitignore them. (added 2026-06-02.)
   - **Gemma decomposition (optional)** — if more Gemma facts are ever desired, the `GEMINI_FACT_EXPANSION_ADDENDUM` (or equivalent) could be applied to the Gemma prompt path. Currently NOT done — 49 is Gemma's design target and its v3.3 prompt is deliberately untouched. (added 2026-06-04.)
   - **3.5 Flash multi-value tracking** — Flash produces 0 cross-frame multi-value `value_updates` even with the same addendum that gives 2.5 Pro / 3.1 Pro 3 entries each. Likely a model-capability limitation (weaker cross-frame state tracking), not a prompt bug. Worth investigating if Flash becomes a primary arm. (added 2026-06-04.)
   - **Qwen / Llama 4 post-expansion empirical confirmation** — they were NOT re-run after gemini-fact-expansion. Provably unaffected (their prompt path is byte-identical; they never call the addendum), but no fresh run was done. (added 2026-06-04.)
   - **Visual recovery for KRX individual stocks + Hana Bank multi-currency board** — both prior approaches now proven dead-ends: aggregator-side scan (Option B `9bbb412`) AND OCR-pipeline tuning (E1 `81c0c07`+reverted, 2026-06-04). E1 showed upscale (C1) + DBSCAN fragmentation (C2) CAN surface the Hana board, but bundled with +33s latency + 95-fact noise, and the only mitigation breaks KOSPI multi-value tracking — no tuning of the current PaddleOCR stack separates the win from the costs. KRX stocks never cleanly recovered (PaddleOCR garbles tiny fonts: 현→허, 1,630,000→630000). **The remaining real fix requires DIFFERENT TOOLING, not tuning:** (a) table-aware OCR (PaddleStructure) or a commercial Korean OCR API for the dense boards, (b) higher-res capture (Mentra Live / better sensor). Needs fresh explicit authorization to touch `ocr_preprocessor.py` (or a new OCR component). Est. 1-2 days. (updated 2026-06-04 after E1.)
   - ~~**Aggregator-side absolute-value backfill**~~ — ✅ **DONE 2026-06-04 in `b7a5946`** (see "Recently completed" at the top of §9). Base-value-only; cross-arm; deterministic; dedup-safe.
3. **Recall:** stuck ~58% substring / **~88% fuzzy** (`recall_fuzzy` in `tests/test_recall_measure.py`). The substring metric is hostile; real capture ~88%. Ceiling is OCR read-quality + the metric — only addressable via off-limits higher-DPI / DBSCAN-eps.

---

## 10. How much we covered (progress)

- **Full Report feature:** ✅ 100% (backend aggregator + Word export + frontend modal + 6th button).
- **v3.3 quality upgrade:** ✅ 100% (OCR filter + prompt v3.3 + Word restructure). observed_facts 17→59 substantive; enumerated noise 82%→0%.
- **4 production fixes:** ✅ 100% (Whisper 127, dates, Gemma VRAM, Qwen/Llama4).
- **7 polish items (final demo pass):** ✅ 100% — 6/7 fully done; item 4 closed by decision (user chose A: ship v4 at 49 facts; the 42-45 target was deliberately not forced to avoid over-merge regression).

---

## 11. Where all the data & information live (for the new session)

| What | Where |
|---|---|
| **Repo root** | `C:\Users\A\projects\healthcare-ai-agent` |
| **This handoff (read first)** | `handoff.md` (this file) |
| **Detailed session delta** | `handoff_2026-06-02.md`, then `handoff_2026-05-29.md` |
| **Architecture** | `CLAUDE.md` |
| **Backend code** | `backend/app/` (api, services) + `backend/glasses_watcher/` |
| **Aggregator (open in IDE)** | `backend/app/services/full_report_aggregator.py` |
| **Word exporter** | `backend/app/services/word_exporter.py` |
| **OCR quality filter + tests** | `backend/glasses_watcher/ocr_quality_filter.py`, `backend/glasses_watcher/tests/` |
| **Prompt + watcher logic** | `backend/glasses_watcher/_lifelog_test.py` |
| **Frontend lifelog page** | `frontend/hrt-dashboard/app/lifelog/page.tsx` |
| **Test clip + reports + JSON snapshots** | `test_data/kbs_clip/` (latest report: `test_report_v33_fixed_v4.docx`) |
| **Migrations** | `migrations/` (007/008/009 applied; no new migration this session) |
| **Memory index** | `C:\Users\A\.claude\projects\C--Users-A\memory\MEMORY.md` |
| **DB** | Supabase project `klnykuxzucujahucvbct` (Seoul). Access via repo httpx `SupabaseClient` / `get_db_admin()` — NOT supabase-py |
| **Services** | FastAPI `http://localhost:8888` (`/api/v1` prefix, `--reload`); Next.js `http://localhost:3000` |

---

## ⚠️ Environment Dependencies (NON-DEFAULT — required for a fresh `.venv`)

**A fresh `.venv` must `pip install` these or audio preprocessing silently disables itself (graceful, but you lose the fix):**
- **`noisereduce` (3.0.3)** + **`soundfile` (0.13.1)** — added 2026-06-04 (`85bf21f`) for the Whisper audio-preprocessing step. Install: `.venv\Scripts\python.exe -m pip install noisereduce soundfile`.
- **`librosa` is deliberately NOT used** — `audio_preprocessor.py` uses `soundfile` for I/O so it never pulls `numba`/`llvmlite` (keeps the torch/paddle/ctranslate2 DLL stack stable; numpy stays 1.26.4). Do NOT "add librosa for convenience."
- There is **no `requirements.txt`** in this project (deliberate — creating one is a separate refactor, out of scope). This handoff section is the dependency record. The audio module degrades gracefully if the libs are missing (`AUDIO_PREPROC_AVAILABLE=False` → raw audio), so the pipeline won't crash — it just won't denoise.
- **Existing pinned stack (do not perturb):** numpy 1.26.4 · torch 2.11.0+cu128 · ctranslate2 4.7.2 · faster_whisper 1.2.1 · paddle 2.6.2 · scipy 1.17.1.
- **Escape hatch:** set `SKIP_AUDIO_PREPROC=1` in `backend/.env` to disable preprocessing without code changes.

---

## 12. Operational reminders (HARD constraints — preserve)

- **Always run `.venv\Scripts\python.exe`** — never conda `(base)` or system Python311 (DLL shadowing → WinError 127). Run watchers from a non-conda shell.
- **Whisper is CPU now** — keeps the 32GB GPU free for Gemma 26B Q8 + Paddle.
- **One GPU processor at a time** — don't run multiple watchers + a manual clip together (they time each other out).
- **DO NOT touch** `ocr_preprocessor.py` (extraction pipeline). *(The 2026-06-04 E1 one-session authorization is CLOSED — off-limits RESTORED. The C1 density-aware-upscale change `81c0c07` survives in history as that authorized exception; everything else from E1 was reverted. Any future change needs NEW explicit authorization.)*
- **DO NOT** add a new Supabase column/migration, install new npm packages, or use Unicode emoji in `print()` (cp949 crash → use `[OK]/[ERR]/[INFO]`). *(Python-package exception, 2026-06-04: `noisereduce` + `soundfile` were added with user sign-off after a dry-run confirmed the torch/paddle stack was untouched — see "Environment Dependencies" above. Any future pip install must clear the same DLL-safety bar.)*
- **DO NOT commit** `failed_parses/`, `.venv/`, large model files, or `test_data/` binaries.
- FastAPI `--reload` + frontend hot-reload pick up aggregator/exporter/page edits — no restart needed.

> **Note on working tree:** there are pre-existing **uncommitted/untracked** changes from earlier work (e.g. `lifelog_chat.py`, `watcher.py`, several frontend components, `gemma4_watcher.py` etc., and many `test_data/*.json`). These are NOT part of this session's committed Full-Report/v3.3 work and were left as-is. Don't blanket `git add .` — commit deliberately, and keep `test_data/` binaries + `failed_parses/` out.

---

*End of resume handoff — 2026-06-02. Full Report feature + v3.3 quality upgrade complete and demo-ready; one open A/B decision on final fact-count polish.*
