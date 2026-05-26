-- ============================================================================
-- Healthcare AI Agent - Migration 002: Add Missing Tables
-- Triple-H Co., Ltd. | 2026-04-22
-- Patent No. 10-2025-0145274
--
-- v1.1 fix: This migration now correctly works on top of migration 001.
--           Earlier v1.0 draft mistakenly did `CREATE TABLE users (id UUID...)`
--           which would have failed because migration 001 already created
--           `users(user_id UUID ...)`. That draft also referenced `users(id)`
--           in child-table FKs — the correct column is `users(user_id)`.
--
-- Adds 22 tables across 4 domains:
--   User Management  (5 new tables + ALTER TABLE users)
--   Admin            (5 tables)
--   Notifications    (4 tables)
--   Expert System    (4 tables)
--   Shared / Helpers (3 tables)
--
-- PREREQUISITES:
--   - 001_initial_schema.sql must have been applied
--   - pgcrypto + vector extensions are already enabled
--   - `users(user_id UUID)` table exists with `auth.users.id`-matching values
--
-- RUN:
--   Supabase Dashboard > SQL Editor > New query > Paste > Run
-- ============================================================================

-- ============================================================================
-- DEPENDENCY ORDERING
-- ============================================================================
--   users (ALTERed) → user_profiles, user_settings, user_devices,
--                     user_subscriptions, user_activity_log
--   admin_users     → admin_permissions, admin_audit_log
--   notification_templates → notifications → notification_log
--   experts         → expert_availability, expert_reviews, expert_consultations
-- All user_id FKs use ON DELETE CASCADE.

-- ============================================================================
-- 1. USER MANAGEMENT DOMAIN
-- ============================================================================

-- ── users (extend existing table from migration 001) ────────────────────────
-- Migration 001 created users(user_id UUID, user_hash, age_group, gender,
-- disability_yn, income_decile, country_code, created_at, is_active).
-- We now add the operational fields needed for app integration.
-- All new columns are NULLable so existing rows from 001 aren't broken.

ALTER TABLE users ADD COLUMN IF NOT EXISTS email              VARCHAR(255) UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone              VARCHAR(20);
ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name       VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url         TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS locale             VARCHAR(10)  DEFAULT 'ko-KR';
ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone           VARCHAR(50)  DEFAULT 'Asia/Seoul';
ALTER TABLE users ADD COLUMN IF NOT EXISTS account_status     VARCHAR(20)  DEFAULT 'active';
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at  TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at         TIMESTAMPTZ  DEFAULT NOW();
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at      TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_at         TIMESTAMPTZ;

