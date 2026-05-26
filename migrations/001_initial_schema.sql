-- ============================================================================
-- Healthcare AI Agent - Initial Schema Migration
-- Triple-H Co., Ltd. | April 2026
-- Patent No. 10-2025-0145274
--
-- Run this in Supabase SQL Editor (Dashboard > SQL Editor > New query > Paste > Run)
-- This creates: pgvector extension, 14 HRT tables, indexes, RLS policies
-- ============================================================================

-- ============================================================================
-- 1. EXTENSIONS
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";      -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "vector";         -- pgvector for embeddings

-- ============================================================================
-- 2. STANDARD HRT TABLES (4 tables - reference data, not time-series)
-- ============================================================================

-- ── std_population_category ─────────────────────────────────────────────────
CREATE TABLE std_population_category (
    category_id    SERIAL PRIMARY KEY,
    age_group      VARCHAR(20)   NOT NULL,
    gender         CHAR(1)       NOT NULL CHECK (gender IN ('M', 'F', 'O')),
    disability_yn  BOOLEAN       DEFAULT false,
    income_decile  SMALLINT      CHECK (income_decile BETWEEN 1 AND 10),
    country_code   CHAR(3)       DEFAULT 'KOR',
    created_at     TIMESTAMPTZ   DEFAULT NOW()
);

COMMENT ON TABLE std_population_category IS 'Standard population categories for health benchmarking (age/gender/disability/income)';

-- ── std_diagnosis_norm ──────────────────────────────────────────────────────
CREATE TABLE std_diagnosis_norm (
    norm_id        SERIAL PRIMARY KEY,
    category_id    INT           NOT NULL REFERENCES std_population_category(category_id),
    metric_code    VARCHAR(50)   NOT NULL,
    metric_name_en VARCHAR(100),
    unit           VARCHAR(20),
    normal_min     NUMERIC(10,4),
    normal_max     NUMERIC(10,4),
    warning_min    NUMERIC(10,4),
    warning_max    NUMERIC(10,4),
    critical_min   NUMERIC(10,4),
    critical_max   NUMERIC(10,4),
    source         VARCHAR(200),
    effective_date DATE
);

COMMENT ON TABLE std_diagnosis_norm IS 'Standard diagnosis normal/warning/critical ranges per population category';

CREATE INDEX idx_diagnosis_norm_category ON std_diagnosis_norm(category_id);
CREATE INDEX idx_diagnosis_norm_metric ON std_diagnosis_norm(metric_code);

-- ── std_lifestyle_plan ──────────────────────────────────────────────────────
CREATE TABLE std_lifestyle_plan (
    plan_id        SERIAL PRIMARY KEY,
    category_id    INT           NOT NULL REFERENCES std_population_category(category_id),
    plan_type      VARCHAR(20)   NOT NULL CHECK (plan_type IN ('diet', 'exercise', 'sleep', 'medication')),
    plan_name      VARCHAR(200),
    detail_json    JSONB,
    evidence_level VARCHAR(10)   CHECK (evidence_level IN ('A', 'B', 'C')),
    created_by     VARCHAR(100),
    updated_at     TIMESTAMPTZ   DEFAULT NOW()
);

COMMENT ON TABLE std_lifestyle_plan IS 'Role-model lifestyle management plans per population category (diet/exercise/sleep/medication)';

CREATE INDEX idx_lifestyle_plan_category ON std_lifestyle_plan(category_id);
CREATE INDEX idx_lifestyle_plan_type ON std_lifestyle_plan(plan_type);

-- ── std_disease_risk_weight ─────────────────────────────────────────────────
CREATE TABLE std_disease_risk_weight (
    weight_id      SERIAL PRIMARY KEY,
    disease_code   VARCHAR(20)   NOT NULL,
    disease_name   VARCHAR(100),
    metric_code    VARCHAR(50),
    weight_value   NUMERIC(5,4)  NOT NULL,
    category_id    INT           REFERENCES std_population_category(category_id),
    formula_type   VARCHAR(20)   DEFAULT 'linear' CHECK (formula_type IN ('linear', 'sigmoid', 'exponential'))
);

COMMENT ON TABLE std_disease_risk_weight IS 'Disease risk contribution weights per metric per population category (ICD-11)';

