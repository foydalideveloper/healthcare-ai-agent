# HRT + LRT Unified Database Plan
## Triple-H Co., Ltd. | April 15, 2026
## Version 1.0 — Complete Technical Specification

---

## 1. Why We Must Unify

### The Problem
Right now, Triple-H has **two separate systems** tracking the same user:

```
SYSTEM 1: HRT (Health Record Table)          SYSTEM 2: LRT (Lifetime Record Table)
Supabase: oqotdxlmdgjieukyzegj               Supabase: rietbmwbraqisoneoill
14 tables                                    17 tables
Focus: Health data                           Focus: Life events + commerce

User "Kim" has:                              Same user "Kim" has:
- Blood pressure: 130/85                     - Getting married next year
- Ate 김치찌개 for lunch                      - Needs to buy a house
- Glucose trending up                        - Income bracket: middle
- BMI: 25.3                                  - MBTI: INTJ
```

**The problem:** These two systems don't talk to each other. But they SHOULD, because:

1. **Health affects purchases.** Kim's high blood pressure means the LRT Pre-Order system should recommend low-sodium food products, health supplements, or a blood pressure monitor — not just any random product.

2. **Life events affect health.** Kim getting married (LRT event) → stress increases → blood pressure goes up → HRT simulation should factor this in.

3. **Same AI glasses pipeline.** Both systems plan to use AI glasses for data collection. Building two separate pipelines is wasteful.

4. **Same user, one experience.** The user shouldn't have two different apps, two different logins, two different AI agents. They should have ONE system that understands their whole life.

5. **Patent alignment.** The healthcare patent (10-2025-0145274) describes a system that uses "1st/2nd/3rd degree collaborative agents" and "multimodal data collection" — both of which LRT already implements better than HRT alone.

### The Goal
One unified database where:
- HRT handles health prediction (BMI, glucose, cholesterol → 10-year trajectory)
- LRT handles life prediction (purchases, events, behavioral patterns)
- Both share the same user, same glasses data, same AI agents
- The health simulation INFORMS the purchase recommendations (and vice versa)

---

## 2. Current State: What Exists

### HRT Database (14 tables, your project)

| Table | Rows | Purpose |
|-------|------|---------|
| `users` | 8 | User profiles (UUID PK) |
| `user_demographic` | 0 | Sociodemographic time-series |
| `user_biometric` | 5,042 | Heart rate, glucose, SpO2 from wearables |
| `user_diagnosis` | 0 | Medical lab data (BMI, BP, cholesterol) |
| `user_lifestyle` | 1 | Daily diet, exercise, sleep |
| `user_activity_event` | 193 | AI glasses events (meals, drinks, medication) |
| `user_health_level` | 1 | Healthcare Index, Disease Risk Index |
| `user_multimodal` | 0 | Voice/image/video with pgvector embeddings |
| `agent_conversation_log` | 0 | AI agent chat history |
| `simulation_result` | 0 | LSTM health predictions |
| `std_population_category` | 26 | Population segments for health benchmarking |
| `std_diagnosis_norm` | 298 | Normal/warning/critical health ranges |
| `std_lifestyle_plan` | 56 | Role-model lifestyle plans |
| `std_disease_risk_weight` | 44 | Disease risk contribution weights |

### LRT Database (17 tables, teammate's project)

| Table | Rows | Purpose |
|-------|------|---------|
| `users` | 0 | User profiles (BIGINT PK, MBTI, occupation) |
| `demographic_clusters` | 0 | Population segments for life prediction |
| `standard_lrt_header` | 0 | Standard LRT templates per cluster |
| `standard_lrt_events` | 0 | Expected life events (marriage, birth, retirement) |
| `standard_lrt_activities` | 0 | Expected behaviors per event (spending, needs) |
| `standard_lrt_products` | 0 | Product recommendations per activity |
| `personal_lrt_header` | 0 | Per-user personalized LRT |
| `personal_lrt_events` | 0 | Individual predicted life events |
| `personal_lrt_activities` | 0 | Individual behaviors with predicted/actual spend |
| `agents` | 0 | AI agents (User, Supplier, Holder, Producer) |
| `agent_sessions` | 0 | Agent conversation sessions |
| `agent_relationship_permissions` | 0 | 1st/2nd/3rd degree sharing permissions |
| `contracts` | 0 | Auto-negotiated purchase contracts |
| `orders` | 0 | Order execution with delivery |
| `history_record_table` | 0 | Blockchain-style audit trail |
| `multimodal_inputs` | 0 | Multimodal data with TTL |
| `lrt_simulations` | 0 | Monte Carlo/Particle Filter simulations |

