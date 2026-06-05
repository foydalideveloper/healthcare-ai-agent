# OCR Engine Evaluation Session — COMPLETE (2026-06-05)

> **✅ SESSION COMPLETE (updated 2026-06-05, resumed run).** Phases C + E finished.
> EasyOCR evaluated → **underperforms PaddleOCR on both frames (50% vs 73%); NO swap.**
> Korean ceiling confirmed unbreakable by free tooling → escalate to Naver Clova (paid)
> or Mentra Live hardware. One free upside: PaddleStructure(en) hybrid for Latin currency
> boards (f08 90% vs 70%). Full decision matrix: **`backend/ocr_eval/RECOMMENDATION.md`**.
> Results: `backend/ocr_eval/results/phase_c_easyocr.json`. Production UNTOUCHED; eval still uncommitted.

**This file = the live state of the OCR-engine-evaluation session.** A new Claude Code session
should read THIS first, then `handoff.md` (umbrella/history), then `CLAUDE.md` (architecture).
The original body below is preserved as the phase-by-phase record.

---

## 1. What this project is
**Triple-H Co., Ltd. Healthcare AI Agent** — patent-protected lifelong health-timeline driven
by AI glasses (AIMB-G1) + wearables, 100k Korean users. Sub-area worked on: the **Lifelog
pipeline** — glasses video → OCR (PaddleOCR) + audio (Whisper) + multi-arm multimodal LLM
extraction (6 arms) → structured events → Supabase → Next.js dashboard + Word report.
- Repo root: `C:\Users\A\projects\healthcare-ai-agent`
- DB: Supabase `klnykuxzucujahucvbct` (Seoul). Access via repo httpx `SupabaseClient` / `get_db_admin()`.
- Services: FastAPI `http://localhost:8888` (`/api/v1` prefix, `--reload`); Next.js `http://localhost:3000`.

## 2. What THIS session is trying to build
An **OCR engine evaluation** — a rigorous side-by-side comparison of alternative OCR engines
(PaddleStructure, EasyOCR, optionally Naver Clova) against the current **PaddleOCR baseline**,
on the EXACT frames where PaddleOCR fails on Korean financial broadcast content. Deliverable =
a **decision matrix + recommendation** for a FUTURE authorized integration session.
**NO production integration this session.** This is the evaluation phase only.

Why: today's "three-instance pattern" (Rule 1a `f2e74dd`, Option B `9bbb412`, E1 C2 in the
reverted `81c0c07` work) proved PaddleOCR tuning can't break its Korean-financial char-accuracy
ceiling → the fix is **different tooling, not more tuning**. This session finds which tool.

## 3. The goal we are working toward
Produce `backend/ocr_eval/` (evaluation framework + results JSON) + a decision-matrix report,
and a handoff §9 entry recommending the best engine. Then STOP (integration is a later session).

**Decision-matrix CASE framework (for Phase E):**
- CASE α — both alternatives win f07 (Korean KRX large text) → engine ARCHITECTURE is the ceiling → recommend integrating winning free engine.
- CASE β — alternatives only win f08 (Hana tiny text) → arch AND resolution matter → hybrid or wait for Mentra Live hardware.
- CASE γ — one wins f07 only, other wins f08 only → engine-specific strengths → hybrid by content type.
- CASE δ — neither beats PaddleOCR → PaddleOCR is the free-engine ceiling → recommend Clova (paid) eval next session OR hardware (Mentra Live).

## 4. Current state of the project
**OCR eval ~60% done.** Phase 0 (discovery) ✓, Phase A (harness + baseline sanity) ✓,
Phase B (PaddleStructure) ✓. **Phase C (EasyOCR) NOT started** — context died right before
installing EasyOCR. Phase D (Clova) SKIPPED (no API key). Phase E (decision matrix) pending.
Production pipeline UNTOUCHED throughout. All v3.4 features intact.