CREATE INDEX idx_disease_risk_category ON std_disease_risk_weight(category_id);
CREATE INDEX idx_disease_risk_disease ON std_disease_risk_weight(disease_code);

-- ============================================================================
-- 3. PERSONAL HRT TABLES (10 tables - time-series user health data)
-- ============================================================================

-- ── users ───────────────────────────────────────────────────────────────────
CREATE TABLE users (
    user_id        UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    user_hash      VARCHAR(64)   UNIQUE,
    age_group      VARCHAR(20),
    gender         CHAR(1)       CHECK (gender IN ('M', 'F', 'O')),
    disability_yn  BOOLEAN       DEFAULT false,
    income_decile  SMALLINT      CHECK (income_decile BETWEEN 1 AND 10),
    country_code   CHAR(3)       DEFAULT 'KOR',
    created_at     TIMESTAMPTZ   DEFAULT NOW(),
    is_active      BOOLEAN       DEFAULT true
);

COMMENT ON TABLE users IS 'User basic info. No direct PII stored - de-identification via user_hash (SHA-256)';

-- ── user_demographic ────────────────────────────────────────────────────────
CREATE TABLE user_demographic (
    demo_id        BIGSERIAL     PRIMARY KEY,
    user_id        UUID          NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    recorded_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    age            SMALLINT,
    gender         CHAR(1)       CHECK (gender IN ('M', 'F', 'O')),
    disability_type VARCHAR(50),
    income_decile  SMALLINT,
    past_history   TEXT[],
    family_history TEXT[]
);

COMMENT ON TABLE user_demographic IS 'Sociodemographic data (time-series). Updated when user profile changes.';

CREATE INDEX idx_demographic_user_time ON user_demographic(user_id, recorded_at DESC);

-- ── user_biometric ──────────────────────────────────────────────────────────
CREATE TABLE user_biometric (
    bio_id         BIGSERIAL     PRIMARY KEY,
    user_id        UUID          NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    measured_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    device_type    VARCHAR(50),
    heart_rate     SMALLINT,
    hrv            SMALLINT,
    spo2           NUMERIC(4,1),
    body_temp      NUMERIC(4,1),
    resp_rate      SMALLINT,
    step_count     INT,
    stress_index   NUMERIC(4,1),
    glucose_mgdl   NUMERIC(5,1),
    glucose_trend  VARCHAR(20),
    raw_ecg_ref    VARCHAR(255)
);

COMMENT ON TABLE user_biometric IS 'Real-time biometric data from wearables/CGM. High-frequency (1sec HR, 5min CGM).';

CREATE INDEX idx_biometric_user_time ON user_biometric(user_id, measured_at DESC);
CREATE INDEX idx_biometric_device ON user_biometric(user_id, device_type, measured_at DESC);

-- ── user_diagnosis ──────────────────────────────────────────────────────────
CREATE TABLE user_diagnosis (
    diag_id        BIGSERIAL     PRIMARY KEY,
    user_id        UUID          NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    period_type    VARCHAR(10)   NOT NULL CHECK (period_type IN ('daily', 'weekly', 'monthly')),
    period_start   DATE          NOT NULL,
    height_cm      NUMERIC(5,1),
    weight_kg      NUMERIC(5,1),
    bmi            NUMERIC(4,1),
    sbp            SMALLINT,
    dbp            SMALLINT,
    fasting_glucose SMALLINT,
    total_chol     SMALLINT,
    hdl_chol       SMALLINT,
    ldl_chol       SMALLINT,
    triglyceride   SMALLINT,
    hemoglobin     NUMERIC(4,1),
    creatinine     NUMERIC(5,2),
    alt            SMALLINT,
    ast            SMALLINT,
    ggt            SMALLINT,
    body_fat_pct   NUMERIC(4,1),
    muscle_mass_kg NUMERIC(5,1),
    data_source    VARCHAR(50)
);

COMMENT ON TABLE user_diagnosis IS 'Periodic diagnostic data aggregation (daily/weekly/monthly). Hospital + wearable derived.';

CREATE INDEX idx_diagnosis_user_time ON user_diagnosis(user_id, period_start DESC);
CREATE INDEX idx_diagnosis_period ON user_diagnosis(user_id, period_type, period_start DESC);

