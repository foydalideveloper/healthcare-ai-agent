-- ============================================================================
-- Healthcare AI Agent - Migration 003: Agent Context + Agent Memory
-- Triple-H Co., Ltd. | 2026-04-22
-- Patent No. 10-2025-0145274
--
-- Resolves v4.1 reconciliation item R8:
--   OpenClaw SoulSpec runtime model at 100K scale.
--   USER.md + MEMORY.md cannot exist as per-user flat files (200K files
--   unmanageable). Must be hydrated from DB tables at runtime.
--
-- Adds 2 tables:
--   agent_user_context  - Replaces per-user USER.md flat files
--   agent_memory        - Replaces per-user MEMORY.md flat files
--
-- ────────────────────────────────────────────────────────────────────────────
-- POST-AUDIT CLARIFICATIONS (ground truth discovered 2026-04-22):
-- ────────────────────────────────────────────────────────────────────────────
-- The earlier draft of this migration (003_food_med_agent_tables.sql) also
-- tried to create user_food_log + user_medication. That was based on the
-- v4.1 PDF R7 claim that those tables didn't exist. A direct DB audit
-- showed they DO exist and have data (9 food_log rows, 1 medication row).
-- R7 is therefore RESOLVED — no migration needed for food_log/medication.
--
-- Only R8 remains. This migration adds just those 2 tables.
--
-- Also confirmed in the audit:
--   - users.user_id is BIGINT (not UUID as v4.1 R3 claimed)
--   - get_my_user_id() helper DOES exist in the DB (maps auth.uid() UUID
--     via users.auth_user_id → users.user_id BIGINT)
--   - This migration uses BIGINT FKs matching deployed reality
-- ────────────────────────────────────────────────────────────────────────────
--
-- PREREQUISITES:
--   - users table exists with user_id BIGINT PK
--   - pgcrypto extension enabled (for gen_random_uuid if needed)
--
-- IDEMPOTENT: Uses IF NOT EXISTS everywhere — safe to re-run.
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. agent_user_context — Per-user hydrated agent context (R8)
-- ============================================================================
-- Each row = one agent's context for one user.
-- At runtime, the agent loads {placeholder} USER.md template from the repo
-- and hydrates it with values from this row's context_json.
-- ============================================================================

CREATE TABLE IF NOT EXISTS agent_user_context (
    context_id       BIGSERIAL     PRIMARY KEY,
    user_id          BIGINT        NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    agent_name       VARCHAR(100)  NOT NULL,
    template_version VARCHAR(20)   DEFAULT '1.0',
    context_json     JSONB         NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ   DEFAULT NOW(),
    updated_at       TIMESTAMPTZ   DEFAULT NOW(),
    UNIQUE (user_id, agent_name)
);

CREATE INDEX IF NOT EXISTS idx_agent_context_user
    ON agent_user_context(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_context_agent
    ON agent_user_context(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_context_gin
    ON agent_user_context USING GIN (context_json jsonb_path_ops);

COMMENT ON TABLE agent_user_context IS
    'R8: Per-user hydrated agent context. Replaces per-user USER.md flat files at 100K scale.';
COMMENT ON COLUMN agent_user_context.context_json IS
    'Example shape: {"allergies": ["peanut"], "chronic": ["hypertension"], "goals": ["lose 5kg"], "preferences": {"language": "ko", "response_length": "short"}}';


-- ============================================================================
-- 2. agent_memory — Cross-conversation persistent agent memory (R8)
-- ============================================================================
-- Each row = one fact/observation/preference an agent remembers across chats.
-- Importance field lets the runtime GC low-value memories first.
-- ============================================================================

CREATE TABLE IF NOT EXISTS agent_memory (
    memory_id        BIGSERIAL     PRIMARY KEY,
    user_id          BIGINT        NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    agent_name       VARCHAR(100)  NOT NULL,
    memory_type      VARCHAR(30)   NOT NULL DEFAULT 'fact'
        CHECK (memory_type IN ('fact', 'preference', 'goal', 'observation', 'feedback', 'reminder')),
    memory_key       VARCHAR(200)  NOT NULL,
    memory_value     TEXT          NOT NULL,
    importance       SMALLINT      DEFAULT 5
        CHECK (importance BETWEEN 1 AND 10),
    source           VARCHAR(100),
    created_at       TIMESTAMPTZ   DEFAULT NOW(),
    last_accessed_at TIMESTAMPTZ   DEFAULT NOW(),
    access_count     INTEGER       DEFAULT 0,
    expires_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_agent_memory_user_agent
    ON agent_memory(user_id, agent_name, importance DESC);
CREATE INDEX IF NOT EXISTS idx_agent_memory_type
    ON agent_memory(user_id, memory_type, importance DESC);
CREATE INDEX IF NOT EXISTS idx_agent_memory_expires
    ON agent_memory(expires_at)
    WHERE expires_at IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_memory_unique
    ON agent_memory(user_id, agent_name, memory_key);

COMMENT ON TABLE agent_memory IS
    'R8: Cross-conversation agent memory. Replaces per-user MEMORY.md flat files at 100K scale.';
COMMENT ON COLUMN agent_memory.importance IS
    '1 = ephemeral (GC first), 10 = critical (never expire)';
COMMENT ON COLUMN agent_memory.memory_type IS
    'fact | preference | goal | observation | feedback | reminder';


-- ============================================================================
-- 3. RLS — Aligned with existing pattern (get_my_user_id helper exists)
-- ============================================================================
-- Other tables in this DB use auth-gated RLS via the get_my_user_id() helper.
-- Following the same pattern for consistency.
-- ============================================================================

ALTER TABLE agent_user_context ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_memory       ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agent_user_context_own ON agent_user_context;
CREATE POLICY agent_user_context_own ON agent_user_context
    FOR ALL
    USING (user_id = get_my_user_id())
    WITH CHECK (user_id = get_my_user_id());

DROP POLICY IF EXISTS agent_memory_own ON agent_memory;
CREATE POLICY agent_memory_own ON agent_memory
    FOR ALL
    USING (user_id = get_my_user_id())
    WITH CHECK (user_id = get_my_user_id());


COMMIT;

-- ============================================================================
-- VERIFICATION QUERIES (run after migration)
-- ============================================================================
-- 1. Confirm both tables exist:
-- SELECT table_name FROM information_schema.tables
-- WHERE table_schema = 'public'
--   AND table_name IN ('agent_user_context', 'agent_memory');
--
-- 2. Confirm BIGINT FK type:
-- SELECT column_name, data_type FROM information_schema.columns
-- WHERE table_name IN ('agent_user_context', 'agent_memory')
--   AND column_name = 'user_id';
-- Expected: bigint for both
--
-- 3. Confirm RLS enabled:
-- SELECT tablename, rowsecurity FROM pg_tables
-- WHERE schemaname = 'public'
--   AND tablename IN ('agent_user_context', 'agent_memory');
-- Expected: rowsecurity = true for both
-- ============================================================================
