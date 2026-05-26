# System Architecture - Operator & User Side
## Triple-H Co., Ltd. | Healthcare AI Agent

---

# PART 1: System Operator (Server Side)

## Case I: Local Deployment (On-Premise)

### a. Software Needed

| Software | Purpose | Install Where | Qty |
|----------|---------|---------------|-----|
| **OpenClaw v2026.4** | AI agent framework (11 agents) | App Server | 3 (HA) |
| **NemoClaw (NVIDIA)** | Security sandbox for agents | All Servers | All |
| **PostgreSQL 16 + TimescaleDB** | Health record database (HRT) | DB Server | 1 Primary + 3 Replicas |
| **pgvector extension** | Vector similarity search (embeddings) | DB Server | With PostgreSQL |
| **Redis 7.x Cluster** | Session cache, rate limiting, agent state | Gateway | 6 nodes |
| **Apache Kafka (KRaft)** | Message queue between agents/devices | Gateway | 5-15 brokers |
| **FastAPI (Python)** | REST API server, simulation backend | App Server | 3 (HA) |
| **NGINX / HAProxy** | Load balancer, TLS termination | Gateway (DMZ) | 2-4 (HA) |
| **Apache Airflow 2.9+** | Data pipeline orchestration (3 DAGs) | Pipeline Server | 1 |
| **vLLM / Triton** | LLM model serving (Qwen 7B, Meditron 70B) | GPU Server | 2-6 |
| **PyTorch 2.3+** | LSTM training, food recognition, DPO | Training GPU | 1-2 |
| **FFmpeg 7.x** | Video transcoding (H.265) | Processing GPU | 2 |
| **Whisper (OpenAI)** | Speech-to-text (Korean + English) | GPU Server | With vLLM |
| **YOLOv8 / YOLOv11** | Food/object detection, face anonymization | GPU Server | With vLLM |
| **HAPI FHIR Server** | Hospital EMR integration (HL7 FHIR R4) | App Server | 1 + replica |
| **Prometheus + Grafana** | Monitoring, dashboards, alerting | Monitor Server | 2 (HA) |
| **ELK Stack** | Centralized logging, HIPAA audit trail | Monitor Server | 1 |
| **HashiCorp Vault** | Secrets management, encryption keys | Security Server | 1 |
| **Keycloak** | OAuth 2.0 / OIDC identity management | Security Server | 1 |
| **MinIO** | On-premise object storage (S3 compatible) | Storage Server | 4 nodes |
| **Node.js 24+** | OpenClaw runtime | App Server | With OpenClaw |
| **Next.js** | HRT Dashboard, Admin Panel (web) | App Server | With FastAPI |
| **Docker + Kubernetes** | Container orchestration | All Servers | All |

**Total: 23 software components**

### b. Databases Needed (Local)

| Database | Type | Qty | Location | Purpose |
|----------|------|-----|----------|---------|
| **PostgreSQL 16 + TimescaleDB** | Primary (Write) | 1 | DB Primary (32c/512GB/NVMe 16TB) | All HRT tables (38+), hypertables |
| **PostgreSQL 16 + TimescaleDB** | Read Replica | 3 | Replica Servers | R1: App, R2: ML/Analytics, R3: Reporting |
| **pgvector** | Vector index | On Primary + R2 | Same as PostgreSQL | HNSW index for embeddings |
| **PgBouncer** | Connection pool | 2 (HA) | Between app and DB | 100K connections → 500 PG connections |
| **Redis 7.x Cluster** | In-memory cache | 6 nodes | Gateway layer | Sessions, rate limiting, agent state |
| **Apache Kafka** | Message broker | 5-15 brokers | Gateway layer | 10 topics for agent communication |
| **MinIO** | Object storage | 4 nodes | Storage layer | Thumbnails, video clips, model weights |
| **HAPI FHIR** | FHIR R4 store | 1 + replica | App layer | Hospital data integration |
| **SQLite** | Local food DB | 2 files | App Server | MFDS 275K + USDA 13K foods |

**Total: ~18-32 database instances depending on scale**

```
Architecture Diagram (Local):

[Users/Devices]
      ↓
[NGINX Load Balancer] ← DMZ
      ↓
[Redis Cache] ←→ [Kafka Message Queue]
      ↓
[OpenClaw Gateway + FastAPI App Servers x3]
      ↓               ↓
[PostgreSQL]    [GPU Servers]
[Primary+3Rep]  [vLLM + YOLO + Whisper]
      ↓
[MinIO Storage]  [HAPI FHIR]
```

---

## Case II: SaaS Deployment (Cloud - AWS)

### a. Software (Managed Services Replace Local)

