# Healthcare AI Agent — Session Handoff

**Last updated:** 2026-05-12, end of session.
**Read this FIRST when resuming.** This is the umbrella project; `aimb-bridge-android` is one small dependency.

---

## 1. What this project is

**Triple-H Co., Ltd. Healthcare AI Agent** — patent-protected (10-2025-0145274, Lee Chom-Sik, Oct 2, 2025).
A lifelong AI-assisted health timeline driven by AI glasses + wearables, targeting 100,000 Korean users.

Single sentence: *Korean users wear AI glasses; the system records everything they eat / drink / take / do, runs it through a multi-tier extraction pipeline (CNN cascade → Gemma multimodal → Qwen VLM → MFDS/USDA nutrition DBs), persists it to a 40+ table Supabase database, and serves a Next.js dashboard with multi-dimensional drill-down + LSTM-Transformer health forecasting.*

**Core product**: HRT (Health Record Timeline) — multi-dimensional drill-down timeline of every health event, plus AI-generated daily/weekly summaries and predictions.

**Moat — 4 pillars**:
1. Korean food MFDS DB (275,856 rows) — Western competitors don't have this
2. AI-glasses always-on capture loop — most rivals are watch/ring-only
3. HRT lifelong multi-dim drill-down — patent-protected
4. Korean gov/insurance distribution path (NHIS, MFDS) — outside Apple/Samsung's playbook

---

## 2. What we are trying to build

A complete, production-ready health-AI platform with this end-to-end data flow:

```
AI glasses (AIMB-G1 today, Mentra Live planned)
    ↓ records short video chunks (3-min default)
phone (Galaxy Note 10 5G today, iPhone 16 / Galaxy S25 planned)
    ↓ on-device ML (YOLOv8 + Whisper-tiny + MFDS SQLite, ~75ms / event)
    ├─ high confidence (≥0.7) → Supabase direct  (85-95% of events)
    └─ low confidence  (<0.7) → S3 raw clip → cloud GPU re-analyzes → Supabase
                                ↓ Gemma 4 E4B Q8 (RTX 5090 production / RTX 4070 SUPER dev)
                                ↓ Qwen 3.5 VLM 397B (NVIDIA NIM, cloud fallback only)
Supabase Postgres (Seoul, project klnykuxzucujahucvbct)
    ↓ 40+ tables across 6 health domains
FastAPI backend (Python 3.12)
    ↓ /hrt, /lifelog, /predictions, /agents endpoints
Next.js dashboard (hrt-dashboard)
    ↓ HRT timeline + drill-down + lifelog + predictions
User
```

Plus a parallel agent system (OpenClaw 11-agent topology) for conversational queries (Doctor AI, Family Agent, Expert Agent).

---

## 3. Where everything lives

### Top-level
| Path | What |
|---|---|
| `C:\Users\tripleh\projects\healthcare-ai-agent\` | **Project root** |
| `C:\Users\tripleh\projects\healthcare-ai-agent\CLAUDE.md` | Project structural overview (read after this handoff) |
| `C:\Users\tripleh\projects\healthcare-ai-agent\handoff.md` | **This file** |
| `C:\Users\tripleh\projects\healthcare-ai-agent\Healthcare_AI_Agent_Plan_v4_FINAL.docx` | Boss's canonical v4.1 plan (115 KB) |

### Backend
| Path | What |
|---|---|
| `backend/app/main.py` | FastAPI entrypoint. Registers all routers under `/api/v1`. |
| `backend/app/api/` | REST endpoints: `hrt_drilldown.py`, `lifelog.py`, `health.py`, `health_level.py`, `biometric.py`, `activity_events.py`, `food_lookup.py`, `dashboard.py`, `simulation.py`, `users.py`, `db_diagram.py` |
| `backend/app/database.py` | Supabase HTTP client (httpx-based, no SQLAlchemy) |
| `backend/glasses_watcher/` | **The whole capture-extraction pipeline lives here** (see Section 6) |
| `backend/.env` | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `NVIDIA_API_KEY` (~70 chars, format `nvapi-...`), `ANTHROPIC_API_KEY` |
| `backend/data/food_db/` | MFDS SQLite (108 MB, 275K foods) + USDA SQLite (62 MB, 13K foods) |

### Frontend
| Path | What |
|---|---|
| `frontend/hrt-dashboard/` | Next.js app |
| `frontend/hrt-dashboard/app/page.tsx` | Main HRT drill-down dashboard |
| `frontend/hrt-dashboard/app/lifelog/page.tsx` | Daily Lifelog page (new May 11) |
| `frontend/hrt-dashboard/app/predictions/page.tsx` | 8-disease × 4-horizon predictions |
| `frontend/hrt-dashboard/components/DetailPanel.tsx` | The drill-down detail card with per-item kcal pills |
| `frontend/hrt-dashboard/AGENTS.md` + `CLAUDE.md` | **CRITICAL**: this is a heavily-modified Next.js. Read `node_modules/next/dist/docs/` before writing frontend code. |

### Database
| Item | Detail |
|---|---|
| Supabase project ID | `klnykuxzucujahucvbct` |
| Region | `ap-northeast-2` (Seoul) |
| URL | `https://klnykuxzucujahucvbct.supabase.co` |
| Tables | 41 base tables + 5 views = 46 objects (MCP-verified 2026-04-23) |
| `user_id` type | BIGINT internal + UUID `user_token` external |
| Auth bypass for backend | `auth.role()='service_role'` granted via `require_current_user_id()` (locked Apr 24) |

