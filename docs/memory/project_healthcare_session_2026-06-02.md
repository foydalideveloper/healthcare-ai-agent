---
name: project-healthcare-session-2026-06-02
description: "Healthcare AI Agent (Triple-H lifelog) — 2026-06-02 session close: v3.3 quality upgrade + Full Report feature shipped, 49 substantive facts, caveats & deferred work."
metadata: 
  node_type: memory
  type: project
  originSessionId: ca30b8c8-372d-44be-97df-a9e0250935d2
---

# Healthcare AI Agent (Triple-H lifelog pipeline) — Session 2026-06-02 (CLOSED)

Repo: `C:\Users\A\projects\healthcare-ai-agent`. Resume entry point: `handoff.md` → `handoff_2026-06-02.md` → `CLAUDE.md`.

## What this session covered
- **v3.3 data-quality upgrade** — observed_facts went **17 → 49 substantive** items, **0% noise/mojibake** (enumerated noise 82% → 0%). OCR raw dump replaced by a filtered "Key Terms" layer + demoted 8pt "Technical OCR Reference" appendix.
- **Full Report feature shipped** — backend aggregator (`full_report_aggregator.py`) + Word export (`word_exporter.py`) + frontend modal + 6th button (`📄 Full Report`) + download. Endpoints: `/api/v1/lifelog/full-report[.docx]`.

## Final outcome
- **Shipped report:** `test_data/kbs_clip/test_report_v33_fixed_v4.docx` (v4).
- **Final fact count: 49 substantive observed_facts, 0 noise.**
- **Open A/B decision RESOLVED: user chose (A)** — ship v4 at 49 facts. The ~4-fact overage (fan/monitor/studio ambient scene clutter) was NOT force-merged: not worth the regression risk, and it does not affect the boss-facing top-25 financial facts. Same over-merge-avoidance principle applied to the date fact.
- Last code commit: `046a112`. Session-close commit: handoff.md update (this session's docs only; pre-existing unrelated working-tree changes left untouched).

## Known caveats (carry forward)
a. **Value Updates show single-value snapshots** ("Times Observed: 1") on noisy clips — multi-value deltas work on cleaner OCR. Fix lives in off-limits `ocr_preprocessor.py`.
b. **3 date facts kept distinct** — one carries unique spatial info ("top left corner") + EN/KO phrasing differs; deliberate, avoids over-merge.
c. **4 ambient scene facts kept distinct** — unique spatial nuance (fan/monitor/studio); the Option-A overage.
d. **Whisper Korean transcript has minor errors** — AIMB-G1 hardware/mic limitation, not a pipeline bug.
e. **Key Terms section has filtered residuals** — the Option-A tradeoff (conservative dedup over aggressive merge).

## Deferred for future sessions
- Date-entity targeted dedup (cosmetic only).
- Multi-arm comparison in the Word doc (currently single arm per report; cross-arm JSON already works by omitting `source_model`).
- Audio quality via external mic / Mentra Live migration.
- Value-updates multi-value deltas on noisy OCR (requires `ocr_preprocessor.py` changes — off-limits this session).
- Semantic cluster dedup for ambient scene facts (cosmetic).

## Hard constraints (preserve)
- Always `.venv\Scripts\python.exe` — never conda/system Python (WinError 127 DLL shadowing).
- **Do NOT touch** `backend/glasses_watcher/ocr_preprocessor.py`.
- No new Supabase migrations/columns, no new npm packages, no emoji in `print()` (use `[OK]/[ERR]/[INFO]`).
- Never blanket `git add .` — working tree has unrelated pre-existing changes; keep `test_data/` binaries + `failed_parses/` out.
- Whisper runs CPU (int8) to free the 32GB GPU for Gemma 26B Q8 + Paddle; one GPU processor at a time.

Dependable LLM arms for demo: **Gemma 4 26B (local) + Gemini 2.5 Pro (cloud)**. Llama4 NIM flaky; Qwen Q4 via JSON salvage.
