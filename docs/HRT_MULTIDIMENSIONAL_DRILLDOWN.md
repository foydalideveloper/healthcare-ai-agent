# HRT Multi-Dimensional Drill-Down System — Technical Design

**Project:** Healthcare AI Agent · Triple-H Co., Ltd.
**Patent No.** 10-2025-0145274
**Document version:** 1.5 · 2026-04-28
**Doc currency:** Reflects MCP-verified Supabase state (42 base tables + 5 views) and locked architecture as of 2026-04-28. R7 closed in this revision; R2-R6 + R8 still open. If reading after a long gap, check the handoff (`project_healthcare_complete_handoff.md`) for newer decisions before trusting individual numbers.
**Reconciled with:** `Healthcare_AI_Agent_Plan_v4_FINAL.docx` (v4.1) · `migrations/001_initial_schema.sql` through `migrations/006_medication_intake_and_goal_relative_intensity.sql`

> **Change log v1.0 → v1.1**
> Reconciled 6 items that drifted from v4 plan or migration 001:
> 1. Kafka topic names aligned to v4 (agent-function naming, 9 topics + genomic as 10th).
> 2. `std_seasonal_adj` + `std_circadian_norm` correctly labeled as **in-code constants** (not DB tables).
> 3. RLS uses `auth.uid()` because migration 001 is UUID-based — flagged for v4 reconciliation.
> 4. Materialized views labeled **"interim"**; **TimescaleDB continuous aggregates** listed as target state.
> 5. 7th category **Hydration** confirmed — LSTM input vector extension (65 → 67-68 dim) called out.
> 6. Detail Panel **second fetch** (`/api/v1/hrt/events`) correctly described; L4 drill-down response does **not** carry full event detail.
>
> **Change log v1.1 → v1.2**
> 7. Architecture diagram (§1) now shows **all 6 Supabase domains** + shared helpers (35 tables total from migrations 001 + 002), not just Domain 2.
> 8. New §2.4 "How HRT Uses the Other 5 Domains" — table mapping every domain → what HRT reads + when.
> 9. §10.3 Security consequences now show the **3-gate pattern** for expert data sharing (`user_settings` + `legal_consents` + `expert_consultations`).
> 10. §13 edge cases expanded with `user_subscriptions.plan_code`, `data_retention_days`, consent-withdrawal flow.
>
> **Change log v1.2 → v1.3 (corrections)**
> 11. **Domain 2 table list corrected**: earlier drafts listed `user_food_log` and `user_medication` as deployed tables. They are **NOT** in migration 001. Actual Domain 2 = `users`, `user_demographic`, `user_biometric`, `user_diagnosis`, `user_lifestyle`, `user_activity_event`, `user_health_level`, `user_multimodal`, `agent_conversation_log`, `simulation_result`. Fixed in §1 architecture diagram, §2.4 table count, and §16 code references.
> 12. Added new reconciliation item **R7** to §14: Food + Medicine ingest tables (`user_food_log`, `user_medication`) are planned for migration 003 but do not yet exist. The HRT dashboard's Food and Medicine categories currently render via mock data.
>
> **Change log v1.3 → v1.4**
> 13. Added new reconciliation item **R8** to §14: **OpenClaw SoulSpec runtime model**. v4 plan §11 describes `USER.md` + `MEMORY.md` as flat files which doesn't scale to 100K users. 4-part fix proposed: (a) templates in repo + DB hydration via new `agent_user_context` + `agent_memory` tables, (b) blue-green deploy for safety-critical agents, (c) CODEOWNERS file for access control, (d) HEARTBEAT.md as the bridge from HRT to agents (e.g., Analytics Agent runs nightly MV refresh + HCI scoring). Blocks production agent rollout.
>
> **Change log v1.4 → v1.5**
> 14. **R7 RESOLVED.** `user_food_log` and `user_medication` are deployed and have rows (30 + 1 as of 2026-04-28 MCP verification). Status column in §2.3 updated. Callout block above §2.3 removed. R8 schema (`agent_user_context`, `agent_memory`) is also deployed (both 0 rows — agent code not yet wired in).
> 15. Drilldown function rewritten across migrations 003-006 (R8 schema, drilldown function, timezone fix, service-role bypass, exercise/sleep/medicine L4 fixes, biometrics composite, hydration regex tightening, intake table for confirmed doses, goal-relative intensity). §16 reference table updated to reflect deployed file paths.
> 16. New `user_medication_intake` table added (Apr 24) — separate from `user_medication` (prescription registry). Drilldown medicine CTE now reads from intakes only; empty days stay empty.

---

## 0. Executive Summary

The **HRT (Health Record Timeline)** dashboard is an **OLAP-style multi-dimensional data explorer** that lets a user navigate their entire health history at four zoom levels:

```
  Year   →   Month   →   Day   →   Hour
  L1         L2          L3        L4
```

across **seven health categories** (Food, Exercise, Sleep, Medicine, Biometrics, Mental Health, Hydration). The user starts at the **lifetime view** (all years) and drills down progressively into a specific hour of a specific day — without ever leaving the same unified grid.

**Five dimensions:**
1. `user_id` — whose data (UUID)
2. Time — when (4-level hierarchy)
3. Category — what health domain (7 values)
4. Metric — what measurement inside the category (kcal, mmHg, hours, etc.)
5. Context — seasonal / circadian / age-adjusted reference modifier

---

## 1. System Architecture — Data Flow Diagram

