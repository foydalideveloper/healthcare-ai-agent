-- Migration 008 — OCR v2 recall improvements (Fixes 1-4)
-- ─────────────────────────────────────────────────────────────────────
-- Builds on migration 007 (v3 modality columns). Adds 4 new columns
-- powering the dashboard's "panels detected", "value updates", and
-- "timeline" sub-sections on the existing v3 panels. All NULL-able for
-- backward compat — old rows from migration 007 keep loading cleanly.
--
-- frame_sampling_rate    INTEGER   - 8 (cheap path), 20 (mid), or 60 (broadcast @1fps)
-- panels_detected        JSONB     - list of bboxes (DBSCAN clusters) per chunk
-- value_updates          JSONB     - cross-frame metric updates per chunk
--                                    [{label, values:[{value,frame_idx,timestamp_sec}], change_count, first_seen_sec, last_seen_sec}]
-- timeline               JSONB     - per-sub-window narrative (Fix 4)
--                                    [{window_sec, summary, key_items}]
--
-- Idempotent: every column is gated by IF NOT EXISTS.

ALTER TABLE public.lifelog_event
  ADD COLUMN IF NOT EXISTS frame_sampling_rate INTEGER,
  ADD COLUMN IF NOT EXISTS panels_detected     JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS value_updates       JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS timeline            JSONB DEFAULT '[]'::jsonb;

-- Partial index for "find all events where a value actually changed".
CREATE INDEX IF NOT EXISTS idx_lifelog_event_has_value_updates
  ON public.lifelog_event (user_id, observed_at DESC)
  WHERE jsonb_array_length(value_updates) > 0;

COMMENT ON COLUMN public.lifelog_event.frame_sampling_rate IS 'v3.1 Fix 1: how many frames were OCR''d per chunk (8/20/60)';
COMMENT ON COLUMN public.lifelog_event.panels_detected     IS 'v3.1 Fix 2: DBSCAN panel bboxes detected on the chunk''s frames';
COMMENT ON COLUMN public.lifelog_event.value_updates       IS 'v3.1 Fix 3: cross-frame metric updates ({label, values[], ...})';
COMMENT ON COLUMN public.lifelog_event.timeline            IS 'v3.1 Fix 4: per-sub-window narrative ({window_sec, summary, key_items})';