## 5. Current state of code (what's built)
**ALL evaluation code is UNCOMMITTED / untracked** under `backend/ocr_eval/` (commit only at
Phase E end, as `ocr-engine-evaluation-results`). Files built this session:
- `backend/ocr_eval/__init__.py`, `engines/__init__.py`
- `backend/ocr_eval/engines/base.py` — `OCREngine` ABC + `OCRResult` dataclass.
- `backend/ocr_eval/engines/paddle_baseline.py` — reuses PRODUCTION `ocr_preprocessor._ensure_ocr()` + `_run_paddleocr_once()` (read-only import; identical to production primary OCR by construction).
- `backend/ocr_eval/engines/paddle_structure.py` — PP-Structure (table-aware). **lang='en' only** (korean unsupported — see §10).
- `backend/ocr_eval/engines/easy_ocr.py` — **NOT YET CREATED** (Phase C; spec in the mission prompt — `easyocr.Reader(['ko','en'], gpu=True)`).
- `backend/ocr_eval/engines/clova_ocr.py` — NOT created (Phase D skipped, no key).
- `backend/ocr_eval/metrics.py` — pure-stdlib: entity recovery (garble-tolerant, FUZZY_THRESHOLD=0.80) + Levenshtein char-accuracy + latency.
- `backend/ocr_eval/harness.py` — runner; `{venv} -m ocr_eval.harness --engines paddle_baseline,paddle_structure[,easy_ocr]` (run from `backend/`); skips `appendix:true` frames.
- `backend/ocr_eval/report.py` — side-by-side report renderer.
- `backend/ocr_eval/test_data/frames/` — `f04_t10s.png` (appendix), `f07_t17s.png` (KRX board), `f08_t20s.png` (Hana board).
- `backend/ocr_eval/test_data/ground_truth.json` — 3 frames; f04 marked `"appendix": true` (NOT scored).
- `backend/ocr_eval/results/` — `results.json`, `phase_b_paddlestructure.json`.

**Production files — UNTOUCHED (verify with `git status`; only doc/eval files should differ):**
`ocr_preprocessor.py`, `_lifelog_test.py`, `audio_fact_extractor.py`, `audio_preprocessor.py`,
`full_report_aggregator.py`, `word_exporter.py`, all LLM callers, watchers, frontend.

## 6. Files actively edited / being modified this session
- Created the whole `backend/ocr_eval/` tree (above). **Next file to create:** `backend/ocr_eval/engines/easy_ocr.py`.
- `handoff.md` (this umbrella doc) + this dated file — documentation only.
- **NO production code touched.**

## 7. What's been touched/changed this session
- NEW: `backend/ocr_eval/` evaluation framework (uncommitted).
- Extracted 3 PNG frames from the test clip; wrote `ground_truth.json` (26 must_contain tokens; f04 → appendix, so 22 scored across f07+f08).
- Installed/confirmed `paddleocr[structure]` — was **already satisfied** at paddleocr 2.8.1; **NO new core packages**; DLL stack intact.
- EasyOCR NOT yet installed.

## 8. Key RESULTS so far (the empirical findings)
Ground-truth frames (test clip `20260528144922838.mp4`, visually verified):
- **f07_t17s** = KRX individual-stocks board (유가증권시장), large readable text: 삼성전자 307,000, SK하이닉스 2,243,000, **SK스퀘어 1,276,000, 삼성전자우 192,000, 현대차 681,000, 삼성전기 1,630,000** (12 tokens).
- **f08_t20s** = Hana Bank multi-currency board, small ticker: KOSPI 8,428.84, KOSDAQ 1,148.16, **CNH/KRW 221.27, USD/KRW 1,500.40, EUR/USD, CAD/KRW** (10 tokens; Latin currencies).

| Engine | f07 Korean KRX | f08 Latin Hana | overall | p50 latency | cost/1k |
|---|---|---|---|---|---|
| **PaddleOCR (baseline)** | 9/12 (75%) | 7/10 (70%) | **16/22 (73%)** | 777ms | $0 |
| **PaddleStructure (en)** | 5/12 (42%) ⬇ | **9/10 (90%) ⬆** | 14/22 (64%) | 506ms ⚡ | $0 |