---

## 3. Conflicts and Solutions

### Conflict 1: User ID Type (CRITICAL)

```
HRT: user_id UUID (e.g., "2b513e01-8f3a-4315-ac00-4cd0ac342bed")
LRT: user_id BIGINT (e.g., 12345)
```

**Solution: Use UUID**

Reason:
- UUID is globally unique — no collision when merging databases
- UUID is the Supabase standard (Supabase Auth uses UUID)
- UUID works across distributed systems (future scaling)
- BIGINT requires a central sequence — breaks in multi-node setup
- HRT already has 8 real users + 193 events with UUID — changing HRT is harder

**Action:** LRT changes `user_id` from BIGINT to UUID. LRT has 0 rows, so no data migration needed.

### Conflict 2: Gender Code

```
HRT: CHAR(1) with CHECK (M, F, O)     — "O" for Other
LRT: ENUM gender_code (M, F, X)       — "X" for Other
```

**Solution: Use CHAR(1) with (M, F, X)**

Reason:
- "X" is the international standard (ICAO passport standard for non-binary)
- "O" is ambiguous (could mean "Other" or "Omitted")
- CHAR(1) is more flexible than ENUM (easier to add values later)

**Action:** HRT changes "O" to "X" in gender CHECK constraint. Update any existing data with gender='O' to 'X'.

### Conflict 3: Multimodal Data (Two Different Tables)

```
HRT: user_multimodal                    LRT: multimodal_inputs
├── modal_type (voice/image/video)      ├── input_type (IMAGE/AUDIO/TEXT/SENSOR/BIO_SIGNAL)
├── embedding_vec vector(1536)          ├── feature_vector JSONB
├── emotion_state VARCHAR               ├── emotion_tags JSONB
├── storage_ref VARCHAR                 ├── raw_data_ref TEXT
├── context_place VARCHAR               ├── health_metrics JSONB
├── context_weather VARCHAR             ├── ttl_delete_at TIMESTAMPTZ
```

**Solution: Merge into one table, keep best features from both**

New unified `multimodal_inputs` table:
- Keep LRT's `input_type` ENUM (more types: includes SENSOR, BIO_SIGNAL)
- Keep HRT's `embedding_vec` vector (pgvector for semantic search)
- Keep LRT's `emotion_tags` JSONB (more flexible than VARCHAR)
- Keep LRT's `health_metrics` JSONB (connects health + multimodal)
- Keep LRT's `ttl_delete_at` (auto-deletion for privacy/HIPAA)
- Keep HRT's `context_place` and `context_weather` (add as columns)

### Conflict 4: Simulation (Two Different Engines)

```
HRT: simulation_result                  LRT: lrt_simulations
├── LSTM-Transformer                    ├── Monte Carlo / Particle Filter / Scenario Tree
├── Health trajectory prediction        ├── Life event prediction
├── scenario: current/twin/optimistic   ├── trigger: ANOMALY/PEER_UPDATE/GROUP_SHIFT
```

**Solution: Keep BOTH tables — they serve different purposes**

- `health_simulations` (renamed from simulation_result) — predicts health trajectory
- `lrt_simulations` — predicts life events and purchase timing

Both link to the same user. Health simulation results feed into LRT (health status affects life predictions). LRT events feed into health simulation (life stress affects health).

### Conflict 5: Agent System

```
HRT: agent_conversation_log            LRT: agents + agent_sessions + agent_relationship_permissions
(simple chat log)                       (full agent system with roles, sessions, permissions)
```

**Solution: Use LRT's agent system — it's more complete**

LRT's agent system already implements:
- Multi-role agents (User, Supplier, Holder, Producer)
- Session management
- 1st/2nd/3rd degree relationship permissions
- Security levels

HRT's `agent_conversation_log` becomes a child table of LRT's `agent_sessions`.

---

## 4. Unified Database Schema

### Architecture: ONE Supabase Project, THREE Domains

