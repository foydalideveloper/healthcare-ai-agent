-- Migration 007: Lifelog event table
-- Captures every observable activity, interaction, conversation, etc.
-- extracted by AI-glasses video processing. ONE row per event.
-- The source_model column lets us run BOTH Gemma 4 E4B AND Qwen 3.5 VLM
-- on the same video and compare what each found.
--
-- Why one wide table instead of per-category tables: lifelog is exploratory.
-- We don't know yet which categories produce signal worth its own schema.
-- After 2-4 weeks of real captures, we'll know which fields are noisy and
-- which deserve dedicated tables (e.g. interactions, purchases). Until then,
-- the wide table + JSONB extras is the fastest path to "see the data."

CREATE TABLE IF NOT EXISTS lifelog_event (
    lifelog_id         BIGSERIAL PRIMARY KEY,
    user_id            BIGINT NOT NULL,

    -- When + how long
    observed_at        TIMESTAMPTZ NOT NULL,
    duration_sec       INTEGER,

    -- What kind + short description
    category           VARCHAR(50),
    description        TEXT NOT NULL,

    -- Social context
    people             JSONB,                 -- ["boss","colleague"]
    people_count       SMALLINT,

    -- Spatial context
    location           VARCHAR(50),
    indoor_outdoor     VARCHAR(20),

    -- Physical state
    posture            VARCHAR(30),
    mood               VARCHAR(30),
    energy_signs       VARCHAR(30),

    -- Activity details
    objects            JSONB,                 -- ["laptop","coffee mug"]
    screen             TEXT,
    topic              TEXT,
    decision           TEXT,
    audio_heard        TEXT,
    numbers_mentioned  TEXT,

    -- Health overlap (still keeps cross-link with healthcare tables)
    kcal               INTEGER,
    amount_ml          INTEGER,

    -- Provenance
    source_model       VARCHAR(30) NOT NULL,  -- 'gemma_4_e4b' | 'qwen_3_5_vlm' | 'merged'
    source_video       TEXT,
    chunk_idx          SMALLINT,
    raw_event          JSONB,                 -- the full original JSON event

    created_at         TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lifelog_user_time   ON lifelog_event(user_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_lifelog_category    ON lifelog_event(category);
CREATE INDEX IF NOT EXISTS idx_lifelog_source      ON lifelog_event(source_model);
CREATE INDEX IF NOT EXISTS idx_lifelog_source_user ON lifelog_event(source_model, user_id, observed_at DESC);

COMMENT ON TABLE lifelog_event IS
  'Every observable event extracted from AI-glasses video by Gemma 4 / Qwen 3.5 VLM.
   Lifelog (full-day activity log), not just health. Dual-source for model comparison.';
COMMENT ON COLUMN lifelog_event.source_model IS
  'Which multimodal LLM extracted this event. Allows side-by-side comparison.';
COMMENT ON COLUMN lifelog_event.raw_event IS
  'The complete original JSON event from the model output, for debugging or
   field-recovery if we later add a column we did not capture.';
