# Healthcare AI Agent — RESUME HERE (Session Handoff)

**Last updated:** 2026-06-02, end of **audio-xref session** (schema v3.3 → **v3.4**).
**This is the FIRST file to read when resuming.** It is the umbrella + the current-state pointer.

> ## Read order on resume
> 1. **This file** (`handoff.md`) — current state, what to do next, where everything lives.
> 2. **`handoff_2026-06-02.md`** — full delta for the work done in the last two sessions (Full Report feature + v3.3 quality upgrade + production fixes). Detailed.
> 3. **`handoff_2026-05-29.md`** — prior session (paths, services, quick-start commands).
> 4. **`CLAUDE.md`** — architecture overview (LLM layers, DB, project structure).
> 5. Deep state of record: `~/.claude/projects/C--Users-tripleh/memory/project_healthcare_complete_handoff.md` (0-to-100% locked decisions). NOTE: this session ran under user `C--Users-A`; memory index is at `C:\Users\A\.claude\projects\C--Users-A\memory\MEMORY.md`.

---

## ⭐ LATEST: v3.4 Audio-OCR Cross-Reference Layer (2026-06-02) — COMPLETE

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

1. **Immediate:** ✅ DONE — user chose (A); v4 (49 facts) accepted as the shipped report. No further action on item 4.
2. **Deferred (from `handoff_2026-06-02.md` §5 — not active):**
   - Date-entity dedup (3 date facts → 1; cosmetic, regression risk, deliberately skipped).
   - Multi-arm comparison inside the Word doc (cross-arm JSON aggregation already works by omitting `source_model`).
   - Audio quality — external mic / Mentra Live migration to fix Korean transcript errors.
   - value_updates multi-value deltas on noisy OCR — needs `detect_value_changes` robustness in the **off-limits** `ocr_preprocessor.py`.
   - Glasses clock re-sync via AIMB bridge (mtime fallback is a safety net, not a cure).
   - AIMB-G1 BLE auto-wake (blocked — see `aimb-bridge-android/handoff.md`).
   - **Multi-entity positional pairing with 각각/respectively marker** — the audio-xref extractor (`audio_fact_extractor.py`) uses nearest-left entity match; it doesn't handle list-pair semantics where N values map to N entities by position. e.g. "각각 2.7%, 9.3% 급등한 삼성전자와 SK하이닉스" attaches 삼성전자 to BOTH percentages, when 9.3% should pair to SK하이닉스. Cosmetic mislabel on the audio Value-Updates rows; deferred (added 2026-06-02 audio-xref session).
   - **Source tagging on `observed_facts`** (audio / video / both) — would require a LIFELOG_PROMPT change + **re-extraction** of events; skipped this session to avoid regression risk. The v3.4 layer only tags `value_updates`, which is post-processing-safe.
   - **Audio-fact entity-coverage expansion** — `KOREAN_FINANCIAL_ENTITIES` currently covers EN/KO financial names (semiconductors, indices, banks). Could extend to more sectors (healthcare, energy, consumer) as the clip corpus broadens.
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

## 12. Operational reminders (HARD constraints — preserve)

- **Always run `.venv\Scripts\python.exe`** — never conda `(base)` or system Python311 (DLL shadowing → WinError 127). Run watchers from a non-conda shell.
- **Whisper is CPU now** — keeps the 32GB GPU free for Gemma 26B Q8 + Paddle.
- **One GPU processor at a time** — don't run multiple watchers + a manual clip together (they time each other out).
- **DO NOT touch** `ocr_preprocessor.py` (extraction pipeline).
- **DO NOT** add a new Supabase column/migration, install new npm packages, or use Unicode emoji in `print()` (cp949 crash → use `[OK]/[ERR]/[INFO]`).
- **DO NOT commit** `failed_parses/`, `.venv/`, large model files, or `test_data/` binaries.
- FastAPI `--reload` + frontend hot-reload pick up aggregator/exporter/page edits — no restart needed.

> **Note on working tree:** there are pre-existing **uncommitted/untracked** changes from earlier work (e.g. `lifelog_chat.py`, `watcher.py`, several frontend components, `gemma4_watcher.py` etc., and many `test_data/*.json`). These are NOT part of this session's committed Full-Report/v3.3 work and were left as-is. Don't blanket `git add .` — commit deliberately, and keep `test_data/` binaries + `failed_parses/` out.

---

*End of resume handoff — 2026-06-02. Full Report feature + v3.3 quality upgrade complete and demo-ready; one open A/B decision on final fact-count polish.*