```
┌─────────────────────────────────────────────────────────────────┐
│                    UNIFIED DATABASE                              │
│                    (One Supabase Project)                        │
│                                                                  │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │ SHARED CORE (5)  │  │ HEALTH DOMAIN (8)│  │ LIFE DOMAIN(9)│  │
│  │                  │  │ (from HRT)       │  │ (from LRT)    │  │
│  │ users            │  │ user_biometric   │  │ std_lrt_header│  │
│  │ demographic_     │  │ user_diagnosis   │  │ std_lrt_events│  │
│  │   clusters       │  │ user_lifestyle   │  │ std_lrt_      │  │
│  │ multimodal_      │  │ user_health_level│  │   activities  │  │
│  │   inputs         │  │ health_          │  │ std_lrt_      │  │
│  │ agents           │  │   simulations    │  │   products    │  │
│  │ agent_sessions   │  │ std_population_  │  │ personal_lrt_ │  │
│  │                  │  │   category       │  │   header      │  │
│  │                  │  │ std_diagnosis_   │  │ personal_lrt_ │  │
│  │                  │  │   norm           │  │   events      │  │
│  │                  │  │ std_lifestyle_   │  │ personal_lrt_ │  │
│  │                  │  │   plan           │  │   activities  │  │
│  │                  │  │ std_disease_     │  │ contracts     │  │
│  │                  │  │   risk_weight    │  │ orders        │  │
│  └────────┬─────────┘  └────────┬─────────┘  └──────┬────────┘  │
│           │                     │                    │           │
│  ┌────────┴─────────────────────┴────────────────────┴────────┐  │
│  │                    CROSS-DOMAIN (4)                         │  │
│  │ user_activity_event — glasses events (food + life events)  │  │
│  │ agent_relationship_permissions — 1st/2nd/3rd degree        │  │
│  │ agent_conversation_log — all agent chats                   │  │
│  │ history_record_table — blockchain audit trail              │  │
│  └────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘

Total: 26 tables (was 14 HRT + 17 LRT = 31, reduced by merging overlaps)
```

### Table-by-Table Decisions

| # | Table | Source | Action | Notes |
|---|-------|--------|--------|-------|
| 1 | `users` | Both | **MERGE** | UUID PK, combine fields from both |
| 2 | `demographic_clusters` | LRT | **KEEP** | Better than HRT's std_population_category for user clustering |
| 3 | `std_population_category` | HRT | **KEEP** | Health-specific benchmarking (different from demographic_clusters) |
| 4 | `std_diagnosis_norm` | HRT | **KEEP** | Health norms — LRT doesn't have this |
| 5 | `std_lifestyle_plan` | HRT | **KEEP** | Health lifestyle plans |
| 6 | `std_disease_risk_weight` | HRT | **KEEP** | Disease risk weights |
| 7 | `user_demographic` | HRT | **REMOVE** | Merged into unified `users` table |
| 8 | `user_biometric` | HRT | **KEEP** | Health-specific, LRT doesn't have |
| 9 | `user_diagnosis` | HRT | **KEEP** | Health-specific |
| 10 | `user_lifestyle` | HRT | **KEEP** | Daily health lifestyle |
| 11 | `user_activity_event` | HRT | **EXTEND** | Add LRT event types (purchase, social, mobility) |
| 12 | `user_health_level` | HRT | **KEEP** | HCI/DRI scores |
| 13 | `multimodal_inputs` | Both | **MERGE** | Best features from both |
| 14 | `agents` | LRT | **KEEP** | Replace HRT's simple agent system |
| 15 | `agent_sessions` | LRT | **KEEP** | Session management |
| 16 | `agent_relationship_permissions` | LRT | **KEEP** | 1st/2nd/3rd degree permissions |
| 17 | `agent_conversation_log` | HRT | **KEEP** | Becomes child of agent_sessions |
| 18 | `health_simulations` | HRT | **RENAME** | Was simulation_result |
| 19 | `lrt_simulations` | LRT | **KEEP** | Life event simulations |
| 20 | `standard_lrt_header` | LRT | **KEEP** | Life event templates |
| 21 | `standard_lrt_events` | LRT | **KEEP** | Expected life events |
| 22 | `standard_lrt_activities` | LRT | **KEEP** | Expected behaviors |
| 23 | `standard_lrt_products` | LRT | **KEEP** | Product recommendations |
| 24 | `personal_lrt_header` | LRT | **KEEP** | Per-user LRT |
| 25 | `personal_lrt_events` | LRT | **KEEP** | Individual predicted events |
| 26 | `personal_lrt_activities` | LRT | **KEEP** | Individual behaviors |
| 27 | `contracts` | LRT | **KEEP** | Purchase contracts |
| 28 | `orders` | LRT | **KEEP** | Order execution |
| 29 | `history_record_table` | LRT | **KEEP** | Blockchain audit trail |