| Local Component | AWS SaaS Replacement | Advantage |
|-----------------|---------------------|-----------|
| PostgreSQL + TimescaleDB | **Supabase** (beta→30K) → **Timescale Cloud** (30K+) | Managed HA, Auth, Realtime |
| MinIO | **Supabase Storage** → **AWS S3** | 4-tier lifecycle (Standard→IA→Glacier→Deep) |
| Kafka | **Amazon MSK Serverless** | Auto-scaling partitions |
| Redis | **Amazon ElastiCache** | Managed clustering |
| GPU Processing | **EC2 g5/p4d + SageMaker** | Pay-per-use, spot instances |
| vLLM/Triton | **SageMaker Endpoints** | Managed serving, A/B testing |
| NGINX | **ALB + API Gateway + CloudFront** | Global CDN |
| Airflow | **Amazon MWAA** | Managed workers |
| Vault | **AWS Secrets Manager + KMS** | Auto rotation |
| Keycloak | **Supabase Auth** → **Amazon Cognito** | Native mobile SDK |
| HAPI FHIR | **AWS HealthLake** | HIPAA-compliant, managed |
| Prometheus | **Amazon CloudWatch + Managed Prometheus** | No server needed |

### b. Databases (SaaS)

| Service | Configuration | Purpose | Monthly Cost |
|---------|--------------|---------|-------------|
| **Supabase** (beta→30K) | Pro plan, Seoul, pgvector + Auth + Storage | All-in-one platform | $25-$2,000 |
| **Timescale Cloud** (30K+) | 64vCPU/512GB, io2 16TB + 3 replicas | Dedicated hypertables | $2,000-$5,000 |
| **ElastiCache Redis** | 3 shards × 2 replicas, r7g.xlarge | Sessions, cache | $500-$1,500 |
| **Amazon MSK** | Serverless, ~300 partitions at 100K | Event streaming | $300-$1,000 |
| **AWS S3** | 4 lifecycle tiers | Media storage | $1,000-$10,000 |
| **AWS HealthLake** | FHIR R4 | Hospital interop | $500-$2,000 |

---

# PART 2: User System (Client Side)

## Case I: Local (On-Device)

### a. Software on User Devices

**AI Glasses (AIMB-G1 / Mentra Live):**

| Software | Purpose | Size |
|----------|---------|------|
| Built-in camera firmware | Photo/video capture | In hardware |
| Bluetooth/WiFi stack | Transfer to phone | In hardware |
| Cyan App (companion) | Import media from glasses | Phone app |

**User's Smartphone (iPhone/Android):**

| Software | Purpose | Size |
|----------|---------|------|
| Healthcare Agent App (React Native) | Main UI, chat, dashboard, food correction | ~50 MB |
| OneDrive / Google Drive | Auto-sync photos to cloud | System app |
| MobileNetV2-Food (TFLite) | On-device food recognition | ~4 MB |
| YOLOv8n (TFLite) | On-device object detection | ~6 MB |
| Google Health Connect / Apple HealthKit | Aggregate watch/ring data | System SDK |
| SQLite local database | Offline cache, pending uploads | ~50-200 MB |
| Background Sync Service | Upload data when on WiFi | Part of app |
| AES-256 Encryption | Encrypt all local health data | Part of app |

**User's PC/Web Browser:**

| Software | Purpose |
|----------|---------|
| Web browser (Chrome/Safari) | HRT Dashboard, Chat UI |
| No installation needed | Everything runs in browser |

### b. Databases on User Side

| Location | Type | Capacity | Contents |
|----------|------|----------|----------|
| AI Glasses | RAM buffer | ~50 MB | 30-second video buffer (circular, overwritten) |
| Smartphone | SQLite | ~50-200 MB | Recent events (7 days), pending uploads, preferences |
| Smartphone | File cache | ~1-3 GB max | Thumbnails + clips waiting upload, auto-purge after sync |
| Smartphone | Encrypted Keychain | ~1 MB | OAuth tokens, encryption keys |
| PC/Web | Browser localStorage | ~5 MB | Session data, UI preferences only |

**Total user-side: 1 database (SQLite on phone), 1-3 GB storage, 0 on PC**

---

## Case II: SaaS (User Side Differences)

User-side software is IDENTICAL. Only server endpoints change:

| Aspect | Local | SaaS |
|--------|-------|------|
| Upload endpoint | https://health.internal/api/ingest | https://api.healthcare-agent.com/v1/ingest |
| Auth | Self-hosted Keycloak | Supabase Auth / Amazon Cognito |
| Agent WebSocket | Direct to OpenClaw Gateway | API Gateway → ALB → OpenClaw |
| Media upload | Direct to MinIO | Pre-signed S3 URLs via CloudFront |

---

# SYSTEM BLOCK DIAGRAM

