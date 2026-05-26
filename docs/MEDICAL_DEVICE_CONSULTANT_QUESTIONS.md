# Korean Medical-Device Consultant — Question List

**Project:** Healthcare AI Agent · Triple-H Co., Ltd.
**Patent No.** 10-2025-0145274
**Purpose:** Pre-meeting question prep for a Korean medical-device regulatory consultant. The goal is to walk out of one ~1-hour meeting with a defensible answer on whether Triple-H's Healthcare AI Agent is a *wellness app* (낮은 위험도, faster path) or a *Software-as-Medical-Device (SaMD)* — and what changes if we're wrong about the classification.

> **Hand this list to the consultant 24h before the meeting** so they can prepare answers grounded in current MFDS guidance instead of improvising. Read along with `Healthcare_Pipeline_Diagram.docx` and the 7-category HRT design.

---

## Block A — Classification (the core question)

1. **Wellness vs SaMD line for our `/predictions` page.** The dashboard surfaces 8 disease-risk forecasts × 4 horizons (computed from a Hybrid LSTM-Transformer over user lifestyle + biometric data). Does this trigger MFDS medical-device classification under 의료기기법, or does it fall under wellness/health-management software (의료기기 비해당)?
   - If SaMD: which class (I, IIa, IIb, III)?
   - If wellness: what disclaimer language, UI placement, and data-use restrictions keep it on the wellness side of the line?

2. **Compliance scoring.** Showing "94% medication compliance" computed from `user_medication_intake` events — does this constitute a clinical decision support output? Same question for "BP trend anomaly" (3 consecutive readings > 140) which we plan to surface as a notification.

3. **AI-driven food recognition + nutrition output.** AI glasses photo → EfficientNetV2-S → MFDS food lookup → kcal/macro estimate. Is calorie estimation a medical-device function under Korean law, or a wellness/lifestyle output? Does it change if we surface diabetic exchanges or sodium warnings?

4. **Risk reclassification triggers.** What specific feature additions would push us from wellness → SaMD classification (e.g., adding a glucose forecast, adding "consult your doctor about X" prompts, adding an anomaly that auto-pages emergency contacts)?

## Block B — Korean PIPA + AI glasses capture

5. **Always-on glasses capture under PIPA.** AIMB-G1 / Mentra Live capture 12 MP photos passively (every meal, every bystander). Mandatory on-device YOLO-Face blur runs FIRST on every photo. What additional consent / signage / data-handling requirements does PIPA impose for:
   - The wearer (active consent, easy.)
   - **Bystanders** (cannot consent in advance — what's the legal posture)?
   - Audio capture in shared/public spaces (3-mic array)?

6. **PIPA vs HIPAA mapping.** We're modeling 7-year data retention on HIPAA. Does PIPA recognize a comparable retention obligation for health data in Korea, or is the right anchor 개인정보 보호법 + 의료법 + 보건의료기본법? Where do they conflict?

7. **Photos framework / opt-in backfill.** Decision Apr 28: **never** auto-scan the user's photo gallery; use only the system photo picker for one-time opt-in backfill. Does that posture satisfy PIPA, or do we need explicit consent screens beyond the OS-level photo permission?

## Block C — MFDS food database usage

8. **MFDS food DB licensing.** We embed a 275K-row Korean food SQLite DB on the phone (~108 MB) sourced from MFDS public datasets. Are there usage restrictions (commercial use, redistribution, attribution requirements) that affect a 100K-user consumer product?

9. **MFDS → user calorie estimate liability.** If a diabetic user follows our calorie/macro output and over-doses insulin, where does liability sit when the source of truth is a public MFDS dataset that we re-package and surface? Does adding a disclaimer remove the liability?

## Block D — NHIS data integration

10. **NHIS cohort approval scope.** A colleague is applying for NHIS cohort access for LSTM training (still pending after ~2 weeks). What's the realistic timeline for a small startup, what data-use limitations attach to the approval, and what re-consent obligations propagate to the 100K end-users if their HRT predictions are partially trained on NHIS data?

11. **External records (FHIR) integration consent.** Our `external_records` table is designed to receive hospital EMR data via FHIR R4. What's the Korean equivalent of an OAuth-style patient-mediated EMR pull (cf. US 21st Century Cures Act, Apple Health Records)? Is 마이데이터 the right rail, and does it apply to pre-existing hospital records or only forward?

## Block E — Hardware procurement + cross-border data

12. **Mentra Live / Solos AirGo V2 medical-device implications.** These are off-the-shelf consumer AI glasses. Does shipping them with our healthcare app rebrand them as components of a medical device? What about the wearables (Apple Watch, Galaxy Watch, smart ring) we ingest from?

13. **Cloud GPU overflow + cross-border data transfer.** Production overflow uses Modal / RunPod / Cloud Run (likely US-based). Transient PHI (raw clip with face blurred, voice transcript) crosses the Korean border for ~6 seconds during cloud-fallback extraction before the result returns. Does this trigger 개인정보 국외이전 obligations even though no data is stored outside Korea?

## Block F — Patent + competitive

14. **Patent claim scope on regulatory.** Patent 10-2025-0145274 (Lee Chom-Sik) covers the AI-glasses-driven HRT system. Are any patent claims affected by — or affect — our regulatory classification? E.g., does claiming a "diagnosis-supporting prediction" in the patent itself push us toward SaMD classification?

15. **Disclosure timing.** When are we required to file with MFDS — at beta (any paid users) or at consumer launch? Does running an internal-only beta with Triple-H employees count as "user testing" that resets the regulatory clock?

---

## What "good" looks like for this meeting

By the end, we should have:
- A written answer to **Block A** (wellness vs SaMD) with the consultant's reasoning + the specific feature flags / disclaimer requirements that hold the answer.
- A short list of **changes required** before any beta launch (UI disclaimers, consent flows, retention adjustments, cross-border transfer notices).
- A **timeline + cost estimate** if SaMD is the answer (clinical validation, audit trail, MFDS filing) and a **second timeline + cost** if we re-scope to stay wellness.
- A **recommended next-steps document** the consultant signs off on, so we can show the boss exactly what's needed and at what cost.

---

## Materials to send the consultant 24h ahead

1. This question list.
2. `docs/Healthcare_Pipeline_Diagram.docx` — production architecture.
3. `docs/HRT_MULTIDIMENSIONAL_DRILLDOWN.md` — current HRT design (v1.5).
4. Patent 10-2025-0145274 — abstract + claims (1-page summary, once available).
5. A short list of features visible in the live `/predictions` and HRT dashboard (so the consultant sees what's user-facing today).
