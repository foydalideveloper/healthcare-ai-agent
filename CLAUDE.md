# Healthcare AI Agent Project

> **Doc currency:** Last updated 2026-05-07. Reflects deployed Supabase state (42 base tables + 5 views, migrations 001-006). Two-layer LLM architecture locked Apr 27-28. Tier 0/1 CNN cascade (Korean food + Food-101) integrated into watcher.py May 7. If reading after a long gap, MCP-verify the table count and check the handoff for newer decisions before trusting individual numbers.

## Overview
Generative AI-Based Autonomous Healthcare System for Triple-H Co., Ltd.
Patent No. 10-2025-0145274 | Target: 100,000 users

## Tech Stack
- **Database**: Supabase (PostgreSQL 17 + pgvector, project `klnykuxzucujahucvbct`, ap-northeast-2 / Seoul) -> TimescaleDB at scale
- **Backend**: FastAPI (Python 3.12+)
- **Agent**: OpenClaw v2026.4 + NemoClaw
- **Edge AI**: TensorFlow Lite + Snapdragon AR1+ Gen 1
- **Frontend**: React Native (mobile), Next.js (web)
- **Pipeline**: Apache Kafka + Airflow
- **ML**: PyTorch 2.3+ (Hybrid LSTM-Transformer)

## LLM Architecture (TWO independent layers — do NOT collapse)

The system runs two LLM stacks for two different jobs. They coexist by design.

### Layer 1 — Voice extraction (transcript → structured JSON)
- **Phone fast path**: regex extractor in `backend/glasses_watcher/event_processor.py` (~10 ms, F1 1.000 on exercise + meds)
- **Cloud fallback** (5-15% low-confidence events): **Gemma 4 E4B Q8** on GPU (food F1 1.000, p50 6.59 s on RTX 4070 SUPER CUDA)
- Locked Apr 27, 2026. See memory: `project_healthcare_gemma4_decision.md`.

### Photo extraction — Tier 0/1 CNN cascade (free, in-house)
Runs BEFORE Layer 1 multimodal supplements on every photo and on sampled video frames. Confident hits land in `user_food_log` directly via MFDS / Food-101 nutrition lookup, no LLM call.
- **Tier 0**: Korean food CNN (150 classes, 88.41% TTA, EfficientNetV2-S, 84 MB ONNX) — fine-tuned on AI Hub Korean meals. CPU inference ~100 ms/image.
- **Tier 1**: Food-101 international CNN (101 classes, 88.15% TTA, same backbone, 80 MB ONNX) — falls through here when Tier 0 confidence < 0.60 or top-1/top-2 margin < 0.15.
- **Fall-through**: when neither CNN is confident, the existing Phase 2 Gemma + Nemotron multimodal supplement runs as before. Cross-arm dedup blocks the supplement from re-writing the CNN's row.
- Wrappers: `backend/glasses_watcher/food_classifier.py` + `hybrid_classifier.py` (USB-shipped). Orchestrator: `food_cnn_cascade.py`. Food-101 nutrition table: `food101_nutrition.py`.
- Free-stack architecture lock: no paid multimodal API anywhere in this path.

### Layer 2 — Conversational agents (Doctor AI, Family Agent, Expert Agent, etc.)
- **Primary medical conversationalist**: **Qwen 3.5 v12** — medical fine-tune on 228K English med Q&A, LoRA on RTX 4070 SUPER (~19h training Apr 23-24), deployed to Ollama (8.1 GB, 92% on internal medical 25Q eval)
- **Korean-language conversational fallback**: Llama 3.1 8B
- **Heavy medical reasoning** (cloud-only): Meditron-70B
- All SFT + DPO fine-tuned per v4.1 plan.

> **Important**: Layer 1 and Layer 2 are not interchangeable. Gemma 4 E4B is a general multimodal extractor and is not domain-tuned for medical reasoning. Qwen 3.5 v12 is the medical conversationalist and would be wasted on JSON extraction. Do not "consolidate" or "swap" between layers.

## Project Structure
```
backend/          - FastAPI application server
  app/api/        - REST API endpoints
  app/models/     - SQLAlchemy/Pydantic models
  app/services/   - Business logic
  app/skills/     - OpenClaw skill backends
  glasses_watcher/ - AIMB-G1 watcher + regex extractor (Layer 1 fast path) +
                     Tier 0/1 CNN cascade (food_cnn_cascade.py, models/{korean,international}/)
migrations/       - SQL migrations (top-level, NOT under backend/)
agent/            - OpenClaw agent definitions
  skills/         - 11 agent skills (2 orchestration + 9 functional)
frontend/         - React Native + Next.js
edge-ai/          - On-glasses model configs
ml/               - Training and inference code
  inference/      - Gemma extraction benchmark, runtime
  training/       - EfficientNetV2-S Korean food fine-tune (script ready, not yet run)
infra/            - Docker, K8s, Airflow DAGs
docs/             - Documentation
  daily_reports/  - Per-session daily summaries
```

## Database
- Supabase project: `klnykuxzucujahucvbct` (ap-northeast-2 / Seoul)
- **42 base tables + 5 views = 47 objects across 6 domains** (Reference Standards, Personal Health Data, User Management, Admin/Operator, Notifications, Expert/External + Shared helpers)
- Local migrations: `001_initial_schema.sql` through `006_medication_intake_and_goal_relative_intensity.sql` (Supabase shows 16 migration rows including timestamped fixes)
- Key: user_id (UUID) before timestamp in all indexes
- pgvector for multimodal embeddings (HNSW index)
- `get_my_user_id()` helper + `require_current_user_id()` with `auth.role()='service_role'` bypass

## Commands
- Backend: `cd backend && uvicorn app.main:app --reload`
- Tests: `cd backend && pytest`

## Authoritative project state

For 0-to-100% project context (locked decisions, hardware, pipelines, open questions, future plans), read **`~/.claude/projects/C--Users-tripleh/memory/project_healthcare_complete_handoff.md`** first. This file (`CLAUDE.md`) is the structural overview; the handoff is the operational source of truth.