### Migrations
| File | What |
|---|---|
| `migrations/001_initial_schema.sql` | Base HRT schema |
| `migrations/002_add_missing_tables.sql` | 22 tables for Domains 3-6 + shared helpers |
| `migrations/003_agent_context_memory.sql` | R8: agent_user_context + agent_memory |
| `migrations/004_hrt_drilldown_full_function.sql` | Main HRT drilldown RPC |
| `migrations/005_hrt_drilldown_logic_fixes.sql` | 6 audit bugs fixed (Apr 24) |
| `migrations/006_medication_intake_and_goal_relative_intensity.sql` | intake table + goal-relative intensity |
| `migrations/007_lifelog_event.sql` | New wide `lifelog_event` table for May 11 lifelog pipeline |

### ML
| Path | What |
|---|---|
| `ml/training/finetune_korean_food.py` | EfficientNetV2-S Korean food fine-tune script (~696 lines, 3-phase). Data ready. Trained on RTX 5090 — 88.41% TTA. |
| `ml/inference/benchmark_extractor.py` | Gemma 4 vs regex benchmark harness |
| `ml/data/aihub_korean_food/` | AI Hub Korean food images (150K images, 16 GB) |

### Docs
| Path | What |
|---|---|
| `docs/HRT_MULTIDIMENSIONAL_DRILLDOWN.md` | System design v1.5 |
| `docs/Healthcare_Pipeline_Diagram.docx` | Production architecture diagram (Apr 27) |
| `docs/daily_reports/` | Every day's session summary |