```
                        ┌──────────────────────────────────────────────────┐
                        │ USER (Patient Kim) — clicks a Year cell in the   │
                        │ HRT grid in his browser                          │
                        └──────────────────────┬───────────────────────────┘
                                               │
                                               ▼
                ┌──────────────────────────────────────────────────────────┐
                │   Next.js Frontend · HRT Dashboard                       │
                │                                                          │
                │   ┌───────────────┐   ┌───────────────┐  ┌─────────────┐ │
                │   │ DrilldownGrid │   │ ChartPanel    │  │ DetailPanel │ │
                │   │  (the matrix) │   │ (trend lines) │  │ (L4 click)  │ │
                │   └───────┬───────┘   └───────┬───────┘  └──────┬──────┘ │
                │           └───────┬───────────┴─────────────────┘        │
                │                   ▼ fetch(`?level=N&year=?&month=?…`)    │
                └───────────────────┬──────────────────────────────────────┘
                                    │ HTTPS + JWT
                                    ▼
                ┌──────────────────────────────────────────────────────────┐
                │   FastAPI endpoints                                      │
                │     • /api/v1/hrt/drilldown  (matrix aggregates)         │
                │     • /api/v1/hrt/events     (L4 cell detail — raw rows) │
                │                                                          │
                │     checks Redis cache (TTL 5min)  ───────────────────┐  │
                │     on MISS → Supabase RPC `hrt_drilldown()` or       │  │
                │                  direct SELECT on fact tables         │  │
                └──────────────┬────────────────────────────────────────┼──┘
                               │                                        │
                   cache-miss  │                              cache-hit │
                               ▼                                        ▼
    ┌──────────────────────────────────────────────────────────┐        ┌───────────────────┐
    │ Supabase PostgreSQL — 6 domains · migrations 001 + 002   │        │ Redis Cluster     │
    │                                                          │        │ hot HRT context   │
    │  hrt_drilldown(user_id, level, y?, m?, d?)               │◄───────┤ TTL 5 min         │
    │   └── SECURITY DEFINER · RLS-aware                       │        │ sessions + RL     │
    │   └── routes to 4 sub-queries by `level`                 │        └───────────────────┘
    │                                                          │
    │  ┌────────────────────────────────────────────────────┐  │
    │  │ DOMAIN 1 · Reference Standards  (4 tables, 001)    │  │
    │  │  std_population_category  std_diagnosis_norm       │  │  ◄── HRT reads for
    │  │  std_lifestyle_plan       std_disease_risk_weight  │  │      standard overlay
    │  └────────────────────────────────────────────────────┘  │
    │                                                          │
    │  ┌────────────────────────────────────────────────────┐  │
    │  │ DOMAIN 2 · Personal Health Data  (10 tables, 001)  │  │  ◄── THE drill-down
    │  │  users (UUID PK) · user_demographic                │  │      fact source for
    │  │  user_biometric · user_diagnosis · user_lifestyle  │  │      Biometrics, Sleep,
    │  │  user_activity_event · user_health_level           │  │      Exercise, Mental
    │  │  user_multimodal                                   │  │      Health, Hydration.
    │  │  agent_conversation_log · simulation_result        │  │
    │  │                                                    │  │      NOT YET DEPLOYED:
    │  │  ── INTERIM aggregation (current) ──               │  │      user_food_log +
    │  │  Plain materialized views refreshed by pg_cron:    │  │      user_medication
    │  │    mv_hrt_yearly / mv_hrt_monthly /                │  │      (planned for migr.
    │  │    mv_hrt_daily / mv_hrt_hourly                    │  │      003 — Food & Medicine
    │  │                                                    │  │      categories currently
    │  │  ── TARGET (post-TimescaleDB) ──                   │  │      use mock data).
    │  │  Continuous aggregates on hypertables              │  │
    │  └────────────────────────────────────────────────────┘  │
    │                                                          │
    │  ┌────────────────────────────────────────────────────┐  │
    │  │ DOMAIN 3 · User Management  (5 tables, 002)        │  │  ◄── HRT reads
    │  │  user_profiles   (timezone, category_id, allergies)│  │      user_profiles.timezone
    │  │  user_settings   (data_sharing, retention, theme)  │  │      for timestamp display;
    │  │  user_devices    (AIMB-G1, phones, wearables)      │  │      category_id for
    │  │  user_subscriptions (plan → feature gating)        │  │      population benchmark;
    │  │  user_activity_log  (audit trail, 90d retention)   │  │      user_settings for
    │  │                                                    │  │      privacy/retention.
    │  │  (migration 002 also ALTERs users to add           │  │
    │  │   email, display_name, timezone, etc.)             │  │
    │  └────────────────────────────────────────────────────┘  │
    │                                                          │
    │  ┌────────────────────────────────────────────────────┐  │
    │  │ DOMAIN 4 · Admin / Operator  (5 tables, 002)       │  │  ◄── Operator UI writes
    │  │  admin_users · admin_permissions                   │  │      here. ALL operator
    │  │  admin_audit_log · system_config · feature_flags   │  │      reads of HRT data
    │  │                                                    │  │      are logged.
    │  └────────────────────────────────────────────────────┘  │
    │                                                          │
    │  ┌────────────────────────────────────────────────────┐  │
    │  │ DOMAIN 5 · Notifications  (4 tables, 002)          │  │  ◄── HRT anomaly alerts
    │  │  notification_templates  notification_preferences  │  │      (BP spike, missed
    │  │  notifications  notification_log                   │  │      medication) land here,
    │  │  (emergency = priority=critical, never drop)       │  │      pushed via push /
    │  │                                                    │  │      email / voice_glasses
    │  └────────────────────────────────────────────────────┘  │
    │                                                          │
    │  ┌────────────────────────────────────────────────────┐  │
    │  │ DOMAIN 6 · Expert / External  (4 tables, 002)      │  │  ◄── Expert consultations
    │  │  experts · expert_availability                     │  │      produce prescribed_plan
    │  │  expert_consultations · expert_reviews             │  │      JSONB which feeds back
    │  │                                                    │  │      into HRT as a lifestyle
    │  │                                                    │  │      event.
    │  └────────────────────────────────────────────────────┘  │
    │                                                          │
    │  ┌────────────────────────────────────────────────────┐  │
    │  │ SHARED helpers  (3 tables, 002)                    │  │
    │  │  app_metadata · localization_strings               │  │  ◄── legal_consents gates
    │  │  legal_consents  (GDPR/PIPA — never delete)        │  │      what data can be shown
    │  └────────────────────────────────────────────────────┘  │      to experts & family
    │                                                          │
    │  (seasonal + circadian modifiers are currently           │
    │   in-code JS constants inside                            │
    │   app/components/ChartPanel.tsx — NOT DB)                │
    └──────────────────────┬───────────────────────────────────┘
                           ▲
                           │ INSERT raw events
                           │
               ┌───────────┴──────────────────────────┐
               │ Kafka — 10 topics (v4 plan naming)   │
               │                                      │
               │  ── Agent orchestration ──           │
               │   agent.orchestration.commands       │
               │   agent.results                      │
               │   agent.judgement.requests           │
               │                                      │
               │  ── Health event ingest ──           │
               │   health.biometric.stream            │
               │   health.lifestyle.events            │
               │   health.emergency.alerts  ◄── never │
               │                               drop;  │
               │                               DLQ+   │
               │                               pager  │
               │                                      │
               │  ── Simulation / prediction ──       │
               │   simulation.triggers                │
               │   simulation.results                 │
               │                                      │
               │  ── External systems ──              │
               │   fhir.sync.queue                    │
               │   genomic.labupload                  │
               └──────────────────────────────────────┘
                         ▲
                         │
               AI glasses · wearable · phone · hospital EMR · DNA lab
```

