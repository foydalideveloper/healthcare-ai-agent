-- Migration 009 — v3.2 detailed enumeration ("359 items problem")
--
-- Adds a flat list of one-sentence plain-English facts, ONE per significant
-- captured item (every number / ticker / % / currency / headline / OCR item).
-- The watcher (_lifelog_test.py) populates it from the LLM's new
-- `enumerated_observations` field; the dashboard renders it under
-- "Observed Facts" so the user can SEE every captured item instead of the
-- ~6-10 high-level bullets the model used to compress everything into.
--
-- Apply: paste into the Supabase SQL Editor and Run.
--   https://supabase.com/dashboard/project/klnykuxzucujahucvbct/sql/new

ALTER TABLE public.lifelog_event
  ADD COLUMN IF NOT EXISTS enumerated_observations JSONB DEFAULT '[]'::jsonb;

-- Index on list length so we can quickly find rows with rich enumeration
-- (e.g. dashboard "most-detailed clips" or recall-health queries).
CREATE INDEX IF NOT EXISTS lifelog_event_enum_obs_count_idx
  ON public.lifelog_event ((jsonb_array_length(enumerated_observations)));