### External / cross-project
| Path | What |
|---|---|
| `C:\Users\tripleh\projects\aimb-bridge-android\` | Custom Android app to bridge AIMB-G1 glasses → OneDrive → this project (own handoff at `aimb-bridge-android/handoff.md`) |
| `C:\Users\tripleh\OneDrive\Pictures\Camera Roll\2026\05\` | Where iPhone / glasses videos land before `lifelog_watcher.py` picks them up |
| `C:\healthcare_finetune\` | On the **RTX 4070 SUPER server** (different PC): `models/gemma-4-E4B-it-Q8_0.gguf`, `llama-cpp-cuda/` build, GEMMA4_BENCHMARK_CONFIG.md, fine-tune scripts |
| `100.69.125.64:8081` | Mac mini llama.cpp serving Gemma 4 E4B Q8 (over Tailscale) |
| `100.69.125.64:8082` | Mac mini Whisper large-v3 server (over Tailscale) |

### Auto-memory (every memory file is at `~/.claude/projects/C--Users-tripleh/memory/`)
- `MEMORY.md` — index of all healthcare memories
- `project_healthcare_complete_handoff.md` — overall project state (Apr 27)
- `project_healthcare_lifelog_pipeline.md` — lifelog pipeline (May 11) ← most recent
- `project_healthcare_20260507_cnn_integration.md` — CNN cascade integration (May 7)
- `project_healthcare_phase2_complete.md` — Gemma vs watcher.py live comparison (Apr 28)
- `project_healthcare_gemma4_decision.md` — why Gemma 4 E4B was chosen
- `project_healthcare_gemma_llamacpp_request_format.md` — working llama.cpp request shape
- `project_healthcare_haiku_temporary_gemini_swap.md` — May 4 temporary Layer 1 swap (revert when billing restored)
- `project_healthcare_patent_claims.md` — patent claim-scope summary (placeholder)
- `feedback_healthcare_free_stack.md` — **STRICT: free local models only, no paid multimodal**
- `feedback_helmet_vs_healthcare.md` — boss-explicit: don't mix helmet + healthcare projects
- Daily session reports: `project_healthcare_20260414.md` through `project_healthcare_20260507.md`

---

## 4. The goal we're working toward

**Short term (this month):** A working end-to-end lifelog pipeline from glasses-wear to dashboard, fully automated, with the boss-demo target of "AI glasses can record everything during the day."

**Medium term (1-3 months):**
- Production stack on RTX 5090 (currently dev on RTX 4070 SUPER)
- Mentra Live glasses procurement + integration (replaces AIMB-G1)
- HealthKit / Health Connect auto-collection from wearables
- EfficientNetV2-S Korean food fine-tune → distill → on-phone TFLite

**Long term (3-6 months):**
- LSTM-Transformer training on KNHANES (27K parsed) + NHIS cohort (NHIS application status unknown — was "2-4 weeks" since Apr 14)
- Patent figure 4/5 forecasting model
- Monte Carlo Dropout uncertainty quantification
- Digital Twin comparison (user trajectory vs std_lifestyle_plan)
- DNA / family history cold-start model
- Hospital EMR FHIR R4 sync (external_records table is already there)
- Production launch with first 100-1,000 beta users

---

## 5. Current state of the project — phase by phase

| Phase | Status |
|---|---|
| **Database schema** | ✅ DONE. 41 tables + 5 views deployed. Migrations 001-007 applied. |
| **HRT drill-down RPC** | ✅ DONE. `hrt_drilldown_full_function`. 9 audit bugs found, 7 fixed in migrations 005/006. |
| **Phase 0 capture (AIMB-G1 → OneDrive → PC)** | ✅ DONE but manual (Cyan Import tap required). |
| **Phase 0 watcher (`watcher.py`)** | ✅ DONE. HEIC support, 48h mtime window, regex + Gemma fallback. |
| **Layer 1 voice extraction** | ✅ DONE. Hybrid regex + Gemma 4 E4B Q8 fallback. F1 1.000 on test set (CUDA, Korean prompt). |
| **Photo CNN cascade (Tier 0 + Tier 1)** | ✅ DONE (May 7). Korean food CNN 88.41% TTA + Food-101 88.15% TTA, ONNX, CPU inference. Integrated into `watcher.py`. Cross-class dedup via `food_class_groups.py`. |
| **Phase 2 multimodal supplement** | ✅ DONE (Apr 28). Gemma 4 + Nemotron 30B in parallel, dual-extraction logger, MAX-count dedup. |
| **Lifelog pipeline (broad extraction)** | ✅ DONE (May 11). New `lifelog_event` table, standalone `_lifelog_test.py`, `lifelog_watcher.py` auto-watcher, FastAPI `/api/v1/lifelog/events`, Next.js `/lifelog` page. 6 videos processed via lifelog_watcher so far. |
| **HRT dashboard** | ✅ DONE. Drill-down grid, predictions page, lifelog page. |
| **Phase 3 capture window (real-world test)** | 🟡 IN PROGRESS. Boss demo needs 30-60 min capture. Hasn't been done. |
| **Layer 2 conversational agents** | 🟡 PARTIAL. Qwen 3.5 v12 medical fine-tune deployed to Ollama (92% on 25Q eval). Llama 3.1 8B Korean fallback ready. OpenClaw 11-agent skill code not yet written. |
| **AIMB-G1 → auto capture (zero-tap)** | ❌ BLOCKED. See `C:\Users\tripleh\projects\aimb-bridge-android\handoff.md`. BLE wake fails 20/20 attempts. |
| **Mentra Live procurement** | ❌ NOT STARTED. $349 + $30 forwarding decided Apr 15. |
| **EfficientNetV2-S Korean food fine-tune (full re-run)** | 🟡 ONE-RUN DONE (88.41% TTA). Script + USB ready for future re-runs. |
| **Korean snack CNN** | ❌ SKIPPED — license-blocked, no usable free dataset (snack_research.md). |
| **LSTM-Transformer training** | ❌ NOT STARTED. Blocked on NHIS cohort approval. |
| **Phone-side ML stack (232 MB)** | 🟡 PARTIAL. Components identified, not yet packaged onto Note 10. |
| **Production launch** | ❌ NOT STARTED. Blocked on regulatory posture (#1 open question). |

**Coverage estimate:** ~55% across the full v4.1 plan. Capture + extraction + storage + dashboard are essentially complete; agents, predictions training, production deployment, and regulatory work remain.

---

## 6. Current state of code

### Active production daemon (the thing that runs constantly)
**`backend/glasses_watcher/watcher.py`** — the main capture pipeline. Reads new files from `~/OneDrive/Pictures/Camera Roll/2026/MM/`, classifies them, extracts events, writes to Supabase.

The flow for one photo:
```
1. Watch new file → detect HEIC/MP4/PNG
2. upload_event(audit row, always) in user_activity_event
3. Non-health gate: skip if no YOLO health frames + no voice health keywords
4. Tier 0/1 CNN cascade (multi-crop) → confident dish rows direct to user_food_log
5. Phase 2 multimodal (Gemma + Nemotron in parallel) → cross-class dedup with CNN
6. Cross-model arbitration on close calls → Gemma image arbitration via Mac mini
7. distribute_to_tables with skip_meal_placeholder / skip_drink_placeholder
```

### Glasses_watcher module contents
| File | What |
|---|---|
| `watcher.py` | Main daemon. _CNN_ENABLED bootstrap, process_image, process_video Phase 2, distribute_to_tables |
| `_lifelog_test.py` | Standalone broad-extraction script. Chunks video → 8 frames/chunk → Gemma (+optional Qwen) → `lifelog_event` table |
| `lifelog_watcher.py` | Auto-watcher sibling to watcher.py. Separate `lifelog_processed.json` cache. |
| `event_processor.py` | Regex Layer 1 + MFDS/USDA nutrition lookup. `lookup_food_nutrition(name, portion_g=None)` scales per-100g to portion. |
| `food_classifier.py` | KoreanFoodClassifier ONNX wrapper (USB-shipped). 150 classes. |
| `food_cnn_cascade.py` | Orchestrator. `classify_image_multi()` returns ALL confident hits across crops, dedup'd per (tier, class). |
| `food_class_groups.py` | Semantic equivalence map. `food_class(name)` returns canonical id. Handles Korean+English synonyms, ASR typos. DRINK_CLASSES frozenset. |
| `food101_nutrition.py` | 101-entry kcal/protein/fat/carb table |
| `gemma_dual_extractor.py` | Mac mini Gemma 4 E4B client + frame sampler. Also `gemma_arbitrate_image_candidates()` for close-call arbitration. |
| `nemotron_extractor.py` | NVIDIA NIM Nemotron 30B Omni client (still works; lower priority post-CNN). |
| `llm_extractor.py` | Layer 1 cloud extractor (currently Gemini-via-temporary-swap, revert to Haiku when Anthropic billing restored — see `project_healthcare_haiku_temporary_gemini_swap.md`) |
| `watcher_gemma.py` | Phase 2 Gemma-only logging side-channel (writes to `dual_extraction_*.jsonl`). |
| `models/korean/` | korean_food_classifier.onnx + .onnx.data (~83 MB) + class_names.txt + class_mapping_kr_to_en.json |
| `models/international/` | food101_classifier.onnx + .onnx.data (~80 MB) + class_names.txt |
| `processed.json` | watcher.py's seen-files cache (md5 hashes) |
| `processed_gemma.json` | watcher_gemma.py's separate cache |
| `lifelog_processed.json` | lifelog_watcher.py's separate cache — **6 hashes** (real videos already processed) |
| `logs/dual_extraction_YYYY-MM-DD.jsonl` | Phase 2 dual-extraction comparison log (one row per chunk) |

### FastAPI routers (`backend/app/api/`)
| File | Endpoint prefix | What |
|---|---|---|
| `hrt_drilldown.py` | `/hrt` | Multi-dim drill-down. Bypasses RPC for `category=food` (direct SELECT with KST→UTC). |
| `lifelog.py` | `/lifelog` | `GET /events?user_id=&date=&source_model=&category=` |
| `health.py` | `/health` | Health summaries |
| `health_level.py` | `/health-level` | Stress / mental health |
| `biometric.py` | `/biometric` | HR/BP/SpO2/glucose/temp |
| `activity_events.py` | `/activity-events` | Raw glasses events |
| `food_lookup.py` | `/food` | MFDS direct lookup (no caching) |
| `dashboard.py` | `/dashboard` | Aggregated dashboard data |
| `simulation.py` | `/simulation` | Predictions page |
| `users.py` | `/users` | User CRUD |
| `db_diagram.py` | `/db-diagram` | Live DB visualization |

### Next.js pages (`frontend/hrt-dashboard/app/`)
| Page | What |
|---|---|
| `page.tsx` | Main HRT dashboard with drill-down grid + predictions button + 📖 Daily Lifelog link |
| `lifelog/page.tsx` | New (May 11). KPI strip + chronological timeline of lifelog events, source-model filter (Gemma/Qwen/both), category filter. Reads via FastAPI `/api/v1/lifelog/events`. |
| `predictions/page.tsx` | 8-disease × 4-horizon risk predictions |
| `chart-demo/` | Chart playground |
| `components/DetailPanel.tsx` | Drill-down detail with per-item kcal pills (uses `realEvents` from RPC, falls back to `details: string[]`) |

### Build / run commands
```powershell
# Backend
cd C:\Users\tripleh\projects\healthcare-ai-agent\backend
C:\Users\tripleh\AppData\Local\Python\pythoncore-3.11-64\python.exe -m uvicorn app.main:app --reload --port 8000