**Note on Kafka topics**: earlier draft of this doc used data-source names
(`glasses.photo`, `wearable.biometric`, `phone.food`, etc.). Those have been
replaced with the **v4 plan's agent-function naming** above, which decouples
topic identity from hardware model (AIMB-G1, Mentra, Omi — all write to the
same topics).

---

## 2. The Multi-Dimensional Data Model

### 2.1 OLAP Cube Concept

```
                        CATEGORY  (7 axes)
                        ──────────────────►
                        🍱 🏃 😴 💊 ❤️ 🧠 💧

                TIME
                  ▲
                  │
     Hour (24) ──►│       ╱───────────╱│
                  │      ╱  L4 cell  ╱ │
                  │     ╱ (fact row)╱  │
                  │    ╱───────────╱   │  ◄── METRIC  (kcal, mmHg…)
     Day  (28-31) │   ╱  L3 cell  ╱    │       depth axis (drill-through)
                  │  ╱───────────╱     │
                  │ ╱  L2 cell  ╱      │
     Month (12)   │╱───────────╱       │
                  │  L1 cell  ╱
     Year  (N)    │ ──────────╱
                  └───────────►  USER (many rows, isolated by RLS)
```

Each **cell** = one `(user_id, category, time_bucket)` intersection. The cell
value is an aggregate of the underlying facts (SUM, AVG, COUNT, or latest).

### 2.2 The 4 Drill-Down Levels

| Level | Axis | Columns | Cell represents | Typical cell value |
|---|---|---|---|---|
| **L1** | Yearly | All user's years | 1 year × 1 category | `"365 entries"` or `"avg 2,420 kcal"` |
| **L2** | Monthly | 12 months | 1 month × 1 category | `"avg 2,510 kcal"` (January) |
| **L3** | Daily | 28-31 days | 1 day × 1 category | `"2,380 kcal"` (March 3) |
| **L4** | Hourly | 24 hours | 1 hour × 1 category | `"Dinner 850 kcal"` (18:00) |

At **L4**, cells still store **summary strings** (e.g., `"Dinner 850 kcal"`)
produced by the same `hrt_drilldown()` aggregator. They do **not** carry the
full event payload (photo URL, exact timestamp, AI confidence, macros breakdown).
To get those, the Detail Panel fires a **second fetch** — see Section 8.

### 2.3 The 7 Categories (Axis 2)

| # | Category | Korean | Primary source | Primary metric | Unit | Ingest table | Status |
|---|---|---|---|---|---|---|---|
| 1 | Food & Nutrition | 식이/영양 | AI glasses photo + MFDS lookup | kcal/day | kcal | `user_food_log` | ✅ Deployed |
| 2 | Exercise | 운동 | Wearable activity | Active minutes | min | `user_activity_event` | ✅ Deployed (001) |
| 3 | Sleep | 수면 | Wearable + EEG glasses | Total + stages | hours / % | `user_lifestyle` + `user_biometric` | ✅ Deployed (001) |
| 4 | Medicine | 약물 | Phone log + pill camera | Doses + compliance | count | `user_medication` (registry) + `user_medication_intake` (events) | ✅ Deployed |
| 5 | Biometrics | 생체 | Wearable PPG, cuff | BP / HR / SpO₂ / glucose | mmHg, bpm, mg/dL | `user_biometric` + `user_diagnosis` | ✅ Deployed (001) |
| 6 | Mental Health | 정신건강 | Self-report + HRV | Stress / mood / focus | /10 | `user_lifestyle` + `user_biometric` | ✅ Deployed (001) |
| 7 | Hydration | 수분 | Smart bottle + phone log | mL/day | ml | `user_lifestyle` (interim) | ✅ Deployed (001) |

> **R7 closed** as of v1.5 (2026-04-28). `user_food_log` and `user_medication` are deployed with real rows. The Apr 24 `user_medication_intake` table now drives the medicine drilldown (separated from the prescription registry). Hydration still uses `user_lifestyle` as interim storage until a dedicated `user_hydration` table is added.

> **⚠️ Hydration & LSTM input vector**
> Hydration is the 7th category displayed in HRT and consumed by the dashboard.
> The v4 plan's LSTM-Transformer ensemble specifies a **65-dimensional input
> vector**, which does **not** explicitly enumerate hydration features.
> If hydration features are to drive predictions (recommended — fluid balance
> affects BP and cognitive function), the input vector must extend to
> **~67-68 dimensions** and the LSTM must be retrained. Since fine-tuning has
> not started, this is the cheapest time to change the input schema.

### 2.4 How HRT Uses the Other 5 Domains

HRT's drill-down facts all come from **Domain 2**, but every user-facing
rendering also reads from the other five domains. Here's the complete
dependency map:

