-- ============================================================================
-- Healthcare AI Agent - Migration 006: Intake-based Medicine + Goal-Relative Intensity
-- Triple-H Co., Ltd. | 2026-04-24
-- Patent No. 10-2025-0145274
--
-- Addresses the "dashboard is lying" concern from the user:
--   "Did you put Vitamin D on all days? Will it show tomorrow Apr 25 even if
--   I don't actually take it?"
--
-- YES, under migration 005 it would have. Medication was being auto-expanded
-- from the prescription window [start_date, today]. That's a prescription
-- view, NOT a confirmed-intake view. This migration separates them.
--
-- Fix 4 (medicine intake vs prescription):
--   1. New table `user_medication_intake` records actual dose events with
--      taken_at timestamp (from voice reports, pill camera, manual entry).
--   2. `user_medication` keeps its role as prescription registry.
--   3. Drill-down `medicine` CTE now aggregates from user_medication_intake,
--      so empty days stay empty and tomorrow won't auto-show anything.
--   4. L4 hour now meaningful (actual taken_at hour, not meta created_at).
--
-- Fix 7 (goal-relative intensity):
--   Thresholds were hardcoded absolutes (200 kcal/hour = intensity 1, etc).
--   Now pull per-user targets from std_lifestyle_plan via user's demographic
--   category (users.age_group + users.gender → std_population_category.category_id).
--   Intensity computed as fraction-of-target. Fallback to KDRI/ACSM/EFSA
--   defaults for users without a matching category.
--
-- Also in this session (in code, not SQL):
--   - event_processor.write_medication now writes to user_medication_intake
--   - event_processor.write_food_log stamps nutrients_json with
--     portion_source + portion_confidence so the dashboard knows which
--     portion values are FOOD_DB lookups (high conf) vs 200g defaults
--     (low conf). FOOD_DB extended with breakfast/lunch/dinner/snack/meal
--     and drink (cup|bottle|glass) entries.
-- ============================================================================

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- Part 1 - user_medication_intake table (fix 4)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_medication_intake (
    intake_id    BIGSERIAL     PRIMARY KEY,
    user_id      BIGINT        NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    med_id       BIGINT        REFERENCES user_medication(med_id) ON DELETE SET NULL,
    drug_name    VARCHAR(255)  NOT NULL,
    drug_code    VARCHAR(50),
    dose         NUMERIC,
    unit         VARCHAR(20),
    taken_at     TIMESTAMPTZ   NOT NULL,
    source       VARCHAR(30)   NOT NULL DEFAULT 'voice_report'
                 CHECK (source IN ('voice_report','pill_camera','manual','wearable')),
    confidence   NUMERIC(3,2),
    notes        TEXT,
    created_at   TIMESTAMPTZ   DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_med_intake_user_time
    ON user_medication_intake(user_id, taken_at DESC);
CREATE INDEX IF NOT EXISTS idx_med_intake_drug
    ON user_medication_intake(user_id, drug_name);

ALTER TABLE user_medication_intake ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS med_intake_own ON user_medication_intake;
CREATE POLICY med_intake_own ON user_medication_intake
    FOR ALL
    USING (user_id = get_my_user_id())
    WITH CHECK (user_id = get_my_user_id());

COMMENT ON TABLE user_medication_intake IS
    'Confirmed dose events. Drives HRT medicine drill-down. Separate from user_medication (prescription registry).';


-- ─────────────────────────────────────────────────────────────────────────────
-- Part 2 - hrt_drilldown_full_unchecked: intake-based medicine + goal intensity
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.hrt_drilldown_full_unchecked(
    p_user_id bigint, p_level integer,
    p_year integer DEFAULT NULL::integer,
    p_month integer DEFAULT NULL::integer,
    p_day integer DEFAULT NULL::integer
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'public', 'auth', 'pg_temp'
AS $function$
DECLARE
    v_columns JSONB; v_start_ts TIMESTAMPTZ; v_end_ts TIMESTAMPTZ;
    v_bucket_type TEXT; v_rows JSONB;
    v_target_date DATE;
    v_drink_re    TEXT := '\y(drink|water|coffee|tea|juice|milk|물|커피|차|주스|우유|홍차|녹차|아이스티|라떼)\y';
    v_food_sfx_re TEXT := '\y(sandwich|cake|cookie|bread|pie|muffin|pastry|ice\s*cream|ice-cream|burger|pizza|sushi|curry|아이스크림|케이크|쿠키|빵|파이|무스|사탕)\y';
    v_cat_id                  BIGINT;
    v_target_food_daily       NUMERIC := 2500;  -- KDRI 2025 Korean male 30-39
    v_target_exercise_daily   NUMERIC := 30;    -- ACSM ≈ 150 min/week ÷ 5
    v_target_sleep_hours      NUMERIC := 7.5;   -- National Sleep Foundation
    v_target_hydration_daily  NUMERIC := 2500;  -- EFSA male adult
BEGIN
    SELECT c.category_id INTO v_cat_id
      FROM users u
      JOIN std_population_category c
        ON c.age_group = u.age_group AND c.gender = u.gender
     WHERE u.user_id = p_user_id LIMIT 1;

    IF v_cat_id IS NOT NULL THEN
        SELECT COALESCE((detail_json->>'daily_calories_kcal')::numeric, v_target_food_daily)
          INTO v_target_food_daily
          FROM std_lifestyle_plan WHERE category_id = v_cat_id AND plan_type = 'diet' LIMIT 1;
        SELECT COALESCE(((detail_json->>'weekly_aerobic_min')::numeric) / 7.0, v_target_exercise_daily)
          INTO v_target_exercise_daily
          FROM std_lifestyle_plan WHERE category_id = v_cat_id AND plan_type = 'exercise' LIMIT 1;
        SELECT COALESCE((detail_json->>'target_hours')::numeric, v_target_sleep_hours)
          INTO v_target_sleep_hours
          FROM std_lifestyle_plan WHERE category_id = v_cat_id AND plan_type = 'sleep' LIMIT 1;
    END IF;

    IF p_level = 1 THEN
        v_bucket_type := 'year';
        v_start_ts := '2020-01-01 00:00:00'::timestamp AT TIME ZONE 'Asia/Seoul';
        v_end_ts   := '2027-01-01 00:00:00'::timestamp AT TIME ZONE 'Asia/Seoul';
        SELECT jsonb_agg(jsonb_build_object('key', y::text, 'label', y::text) ORDER BY y) INTO v_columns
        FROM generate_series(2020, 2026) y;
    ELSIF p_level = 2 THEN
        v_bucket_type := 'month';
        v_start_ts := make_date(p_year, 1, 1)::timestamp AT TIME ZONE 'Asia/Seoul';
        v_end_ts   := make_date(p_year + 1, 1, 1)::timestamp AT TIME ZONE 'Asia/Seoul';
        SELECT jsonb_agg(jsonb_build_object('key', m::text, 'label', to_char(make_date(2000, m, 1), 'Mon')) ORDER BY m) INTO v_columns
        FROM generate_series(1, 12) m;
    ELSIF p_level = 3 THEN
        v_bucket_type := 'day';
        v_start_ts := make_date(p_year, p_month, 1)::timestamp AT TIME ZONE 'Asia/Seoul';
        v_end_ts   := (make_date(p_year, p_month, 1) + interval '1 month')::timestamp AT TIME ZONE 'Asia/Seoul';
        SELECT jsonb_agg(jsonb_build_object('key', d::text, 'label', d::text) ORDER BY d) INTO v_columns
        FROM generate_series(1, EXTRACT(DAY FROM (make_date(p_year, p_month, 1) + interval '1 month - 1 day'))::int) d;
    ELSIF p_level = 4 THEN
        v_bucket_type := 'hour';
        v_target_date := make_date(p_year, p_month, p_day);
        v_start_ts := v_target_date::timestamp AT TIME ZONE 'Asia/Seoul';
        v_end_ts   := v_start_ts + interval '1 day';
        SELECT jsonb_agg(jsonb_build_object('key', h::text, 'label', lpad(h::text, 2, '0') || ':00') ORDER BY h) INTO v_columns
        FROM generate_series(0, 23) h;
    ELSE RAISE EXCEPTION 'Invalid level: %. Must be 1-4.', p_level;
    END IF;

    WITH
    food AS (
        SELECT CASE v_bucket_type
            WHEN 'year'  THEN EXTRACT(YEAR  FROM consumed_at AT TIME ZONE 'Asia/Seoul')::int::text
            WHEN 'month' THEN EXTRACT(MONTH FROM consumed_at AT TIME ZONE 'Asia/Seoul')::int::text
            WHEN 'day'   THEN EXTRACT(DAY   FROM consumed_at AT TIME ZONE 'Asia/Seoul')::int::text
            WHEN 'hour'  THEN EXTRACT(HOUR  FROM consumed_at AT TIME ZONE 'Asia/Seoul')::int::text END AS bucket_key,
            COALESCE(SUM((nutrients_json->>'energy_kcal')::numeric), 0) AS val,
            COUNT(*) AS cnt,
            string_agg(DISTINCT food_name, ', ' ORDER BY food_name) AS detail
        FROM user_food_log
        WHERE user_id = p_user_id AND consumed_at >= v_start_ts AND consumed_at < v_end_ts
          AND NOT (food_name ~* v_drink_re AND food_name !~* v_food_sfx_re)
        GROUP BY bucket_key
    ),
    exercise AS (
        SELECT bucket_key, SUM(val) AS val, SUM(cnt) AS cnt, string_agg(DISTINCT detail, ', ') AS detail
        FROM (
            SELECT CASE v_bucket_type
                WHEN 'year'  THEN EXTRACT(YEAR  FROM recorded_date)::int::text
                WHEN 'month' THEN EXTRACT(MONTH FROM recorded_date)::int::text
                WHEN 'day'   THEN EXTRACT(DAY   FROM recorded_date)::int::text
                WHEN 'hour'  THEN COALESCE(
                    (SELECT EXTRACT(HOUR FROM MIN(e.detected_at) AT TIME ZONE 'Asia/Seoul')::int::text
                     FROM user_activity_event e
                     WHERE e.user_id = p_user_id AND e.event_type = 'voice_report'
                       AND (e.detected_at AT TIME ZONE 'Asia/Seoul')::date = v_target_date),
                    '0') END AS bucket_key,
                exercise_min AS val,
                CASE WHEN exercise_min > 0 THEN 1 ELSE 0 END AS cnt,
                exercise_type AS detail
            FROM user_lifestyle
            WHERE user_id = p_user_id
              AND recorded_date >= (v_start_ts AT TIME ZONE 'Asia/Seoul')::date
              AND recorded_date <  (v_end_ts   AT TIME ZONE 'Asia/Seoul')::date
              AND exercise_min > 0
        ) s GROUP BY bucket_key
    ),
    sleep AS (
        SELECT bucket_key, AVG(val) AS val, SUM(cnt) AS cnt, NULL::text AS detail
        FROM (
            SELECT CASE v_bucket_type
                WHEN 'year'  THEN EXTRACT(YEAR  FROM recorded_date)::int::text
                WHEN 'month' THEN EXTRACT(MONTH FROM recorded_date)::int::text
                WHEN 'day'   THEN EXTRACT(DAY   FROM recorded_date)::int::text END AS bucket_key,
                sleep_hours AS val,
                CASE WHEN sleep_hours IS NOT NULL THEN 1 ELSE 0 END AS cnt
            FROM user_lifestyle
            WHERE v_bucket_type IN ('year','month','day')
              AND user_id = p_user_id AND sleep_hours IS NOT NULL
              AND recorded_date >= (v_start_ts AT TIME ZONE 'Asia/Seoul')::date
              AND recorded_date <  (v_end_ts   AT TIME ZONE 'Asia/Seoul')::date
            UNION ALL
            SELECT EXTRACT(HOUR FROM h AT TIME ZONE 'Asia/Seoul')::int::text AS bucket_key,
                   1::numeric AS val, 1 AS cnt
            FROM user_lifestyle l,
                 LATERAL generate_series(
                    GREATEST(l.sleep_start, v_start_ts),
                    LEAST(l.sleep_end, v_end_ts) - interval '1 second',
                    interval '1 hour'
                 ) h
            WHERE v_bucket_type = 'hour' AND l.user_id = p_user_id
              AND l.sleep_start IS NOT NULL AND l.sleep_end IS NOT NULL
              AND l.sleep_start < v_end_ts AND l.sleep_end > v_start_ts
        ) s WHERE bucket_key IS NOT NULL GROUP BY bucket_key
    ),
    medicine AS (
        SELECT CASE v_bucket_type
            WHEN 'year'  THEN EXTRACT(YEAR  FROM taken_at AT TIME ZONE 'Asia/Seoul')::int::text
            WHEN 'month' THEN EXTRACT(MONTH FROM taken_at AT TIME ZONE 'Asia/Seoul')::int::text
            WHEN 'day'   THEN EXTRACT(DAY   FROM taken_at AT TIME ZONE 'Asia/Seoul')::int::text
            WHEN 'hour'  THEN EXTRACT(HOUR  FROM taken_at AT TIME ZONE 'Asia/Seoul')::int::text END AS bucket_key,
            COUNT(DISTINCT drug_name)::numeric AS val, COUNT(*) AS cnt,
            string_agg(DISTINCT drug_name, ', ' ORDER BY drug_name) AS detail
        FROM user_medication_intake
        WHERE user_id = p_user_id AND taken_at >= v_start_ts AND taken_at < v_end_ts
        GROUP BY bucket_key
    ),
    biometrics AS (
        SELECT CASE v_bucket_type
            WHEN 'year'  THEN EXTRACT(YEAR  FROM measured_at AT TIME ZONE 'Asia/Seoul')::int::text
            WHEN 'month' THEN EXTRACT(MONTH FROM measured_at AT TIME ZONE 'Asia/Seoul')::int::text
            WHEN 'day'   THEN EXTRACT(DAY   FROM measured_at AT TIME ZONE 'Asia/Seoul')::int::text
            WHEN 'hour'  THEN EXTRACT(HOUR  FROM measured_at AT TIME ZONE 'Asia/Seoul')::int::text END AS bucket_key,
            ROUND(AVG(heart_rate)   FILTER (WHERE heart_rate   IS NOT NULL)::numeric, 0) AS avg_hr,
            ROUND(AVG(spo2)         FILTER (WHERE spo2         IS NOT NULL)::numeric, 0) AS avg_spo2,
            ROUND(AVG(glucose_mgdl) FILTER (WHERE glucose_mgdl IS NOT NULL)::numeric, 0) AS avg_glucose,
            ROUND(AVG(body_temp)    FILTER (WHERE body_temp    IS NOT NULL)::numeric, 1) AS avg_temp,
            COUNT(*) FILTER (WHERE heart_rate IS NOT NULL OR spo2 IS NOT NULL
                               OR glucose_mgdl IS NOT NULL OR body_temp IS NOT NULL) AS cnt
        FROM user_biometric
        WHERE user_id = p_user_id AND measured_at >= v_start_ts AND measured_at < v_end_ts
        GROUP BY bucket_key
    ),
    mental AS (
        SELECT CASE v_bucket_type
            WHEN 'year'  THEN EXTRACT(YEAR  FROM measured_at AT TIME ZONE 'Asia/Seoul')::int::text
            WHEN 'month' THEN EXTRACT(MONTH FROM measured_at AT TIME ZONE 'Asia/Seoul')::int::text
            WHEN 'day'   THEN EXTRACT(DAY   FROM measured_at AT TIME ZONE 'Asia/Seoul')::int::text
            WHEN 'hour'  THEN EXTRACT(HOUR  FROM measured_at AT TIME ZONE 'Asia/Seoul')::int::text END AS bucket_key,
            ROUND(AVG(stress_level)::numeric, 1) AS val,
            COUNT(*) FILTER (WHERE stress_level IS NOT NULL) AS cnt, NULL::text AS detail
        FROM user_health_level
        WHERE user_id = p_user_id AND measured_at >= v_start_ts AND measured_at < v_end_ts
          AND stress_level IS NOT NULL
        GROUP BY bucket_key
    ),
    hydration AS (
        SELECT CASE v_bucket_type
            WHEN 'year'  THEN EXTRACT(YEAR  FROM consumed_at AT TIME ZONE 'Asia/Seoul')::int::text
            WHEN 'month' THEN EXTRACT(MONTH FROM consumed_at AT TIME ZONE 'Asia/Seoul')::int::text
            WHEN 'day'   THEN EXTRACT(DAY   FROM consumed_at AT TIME ZONE 'Asia/Seoul')::int::text
            WHEN 'hour'  THEN EXTRACT(HOUR  FROM consumed_at AT TIME ZONE 'Asia/Seoul')::int::text END AS bucket_key,
            COALESCE(SUM(portion_g), 0) AS val, COUNT(*) AS cnt,
            string_agg(DISTINCT food_name, ', ' ORDER BY food_name) AS detail
        FROM user_food_log
        WHERE user_id = p_user_id AND consumed_at >= v_start_ts AND consumed_at < v_end_ts
          AND food_name ~* v_drink_re AND food_name !~* v_food_sfx_re
        GROUP BY bucket_key
    )
    SELECT jsonb_build_array(
        jsonb_build_object('category_id','food','category_name','Food & Nutrition','category_icon','/icons/food.png',
            'cells', COALESCE((SELECT jsonb_object_agg(bucket_key, jsonb_build_object(
                'value', to_char(val, 'FM999,999,999') || ' kcal', 'count', cnt,
                'intensity', LEAST(5, GREATEST(1, CASE
                    WHEN v_bucket_type='hour'  THEN (val / (v_target_food_daily / 5.0))::int
                    WHEN v_bucket_type='day'   THEN CASE
                        WHEN val < v_target_food_daily * 0.4 THEN 1
                        WHEN val < v_target_food_daily * 0.8 THEN 2
                        WHEN val < v_target_food_daily * 1.1 THEN 3
                        WHEN val < v_target_food_daily * 1.3 THEN 4
                        ELSE 5 END
                    WHEN v_bucket_type='month' THEN (val / (v_target_food_daily * 30))::int
                    ELSE (val / (v_target_food_daily * 365))::int END)),
                'details', CASE WHEN detail IS NOT NULL THEN jsonb_build_array(detail) ELSE '[]'::jsonb END))
                FROM food WHERE bucket_key IS NOT NULL AND cnt > 0), '{}'::jsonb)),
        jsonb_build_object('category_id','exercise','category_name','Exercise','category_icon','/icons/exercise.webp',
            'cells', COALESCE((SELECT jsonb_object_agg(bucket_key, jsonb_build_object(
                'value', val::text || ' min' || COALESCE(' (' || detail || ')', ''), 'count', cnt,
                'intensity', LEAST(5, GREATEST(1, CASE
                    WHEN v_bucket_type='day' THEN CASE
                        WHEN val < v_target_exercise_daily * 0.3 THEN 1
                        WHEN val < v_target_exercise_daily * 0.8 THEN 2
                        WHEN val < v_target_exercise_daily * 1.2 THEN 3
                        WHEN val < v_target_exercise_daily * 1.8 THEN 4
                        ELSE 5 END
                    WHEN v_bucket_type='hour' THEN GREATEST(1, (val / v_target_exercise_daily * 5)::int)
                    ELSE (val / (v_target_exercise_daily * 30))::int END))))
                FROM exercise WHERE bucket_key IS NOT NULL AND val > 0), '{}'::jsonb)),
        jsonb_build_object('category_id','sleep','category_name','Sleep','category_icon','/icons/Sleep.svg.png',
            'cells', COALESCE((SELECT jsonb_object_agg(bucket_key, jsonb_build_object(
                'value', CASE WHEN v_bucket_type='hour' THEN 'Sleeping' ELSE ROUND(val,1)::text || 'h' END, 'count', cnt,
                'intensity', CASE
                    WHEN v_bucket_type='hour' THEN 3
                    WHEN val < v_target_sleep_hours - 2.5 THEN 1
                    WHEN val < v_target_sleep_hours - 1.0 THEN 2
                    WHEN val < v_target_sleep_hours + 0.5 THEN 3
                    WHEN val < v_target_sleep_hours + 1.5 THEN 4
                    ELSE 5 END))
                FROM sleep WHERE bucket_key IS NOT NULL AND val IS NOT NULL), '{}'::jsonb)),
        jsonb_build_object('category_id','medicine','category_name','Medicine','category_icon','/icons/medicine1.webp',
            'cells', COALESCE((SELECT jsonb_object_agg(bucket_key, jsonb_build_object(
                'value', COALESCE(detail, val::text || ' drugs'), 'count', cnt,
                'intensity', LEAST(5, GREATEST(1, val::int))))
                FROM medicine WHERE bucket_key IS NOT NULL), '{}'::jsonb)),
        jsonb_build_object('category_id','biometrics','category_name','Biometrics','category_icon','/icons/biometrics.webp',
            'cells', COALESCE((SELECT jsonb_object_agg(bucket_key, jsonb_build_object(
                'value', trim(TRAILING ' · ' FROM
                    COALESCE('HR '    || avg_hr::text      || ' · ', '') ||
                    COALESCE('SpO₂ '  || avg_spo2::text    || '% · ', '') ||
                    COALESCE('Glu '   || avg_glucose::text || ' · ', '') ||
                    COALESCE('T '     || avg_temp::text    || '°C · ', '')),
                'count', cnt,
                'intensity', CASE
                    WHEN avg_glucose IS NOT NULL AND avg_glucose >= 126 THEN 5
                    WHEN avg_glucose IS NOT NULL AND avg_glucose >= 100 THEN 4
                    WHEN avg_spo2    IS NOT NULL AND avg_spo2    <  92  THEN 5
                    WHEN avg_hr      IS NOT NULL AND avg_hr      >= 90  THEN 4
                    WHEN avg_hr      IS NOT NULL AND avg_hr      >= 80  THEN 3
                    WHEN avg_hr      IS NOT NULL AND avg_hr      >= 70  THEN 2
                    WHEN avg_hr      IS NOT NULL AND avg_hr      <  60  THEN 2
                    ELSE 3 END))
                FROM biometrics WHERE bucket_key IS NOT NULL AND cnt > 0), '{}'::jsonb)),
        jsonb_build_object('category_id','mental','category_name','Mental Health','category_icon','/icons/mental health.png',
            'cells', COALESCE((SELECT jsonb_object_agg(bucket_key, jsonb_build_object(
                'value', val::text || '/10', 'count', cnt,
                'intensity', LEAST(5, GREATEST(1, (val/2)::int))))
                FROM mental WHERE bucket_key IS NOT NULL AND val IS NOT NULL), '{}'::jsonb)),
        jsonb_build_object('category_id','hydration','category_name','Hydration','category_icon','/icons/hydration.png',
            'cells', COALESCE((SELECT jsonb_object_agg(bucket_key, jsonb_build_object(
                'value', to_char(val, 'FM999,999') || 'ml', 'count', cnt,
                'intensity', LEAST(5, GREATEST(1, CASE
                    WHEN v_bucket_type='day' THEN CASE
                        WHEN val < v_target_hydration_daily * 0.2 THEN 1
                        WHEN val < v_target_hydration_daily * 0.6 THEN 2
                        WHEN val < v_target_hydration_daily        THEN 3
                        WHEN val < v_target_hydration_daily * 1.4  THEN 4
                        ELSE 5 END
                    ELSE (val / (v_target_hydration_daily / 5.0))::int END)),
                'details', CASE WHEN detail IS NOT NULL THEN jsonb_build_array(detail) ELSE '[]'::jsonb END))
                FROM hydration WHERE bucket_key IS NOT NULL AND val > 0), '{}'::jsonb))
    ) INTO v_rows;

    RETURN jsonb_build_object('level', p_level, 'columns', COALESCE(v_columns, '[]'::jsonb), 'rows', COALESCE(v_rows, '[]'::jsonb));
END; $function$;

COMMIT;