# Frontend
cd C:\Users\tripleh\projects\healthcare-ai-agent\frontend\hrt-dashboard
npm run dev

# Watcher (production)
cd C:\Users\tripleh\projects\healthcare-ai-agent\backend
C:\Users\tripleh\AppData\Local\Python\pythoncore-3.11-64\python.exe glasses_watcher\watcher.py

# Lifelog watcher (parallel, doesn't conflict with watcher.py)
cd C:\Users\tripleh\projects\healthcare-ai-agent\backend
C:\Users\tripleh\AppData\Local\Python\pythoncore-3.11-64\python.exe glasses_watcher\lifelog_watcher.py
```

### Locked architecture decisions (do NOT re-litigate)
1. **Layer 1 voice extractor = hybrid regex + Gemma 4 E4B Q8 cloud fallback.** Confidence threshold 0.7. (Locked Apr 27.)
2. **Layer 2 conversational agents = Qwen 3.5 v12 (medical fine-tune) + Llama 3.1 8B (Korean fallback) + Meditron-70B (heavy reasoning).** Do NOT swap with Layer 1. (Locked Apr 27-28.)
3. **Production tier = RTX 5090 primary + Modal / RunPod cloud overflow.** Capacity ~150K-200K users at 5% fallback rate.
4. **Storage = Supabase (structured) + Supabase Storage (thumbnails) + S3 (raw clips when conf<0.7, with HIPAA/PIPA tiered retention).**
5. **Glasses = AIMB-G1 today, Mentra Live production target (~2027 for Korean AR glasses with on-chip silicon).** Healthcare glasses are **pure off-chip** until then. Don't mix with the helmet project. (`feedback_helmet_vs_healthcare.md`)
6. **Free-stack lock for vision.** No paid multimodal APIs anywhere. Gemini permitted **only** as Layer 1 voice fallback during the current Anthropic billing gap (will revert to Haiku). (`feedback_healthcare_free_stack.md`)
7. **Lifelog uses ONE wide table** (`lifelog_event` with JSONB `raw_event` backup) until 2-4 weeks of real data tells us which fields deserve dedicated tables.

---

## 7. Files actively being edited / touched

### THIS SESSION (2026-05-12)
**The healthcare codebase itself was not edited this session.** All work was in the sibling project `aimb-bridge-android/`. However, that project's eventual success directly unblocks the healthcare lifelog pipeline (it removes the one remaining manual tap in the capture flow).

Files **actively edited / created in aimb-bridge-android** this session:
- `app/src/main/java/com/tripleh/aimbbridge/ble/GlassesProtocol.kt` — trimmed `INIT_COMMANDS_RAW` from 11 → 7 commands, added Device Info Service UUIDs
- `app/src/main/java/com/tripleh/aimbbridge/ble/GlassesBleClient.kt` — full GATT-reconnect retry loop (20 attempts), firmware reads, 600ms settle delay
- `app/src/main/java/com/tripleh/aimbbridge/MainActivity.kt` — log buffer + auto-save + share button
- `app/src/main/AndroidManifest.xml` — FileProvider declaration
- `app/src/main/res/xml/file_paths.xml` — NEW
- `app/src/main/res/values/strings.xml`, `res/layout/activity_main.xml` — new button + strings
- `reverse_engineering/cyan_base.apk`, `cyan_arm64.apk` — pulled from phone via ADB
- `reverse_engineering/cold_start_btsnoop_hci.log`, `cold_start_12_May_11_29_07.pcap` — fresh cold-start protocol capture
- `reverse_engineering/BLE_PROTOCOL_RAW.md` — auto-regenerated
- `reverse_engineering/handoff.md` — separate detailed handoff for the BLE work

### Files modified / added in PRIOR sessions (still in active rotation)
- `backend/glasses_watcher/watcher.py` — CNN cascade integration (May 7), cross-model dedup, non-health gate (May 8)
- `backend/glasses_watcher/food_class_groups.py` — semantic equivalence map, drink classes, ASR-typo normalization
- `backend/glasses_watcher/gemma_dual_extractor.py` — arbitration function
- `backend/glasses_watcher/_lifelog_test.py`, `lifelog_watcher.py` (May 11)
- `backend/app/api/lifelog.py` (May 11)
- `frontend/hrt-dashboard/app/lifelog/page.tsx` (May 11)
- `frontend/hrt-dashboard/components/DetailPanel.tsx` — per-item kcal pills (May 7)
- `migrations/007_lifelog_event.sql` (May 11)

---

## 8. What's been touched or changed this session (2026-05-12)

This session was 100% AIMB-G1 BLE wake reverse engineering (the auto-capture feature). The healthcare codebase itself was untouched. Specific touches:

1. Captured a fresh **cold-start packet capture** (PCAPdroid + Android Bluetooth HCI snoop log) of Cyan's full pairing + Import flow.
2. **Pulled Cyan APK from phone** via ADB (`com.aitowe.aitoglasses`), 71 MB base + 28 MB ARM64 split. Stored in `aimb-bridge-android/reverse_engineering/`.
3. Partial **JADX decompile** of Cyan APK:
   - `classes5.dex` (Oudmon SDK) — successfully decompiled. Got the wake-frame builder source.
   - `classes.dex` and others (Aitowe app code) — JADX keeps crashing silently on the multi-DEX APK with embedded macOS debug binary.
4. **Verified our wake bytes are byte-for-byte correct** by reading the decompiled Cyan source. `LargeDataHandler.syncHeartBeat(4)` produces exactly `BC 45 02 00 C2 B0 04 01`.
5. **Refactored the Kotlin BLE state machine** to a 20-attempt full-GATT-reconnect loop with firmware reads and a 600 ms pre-wake settle.
6. **Added log save + share feature** to the Android app (saves every cycle to `Android/data/.../files/logs/aimb_log_*.txt`, shares via FileProvider).
7. **Ran 20-attempt test on real hardware** — all 20 attempts failed identically. Glasses respond to every wake with the `bc7308 …01 00 00 01…` error notification.
8. **Wrote two handoff documents:**
   - `C:\Users\tripleh\projects\aimb-bridge-android\handoff.md` (BLE wake side-quest detail)
   - `C:\Users\tripleh\projects\healthcare-ai-agent\handoff.md` (this file — umbrella project state)

**No healthcare backend, frontend, ML, or watcher code was modified.** No migrations applied. No Supabase schema changes. No new lifelog events processed (the user wasn't running watchers during the session — they were testing the Android app).

---

## 9. What didn't work and why

### Healthcare-side (prior sessions, still relevant context)
- **Mock-based integration tests** — burned in Q1 when migration passed in mock but broke prod. Always test against real Supabase. (See `feedback` memory.)
- **Gemma 4 E2B Q4 on CPU** — proven slower AND less accurate than regex (44 s, F1 0.375). Don't propose it. RTX 4070 SUPER + Gemma 4 E4B Q8 CUDA is the correct configuration.
- **Phase 2 supplement filter tuning** (May 6-7) — hit a fundamental capability ceiling on adversarial pronoun-only Korean test videos. Small multimodal models (Gemma 4 E4B 4B, Nemotron 30B) can't reliably handle "I had four of this" with no item names. **Fixed by**: integrating the Korean food CNN cascade (May 7) — direct ID from photo bypasses the LLM hallucination risk entirely.
- **Drink + meal placeholder double-counting** (May 8) — generic "drink (cup)" was being written alongside specific drinks from CNN/Phase 2. **Fixed by**: `skip_drink_placeholder` / `skip_meal_placeholder` flags in `distribute_to_tables`, set based on whether specific items were written.
- **Non-health-video false positives** (May 8) — generic tech-expo footage produced bogus food + bogus exercise rows. **Fixed by**: a non-health gate before CNN cascade + Phase 2 in both `process_image` and `process_video`. Skip when no YOLO health frames AND no voice health keyword.
- **MFDS per-100g vs portion mismatch** (May 7) — first row was 142 kcal at portion=150g but treated as per-100g. **Fixed by**: `lookup_food_nutrition(name, portion_g=None)` scaling using `serving_size` column.
- **Cross-model dedup missing for synonyms** (May 7) — 양념치킨 (CNN T0) + chicken_wings (CNN T1) + "fried chicken" (Gemma) all wrote separate rows for the same dish. **Fixed by**: `food_class_groups.py` with `food_class()` canonical ID mapping + cross-tier dedup.
- **Stdout double-wrap ValueError** (May 7) — `event_processor.py` and `watcher.py` both wrapped stdout in UTF-8 TextIOWrapper. **Fixed by**: idempotent guard checking `sys.stdout.encoding`.

### AIMB-G1 BLE wake (this session — see aimb-bridge-android/handoff.md for the full account)
- **Single-GATT 5-retry wake** → only first wake hit the radio (Android returned -1 on retries 2-5)
- **Full-reconnect 8-retry wake** → all failed, glasses' state byte stuck at `0x06`
- **Removing "poison" commands from init** → got closer; state byte moved to `0x01` but still wrong (Cyan gets `0x04` on success)
- **20-attempt loop with all fixes** → 0/20 success. The state-byte mismatch is deterministic.
- **APK decompile via JADX** → keeps failing silently on multi-DEX APK with embedded macOS `dump_syms.bin`

### Open: regulatory posture
**Nothing yet done.** Wellness vs SaMD classification, MFDS approval, FDA approval if US targeted. The /predictions page already crosses the wellness/SaMD line without disclaimers. Highest-stakes blind spot in the project.

---

## 10. How we fixed the failed errors that *were* fixable

(See "what didn't work" — most were fixed inline in prior sessions. Notably:)
- CNN cascade fixed the multimodal hallucination ceiling.
- Multi-crop fixed the center-crop clipping bug.
- Class-group dedup fixed cross-model duplicates.
- MFDS portion scaling fixed unit-mismatch.
- Non-health gate fixed false positives.
- Stdout double-wrap idempotency fixed the print errors.
- Migration 007 + new lifelog table fixed the "where do broad-extraction events go" question (just make one wide table, evolve schema later).

---

## 11. Where and why we stopped (2026-05-12 end-of-session)

We stopped because:

1. **The 20-attempt BLE wake test produced 20 identical failures.** We have conclusive evidence that our wake bytes are correct (verified against decompiled Cyan source) but the glasses' state byte in response to our init query is `0x01` (not ready), while Cyan gets `0x04` (ready). Something in Cyan's pre-wake sequence flips the state byte from 0x01 → 0x04, and we don't know what.

2. **The fix requires reading Aitowe's app code**, not the Oudmon SDK. We have the Oudmon SDK fully decompiled (in `classes5.dex`) but Aitowe's calling code lives in `classes.dex`, which JADX keeps failing to decompile on this multi-DEX APK.

3. **User explicitly rejected the workaround** (Path B — monitor WiFi scan, require user to tap Import in Cyan). User wants the BLE wake fixed properly.

4. **Session ran out of time** while we were trying decompile workarounds.

**The healthcare project itself is in a healthy state** — extraction, dashboard, and lifelog all work. The blocker is only on the auto-capture feature (one missing piece of the pipeline).

---

## 12. Next plans (priority order)

### 🔴 Immediate (next session start)
1. **Fix the BLE wake** — see `C:\Users\tripleh\projects\aimb-bridge-android\handoff.md` for the detailed plan. Key first step: get JADX to fully decompile `classes.dex` (try deleting `dump_syms/` from extracted APK first, then re-zip and decompile).
2. Once wake works on the test phone, integrate the AIMB Bridge app into the user's daily workflow.

### 🔴 Healthcare-side, blocking
3. **Resolve regulatory posture** — wellness app vs SaMD Class II. Boss + Korean medical-device consultant. Determines whether /predictions can stay public. Highest-stakes blind spot.
4. **Get clarification from boss on "pipelines 3+4"** — what does "PC" mean? Company server (already designed) or user's home PC for backfill? 5-minute conversation unblocks Phase 4 architecture commitment.
5. **Real 30-60 min lifelog test capture** — boss demo. User has to record + run `lifelog_watcher.py` + populate `/lifelog` dashboard with a full workday.
6. **`--compare` mode lifelog test** — run Gemma + Qwen 3.5 VLM 397B on the same video, decide which is worth the cost/latency at scale.

### 🟠 Short-term (1 month)
7. **Deploy production stack on RTX 5090** (currently dev only). Linux preferred (Win11 currently).
8. **Chatbot in HealthGlassesApp** — Cloud Haiku for now (fastest path). Switch to Gemma E2B Q4 on flagship phones (S25 / iPhone 16+).
9. **Pill-event detection + phone push notification** — quick-reply buttons for unknown pills.
10. **S3 lifecycle policy** — Hot 7d → Warm 30d → Glacier 90d → Archive 7 years (HIPAA/PIPA retention).
11. **CUDA Whisper large-v3 on RTX 4070 SUPER** — kills the medium-Korean-English mangle.
12. **HealthKit / Health Connect integration** — auto-collect from Apple Watch / Galaxy Watch / smart ring.
13. **Mentra Live procurement** — order, unbox, integration test.
14. **Face blur (YOLOv8-Face)** — REQUIRED before any real-user rollout (currently waived for testing per boss).
15. **PIPA legal review** — Korean Personal Information Protection Act compliance audit.

### 🟡 Medium-term (1-3 months)
16. **Fine-tune EfficientNetV2-S Korean food** (full re-run, distill to TFLite student) — replaces MobileNetV2 on phone.
17. **OpenClaw 11-agent skill code** — currently empty directories.
18. **Expand test set** with real Mentra clips (vs current AIMB-G1 clips).
19. **Backfill historical data** from user's existing apps (Apple Health, Samsung Health, OneDrive lab PDFs).
20. **Daily AI-generated narrative** on the /lifelog page ("Your day in 3 sentences").
21. **Side-by-side Gemma-vs-Qwen compare panel** on the /lifelog page for chunks where they diverge.
22. **Schema evolution** — after 2-4 weeks of real lifelog data, promote noisy columns to dedicated tables (e.g. `user_interaction`, `user_purchase`).
23. **Fold lifelog into production `watcher.py`** as a third extraction mode alongside narrow food/exercise.

### 🟢 Long-term (3-6 months)
24. **LSTM-Transformer training** on KNHANES + NHIS cohort (when approved). Patent figure 4/5 forecasting.
25. **Monte Carlo Dropout** uncertainty quantification.
26. **Digital Twin comparison** — user trajectory vs `std_lifestyle_plan` ideal.
27. **DNA / family history cold-start model**.
28. **Hospital EMR FHIR R4 sync** — `external_records` table is ready.
29. **Expert marketplace** — consultations, read-only HRT sharing.
30. **Production launch** with first 100-1,000 beta users (gated on regulatory).

---

## 13. How much we covered so far

### Quantitative
- **Database**: 41 tables + 5 views = 46 objects deployed. 7 migrations applied.
- **Extraction pipeline**: 4-tier (Korean CNN → Food-101 CNN → Gemma multimodal → Nemotron) with cross-arm dedup, MFDS/USDA scaling, non-health gate, semantic equivalence map.
- **Models trained**: Korean food CNN 88.41% TTA (150 classes), Food-101 88.15% TTA (101 classes), Gemma 4 E4B Q8 confirmed F1 1.000 on test set, Qwen 3.5 v12 medical 92% on 25Q.
- **Lifelog pipeline**: 5 new files (test script, watcher, FastAPI router, Next.js page, migration). 6 real videos already processed.
- **Frontend pages**: 4 (HRT main, lifelog, predictions, chart-demo). Per-item kcal pills in detail panel. Source-model + category filters in /lifelog.
- **Reverse engineering**: Full HTTP protocol decoded. BLE protocol ~80% decoded (frame format, opcode map, init sequence, wake bytes). 2 packet captures done.

### Qualitative
- **Architecture decisions locked** (Apr 27-28): hybrid extractor, RTX 5090 production target, pure off-chip healthcare (helmet separate), two-layer LLM stack, free-stack lock for vision.
- **Patent**: registered (10-2025-0145274, Oct 2 2025), claims summary not yet pulled from KIPRIS.
- **Hardware inventory**: 2 dev PCs (i3-12100 + RTX 4070 SUPER), production RTX 5090 prepared, Mac mini serving Gemma+Whisper over Tailscale, AIMB-G1 glasses, Note 10 5G test phone.
- **External deps**: NVIDIA NIM (Nemotron 30B + Qwen 3.5 VLM), Mac mini llama.cpp, Anthropic (gap — temporarily swapped to Gemini), OneDrive sync.

### Estimated overall completion
- **End-to-end capture + extraction + storage + display**: ~85% (works manually; auto-capture is the missing piece)
- **Conversational agents**: ~30% (Layer 2 LLMs trained but skill code not written)
- **Predictions / forecasting**: ~10% (page exists, model not trained)
- **Production readiness**: ~25% (dev stack works; production deploy + regulatory + face blur all blocking)
- **Whole v4.1 plan**: **~55%**

---

## 14. Cross-reference

For deep dive on specific topics, read these in order:

- **The AIMB BLE wake side-quest** → `C:\Users\tripleh\projects\aimb-bridge-android\handoff.md` (covers everything about why glasses → phone auto-capture is blocked)
- **The latest lifelog work** → `~/.claude/projects/C--Users-tripleh/memory/project_healthcare_lifelog_pipeline.md`
- **CNN cascade architecture** → `~/.claude/projects/C--Users-tripleh/memory/project_healthcare_20260507_cnn_integration.md`
- **Gemma 4 decision rationale** → `~/.claude/projects/C--Users-tripleh/memory/project_healthcare_gemma4_decision.md`
- **Overall April-end project state** → `~/.claude/projects/C--Users-tripleh/memory/project_healthcare_complete_handoff.md` (some claims are 14 days old; verify against current code before asserting)
- **Free-stack lock + helmet/healthcare separation** → `feedback_healthcare_free_stack.md` and `feedback_helmet_vs_healthcare.md`
- **Live BLE wake log proving the current failure** → `C:\Users\tripleh\Downloads\Android phone\aimb_log_20260512_132917.txt`

---

## 15. Critical user preferences (carry forward)

- **Free-stack only** for vision/extraction. No paid multimodal except Gemini-as-Layer-1-fallback during current Anthropic billing gap.
- **Don't mix healthcare + helmet projects.** Different clients, regulators, hardware.
- **Korean food and drug names stay in Korean.** Do not translate (e.g. `'피자'` not `'Pizza'`).
- **Test against real Supabase**, never mocks. Mock divergence broke a Q1 prod migration.
- **Verify deployed state via Supabase MCP** before trusting cached table counts — memory ages and gets stale.
- **AIMB Bridge auto-capture must work, no manual taps allowed.** User explicitly rejected the "use Cyan + monitor WiFi" workaround. Stay on the BLE-wake path.
- **Terse communication.** User gets frustrated by long answers with multiple options. Give one clear instruction at a time during diagnosis sessions.

---

## 16. How to resume — concrete first actions

1. Read this whole file.
2. Read `aimb-bridge-android/handoff.md` (the immediate blocker).
3. Try the JADX workaround at `aimb-bridge-android/handoff.md` Section 11.1: delete `extracted_base/dump_syms/`, re-zip, decompile.
4. Once decompile succeeds, find the caller of `syncHeartBeat(` (or `addHeader(69`) in `com.aitowe.aitoglasses.*` code.
5. Read the surrounding lines, identify what pre-wake setup we're missing, replicate it in Kotlin.
6. Test on phone with the existing 20-attempt loop. Share log → review.
7. Once wake works: switch focus back to healthcare main project — kick off the deferred items in Section 12.

**For non-blocking healthcare work that doesn't depend on AIMB wake**: any item in Section 12 from #3 onward is fair game (regulatory, real 30-60 min lifelog test, RTX 5090 deploy, EfficientNet fine-tune re-run, etc.). Ask the user which one they want to prioritize.