### Unified `users` Table

```sql
CREATE TABLE users (
    user_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_hash       VARCHAR(64) UNIQUE,                    -- from HRT (de-identification)
    auth_user_id    UUID REFERENCES auth.users(id),        -- from LRT (Supabase Auth link)
    cluster_id      BIGINT REFERENCES demographic_clusters, -- from LRT
    
    -- Demographics (merged from both)
    birth_year      SMALLINT CHECK (birth_year >= 1900 AND birth_year <= 2200),  -- from LRT (more precise than age_group)
    age_group       VARCHAR(20),                           -- from HRT (kept for backward compat)
    gender          CHAR(1) CHECK (gender IN ('M','F','X')), -- unified: X instead of O
    nationality     CHAR(3) DEFAULT 'KOR',                 -- from LRT (was country_code in HRT)
    
    -- Health-specific (from HRT)
    disability_yn   BOOLEAN DEFAULT false,
    income_decile   SMALLINT CHECK (income_decile >= 1 AND income_decile <= 10),
    
    -- Life-specific (from LRT)
    occupation_category TEXT,
    household_type  TEXT,
    income_bracket  TEXT,
    region          TEXT,
    mbti            CHAR(4),
    
    -- System
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now(),
    deleted_at      TIMESTAMPTZ                             -- from LRT (soft delete)
);
```

---

## 5. How It Works After Unification

### User Registration Flow

```
New user signs up
    │
    ├── Supabase Auth creates auth.users record
    │
    ├── Unified users table created with:
    │   ├── auth_user_id → links to Supabase Auth
    │   ├── Basic profile: birth_year, gender, nationality
    │   ├── cluster_id → matched to demographic_clusters
    │   └── Optional: MBTI, occupation, household_type
    │
    ├── HRT side: 
    │   ├── std_population_category matched → health benchmarks loaded
    │   ├── user_health_level initialized → HCI = 0 (no data yet)
    │   └── Ready to receive biometric/diagnosis/lifestyle data
    │
    └── LRT side:
        ├── personal_lrt_header created → linked to standard_lrt for their cluster
        ├── personal_lrt_events generated → predicted life events based on demographics
        └── Ready to receive purchase/activity/behavioral data
```

### AI Glasses Data Flow (Unified)

```
AI Glasses capture event
    │
    ├── FOOD DETECTED (confidence: 0.82)
    │   ├── Write to: user_activity_event (event_type='meal')          ← HRT
    │   ├── Update: user_lifestyle (daily calories, macros)            ← HRT
    │   ├── Cross-domain: LRT checks if food purchase is predicted     ← LRT
    │   └── Agent suggests: "You're eating high-sodium food.           ← BOTH
    │        Your blood pressure is trending up. Consider low-sodium 
    │        alternatives. I found a deal on low-sodium 김치 on Coupang."
    │
    ├── MEDICATION DETECTED (confidence: 0.95)
    │   ├── Write to: user_activity_event (event_type='medication')    ← HRT
    │   ├── Update: user_lifestyle (medication adherence)              ← HRT
    │   ├── Cross-domain: LRT auto-reorders when supply is low         ← LRT
    │   └── Contracts: Supplier agent negotiates best price            ← LRT
    │
    ├── STORE VISIT DETECTED (confidence: 0.75)
    │   ├── Write to: user_activity_event (event_type='purchase')      ← LRT
    │   ├── Update: personal_lrt_activities (actual_spend)             ← LRT
    │   ├── Cross-domain: HRT checks if purchased food is healthy      ← HRT
    │   └── Agent: "You bought ramen. Your cholesterol is elevated.    ← BOTH
    │        Healthier alternatives at this store: ..."
    │
    └── EXERCISE DETECTED (confidence: 0.88)
        ├── Write to: user_activity_event (event_type='exercise')      ← HRT
        ├── Update: user_lifestyle (exercise_min, exercise_kcal)       ← HRT
        ├── Cross-domain: LRT learns exercise patterns for predictions ← LRT
        └── LRT: "Based on your gym frequency, you may need new        ← LRT
             running shoes in 2 months. Pre-order?"
```

### Health Simulation ↔ Life Simulation (Connected)