```
┌─────────────────────────────────────────────────────────────┐
│                    USER SIDE (Client)                        │
│                                                             │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌───────────┐ │
│  │AI Glasses│→ │ iPhone    │  │ Smart    │  │ PC/Web    │ │
│  │AIMB-G1   │  │ React    │  │ Watch    │  │ Browser   │ │
│  │8MP camera│  │ Native   │  │ HR/SpO2  │  │ Dashboard │ │
│  │Bluetooth │  │ App      │  │ Steps    │  │ Chat UI   │ │
│  └────┬─────┘  │          │  └────┬─────┘  └─────┬─────┘ │
│       │        │ SQLite   │       │               │       │
│       └───────→│ YOLOv8n  │←──────┘               │       │
│                │ TFLite   │                        │       │
│                └────┬─────┘                        │       │
│                     │ WiFi/LTE                     │       │
└─────────────────────┼──────────────────────────────┼───────┘
                      ↓                              ↓
            ┌─────────────────────────────────────────────┐
            │           NETWORK (Internet/VPN)             │
            └─────────────────────┬───────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────┐
│              SYSTEM OPERATOR SIDE (Server)                   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Layer 1: Gateway                                     │   │
│  │  NGINX LB → Redis Cache → Kafka Message Queue        │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         ↓                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Layer 2: Application                                 │   │
│  │  OpenClaw Gateway (ws://18789)                       │   │
│  │    → Orchestration Agent (intent classification)     │   │
│  │    → Judgement Agent (medical safety gate)            │   │
│  │    → 9 Functional Agents                             │   │
│  │  FastAPI Server (REST API, HRT drilldown)            │   │
│  │  Next.js (HRT Dashboard, Admin Panel)                │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         ↓                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Layer 3: AI/ML                                       │   │
│  │  vLLM: Qwen 7B + Llama 8B + Meditron 70B            │   │
│  │  LSTM-Transformer: Health prediction (65-dim)        │   │
│  │  Whisper: Speech-to-text                             │   │
│  │  YOLOv11: Food recognition (server-side)             │   │
│  │  EfficientNetV2-S: Korean food classifier            │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         ↓                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Layer 4: Data                                        │   │
│  │  PostgreSQL + TimescaleDB + pgvector                 │   │
│  │    38 Tables | 6 Views | 42 Indexes | 45 RLS         │   │
│  │    hrt_drilldown() function                          │   │
│  │  Redis (sessions) | Kafka (events) | MinIO (media)   │   │
│  │  HAPI FHIR (hospital) | SQLite (MFDS 275K foods)    │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         ↓                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Layer 5: Infrastructure                              │   │
│  │  Docker + Kubernetes | Prometheus + Grafana           │   │
│  │  Vault (secrets) | ELK (logging) | Keycloak (auth)   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Hardware: GPU Servers (RTX 4090 × 2-6, A100 for 70B)      │
│            App Servers (32c/256GB × 3)                      │
│            DB Server (32c/512GB/NVMe 16TB + 3 replicas)     │
│            Total: ~15-30 servers for 100K users              │
└─────────────────────────────────────────────────────────────┘
```

---

# MULTI-DIMENSIONAL DATA OVERVIEW

## What is it?
A way to look at health data from multiple angles simultaneously, like a 3D cube:

```
        TIME (X-axis)
        ─────────────────────→
        Year → Month → Day → Hour
    C   ┌────┬────┬────┬────┐
    A   │    │    │    │    │  Food
    T   ├────┼────┼────┼────┤
    E   │    │    │    │    │  Exercise
    G   ├────┼────┼────┼────┤
    O   │    │    │    │    │  Sleep
    R   ├────┼────┼────┼────┤
    Y   │    │    │    │    │  Medicine
        └────┴────┴────┴────┘
    (Y-axis)
    
Each cell = health data at that time × category
Click any cell → drill down to next level
```

## How it's used:
1. **Doctor view**: "Show me this patient's food history for the last 5 years"
2. **User view**: "What did I eat last Tuesday?"
3. **AI view**: "This user's calorie intake increased 20% in the last 3 months"
4. **Prediction**: "Based on HRT data, predict BMI in 1 year"

## Structure in Database:

```
REAL DATA (Supabase tables):
  user_food_log:     [food_id=7, food="삼겹살", kcal=500, time=2026-04-17 18:30]
  user_lifestyle:    [exercise_min=30, sleep_hours=7.5, date=2026-04-17]
  user_medication:   [drug="Vitamin D", dose=1000IU, date=2026-04-17]
  user_biometric:    [heart_rate=72, spo2=98, bp=120/80, time=2026-04-17 09:00]

AGGREGATED VIEWS (calculated by database):
  hrt_yearly_summary:   "2026: 1095 meals, 5475 min exercise, 7.2h avg sleep"
  hrt_monthly_food:     "April: 90 meals, 54000 kcal, top food: 삼겹살"
  hrt_daily_food:       "April 17: breakfast 450kcal, lunch 550kcal, dinner 850kcal"

DRILL-DOWN FUNCTION (runs inside database):
  hrt_drilldown(user=1, level=2, year=2026)
  → Returns monthly breakdown from the views above
```