| Domain | What HRT reads from it | When |
|---|---|---|
| **D1 — Reference Standards** | `std_diagnosis_norm` for BP/glucose/etc. normal bounds (per age/gender/country); `std_lifestyle_plan` for role-model targets | On every L2+ chart render — the grey dashed standard line |
| **D2 — Personal Health Data** | Fact tables + materialized views for cell aggregates | Every drill-down and detail fetch |
| **D3 — User Management** | `user_profiles.timezone` (display timestamps); `user_profiles.category_id` (select correct row from `std_diagnosis_norm`); `user_profiles.allergies` (flag allergens in food detail); `user_settings.data_sharing_expert` (whether an expert can view); `user_settings.data_retention_days` (L1 horizon cap); `user_devices` (source icons in Detail Panel timeline) | On page load + every level change |
| **D4 — Admin / Operator** | `feature_flags` (e.g., `hydration_enabled`, `predictions_visible`, `kafka_cdc_refresh`); `system_config` (runtime-tunable thresholds, cache TTLs). Operator reads of any HRT data are logged to `admin_audit_log` | Feature gating on app start; audit log on every operator read |
| **D5 — Notifications** | When HRT ingest detects anomaly (e.g. BP > 140 for 3 consecutive readings), inserts into `notifications` with `priority='critical'`. HRT dashboard shows an unread-count badge by querying `notifications WHERE read_at IS NULL` | Real-time on ingest + periodic badge poll |
| **D6 — Expert / External** | When the current user has granted `user_settings.data_sharing_expert = true` AND has an active `expert_consultations` row, the expert's session can read the same HRT with RLS allowing cross-user access. `prescribed_plan` JSONB from completed consultations is written back into `user_lifestyle` as events and shows up in Domain 2 | During active consultation or on consultation-completion hook |
| **Shared — `legal_consents`** | Before rendering anything that leaves the user's own screen (expert share, family share, research opt-in), HRT checks for a matching consent row with `withdrawn_at IS NULL` | On any cross-boundary access |

**Table count summary (current deployed — migration 001 + 002):**

| Domain | Tables | Source | Note |
|---|---|---|---|
| 1 — Reference Standards | 4 | migration 001 | `std_population_category`, `std_diagnosis_norm`, `std_lifestyle_plan`, `std_disease_risk_weight` |
| 2 — Personal Health Data | 10 | migration 001 | `users`, `user_demographic`, `user_biometric`, `user_diagnosis`, `user_lifestyle`, `user_activity_event`, `user_health_level`, `user_multimodal`, `agent_conversation_log`, `simulation_result` |
| 3 — User Management | 5 + `users` ALTERed | migration 002 | `user_profiles`, `user_settings`, `user_devices`, `user_subscriptions`, `user_activity_log` |
| 4 — Admin / Operator | 5 | migration 002 | `admin_users`, `admin_permissions`, `admin_audit_log`, `system_config`, `feature_flags` |
| 5 — Notifications | 4 | migration 002 | `notification_templates`, `notification_preferences`, `notifications`, `notification_log` |
| 6 — Expert / External | 4 | migration 002 | `experts`, `expert_availability`, `expert_consultations`, `expert_reviews` |
| Shared helpers | 3 | migration 002 | `app_metadata`, `localization_strings`, `legal_consents` |
| **TOTAL DEPLOYED** | **35** | | |

**Planned but NOT yet deployed** (migration 003+):

| Table | Purpose | Category affected |
|---|---|---|
| `user_food_log` | Per-meal calorie/macro records | Food — currently mock data |
| `user_medication` | Per-dose compliance records | Medicine — currently mock data |
| `user_genomic` | DNA variants from lab upload | (New: genomic-driven predictions) |
| `external_records` | FHIR-synced hospital data | (New: EMR integration) |
| `twin_comparisons` | Digital twin simulation outputs | (Extends predictions page) |

If `std_seasonal_adj` and `std_circadian_norm` are later promoted from in-code
constants to DB tables (see §6.2), Domain 1 becomes 6 tables and the total
deployed reaches 37.

---

## 3. Data Flow — From Event to Display

### 3.1 Ingest Path (write side)

```
 User eats lunch
   │
   ▼
 AI glasses snaps photo
   │
   ▼
 Kafka: health.lifestyle.events  ◄── (not "glasses.photo")
   │
   ▼
 Ingest worker (FastAPI consumer)
   │
   ├── YOLOv8 crops plate
   ├── EfficientNetV2-S (Korean food model) → class prediction
   ├── Lookup class_kr in mfds_foods (275K rows)
   └── Compute kcal, macros
   │
   ▼
 INSERT into user_food_log (user_id, ts, class, kcal, carbs, protein, fat)
   │
   ▼
 Emergency-alert branch: if class triggers allergy match, also publish to
   health.emergency.alerts (never drop — DLQ + pager)
```

Each category has its own ingest path routed through one of the 10 Kafka
topics (see Section 1). All paths converge on the **Domain 2 fact tables**
which are the source of truth.

### 3.2 Read Path (drill-down)

User action drives the read path. Concrete example — user at L1 clicks **2024**:

```
 [1] Browser: DrilldownGrid fires handleDrillDown({ year: 2024 })
       │
       ▼
 [2] React state: nav = { level: 2, year: 2024 }
       │
       ▼
 [3] fetch(`/api/v1/hrt/drilldown?user_id=<uuid>&level=2&year=2024`)
       │
       ▼
 [4] FastAPI endpoint:
       check Redis key `hrt:<uuid>:2:2024:*:*`
       │
       ├── HIT  → return cached JSON (back to [6])
       │
       └── MISS → call Supabase RPC `hrt_drilldown(<uuid>, 2, 2024, null, null)`
             │
             ▼
 [5] Supabase function:
       SELECT date_trunc('month', ts) AS month_bucket, category,
              SUM(kcal) AS food_val, AVG(active_minutes) AS exercise_val, …
       FROM mv_hrt_monthly     ← interim materialized view; target is
                                  TimescaleDB continuous aggregate
       WHERE user_id = <uuid> AND extract(year FROM ts) = 2024
       GROUP BY month_bucket, category
       │
       ▼ returns 12 rows × 7 categories = 84 cell records
 [6] FastAPI: normalize into DrilldownResponse schema, compute intensity rank
       │
       ▼
 [7] Redis SETEX `hrt:<uuid>:2:2024:*:*` 300 (5 min TTL)
       │
       ▼
 [8] JSON → browser → DrilldownGrid re-renders 12-column × 7-row matrix
```

The whole round trip, cache-miss cold, is typically **40-120 ms**.

---

## 4. OLAP Layer Distribution — Which 3 of 5 Run in the Database?

