-- Migration 007 — 4-pass OCR pipeline columns
-- ─────────────────────────────────────────────────────────────────────
-- Adds 6 columns to lifelog_event to store the new modality-separated
-- extraction output (PaddleOCR sweep + VLM enrichment). All are NULL-able
-- so historical rows (pre-v3 schema) keep loading cleanly.
--
-- video_extraction   JSONB     - { ocr_text_full[], visual_objects[], screen_content{}, broadcast_mode }
-- audio_extraction   JSONB     - { transcript_full, speaker_count_estimate, audio_events[], language_detected, audio_quality }
-- combined_analysis  JSONB     - { what_is_happening, cross_modal_confidence, user_activity_inferred, importance_score, recall_estimate }
-- ocr_text_full      TEXT      - flat denormalized OCR dump (convenience for full-text search)
-- recall_estimate    REAL      - mirrors combined_analysis.recall_estimate (convenience for filtering)
-- broadcast_mode     BOOLEAN   - mirrors video_extraction.broadcast_mode (convenience for filtering)
--
-- Idempotent: every ADD COLUMN is gated by IF NOT EXISTS so re-applying is safe.

ALTER TABLE public.lifelog_event
  ADD COLUMN IF NOT EXISTS video_extraction   JSONB,
  ADD COLUMN IF NOT EXISTS audio_extraction   JSONB,
  ADD COLUMN IF NOT EXISTS combined_analysis  JSONB,
  ADD COLUMN IF NOT EXISTS ocr_text_full      TEXT,
  ADD COLUMN IF NOT EXISTS recall_estimate    REAL,
  ADD COLUMN IF NOT EXISTS broadcast_mode     BOOLEAN DEFAULT FALSE;

-- Index on broadcast_mode for the dashboard's "show only broadcast clips"
-- filter. Partial index because most rows will have broadcast_mode = false.
CREATE INDEX IF NOT EXISTS idx_lifelog_event_broadcast_mode
  ON public.lifelog_event (user_id, observed_at DESC)
  WHERE broadcast_mode = TRUE;

-- Index on recall_estimate for "low-recall events that may need re-extraction".
CREATE INDEX IF NOT EXISTS idx_lifelog_event_recall_low
  ON public.lifelog_event (user_id, observed_at DESC)
  WHERE recall_estimate IS NOT NULL AND recall_estimate < 0.4;

COMMENT ON COLUMN public.lifelog_event.video_extraction  IS 'v3: per-frame OCR + visual objects + screen-content sub-objects';
COMMENT ON COLUMN public.lifelog_event.audio_extraction  IS 'v3: transcript + audio events + language + quality';
COMMENT ON COLUMN public.lifelog_event.combined_analysis IS 'v3: cross-modal synthesis + recall_estimate (0-1)';
COMMENT ON COLUMN public.lifelog_event.ocr_text_full     IS 'v3: flat denormalized OCR dump for full-text search';
COMMENT ON COLUMN public.lifelog_event.recall_estimate   IS 'v3: mirror of combined_analysis.recall_estimate';
COMMENT ON COLUMN public.lifelog_event.broadcast_mode    IS 'v3: mirror of video_extraction.broadcast_mode';