-- account_status CHECK — added separately so ALTER can run on tables that
-- already had this column added in a prior attempt.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'users_account_status_check'
    ) THEN
        ALTER TABLE users
          ADD CONSTRAINT users_account_status_check
          CHECK (account_status IN ('active', 'suspended', 'deleted', 'pending_verification'));
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_users_email       ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_status      ON users(account_status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_users_last_login  ON users(last_login_at DESC) WHERE account_status = 'active';

COMMENT ON COLUMN users.email          IS 'Primary login identifier (nullable for legacy rows from 001)';
COMMENT ON COLUMN users.account_status IS 'Lifecycle state — driven by auth + admin actions';

-- ── user_profiles ───────────────────────────────────────────────────────────
-- Demographic + health baseline data for benchmarking/personalization.
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id            UUID            PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    category_id        INT             REFERENCES std_population_category(category_id),
    birth_date         DATE,
    gender             CHAR(1)         CHECK (gender IN ('M', 'F', 'O')),
    height_cm          NUMERIC(5,2),
    weight_kg          NUMERIC(5,2),
    blood_type         VARCHAR(5),
    disability_yn      BOOLEAN         DEFAULT false,
    occupation         VARCHAR(100),
    income_decile      SMALLINT        CHECK (income_decile BETWEEN 1 AND 10),
    country_code       CHAR(3)         DEFAULT 'KOR',
    medical_history    JSONB           DEFAULT '{}'::jsonb,
    allergies          TEXT[],
    chronic_conditions TEXT[],
    onboarded_at       TIMESTAMPTZ,
    updated_at         TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE user_profiles IS 'Demographic and baseline health data for benchmarking against std_population_category.';
CREATE INDEX IF NOT EXISTS idx_user_profiles_category ON user_profiles(category_id);

-- ── user_settings ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_settings (
    user_id              UUID          PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    units_system         VARCHAR(10)   DEFAULT 'metric' CHECK (units_system IN ('metric', 'imperial')),
    theme                VARCHAR(20)   DEFAULT 'light' CHECK (theme IN ('light', 'dark', 'auto')),
    glass_audio_capture  BOOLEAN       DEFAULT true,
    glass_video_capture  BOOLEAN       DEFAULT true,
    data_sharing_expert  BOOLEAN       DEFAULT false,
    data_sharing_family  BOOLEAN       DEFAULT false,
    data_retention_days  INT           DEFAULT 3650 CHECK (data_retention_days > 0),
    llm_response_style   VARCHAR(20)   DEFAULT 'balanced' CHECK (llm_response_style IN ('concise', 'balanced', 'detailed')),
    prefs_json           JSONB         DEFAULT '{}'::jsonb,
    updated_at           TIMESTAMPTZ   DEFAULT NOW()
);

COMMENT ON TABLE user_settings IS 'Per-user preferences for privacy, UX, and LLM behavior.';

-- ── user_devices ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_devices (
    device_id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID            NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    device_type        VARCHAR(30)     NOT NULL
                                       CHECK (device_type IN ('glasses_aimb_g1', 'glasses_mentra', 'glasses_omi', 'phone_ios', 'phone_android', 'wearable_watch', 'wearable_band', 'other')),
    device_name        VARCHAR(100),
    device_serial      VARCHAR(100),
    os_version         VARCHAR(30),
    app_version        VARCHAR(30),
    push_token         TEXT,
    is_active          BOOLEAN         DEFAULT true,
    registered_at      TIMESTAMPTZ     DEFAULT NOW(),
    last_seen_at       TIMESTAMPTZ,
    unregistered_at    TIMESTAMPTZ
);

COMMENT ON TABLE user_devices IS 'Registered user devices for data ingest and push notifications.';
CREATE INDEX IF NOT EXISTS idx_user_devices_user     ON user_devices(user_id) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_user_devices_type     ON user_devices(device_type);
CREATE INDEX IF NOT EXISTS idx_user_devices_lastseen ON user_devices(last_seen_at DESC);

-- ── user_subscriptions ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_subscriptions (
    subscription_id    UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID            NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    plan_code          VARCHAR(30)     NOT NULL
                                       CHECK (plan_code IN ('free', 'basic', 'premium', 'enterprise', 'trial')),
    status             VARCHAR(20)     DEFAULT 'active'
                                       CHECK (status IN ('active', 'past_due', 'canceled', 'trialing', 'paused')),
    started_at         TIMESTAMPTZ     DEFAULT NOW(),
    current_period_end TIMESTAMPTZ,
    canceled_at        TIMESTAMPTZ,
    provider           VARCHAR(30)     CHECK (provider IN ('stripe', 'kakaopay', 'naverpay', 'apple', 'google', 'manual')),
    provider_ref       VARCHAR(200),
    price_krw          NUMERIC(10,2),
    metadata           JSONB           DEFAULT '{}'::jsonb
);

COMMENT ON TABLE user_subscriptions IS 'Subscription plan and billing state per user. One active row per user expected.';
CREATE INDEX IF NOT EXISTS idx_user_subs_user      ON user_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_subs_status    ON user_subscriptions(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_subs_active ON user_subscriptions(user_id) WHERE status IN ('active', 'trialing');

-- ── user_activity_log ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_activity_log (
    log_id             BIGSERIAL       PRIMARY KEY,
    user_id            UUID            NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    event_type         VARCHAR(50)     NOT NULL,
    event_source       VARCHAR(30),
    ip_address         INET,
    user_agent         TEXT,
    metadata           JSONB           DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE user_activity_log IS 'Non-health user activity for audit/security. Default 90d retention.';
CREATE INDEX IF NOT EXISTS idx_user_activity_user ON user_activity_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_activity_type ON user_activity_log(event_type, created_at DESC);

-- ============================================================================
-- 2. ADMIN DOMAIN (5 tables)
-- ============================================================================

-- ── admin_users ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admin_users (
    admin_id           UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID            UNIQUE REFERENCES users(user_id) ON DELETE SET NULL,
    email              VARCHAR(255)    UNIQUE NOT NULL,
    role               VARCHAR(30)     NOT NULL
                                       CHECK (role IN ('super_admin', 'admin', 'moderator', 'support', 'readonly')),
    department         VARCHAR(50),
    mfa_enabled        BOOLEAN         DEFAULT false,
    is_active          BOOLEAN         DEFAULT true,
    created_at         TIMESTAMPTZ     DEFAULT NOW(),
    deactivated_at     TIMESTAMPTZ
);

COMMENT ON TABLE admin_users IS 'Operator/admin staff accounts. Optionally linked to a regular user account.';
CREATE INDEX IF NOT EXISTS idx_admin_users_role ON admin_users(role) WHERE is_active = true;

-- ── admin_permissions ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admin_permissions (
    permission_id      BIGSERIAL       PRIMARY KEY,
    admin_id           UUID            NOT NULL REFERENCES admin_users(admin_id) ON DELETE CASCADE,
    resource           VARCHAR(50)     NOT NULL,
    action             VARCHAR(20)     NOT NULL CHECK (action IN ('read', 'write', 'delete', 'manage')),
    granted_by         UUID            REFERENCES admin_users(admin_id),
    granted_at         TIMESTAMPTZ     DEFAULT NOW(),
    expires_at         TIMESTAMPTZ,
    UNIQUE (admin_id, resource, action)
);

COMMENT ON TABLE admin_permissions IS 'Per-resource granular permissions (overrides role defaults).';
CREATE INDEX IF NOT EXISTS idx_admin_perms_admin ON admin_permissions(admin_id);

-- ── admin_audit_log ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admin_audit_log (
    audit_id           BIGSERIAL       PRIMARY KEY,
    admin_id           UUID            REFERENCES admin_users(admin_id) ON DELETE SET NULL,
    action             VARCHAR(50)     NOT NULL,
    target_resource    VARCHAR(50),
    target_id          VARCHAR(100),
    before_state       JSONB,
    after_state        JSONB,
    ip_address         INET,
    user_agent         TEXT,
    success            BOOLEAN         DEFAULT true,
    error_message      TEXT,
    created_at         TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE admin_audit_log IS 'Tamper-evident log of admin actions. Required for compliance.';
CREATE INDEX IF NOT EXISTS idx_admin_audit_admin   ON admin_audit_log(admin_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_action  ON admin_audit_log(action, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_target  ON admin_audit_log(target_resource, target_id);

-- ── system_config ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_config (
    config_key         VARCHAR(100)    PRIMARY KEY,
    config_value       JSONB           NOT NULL,
    description        TEXT,
    category           VARCHAR(50)     DEFAULT 'general',
    is_secret          BOOLEAN         DEFAULT false,
    updated_by         UUID            REFERENCES admin_users(admin_id),
    updated_at         TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE system_config IS 'Runtime-tunable business-logic config. Not for secrets (use Vault).';
CREATE INDEX IF NOT EXISTS idx_system_config_category ON system_config(category);

-- ── feature_flags ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS feature_flags (
    flag_key           VARCHAR(100)    PRIMARY KEY,
    enabled            BOOLEAN         DEFAULT false,
    rollout_percentage SMALLINT        DEFAULT 0 CHECK (rollout_percentage BETWEEN 0 AND 100),
    target_user_ids    UUID[],
    target_plans       TEXT[],
    description        TEXT,
    updated_by         UUID            REFERENCES admin_users(admin_id),
    updated_at         TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE feature_flags IS 'Feature rollout toggles. Percentage + user-list + plan-list targeting.';

-- ============================================================================
-- 3. NOTIFICATIONS DOMAIN (4 tables)
-- ============================================================================

-- ── notification_templates ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notification_templates (
    template_id        SERIAL          PRIMARY KEY,
    template_code      VARCHAR(100)    NOT NULL,
    locale             VARCHAR(10)     DEFAULT 'ko-KR',
    channel            VARCHAR(20)     NOT NULL
                                       CHECK (channel IN ('push', 'email', 'sms', 'inapp', 'voice_glasses')),
    subject            VARCHAR(255),
    body_template      TEXT            NOT NULL,
    variables          TEXT[],
    priority           VARCHAR(20)     DEFAULT 'normal'
                                       CHECK (priority IN ('low', 'normal', 'high', 'critical')),
    is_active          BOOLEAN         DEFAULT true,
    created_at         TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE (template_code, locale, channel)
);

COMMENT ON TABLE notification_templates IS 'Canonical notification templates. {{variable}} interpolation.';
CREATE INDEX IF NOT EXISTS idx_notif_tmpl_code ON notification_templates(template_code) WHERE is_active = true;

-- ── notification_preferences ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notification_preferences (
    preference_id      BIGSERIAL       PRIMARY KEY,
    user_id            UUID            NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    template_code      VARCHAR(100)    NOT NULL,
    channel            VARCHAR(20)     NOT NULL
                                       CHECK (channel IN ('push', 'email', 'sms', 'inapp', 'voice_glasses')),
    enabled            BOOLEAN         DEFAULT true,
    quiet_hours_start  TIME,
    quiet_hours_end    TIME,
    updated_at         TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE (user_id, template_code, channel)
);

COMMENT ON TABLE notification_preferences IS 'Per-user opt-in preferences. Defaults: critical always on, others on.';
CREATE INDEX IF NOT EXISTS idx_notif_pref_user ON notification_preferences(user_id);

-- ── notifications ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notifications (
    notification_id    UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID            NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    template_id        INT             REFERENCES notification_templates(template_id),
    channel            VARCHAR(20)     NOT NULL,
    subject            VARCHAR(255),
    body               TEXT            NOT NULL,
    data               JSONB           DEFAULT '{}'::jsonb,
    priority           VARCHAR(20)     DEFAULT 'normal',
    status             VARCHAR(20)     DEFAULT 'queued'
                                       CHECK (status IN ('queued', 'sending', 'sent', 'failed', 'read', 'dismissed')),
    scheduled_at       TIMESTAMPTZ     DEFAULT NOW(),
    sent_at            TIMESTAMPTZ,
    read_at            TIMESTAMPTZ,
    error_message      TEXT,
    retry_count        SMALLINT        DEFAULT 0
);

COMMENT ON TABLE notifications IS 'Outgoing + in-app messages. Emergency alerts MUST use priority=critical and never be dropped.';
CREATE INDEX IF NOT EXISTS idx_notifications_user    ON notifications(user_id, scheduled_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_status  ON notifications(status, scheduled_at) WHERE status IN ('queued', 'sending');
CREATE INDEX IF NOT EXISTS idx_notifications_unread  ON notifications(user_id) WHERE read_at IS NULL AND status = 'sent';

-- ── notification_log ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notification_log (
    log_id             BIGSERIAL       PRIMARY KEY,
    notification_id    UUID            NOT NULL REFERENCES notifications(notification_id) ON DELETE CASCADE,
    attempt_number     SMALLINT        NOT NULL DEFAULT 1,
    provider           VARCHAR(30),
    provider_response  JSONB,
    success            BOOLEAN         NOT NULL,
    error_code         VARCHAR(50),
    error_message      TEXT,
    attempted_at       TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE notification_log IS 'Delivery attempt audit trail. One row per retry.';
CREATE INDEX IF NOT EXISTS idx_notif_log_notif ON notification_log(notification_id, attempted_at DESC);

-- ============================================================================
-- 4. EXPERT SYSTEM DOMAIN (4 tables)
-- ============================================================================

-- ── experts ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS experts (
    expert_id           UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID            UNIQUE REFERENCES users(user_id) ON DELETE SET NULL,
    full_name           VARCHAR(100)    NOT NULL,
    specialty           VARCHAR(50)     NOT NULL
                                        CHECK (specialty IN ('physician', 'dietitian', 'trainer', 'mental_health', 'sleep_specialist', 'pharmacist', 'other')),
    license_number      VARCHAR(50)     UNIQUE,
    license_country     CHAR(3)         DEFAULT 'KOR',
    license_verified_at TIMESTAMPTZ,
    bio                 TEXT,
    languages           TEXT[]          DEFAULT ARRAY['ko'],
    avg_rating          NUMERIC(3,2)    DEFAULT 0.00 CHECK (avg_rating BETWEEN 0 AND 5),
    review_count        INT             DEFAULT 0,
    hourly_rate_krw     NUMERIC(10,2),
    is_active           BOOLEAN         DEFAULT true,
    created_at          TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE experts IS 'Certified experts available for user consultations. License_verified_at gates visibility.';
CREATE INDEX IF NOT EXISTS idx_experts_specialty ON experts(specialty) WHERE is_active = true AND license_verified_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_experts_rating    ON experts(avg_rating DESC);

-- ── expert_availability ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS expert_availability (
    availability_id    BIGSERIAL       PRIMARY KEY,
    expert_id          UUID            NOT NULL REFERENCES experts(expert_id) ON DELETE CASCADE,
    day_of_week        SMALLINT        NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time         TIME            NOT NULL,
    end_time           TIME            NOT NULL CHECK (end_time > start_time),
    slot_duration_min  SMALLINT        DEFAULT 30,
    timezone           VARCHAR(50)     DEFAULT 'Asia/Seoul',
    effective_from     DATE,
    effective_until    DATE,
    UNIQUE (expert_id, day_of_week, start_time)
);

COMMENT ON TABLE expert_availability IS 'Expert recurring weekly availability. Consultations booked within these windows.';
CREATE INDEX IF NOT EXISTS idx_expert_avail_expert ON expert_availability(expert_id);

-- ── expert_consultations ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS expert_consultations (
    consultation_id    UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID            NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    expert_id          UUID            NOT NULL REFERENCES experts(expert_id) ON DELETE RESTRICT,
    scheduled_at       TIMESTAMPTZ     NOT NULL,
    duration_min       SMALLINT        NOT NULL DEFAULT 30,
    status             VARCHAR(20)     DEFAULT 'scheduled'
                                       CHECK (status IN ('scheduled', 'in_progress', 'completed', 'canceled_by_user', 'canceled_by_expert', 'no_show')),
    topic              VARCHAR(200),
    user_notes         TEXT,
    expert_notes       TEXT,
    prescribed_plan    JSONB,
    video_call_url     TEXT,
    price_krw          NUMERIC(10,2),
    paid_at            TIMESTAMPTZ,
    created_at         TIMESTAMPTZ     DEFAULT NOW(),
    completed_at       TIMESTAMPTZ
);

COMMENT ON TABLE expert_consultations IS 'Booked expert sessions. prescribed_plan JSONB feeds back into personal HRT.';
CREATE INDEX IF NOT EXISTS idx_consult_user_sched   ON expert_consultations(user_id, scheduled_at DESC);
CREATE INDEX IF NOT EXISTS idx_consult_expert_sched ON expert_consultations(expert_id, scheduled_at DESC);
CREATE INDEX IF NOT EXISTS idx_consult_status       ON expert_consultations(status, scheduled_at) WHERE status IN ('scheduled', 'in_progress');

-- ── expert_reviews ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS expert_reviews (
    review_id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    consultation_id    UUID            UNIQUE NOT NULL REFERENCES expert_consultations(consultation_id) ON DELETE CASCADE,
    expert_id          UUID            NOT NULL REFERENCES experts(expert_id) ON DELETE CASCADE,
    user_id            UUID            NOT NULL REFERENCES users(user_id) ON DELETE SET NULL,
    rating             SMALLINT        NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment            TEXT,
    is_anonymous       BOOLEAN         DEFAULT false,
    expert_reply       TEXT,
    created_at         TIMESTAMPTZ     DEFAULT NOW(),
    updated_at         TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE expert_reviews IS 'User reviews of experts. One review per consultation. Updates experts.avg_rating via trigger.';
CREATE INDEX IF NOT EXISTS idx_expert_reviews_expert ON expert_reviews(expert_id, created_at DESC);

-- ============================================================================
-- 5. SHARED / HELPER TABLES (3 tables)
-- ============================================================================

-- ── app_metadata ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS app_metadata (
    platform           VARCHAR(20)     PRIMARY KEY CHECK (platform IN ('ios', 'android', 'web', 'glasses_firmware')),
    current_version    VARCHAR(30)     NOT NULL,
    minimum_version    VARCHAR(30)     NOT NULL,
    release_notes_url  TEXT,
    force_upgrade      BOOLEAN         DEFAULT false,
    updated_at         TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE app_metadata IS 'Per-platform app version gating. Clients below minimum_version must upgrade.';

-- ── localization_strings ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS localization_strings (
    string_id          SERIAL          PRIMARY KEY,
    string_key         VARCHAR(150)    NOT NULL,
    locale             VARCHAR(10)     NOT NULL,
    value              TEXT            NOT NULL,
    context            VARCHAR(100),
    updated_at         TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE (string_key, locale)
);

COMMENT ON TABLE localization_strings IS 'Server-side i18n. Client bundles are separate; this is for server-composed content.';
CREATE INDEX IF NOT EXISTS idx_loc_key_locale ON localization_strings(string_key, locale);

-- ── legal_consents ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS legal_consents (
    consent_id         BIGSERIAL       PRIMARY KEY,
    user_id            UUID            NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    document_code      VARCHAR(50)     NOT NULL,
    document_version   VARCHAR(20)     NOT NULL,
    accepted_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    ip_address         INET,
    user_agent         TEXT,
    withdrawn_at       TIMESTAMPTZ,
    UNIQUE (user_id, document_code, document_version)
);

COMMENT ON TABLE legal_consents IS 'Legal consent records. Required for GDPR/PIPA compliance. Never delete, withdraw only.';
CREATE INDEX IF NOT EXISTS idx_legal_consents_user ON legal_consents(user_id, document_code);

-- ============================================================================
-- 6. HELPER TRIGGERS
-- ============================================================================

-- Auto-update *.updated_at on UPDATE
CREATE OR REPLACE FUNCTION _touch_updated_at() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at              ON users;
DROP TRIGGER IF EXISTS trg_user_profiles_updated_at      ON user_profiles;
DROP TRIGGER IF EXISTS trg_user_settings_updated_at      ON user_settings;
DROP TRIGGER IF EXISTS trg_notification_prefs_updated_at ON notification_preferences;
DROP TRIGGER IF EXISTS trg_expert_reviews_updated_at     ON expert_reviews;

CREATE TRIGGER trg_users_updated_at                 BEFORE UPDATE ON users                     FOR EACH ROW EXECUTE FUNCTION _touch_updated_at();
CREATE TRIGGER trg_user_profiles_updated_at         BEFORE UPDATE ON user_profiles             FOR EACH ROW EXECUTE FUNCTION _touch_updated_at();
CREATE TRIGGER trg_user_settings_updated_at         BEFORE UPDATE ON user_settings             FOR EACH ROW EXECUTE FUNCTION _touch_updated_at();
CREATE TRIGGER trg_notification_prefs_updated_at    BEFORE UPDATE ON notification_preferences  FOR EACH ROW EXECUTE FUNCTION _touch_updated_at();
CREATE TRIGGER trg_expert_reviews_updated_at        BEFORE UPDATE ON expert_reviews            FOR EACH ROW EXECUTE FUNCTION _touch_updated_at();

-- Recompute experts.avg_rating + review_count on review insert/update/delete
CREATE OR REPLACE FUNCTION _recompute_expert_rating() RETURNS TRIGGER AS $$
DECLARE
    tgt_expert UUID;
BEGIN
    tgt_expert := COALESCE(NEW.expert_id, OLD.expert_id);
    UPDATE experts SET
        avg_rating   = COALESCE((SELECT AVG(rating)::NUMERIC(3,2) FROM expert_reviews WHERE expert_id = tgt_expert), 0),
        review_count = (SELECT COUNT(*) FROM expert_reviews WHERE expert_id = tgt_expert)
    WHERE expert_id = tgt_expert;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_expert_review_rating ON expert_reviews;

CREATE TRIGGER trg_expert_review_rating
    AFTER INSERT OR UPDATE OR DELETE ON expert_reviews
    FOR EACH ROW EXECUTE FUNCTION _recompute_expert_rating();

-- ============================================================================
-- 7. ROW-LEVEL SECURITY
-- ============================================================================
-- NOTE: All RLS policies reference `user_id = auth.uid()` because migration 001
-- stores user_id as UUID and Supabase Auth's auth.uid() returns UUID directly.
-- The v4 plan's `get_my_user_id()` helper is NOT needed under this schema.
-- See docs/HRT_MULTIDIMENSIONAL_DRILLDOWN.md §10.2 for the reconciliation note.

ALTER TABLE users                     ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_profiles             ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_settings             ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_devices              ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_subscriptions        ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_activity_log         ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications             ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_preferences  ENABLE ROW LEVEL SECURITY;
ALTER TABLE expert_consultations      ENABLE ROW LEVEL SECURITY;
ALTER TABLE expert_reviews            ENABLE ROW LEVEL SECURITY;
ALTER TABLE legal_consents            ENABLE ROW LEVEL SECURITY;

-- Drop stale policies if any were created by an earlier (failed) attempt
DROP POLICY IF EXISTS users_self_select     ON users;
DROP POLICY IF EXISTS users_self_update     ON users;
DROP POLICY IF EXISTS profiles_self_all     ON user_profiles;
DROP POLICY IF EXISTS settings_self_all     ON user_settings;
DROP POLICY IF EXISTS devices_self_all      ON user_devices;
DROP POLICY IF EXISTS subs_self_select      ON user_subscriptions;
DROP POLICY IF EXISTS activity_self_select  ON user_activity_log;
DROP POLICY IF EXISTS notif_self_all        ON notifications;
DROP POLICY IF EXISTS notif_prefs_self_all  ON notification_preferences;
DROP POLICY IF EXISTS consult_self_all      ON expert_consultations;
DROP POLICY IF EXISTS reviews_self_all      ON expert_reviews;
DROP POLICY IF EXISTS consents_self_all     ON legal_consents;
DROP POLICY IF EXISTS consult_expert_select ON expert_consultations;
DROP POLICY IF EXISTS reviews_expert_select ON expert_reviews;

-- users table — the PK column is user_id (from migration 001)
CREATE POLICY users_self_select        ON users                     FOR SELECT USING (user_id = auth.uid());
CREATE POLICY users_self_update        ON users                     FOR UPDATE USING (user_id = auth.uid());

-- child tables — all their user_id columns are UUID FKs to users(user_id)
CREATE POLICY profiles_self_all        ON user_profiles             FOR ALL    USING (user_id = auth.uid());
CREATE POLICY settings_self_all        ON user_settings             FOR ALL    USING (user_id = auth.uid());
CREATE POLICY devices_self_all         ON user_devices              FOR ALL    USING (user_id = auth.uid());
CREATE POLICY subs_self_select         ON user_subscriptions        FOR SELECT USING (user_id = auth.uid());
CREATE POLICY activity_self_select     ON user_activity_log         FOR SELECT USING (user_id = auth.uid());
CREATE POLICY notif_self_all           ON notifications             FOR ALL    USING (user_id = auth.uid());
CREATE POLICY notif_prefs_self_all     ON notification_preferences  FOR ALL    USING (user_id = auth.uid());
CREATE POLICY consult_self_all         ON expert_consultations      FOR ALL    USING (user_id = auth.uid());
CREATE POLICY reviews_self_all         ON expert_reviews            FOR ALL    USING (user_id = auth.uid());
CREATE POLICY consents_self_all        ON legal_consents            FOR ALL    USING (user_id = auth.uid());

-- Experts can also read consultations + reviews where they are the expert
CREATE POLICY consult_expert_select    ON expert_consultations      FOR SELECT USING (expert_id IN (SELECT expert_id FROM experts WHERE user_id = auth.uid()));
CREATE POLICY reviews_expert_select    ON expert_reviews            FOR SELECT USING (expert_id IN (SELECT expert_id FROM experts WHERE user_id = auth.uid()));

-- ============================================================================
-- 8. VERIFICATION QUERY
-- ============================================================================
-- After running this migration, verify with:
--   SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;
--
-- Expected NEW tables added by this migration (21):
--   admin_audit_log, admin_permissions, admin_users, app_metadata,
--   expert_availability, expert_consultations, expert_reviews, experts,
--   feature_flags, legal_consents, localization_strings, notification_log,
--   notification_preferences, notification_templates, notifications,
--   system_config, user_activity_log, user_devices, user_profiles,
--   user_settings, user_subscriptions
--
-- Plus `users` is EXTENDED (not created) with 11 new columns.
-- Verify with: \d users  — should show original columns from 001 plus
--   email, phone, display_name, avatar_url, locale, timezone, account_status,
--   email_verified_at, updated_at, last_login_at, deleted_at.
-- ============================================================================
