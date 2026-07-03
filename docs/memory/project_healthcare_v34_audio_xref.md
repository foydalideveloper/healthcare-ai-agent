---
name: project-healthcare-v34-audio-xref
description: "Healthcare AI Agent (Triple-H lifelog) — v3.4 audio-OCR cross-reference layer (2026-06-02). Audio transcript facts now flow into Value Updates + Key Terms. Schema v3.3→v3.4, zero regressions."
metadata: 
  node_type: memory
  type: project
  originSessionId: ca30b8c8-372d-44be-97df-a9e0250935d2
---

# Healthcare AI Agent — v3.4 Audio-OCR Cross-Reference Layer (2026-06-02, COMPLETE)

Repo: `C:\Users\A\projects\healthcare-ai-agent`. Resume via `handoff.md` (has a prominent ⭐ v3.4 section at the top). Builds on [[project-healthcare-session-2026-06-02]] (v3.3 + Full Report).

## The gap that was fixed
The Whisper transcript was semi-isolated — Value Updates and Key Terms were OCR-only, so audio-spoken values ("SK하이닉스 시가총액 1,600조 원", "마이크론 19% 급등") never reached the structured tables. v3.4 adds a **purely additive, aggregator-time** layer (no pipeline/prompt/re-extraction changes) that parses the transcript, cross-references vs OCR, and promotes audio facts.

## What shipped (5 commits, independently revertible)
- `039638d` audio-xref-extractor — NEW `backend/app/services/audio_fact_extractor.py` (pure stdlib, no pipeline imports). 30 unit tests in `backend/app/services/tests/test_audio_fact_extractor.py`.
- `ea98809` audio-xref-aggregator — wired into `full_report_aggregator.py`; schema v3.3→v3.4; new `audio_only_terms` field + 3 audio metrics.
- `96e60c4` audio-xref-tuning — conservative full-token cross-ref; skip currency-unit/bare-multiplier label noise.
- `16ac9dc` audio-xref-word — `word_exporter.py`: Source column (Audio=blue/Video), claim_type subtitle, Audio-only Mentions sub-section, +2 title metric rows.
- `8ad418f` audio-xref-frontend — `lifelog/page.tsx`: source badges, claim_type subtitles, Audio-only Mentions sub-section, Esc-to-close.
- Plus a session-close docs commit (handoff.md v3.4 section).

## Result on KBS test clip (20260528144922838.mp4, gemma4)
value_updates 4 → 11 (4 video + 7 audio, tagged source + claim_type); audio_only_terms = 4; metrics extracted=10 / cross-referenced=5 / audio-only=5. Word doc 44 → 45.5 KB. Latest artifact: `test_data/kbs_clip/test_report_v34.docx`. Regression baseline: `test_data/kbs_clip/baseline_pre_audio_xref.json`.

## ZERO regressions (all byte-identical to baseline)
observed_facts 49, Key Terms 416, OCR appendix 349, timeline 4 windows, headlines 3, panels 213, recall 0.95, transcript text unchanged, Malgun Gothic intact (34 CJK runs, 0 missing eastAsia), 0 mojibake.

## v3.4 caveats (carry forward)
- a. **Nearest-left entity match** — no multi-entity positional pairing; "각각 2.7%, 9.3% 급등한 삼성전자와 SK하이닉스" mislabels 9.3% to 삼성전자 (should be SK하이닉스). Cosmetic; deferred.
- b. **Conservative cross-ref is deliberate** — matches full normalized token (digits+unit), NOT bare digits, so a lone "1600" in OCR can't mask the audio-only "1,600조 원". Do NOT loosen back to digit-substring.
- c. **Generic-label rows kept** — e.g. `time_range / 3년에서 5년` (supply-contract extension) is kept as a distinct audio row even without an entity label (boss-demo value).

## Deferred (added this session)
- Multi-entity 각각/positional pairing in the extractor.
- Source tagging on `observed_facts` (needs prompt change + re-extraction; skipped).
- Audio-fact entity-coverage expansion beyond EN/KO financial entities.

## Hard constraints honored (unchanged from prior sessions)
`.venv\Scripts\python.exe` only; do NOT touch `ocr_preprocessor.py` / LIFELOG_PROMPT / `_lifelog_test.py` / watchers; no migrations/columns; no new npm packages; no emoji in `print()` ([OK]/[ERR]/[INFO]); never blanket `git add .` (keep test_data binaries + failed_parses out); Whisper CPU; one GPU processor at a time.