```
HEALTH SIMULATION (LSTM-Transformer):
Input: user_diagnosis + user_lifestyle + user_biometric + glasses events
Output: BMI in 1 year = 26.5, Glucose in 1 year = 115 mg/dL
    │
    ├── Feeds INTO LRT: "User will likely need diabetes medication 
    │   within 2 years → pre-order blood glucose monitor"
    │
    └── LRT responds: "Recommended products added to pre-order queue"

LIFE SIMULATION (Monte Carlo):
Input: personal_lrt_events + demographic_clusters + life patterns
Output: Marriage probability in 1 year = 73%, Home purchase = 45%
    │
    ├── Feeds INTO HRT: "Major life event (marriage) predicted → 
    │   expect stress increase → adjust health simulation weights"
    │
    └── HRT responds: "Health simulation updated with stress factor,
         recommending stress management in lifestyle plan"
```

### Agent System (Unified)

```
AGENT HIERARCHY (from LRT, extended for health):

User AI Agent (Direct — manages everything for the user)
├── HealthCore Agent (2nd degree — health queries, HCI monitoring)
├── Nutrition Agent (2nd degree — food analysis, diet recommendations)
├── Exercise Agent (2nd degree — exercise prescription)
├── Medical Agent (2nd degree — FHIR integration, emergency)
├── Glasses Agent (Direct device — processes glasses events)
├── Family Agent (1st degree — family health + life sharing)
├── Community Agent (3rd degree — anonymized trends)
├── Supplier Agent (LRT — negotiates with suppliers)
├── Holder Agent (LRT — manages owned assets/subscriptions)
└── Producer Agent (LRT — interfaces with manufacturers)

All agents share:
- agent_relationship_permissions (who can see what)
- agent_sessions (conversation state)
- agent_conversation_log (full history)
- history_record_table (immutable audit trail)
```

---

## 6. Migration Plan

### Phase 1: Prepare (Week 1)

| Task | Who | Details |
|------|-----|---------|
| Agree on unified users schema | Both teams + boss | UUID PK, gender='X', merged fields |
| Choose which Supabase project to keep | Boss | Recommend: keep HRT project (has real data) |
| Backup both databases | Both | pg_dump both projects |

### Phase 2: Migrate LRT Tables (Week 2)

| Task | Details |
|------|---------|
| Create LRT tables in HRT project | Run migration SQL for all 13 LRT-only tables |
| Modify LRT tables to use UUID user_id | Change BIGINT → UUID in all LRT tables |
| Create unified users table | Drop old, create new with merged columns |
| Migrate HRT data | Re-insert 8 users, 5042 biometric, 193 events, 424 standards |
| Update HRT foreign keys | Point to new unified users table |

### Phase 3: Connect Domains (Week 3)

| Task | Details |
|------|---------|
| Extend user_activity_event | Add LRT event types to CHECK constraint |
| Create cross-domain views | Views that join health + life data for agents |
| Update FastAPI backend | New endpoints for LRT tables, update existing for unified users |
| Update Pydantic models | Add LRT models to backend/app/models/ |

### Phase 4: Verify (Week 4)

| Task | Details |
|------|---------|
| Test all existing HRT endpoints | Must work exactly as before |
| Test all LRT endpoints | Must work with UUID user_id |
| Test cross-domain queries | Health data informs LRT, LRT data informs health |
| RLS policies for all tables | Ensure per-user data isolation |
| Load test | Verify performance with unified schema |

---

## 7. Risk Management

| Risk | Impact | Mitigation |
|------|--------|------------|
| Data loss during migration | HIGH | Full backup before ANY changes |
| Existing HRT API breaks | HIGH | Run full test suite after migration |
| Performance degradation | MEDIUM | 26 tables in one DB is fine for Supabase; index strategy already defined |
| Team conflict on schema decisions | MEDIUM | Boss makes final call on conflicts |
| LRT teammate's code breaks | MEDIUM | LRT has 0 rows — no data to lose, only schema changes needed in code |

---

## 8. Summary

| Question | Answer |
|----------|--------|
| **Why unify?** | Same user, same glasses, same agents — two separate systems waste resources and miss cross-domain insights |
| **Where?** | One Supabase project (keep HRT project, add LRT tables) |
| **How many tables?** | 26 unified (down from 31 separate) |
| **What conflicts?** | user_id type, gender code, multimodal structure, agent system — all resolved |
| **Will HRT still work?** | Yes — all existing HRT tables, API endpoints, and data preserved |
| **Will LRT still work?** | Yes — LRT tables migrated with UUID user_id, all relationships preserved |
| **Timeline?** | 4 weeks for full migration and verification |
| **Who does what?** | You: HRT tables + backend. Teammate: LRT tables + code update. Together: unified users + testing |