-- ── user_lifestyle ──────────────────────────────────────────────────────────
CREATE TABLE user_lifestyle (
    ls_id              BIGSERIAL     PRIMARY KEY,
    user_id            UUID          NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    recorded_date      DATE          NOT NULL,
    total_calories     SMALLINT,
    carb_g             SMALLINT,
    protein_g          SMALLINT,
    fat_g              SMALLINT,
    fiber_g            NUMERIC(5,1),
    sodium_mg          SMALLINT,
    alcohol_ml         SMALLINT,
    meal_count         SMALLINT,
    exercise_min       SMALLINT,
    exercise_type      VARCHAR(50),
    exercise_kcal      SMALLINT,
    exercise_intensity VARCHAR(10)   CHECK (exercise_intensity IN ('low', 'moderate', 'high')),
    sleep_start        TIMESTAMPTZ,
    sleep_end          TIMESTAMPTZ,
    sleep_hours        NUMERIC(4,1),
    sleep_quality      NUMERIC(3,1),
    wake_count         SMALLINT,
    medication_json    JSONB,
    data_source        VARCHAR(50)
);

COMMENT ON TABLE user_lifestyle IS 'Daily lifestyle data: diet, exercise, sleep, medication. Aggregated from glasses + manual + wearable.';

CREATE INDEX idx_lifestyle_user_time ON user_lifestyle(user_id, recorded_date DESC);
CREATE INDEX idx_lifestyle_medication_gin ON user_lifestyle USING GIN (medication_json jsonb_path_ops);

-- ── user_activity_event (NEW - AI Glasses) ──────────────────────────────────
CREATE TABLE user_activity_event (
    event_id           BIGSERIAL     PRIMARY KEY,
    user_id            UUID          NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    detected_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    event_type         VARCHAR(30)   NOT NULL,
    source_device      VARCHAR(30)   NOT NULL,
    confidence_score   NUMERIC(4,2),
    structured_data    JSONB,
    thumbnail_ref      VARCHAR(500),
    clip_ref           VARCHAR(500),
    media_size_bytes   INT,
    edge_model_version VARCHAR(30),
    verified           BOOLEAN       DEFAULT false,
    correction_data    JSONB,
    processing_status  VARCHAR(20)   DEFAULT 'edge_only'
        CHECK (processing_status IN ('edge_only', 'cloud_refined', 'user_verified'))
);

COMMENT ON TABLE user_activity_event IS 'AI Glasses activity events. Structured continuous lifestyle monitoring with confidence scoring and active learning support.';

CREATE INDEX idx_activity_user_type_time ON user_activity_event(user_id, event_type, detected_at DESC);
CREATE INDEX idx_activity_user_time ON user_activity_event(user_id, detected_at DESC);
CREATE INDEX idx_activity_unverified ON user_activity_event(user_id, detected_at DESC)
    WHERE verified = false AND confidence_score < 0.7;
CREATE INDEX idx_activity_data_gin ON user_activity_event USING GIN (structured_data jsonb_path_ops);

-- ── user_health_level ───────────────────────────────────────────────────────
CREATE TABLE user_health_level (
    hl_id              BIGSERIAL     PRIMARY KEY,
    user_id            UUID          NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    measured_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    period_type        VARCHAR(10)   CHECK (period_type IN ('daily', 'weekly', 'monthly')),
    healthcare_index   NUMERIC(5,2),
    dri                NUMERIC(5,2),
    fatigue_level      SMALLINT      CHECK (fatigue_level BETWEEN 1 AND 10),
    stress_level       SMALLINT      CHECK (stress_level BETWEEN 1 AND 10),
    appetite_level     SMALLINT      CHECK (appetite_level BETWEEN 1 AND 10),
    disease_risk_json  JSONB,
    predicted          BOOLEAN       DEFAULT false,
    sim_scenario       VARCHAR(50),
    confidence_interval JSONB
);

COMMENT ON TABLE user_health_level IS 'Healthcare Index (T score 0-100), Disease Risk Index, subjective levels. Includes simulation predictions with uncertainty bounds.';