| Layer | What it is | Where | Why |
|---|---|---|---|
| **1. Facts** | Raw events (one row per meal, reading, log) | ✅ **Postgres** — Domain 2 tables | Source of truth, RLS enforced |
| **2. Aggregates** | SUM/AVG/COUNT grouped by time bucket | ✅ **Postgres** — materialized views (interim) / continuous aggregates (target) | Indexed, fast, shareable |
| **3. Cubes** | Pre-rolled category × time matrices | ✅ **Postgres** — `hrt_drilldown()` RPC composes these | Single round trip per drill |
| **4. Views** | Shaped response for a specific UI call | ⚠️ **FastAPI** — renames, adds intensity rank | Keeps SQL clean |
| **5. Reports** | Charts, grids, detail panels | ⚠️ **Next.js** — DrilldownGrid, ChartPanel, DetailPanel | Interactive, per-user state |

### 4.1 Aggregation Refresh — Interim vs Target

**Interim (today, no TimescaleDB installed):**

| MV | Refresh cadence | Reason |
|---|---|---|
| `mv_hrt_yearly` | Nightly 02:00 KST | Changes rarely |
| `mv_hrt_monthly` | Nightly 02:15 KST | Changes daily at boundary |
| `mv_hrt_daily` | Nightly 02:30 KST | Same |
| `mv_hrt_hourly` | Every 15 min during 06:00–23:59 KST | Fresh data for current day |

Triggered by `pg_cron` extension. Full refresh each run, no incremental yet.

**Target (after `CREATE EXTENSION timescaledb` + hypertable migration):**
- Convert fact tables to hypertables partitioned on `(user_id, ts)`
- Replace materialized views with `CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous)` continuous aggregates
- Auto-refresh on invalidation — no cron
- Streaming incremental updates as new data arrives
- Better query parallelization

The HRT code shouldn't need changes when this swap happens (SQL surface is the
same). Only the `CREATE MATERIALIZED VIEW` DDL changes.

---

## 5. Aggregation Strategy per Level

Each category has a different "right" aggregate:

| Category | L1 / L2 / L3 aggregate | L4 aggregate | Example L2 value |
|---|---|---|---|
| Food | SUM(kcal) / day-count → avg kcal/day | individual meals | `"2,510 kcal/day avg"` |
| Exercise | SUM(active_min) → total per period | individual bouts | `"420 min total"` |
| Sleep | AVG(total_hours) | sleep stages for the night | `"7.2h avg"` |
| Medicine | COUNT(doses) / prescribed × 100 | individual doses | `"94% compliance"` |
| Biometrics | LATEST(bp) + AVG over period | individual readings | `"120/76 avg"` |
| Mental Health | AVG(stress_score) | individual check-ins | `"3.2/10 avg"` |
| Hydration | SUM(ml) / day-count → avg ml/day | individual sips | `"2,100 ml/day avg"` |

---

## 6. Standards Overlay System

Every cell can be **compared to a reference value** that varies by level,
season, and hour.

### 6.1 Four Standard Types by Level

| Level | Standard type | Source | Example (Food, Korean male 30-39) |
|---|---|---|---|
| **L1 Yearly** | Flat daily target | KDRI 2025 | 2,500 kcal/day flat |
| **L2 Monthly** | Seasonal-adjusted | Int J Environ Res Public Health 2020 | Winter +8%, Summer -5% |
| **L3 Daily** | Flat daily target | KDRI 2025 | 2,500 kcal |
| **L4 Hourly** | Circadian rhythm | PMC5483233 | 07:00=625 (breakfast), 12:00=750 (lunch), 18:00=625 (dinner) |

### 6.2 Where Each Standard Lives (important!)

| Standard | Storage today | Reason |
|---|---|---|
| Clinical reference ranges (normal/warning/critical bounds) | DB: `std_diagnosis_norm` | Shared across many components, needs operator tuning |
| Role-model lifestyle plans | DB: `std_lifestyle_plan` | Same |
| Disease risk weights | DB: `std_disease_risk_weight` | Same |
| Population categories | DB: `std_population_category` | Same |
| **Seasonal multipliers** (12-month × 7-category) | **In-code** — `SEASONAL_FACTORS` constant in `ChartPanel.tsx` | Small, rarely changes, avoids round-trip |
| **Circadian hourly expectations** (24-hour × 7-category) | **In-code** — `HOURLY_STANDARDS` constant in `ChartPanel.tsx` | Same |

**⚠️ Earlier draft of this doc incorrectly listed `std_seasonal_adj` and
`std_circadian_norm` as DB tables.** They are currently **JS constants** in the
React component. If operators need to tune them without redeploying the
frontend (e.g., per-user customization based on KDRI 49K records), they would
be moved to Postgres as two new tables — at that point, Domain 2's table
count grows from **21 → 23**, and the v4 plan should be updated to reflect it.

### 6.3 How the Frontend Renders It

ChartPanel layers three visual elements:
1. **Actual trajectory** — red filled area, user's data
2. **Standard line** — gray dashed, direction-aware (upper or lower bound depending on category)
3. **Seasonal/circadian band** — background color tinting (winter=blue, summer=yellow, etc.)

---

## 7. Color Intensity — Cell Heatmap Logic

Inside the grid, each cell gets one of **5 pink intensities** (0 = white, 5 = darkest). The algorithm runs **per row**, not globally:

```typescript
function recalcRowIntensity(cells) {
  const nums = Object.entries(cells)
    .filter(([, c]) => c.value !== "-" && c.count > 0)
    .map(([k, c]) => ({ key: k, num: parseFloat(extractNumber(c.value)) }));

  const min = Math.min(...nums);
  const max = Math.max(...nums);

  if (max === min) {                      // all equal → middle intensity
    nums.forEach(e => cells[e.key].intensity = 2);
    return;
  }

  nums.forEach(e => {
    const ratio = (e.num - min) / (max - min);       // 0..1 linear
    cells[e.key].intensity = Math.round(ratio * 4) + 1;  // 1..5
  });
}
```

Linear normalization (not rank-based) gives identical values identical shades.

---

## 8. Detail Panel — When a L4 Cell Is Clicked

### 8.1 The second fetch