- **The bar to beat: 73% (16/22).**
- **Baseline misses:** f07 → 현대차 (garbled 대차), 681,000 (absent), 307,000 (fragmented). f08 → CNH/KRW, 221.27, CAD/KRW.
- **PaddleStructure finding (CASE γ):** table-aware **en** OCR SOLVES the Latin Hana board (90%, faster) — reads EUR/USD, CAD/KRW, S&P 500, 221.27 — but is **useless for Korean** (can't read Hangul labels; recovers only numbers on f07). PP-Structure layout models support **en/ch only**.
- **Implication:** resolution failure (f08) is solvable with table-aware en OCR; Korean KRX labels (f07) need a Korean-capable engine. **EasyOCR (`['ko','en']`) is the critical test** — the only free engine that could win BOTH with one model.

## 9. What didn't work + how we fixed it (this session)
- **f04 control scored only 1/4** — it's the animated headline where PaddleOCR FRAGMENTS comma-numbers (307,000 → "307"+"000" non-adjacent). FIX: dropped f04 from scoring (`"appendix": true`); kept as a documented separate finding (comma-number fragmentation = its own architectural issue, candidate deferred item). Baseline refined to clean 73% on f07+f08.
- **PaddleStructure `lang='korean'` → hard `sys.exit`** in ppocr ("lang korean is not support, only en/ch for layout models") — NOT a catchable Exception, killed the run. FIX: init with `lang='en'` directly (documented limitation). The en model still reads the Latin Hana currencies (the useful asymmetry).
- **WinError 127 on `import torch` after `from ocr_preprocessor import …`** — a TEST-ORDERING artifact, NOT a regression: ocr_preprocessor loads paddle, and paddle-before-torch breaks torch's DLL (the known issue production avoids). FIX: verify the stack in PRODUCTION order (torch FIRST) — `import torch; import paddle; …` works fine. `_lifelog_test.py:51-52` documents this exact fix. The `paddleocr[structure]` install did NOT break anything.

## 10. Where & why we stopped
**Context window dying.** Stopped right after Phase B verification, **before installing EasyOCR
(Phase C)**. Last user instruction was "GO Phase C" (install EasyOCR ~500MB Korean model,
re-verify DLL stack, run all 3 engines head-to-head) — but we paused to write this handoff.

## 11. NEXT STEPS (resume here, in order)
1. **Phase C — EasyOCR:**
   - Install: `{venv} -m pip install easyocr` (from repo root). Downloads ~500MB Korean model on first `Reader` init.
   - **CRITICAL DLL check (torch-FIRST order):** `{venv} -c "import torch, paddle, ctranslate2, paddleocr, easyocr; print('OK')"`. If it fails → `pip uninstall easyocr -y` and report the conflict. (Note: easyocr is torch-based; torch is already 2.11 — watch for a torch downgrade demand. If easyocr wants an older torch, do NOT downgrade — that would break Whisper/ctranslate2; report instead.)
   - Create `backend/ocr_eval/engines/easy_ocr.py` (spec in the mission prompt): `easyocr.Reader(['ko','en'], gpu=True)`, `readtext(path)` → `[(bbox, text, conf), ...]` → `OCRResult`. `estimated_cost_usd = 0.0`.
   - Run: from `backend/`, `{venv} -m ocr_eval.harness --engines paddle_baseline,paddle_structure,easy_ocr --out ocr_eval/results/phase_c_easyocr.json`.
   - Verify production untouched + DLL (torch-first) after install.
2. **Phase D — SKIP** (no `CLOVA_OCR_API_KEY` in `backend/.env`).
3. **Phase E — Decision matrix + recommendation** via `report.py`; classify CASE α/β/γ/δ; write recommendation MD. Add a handoff §9 entry. Commit `backend/ocr_eval/` as `ocr-engine-evaluation-results` (ONLY the eval dir + handoff; NO production files; keep `test_data/` PNGs — they're small and part of the eval, but confirm with the user since the repo convention keeps test_data binaries out of commits).
4. Final report with the recommendation.

## 12. HARD CONSTRAINTS (obey — this is an evaluation-only session)
- **DO NOT modify production:** `ocr_preprocessor.py`, `_lifelog_test.py`, `audio_fact_extractor.py`, `audio_preprocessor.py`, `full_report_aggregator.py`, `word_exporter.py`, LLM callers, watchers, frontend. All work stays in `backend/ocr_eval/`.
- **DO NOT integrate any engine into production this session.**
- **After EVERY package install, verify the production DLL stack in torch-FIRST order.** If a conflict → rollback that install immediately, report, stop.
- Always `.venv\Scripts\python.exe` (never conda/system Python — WinError 127). Run watchers/heavy OCR from repo root, NOT after `cd backend` (relative paths break — recurring mistake this session; for DB scripts that need `app.database`, cd to `backend/` and use `../.venv/Scripts/python.exe`).
- No Unicode emoji in `print()` (cp949 crash → `[OK]/[ERR]/[INFO]`).
- v3.4 features that MUST stay intact (production is untouched so they are, but re-verify if anything's run): multi-value KOSPI 8,228.70→8,428.84 / KOSDAQ / USD-KRW tracking; audio_only_terms≈4; Option A backfill (KOSPI 8,228.70 standalone fact); audio preprocessing DEFAULT-OFF (opt-in `ENABLE_AUDIO_PREPROC=1`); schema v3.4.

## 13. Where ALL the data/info lives (for the new session)
| What | Where |
|---|---|
| **This session's live state (read FIRST)** | `handoff_ocr_eval_2026-06-05.md` (this file) |
| **Umbrella handoff + full history** | `handoff.md` (§9 = completed-this-session log incl. b7a5946 Option A, 85bf21f/da20d0a audio, 81c0c07 E1 C1, Option B/E1 negative findings) |
| **Architecture** | `CLAUDE.md` |
| **Eval framework + results** | `backend/ocr_eval/` (harness.py, engines/, metrics.py, report.py, test_data/, results/) |
| **Production OCR (off-limits)** | `backend/glasses_watcher/ocr_preprocessor.py` |
| **Production extraction (off-limits)** | `backend/glasses_watcher/_lifelog_test.py` (torch-first import at line ~51) |
| **Test clip** | `C:\Users\A\AIMB-Bridge\20260528144922838.mp4` (61.6s, 1849 frames, 1600x1200) |
| **Memory (persists across sessions)** | `C:\Users\A\.claude\projects\C--Users-A\memory\MEMORY.md` (+ `project_healthcare_*.md`, esp. `project_healthcare_postprocessing_limits.md` = the 3-instance ceiling pattern) |
| **Last commit** | `75e739e` (audio preprocessing default-off). The ocr_eval framework is UNCOMMITTED. |

## 14. Coverage
- Phase 0 (discovery, frames, deps): ✅ 100%
- Phase A (harness + baseline sanity): ✅ 100% (baseline = 73%)
- Phase B (PaddleStructure): ✅ 100% (64% overall; 90% Latin / 42% Korean — CASE γ)
- Phase C (EasyOCR): ✅ 100% — **11/22 (50%); f07 58% / f08 40%; LOSES on both → no swap**
- Phase D (Clova): ⏭ SKIPPED (no key) — now the **recommended next eval** for Korean
- Phase E (decision matrix + recommendation): ✅ 100% — `RECOMMENDATION.md` written
- **Overall = 100% of the evaluation session (commit pending user confirmation).**

## 15. FINAL RESULTS & RECOMMENDATION (Phase C + E, resumed run 2026-06-05)
| Engine | f07 Korean | f08 Latin | Overall | p50 | $/1k |
|---|---|---|---|---|---|
| PaddleOCR (baseline) | 9/12 (75%) | 7/10 (70%) | **16/22 (73%)** | 599ms | $0 |
| PaddleStructure (en) | 5/12 (42%) | **9/10 (90%)** | 14/22 (64%) | 512ms | $0 |
| EasyOCR (ko+en) | 7/12 (58%) | 4/10 (40%) | 11/22 (50%) | 721ms | $0 |

- **EasyOCR rejected** — worse on BOTH frames, slower; recovered 0/4 of the flagged Korean
  ceiling tokens (현대차/681,000/삼성전기/SK스퀘어) that baseline missed.
- **Korean KRX ceiling = CASE δ** (no free engine beats PaddleOCR 75%) → escalate to **Naver
  Clova OCR (paid)** eval next session OR **Mentra Live** hardware (capture-layer fix).
- **Latin currency board = CASE β** → optional free win: route f08-type frames to
  **PaddleStructure(en)** (90% vs 70%, faster). Integration session decides build-vs-defer.
- Env: easyocr installed with `numpy==1.26.4` pinned (plain install would bump numpy→2.4.6 and
  break the DLL stack); torch stayed 2.11; harness imports torch-first; Reader uses `verbose=False`
  (cp949 block-char crash). Full stack verified healthy before/after. Production untouched.

*End of OCR-eval handoff — 2026-06-05 (COMPLETE). See `backend/ocr_eval/RECOMMENDATION.md`. Eval uncommitted pending user OK.*