CREATE INDEX idx_health_level_user_time ON user_health_level(user_id, measured_at DESC);
CREATE INDEX idx_health_level_predicted ON user_health_level(user_id, measured_at DESC) WHERE predicted = true;
CREATE INDEX idx_disease_risk_gin ON user_health_level USING GIN (disease_risk_json jsonb_path_ops);

-- ── user_multimodal ─────────────────────────────────────────────────────────
CREATE TABLE user_multimodal (
    mm_id              BIGSERIAL     PRIMARY KEY,
    user_id            UUID          NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    captured_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    modal_type         VARCHAR(20)   NOT NULL CHECK (modal_type IN ('voice', 'image', 'video', 'sensor')),
    context_place      VARCHAR(100),
    context_weather    VARCHAR(50),
    emotion_state      VARCHAR(50),
    intent_summary     TEXT,
    behavior_motive    TEXT,
    storage_ref        VARCHAR(500),
    embedding_vec      vector(1536)
);

COMMENT ON TABLE user_multimodal IS 'Multimodal data metadata with pgvector embeddings for semantic search.';

CREATE INDEX idx_multimodal_user_time ON user_multimodal(user_id, captured_at DESC);
CREATE INDEX idx_multimodal_modal ON user_multimodal(user_id, modal_type, captured_at DESC);

-- HNSW index for vector similarity search
CREATE INDEX idx_multimodal_embedding ON user_multimodal
    USING hnsw (embedding_vec vector_cosine_ops)
    WITH (m = 24, ef_construction = 128);