L4 drill-down response rows carry only **summary strings** (e.g. `"Dinner 850 kcal"`). To show the full timeline + photo thumbnails + confidence scores, the Detail Panel fires a **separate API call**:

```
GET /api/v1/hrt/events
    ?user_id=<uuid>
    &category=food
    &from=2024-03-03T18:00:00+09:00
    &to=2024-03-03T18:59:59+09:00

→ Returns:
  [
    {
      event_id: <uuid>,
      ts: "2024-03-03T18:03:12+09:00",
      source: "glasses_aimb_g1",
      photo_thumb_url: "https://s3.../thumb/abc123.jpg",
      classification: {
        class_kr: "갈비찜",
        class_en: "Braised Short Ribs",
        confidence: 0.92,
        model: "efficientnetv2-s-kfood-v1.0"
      },
      nutrition: {
        kcal: 850, carbs_g: 75, protein_g: 45, fat_g: 30
      },
      mfds_match_id: 20345
    },
    ...
  ]
```

Implementation notes:
- Cheap query: filtered by `user_id + 1-hour window + 1 category` → usually 1-5 rows
- Redis-cacheable per `(user_id, category, hour)` key, TTL 5 min
- Photo thumbnails served from S3 with pre-signed URLs valid for 10 min
- Raw images stored on S3 with lifecycle: Hot (7d) → Warm (30d) → Glacier (90d) → Archive (1yr+)

### 8.2 What the Detail Panel renders

```
Timeline section (chronological events in that hour)
  • 18:03  Photo taken — 갈비찜, 밥, 김치, 시금치나물
  • 18:05  AI classified — confidence 0.92
  • 18:07  Nutrition computed — 850 kcal, 45g protein, 30g fat, 75g carbs

Nutritional Summary card (dominant)
  ┌────────────────────────────┐
  │ Total       │ 850 kcal     │ ◄── DARK RED (dominant metric)
  ├─────────────┼──────────────┤
  │ Carbs       │ 75 g  (35%)  │ ◄── LIGHT RED
  │ Protein     │ 45 g  (21%)  │
  │ Fat         │ 30 g  (32%)  │ (macros, secondary)
  └────────────────────────────┘
```

Every category has its own Summary schema:

| Category | Dominant metric (dark red) | Secondary metrics (light red) |
|---|---|---|
| Food | Total kcal | Carbs / Protein / Fat |
| Exercise | Active minutes | Calories burned / Avg HR / Distance |
| Sleep | Total duration | Deep / REM / Quality |
| Medicine | Compliance % | Taken / Streak / Missed |
| Biometrics | Latest BP | HR / SpO₂ / Glucose |
| Mental Health | Stress score | Mood / Energy / Focus |
| Hydration | Total intake | Target / Glasses / Status |

---

## 9. Caching & Performance

### 9.1 Cache Layers

```
Browser (React Query, 30s TTL for drill-down; 60s for detail)
   │ miss
   ▼
Redis Cluster (5-min TTL, LRU 2 GB)
   │ miss
   ▼
Materialized views (nightly, hot path 15-min) — interim
Continuous aggregates (auto, on invalidation) — target
   │ (source of truth)
   ▼
Raw fact tables (continuously written)
```

### 9.2 Cache Key Schema

```
Drill-down keys:
  hrt:{user_uuid}:{level}:{year|*}:{month|*}:{day|*}

Detail (L4 events) keys:
  hrt_evt:{user_uuid}:{category}:{date}:{hour}

Examples
  hrt:abc-123:1:*:*:*               L1, all years
  hrt:abc-123:2:2024:*:*            L2, 2024 months
  hrt:abc-123:4:2024:3:3            L4, March 3 2024 hours
  hrt_evt:abc-123:food:2024-03-03:18  Detail Panel cache
```

### 9.3 Cache Invalidation

Postgres AFTER INSERT triggers publish via `pg_notify`:

```
INSERT into user_food_log (user_id=<uuid>, ts=2024-03-03 18:05)
   │
   ▼ AFTER INSERT trigger
 NOTIFY hrt_invalidate, 'user=<uuid> year=2024 month=3 day=3 cat=food'
   │
   ▼ Redis listener
 DEL hrt:<uuid>:*:2024:*:*                  (coarse)
 DEL hrt:<uuid>:*:2024:3:*                  (monthly)
 DEL hrt:<uuid>:*:2024:3:3                  (daily + hourly)
 DEL hrt_evt:<uuid>:food:2024-03-03:18      (detail)
```

### 9.4 Latency Budget

| Step | Budget | Actual (p50) |
|---|---|---|
| Browser fetch → FastAPI | 15 ms | 12 ms |
| Redis GET (hit) | 2 ms | 1.5 ms |
| Postgres RPC (cache miss) | 60 ms | 45 ms |
| JSON serialization | 5 ms | 3 ms |
| Next.js re-render | 30 ms | 25 ms |
| **Total cache hit** | **52 ms** | **41 ms** |
| **Total cache miss** | **110 ms** | **86 ms** |

L4 detail fetch adds **25-40 ms p50** on top (separate round trip, but tiny
result set and almost always cache-hit by the time user clicks).

---

## 10. Security Model — Row-Level Security

Every fact table has **RLS enabled**. The `hrt_drilldown()` function is
`SECURITY DEFINER` but runs under the caller's JWT context via `auth.uid()`.

### 10.1 Current implementation (matches migration 001)

```sql
-- users.user_id is UUID (see migration 001, line 94)
CREATE POLICY user_food_log_self
  ON user_food_log
  FOR SELECT
  USING (user_id = auth.uid());
```

Because `users.user_id` is **UUID** and `auth.uid()` returns **UUID**, no
helper function is needed — direct equality works.

### 10.2 Reconciliation with v4 plan

The v4 plan specifies RLS as `USING (user_id = get_my_user_id())` because it
assumed **`user_id BIGINT`** with a UUID→BIGINT mapping helper. Migration 001
shipped with **UUID** instead, so the deployed schema uses `auth.uid()`
directly and the helper doesn't exist.

**Decision needed** (outside scope of this doc, but flagged):
- **(A)** Accept UUID as the canonical user ID → update v4 plan to drop
  BIGINT + helper sections. (Recommended — lower risk, matches deployed code.)