-- ── agent_conversation_log ──────────────────────────────────────────────────
CREATE TABLE agent_conversation_log (
    log_id         BIGSERIAL     PRIMARY KEY,
    user_id        UUID          NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    agent_name     VARCHAR(50)   NOT NULL,
    channel        VARCHAR(30),
    role           VARCHAR(10)   NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content        TEXT,
    tokens_used    INT,
    model_used     VARCHAR(30),
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE agent_conversation_log IS 'AI Agent conversation history across all channels. Tracks LLM model used for cost routing analysis.';

CREATE INDEX idx_conversation_user_time ON agent_conversation_log(user_id, created_at DESC);
CREATE INDEX idx_conversation_agent ON agent_conversation_log(user_id, agent_name, created_at DESC);

-- ── simulation_result ───────────────────────────────────────────────────────
CREATE TABLE simulation_result (
    sim_id                 BIGSERIAL     PRIMARY KEY,
    user_id                UUID          NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    run_at                 TIMESTAMPTZ   DEFAULT NOW(),
    base_date              DATE          NOT NULL,
    scenario               VARCHAR(50)   NOT NULL CHECK (scenario IN ('current', 'twin', 'optimistic')),
    horizon_days           INT           NOT NULL,
    predicted_diag_json    JSONB,
    predicted_risk_json    JSONB,
    hci_series_json        JSONB,
    confidence_bounds_json JSONB,
    model_version          VARCHAR(30),
    rmse                   NUMERIC(8,4),
    mae_per_metric         JSONB
);

COMMENT ON TABLE simulation_result IS 'LSTM-Transformer simulation results. Stores predicted time-series for current/twin/optimistic scenarios with uncertainty bounds.';

CREATE INDEX idx_simulation_user_time ON simulation_result(user_id, run_at DESC);
CREATE INDEX idx_simulation_scenario ON simulation_result(user_id, scenario, run_at DESC);

-- ============================================================================
-- 4. ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================================================
-- Supabase auto-enables RLS on new tables. We define policies so users
-- can only access their own data via the authenticated JWT.

-- Enable RLS on all personal tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_demographic ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_biometric ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_diagnosis ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_lifestyle ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_activity_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_health_level ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_multimodal ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_conversation_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE simulation_result ENABLE ROW LEVEL SECURITY;

-- Users table: users can only see/modify their own record
CREATE POLICY "Users can view own profile"
    ON users FOR SELECT
    USING (user_id = (select auth.uid()));

CREATE POLICY "Users can update own profile"
    ON users FOR UPDATE
    USING (user_id = (select auth.uid()));

-- user_demographic
CREATE POLICY "Users can view own user_demographic"
    ON user_demographic FOR SELECT USING (user_id = (select auth.uid()));
CREATE POLICY "Users can insert own user_demographic"
    ON user_demographic FOR INSERT WITH CHECK (user_id = (select auth.uid()));

-- user_biometric
CREATE POLICY "Users can view own user_biometric"
    ON user_biometric FOR SELECT USING (user_id = (select auth.uid()));
CREATE POLICY "Users can insert own user_biometric"
    ON user_biometric FOR INSERT WITH CHECK (user_id = (select auth.uid()));

-- user_diagnosis
CREATE POLICY "Users can view own user_diagnosis"
    ON user_diagnosis FOR SELECT USING (user_id = (select auth.uid()));
CREATE POLICY "Users can insert own user_diagnosis"
    ON user_diagnosis FOR INSERT WITH CHECK (user_id = (select auth.uid()));

-- user_lifestyle
CREATE POLICY "Users can view own user_lifestyle"
    ON user_lifestyle FOR SELECT USING (user_id = (select auth.uid()));
CREATE POLICY "Users can insert own user_lifestyle"
    ON user_lifestyle FOR INSERT WITH CHECK (user_id = (select auth.uid()));

-- user_activity_event
CREATE POLICY "Users can view own user_activity_event"
    ON user_activity_event FOR SELECT USING (user_id = (select auth.uid()));
CREATE POLICY "Users can insert own user_activity_event"
    ON user_activity_event FOR INSERT WITH CHECK (user_id = (select auth.uid()));

-- user_health_level
CREATE POLICY "Users can view own user_health_level"
    ON user_health_level FOR SELECT USING (user_id = (select auth.uid()));
CREATE POLICY "Users can insert own user_health_level"
    ON user_health_level FOR INSERT WITH CHECK (user_id = (select auth.uid()));

-- user_multimodal
CREATE POLICY "Users can view own user_multimodal"
    ON user_multimodal FOR SELECT USING (user_id = (select auth.uid()));
CREATE POLICY "Users can insert own user_multimodal"
    ON user_multimodal FOR INSERT WITH CHECK (user_id = (select auth.uid()));

-- agent_conversation_log
CREATE POLICY "Users can view own agent_conversation_log"
    ON agent_conversation_log FOR SELECT USING (user_id = (select auth.uid()));
CREATE POLICY "Users can insert own agent_conversation_log"
    ON agent_conversation_log FOR INSERT WITH CHECK (user_id = (select auth.uid()));

-- simulation_result
CREATE POLICY "Users can view own simulation_result"
    ON simulation_result FOR SELECT USING (user_id = (select auth.uid()));
CREATE POLICY "Users can insert own simulation_result"
    ON simulation_result FOR INSERT WITH CHECK (user_id = (select auth.uid()));

-- Standard HRT tables: readable by all authenticated users (reference data)
ALTER TABLE std_population_category ENABLE ROW LEVEL SECURITY;
ALTER TABLE std_diagnosis_norm ENABLE ROW LEVEL SECURITY;
ALTER TABLE std_lifestyle_plan ENABLE ROW LEVEL SECURITY;
ALTER TABLE std_disease_risk_weight ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated read std_population_category"
    ON std_population_category FOR SELECT USING ((select auth.role()) = 'authenticated');
CREATE POLICY "Authenticated read std_diagnosis_norm"
    ON std_diagnosis_norm FOR SELECT USING ((select auth.role()) = 'authenticated');
CREATE POLICY "Authenticated read std_lifestyle_plan"
    ON std_lifestyle_plan FOR SELECT USING ((select auth.role()) = 'authenticated');
CREATE POLICY "Authenticated read std_disease_risk_weight"
    ON std_disease_risk_weight FOR SELECT USING ((select auth.role()) = 'authenticated');

-- ============================================================================
-- 5. VERIFICATION
-- ============================================================================
-- Run this after migration to verify everything was created correctly

SELECT 'TABLES' as check_type, count(*) as count
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
UNION ALL
SELECT 'INDEXES', count(*)
FROM pg_indexes
WHERE schemaname = 'public'
UNION ALL
SELECT 'RLS POLICIES', count(*)
FROM pg_policies
WHERE schemaname = 'public'
UNION ALL
SELECT 'EXTENSIONS', count(*)
FROM pg_extension
WHERE extname IN ('vector', 'pgcrypto');