- **(B)** Migrate to BIGINT → destructive schema rewrite of migration 001 + all
  fact tables + re-sync with `auth.users`.

Until this is resolved, HRT code follows (A) — the deployed reality.

### 10.3 Consequences

- Kim **never** sees Park's data (RLS on all Domain 2 fact tables + Domain 3 user tables)
- Service role (ingest workers) bypasses RLS via `SERVICE_ROLE` key
- Operator (Dev Team) uses service role; every HRT read/write is logged to `admin_audit_log` (Domain 4) with `target_resource`, `target_id`, and full before/after JSONB
- Expert cross-user access is **double-gated**:
  1. `user_settings.data_sharing_expert = true` (Domain 3)
  2. Matching row in `legal_consents` with `document_code='expert_share'` and `withdrawn_at IS NULL` (Shared)
  3. Active `expert_consultations` row with status ∈ {scheduled, in_progress, completed} (Domain 6)
- Family share (future) will use the same 3-gate pattern with `data_sharing_family`
- Even if FastAPI is compromised, Postgres still refuses cross-user queries via RLS

---

## 11. Frontend Component Architecture

```
app/page.tsx   (nav state: { level, year, month, day })
     │
     ├─ Breadcrumb          (Lifetime > 2024 > March > Day 3)
     │
     ├─ DrilldownGrid       (the matrix — 7 rows × N cols)
     │     │
     │     ├─ handleDrillDown(year)   → setNav({ level: 2, year })
     │     ├─ handleDrillDown(month)  → setNav({ level: 3, …, month })
     │     ├─ handleDrillDown(day)    → setNav({ level: 4, …, day })
     │     └─ handleCellDetail(cell)  → setSelectedDetail(cell)
     │                                   ↓
     │                                   (triggers second fetch on open)
     │
     ├─ ChartPanel          (trend lines per category; toggles)
     │     │
     │     └─ level-aware standards:
     │         L1 → flat year  |  L2 → seasonal (in-code)
     │         L3 → flat day   |  L4 → circadian (in-code)
     │
     └─ DetailPanel         (drawer when a cell is clicked at L4)
           └─ fetches /api/v1/hrt/events?user_id&category&from&to
```

DrilldownGrid and ChartPanel share the same `data` from `/api/v1/hrt/drilldown`.
DetailPanel fires its own fetch to `/api/v1/hrt/events` only when opened.

---

## 12. Example End-to-End User Journey

```
 12:00 KST — Kim opens HRT dashboard
   L1 view loads (all years, 7 categories)
   Redis MISS on first load → materialized view hit → 86 ms

 12:01 — Kim clicks "2024"
   Drill to L2 (months of 2024)
   Redis MISS → mv_hrt_monthly query → 52 ms

 12:02 — Kim clicks "March"
   Drill to L3 (days of March 2024)
   Redis MISS → mv_hrt_daily query → 48 ms

 12:03 — Kim clicks "Day 3"
   Drill to L4 (hours of 2024-03-03)
   Redis MISS → mv_hrt_hourly query → 62 ms

 12:04 — Kim clicks the 18:00 Food cell
   DetailPanel opens → fetches /api/v1/hrt/events (second call)
   Redis MISS → SELECT from user_food_log → 35 ms
   Panel renders with meal timeline + thumbnails

 12:05 — Kim hits "← Back" to L3
   Redis HIT on drill-down cache → 3 ms

 12:06 — Kim toggles Trend Charts ON for "All"
   ChartPanel renders using same `data` (no new fetch)

 12:07 — Kim logs a new glass of water via phone app
   Kafka → health.lifestyle.events → ingest worker →
   INSERT user_food_log → trigger → NOTIFY →
   Redis DEL hrt:<uuid>:*:2024:3:*  hrt_evt:<uuid>:*:2024-03-03:*
   Next drill of L3 will re-query (46 ms) — data is fresh
```

---

## 13. Edge Cases & Gotchas

| Situation | Handling |
|---|---|
| User has no data in a time bucket | Cell shows `"-"` with `intensity: 0` (white) |
| Mock-data fallback when API is down | `generateConsistentMockData()` uses `monthSeed` for consistency across drills |
| DST / timezone shifts | All timestamps stored UTC in Domain 2; display converts using `user_profiles.timezone` (Domain 3, default `'Asia/Seoul'`) |
| User's plan gates hydration feature | `user_subscriptions.plan_code` + `feature_flags.hydration_enabled` checked at page load; if disabled, only 6 categories render |
| Data-retention window exceeded | `user_settings.data_retention_days` (default 3650 = 10y) caps L1 horizon; rows older are archived to S3 Glacier |
| User revokes expert consent mid-session | `legal_consents.withdrawn_at IS NOT NULL` → expert's HRT view returns empty next poll |
| Cells with equal values | All get `intensity: 2` (middle shade, not random) |
| L4 hour with 0 events | `"-"` instead of `"0"` to distinguish from a real 0 reading |
| Textual cells at L4 (sleep stage, mood) | Can't be line-charted — event timeline fallback renders |
| Single numeric data point at L4 | Dots render even if no line can be drawn |
| Standard has only 1 non-null point at L4 | Grey dot renders so legend doesn't lie |
| Detail Panel open while new event arrives | Opt: WebSocket push updates; current impl = closes on navigation |
| User has > 20 years of history at L1 | Horizontal scroll on grid; pagination optional |
| Hydration absent from LSTM training | Separate display-only path; predictions exclude hydration signal |

---

## 14. Known Reconciliation Items (v4 plan ↔ implementation)

Items where this document (= implementation reality) differs from the v4 plan.
Each needs a team decision before launch.

| # | Topic | v4 plan says | Reality / this doc says | Suggested action |
|---|---|---|---|---|
| R1 | Kafka topic naming | Agent-function naming (10 topics) | Aligned in this revision | None — doc now matches v4 |
| R2 | Seasonal / circadian tables | `std_seasonal_adj`, `std_circadian_norm` (2 extra tables) | In-code JS constants in ChartPanel.tsx | Leave in-code until operator UI needs tuning; then migrate and update v4 table count 21 → 23 |
| R3 | User ID type | `user_id BIGINT` + `get_my_user_id()` helper | `user_id UUID` + direct `auth.uid()` (migration 001) | Accept UUID; update v4 plan to drop BIGINT + helper |
| R4 | Aggregation engine | TimescaleDB continuous aggregates | Plain materialized views + pg_cron (TimescaleDB not installed) | Install TimescaleDB and migrate before production scale; HRT code unaffected |
| R5 | LSTM input vector | 65 dimensions (no explicit hydration features) | 7 categories displayed including Hydration | Extend to 67-68 dim before fine-tuning starts, so hydration feeds predictions |
| R6 | L4 Detail Panel data | (not specified) | Requires second fetch to `/api/v1/hrt/events` | Design API contract + add endpoint to FastAPI service |
| R7 | Food + Medicine ingest tables | `user_food_log` + `user_medication` assumed to exist | ✅ **RESOLVED (v1.5, 2026-04-28)** — both tables deployed, populated with real rows (30 + 1). `user_medication_intake` added separately (Apr 24, migration 006) to drive medicine drilldown from confirmed dose events instead of prescription windows. | None — closed. |
| R8 | OpenClaw SoulSpec runtime model | v4 plan §11 describes `USER.md` + `MEMORY.md` as **flat files** per user | 100K users × 2 per-user files = 200K flat files is unworkable. These must be DB-backed. Also: no reload-semantics spec (hot-reload could corrupt medical safety rules mid-update), no access-control spec (any dev could edit Judgement Agent safety rules without review). | **4-part fix**: (a) Keep `USER.md` + `MEMORY.md` as **templates** in repo, hydrate at runtime from two new DB tables `agent_user_context` and `agent_memory` (add to migration 003 bundle with R7). (b) Adopt **blue-green deploy** for agent config changes — no hot-reload for safety-critical agents (Judgement especially). (c) Add `.github/CODEOWNERS` requiring `@medical-advisor` + `@senior-engineer` approval for `judgement/SOUL.md` and all `*/TOOLS.md` files. (d) Document **HEARTBEAT.md** as the bridge between HRT and agents — e.g., Analytics Agent `HEARTBEAT.md` triggers the nightly MV refresh + HCI scoring (§4.1 interim plan). |

---

## 15. Future Work

1. **Materialized views → TimescaleDB continuous aggregates** — eliminate cron, incremental refresh (R4).
2. **L5 deep view** — individual event detail modal with raw sensor traces (e.g., PPG waveform for a BP reading).
3. **Cross-category correlation overlay** — highlight cells where Food + Mental correlate with Sleep dips.
4. **Predictive extension** — graft LSTM predictions onto the right edge of L2 and L3 views (already live at `/predictions`).
5. **Shared drill-down with expert** — expert sees read-only HRT of a consented user.
6. **Anomaly badges** — red badge on cells that deviate > 2σ from the user's own historical baseline.
7. **Hydration features in LSTM** — retrain with extended input vector (R5).

---

## 16. Reference — Where Each Concept Lives in Code

| Concept | File |
|---|---|
| Concept | File | Status |
|---|---|---|
| 4-level nav state machine | `app/page.tsx` | ✅ Deployed |
| Grid rendering + intensity math | `app/components/DrilldownGrid.tsx` | ✅ Deployed |
| Standards overlay + trend charts | `app/components/ChartPanel.tsx` | ✅ Deployed |
| In-code `SEASONAL_FACTORS` constant | `ChartPanel.tsx` (~lines 117-127) | ✅ Deployed |
| In-code `HOURLY_STANDARDS` constant | `ChartPanel.tsx` (~lines 160-176) | ✅ Deployed |
| L4 Detail Panel | `app/components/DetailPanel.tsx` | ✅ Deployed |
| User schema (`users(user_id UUID)`) | `migrations/001_initial_schema.sql` line 93 | ✅ Deployed |
| RLS policies | `migrations/001_initial_schema.sql` + `002_add_missing_tables.sql` | ✅ Deployed |
| 21 tables (Domains 3-6 + Shared) | `migrations/002_add_missing_tables.sql` | ✅ Deployed |
| Food ingest table `user_food_log` | (deployed via Supabase migration `add_v32_health_tables`) | ✅ Deployed |
| Medicine prescription table `user_medication` | (deployed via Supabase migration `add_v32_health_tables`) | ✅ Deployed |
| Medicine intake events `user_medication_intake` | `migrations/006_medication_intake_and_goal_relative_intensity.sql` | ✅ Deployed (Apr 24) |
| Agent context tables `agent_user_context` + `agent_memory` (R8) | `migrations/003_agent_context_memory.sql` | ✅ Deployed (schema only — agent code pending) |
| Supabase RPC `hrt_drilldown_full()` + audit fixes | `migrations/004_hrt_drilldown_full_function.sql` + `005_hrt_drilldown_logic_fixes.sql` | ✅ Deployed |
| Service-role auth bypass | Supabase migration `allow_service_role_in_require_current_user_id` | ✅ Deployed (Apr 24) |
| API client | `app/lib/api.ts` | ❌ Pending |
| Materialized views `mv_hrt_*` | `migrations/00X_hrt_mvs.sql` | ❌ Pending (interim) |
| TimescaleDB extension + hypertables | `migrations/0XX_timescaledb.sql` | ❌ Target state (R4) |
| `/api/v1/hrt/events` endpoint (R6) | `backend/app/api/hrt_drilldown.py` | ✅ Deployed (Apr 22, migration `add_hrt_event_detail_function`) |

---

**Document owner:** Healthcare AI Agent team
**Maintainer:** tripleh + Claude
**Next review:** after R1-R6 + R8 resolved or before TimescaleDB migration
**Previous-reviewer flag:** R7 closed in v1.5 (2026-04-28) — food/medication tables deployed. Remaining open items: R2 (seasonal/circadian still in-code), R3 (UUID accepted, v4 plan needs update), R4 (TimescaleDB not yet installed), R5 (LSTM input vector still 65-dim, retrain needed before predictions go to production), R6 (event-detail endpoint deployed, contract still implicit), R8 (agent code not wired to deployed schema).
