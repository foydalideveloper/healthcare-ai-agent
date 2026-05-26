-- ============================================================================
-- Healthcare AI Agent - Migration 004: hrt_drilldown_full() SQL Function
-- Triple-H Co., Ltd. | 2026-04-22
--
-- Purpose: Return the COMPLETE DrilldownResponse shape for the HRT dashboard
-- in a single RPC call. Replaces the 7-separate-queries approach with one
-- efficient function.
--
-- Covers all 7 dashboard categories at all 4 levels (year/month/day/hour):
--   1. Food & Nutrition   (user_food_log, non-drink items)
--   2. Exercise           (user_lifestyle.exercise_min)
--   3. Sleep              (user_lifestyle.sleep_hours)
--   4. Medicine           (user_medication)
--   5. Biometrics         (user_biometric.heart_rate)
--   6. Mental Health      (user_health_level.stress_level)
--   7. Hydration          (user_food_log, drink items — pattern match)
--
-- Returns JSONB matching the frontend's DrilldownResponse TypeScript interface:
--   { level, columns: [{key,label}], rows: [{category_id, category_name,
--     category_icon, cells: { [colKey]: { value, count, intensity } } }] }
-- ============================================================================

CREATE OR REPLACE FUNCTION hrt_drilldown_full(
    p_user_id BIGINT,
    p_level   INT,
    p_year    INT DEFAULT NULL,
    p_month   INT DEFAULT NULL,
    p_day     INT DEFAULT NULL
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_columns      JSONB;
    v_start_ts     TIMESTAMPTZ;
    v_end_ts       TIMESTAMPTZ;
    v_bucket_type  TEXT;
    v_rows         JSONB;
BEGIN
    -- ========================================================================
    -- 1. Determine columns + time range based on level
    -- ========================================================================
    IF p_level = 1 THEN
        v_bucket_type := 'year';
        v_start_ts    := '2020-01-01'::timestamptz;
        v_end_ts      := '2027-01-01'::timestamptz;
        SELECT jsonb_agg(
                   jsonb_build_object('key', y::text, 'label', y::text)
                   ORDER BY y
               )
        INTO v_columns
        FROM generate_series(2020, 2026) y;

    ELSIF p_level = 2 THEN
        v_bucket_type := 'month';
        v_start_ts    := make_date(p_year, 1, 1);
        v_end_ts      := make_date(p_year + 1, 1, 1);
        SELECT jsonb_agg(
                   jsonb_build_object(
                       'key',   m::text,
                       'label', to_char(make_date(2000, m, 1), 'Mon')
                   )
                   ORDER BY m
               )
        INTO v_columns
        FROM generate_series(1, 12) m;

    ELSIF p_level = 3 THEN
        v_bucket_type := 'day';
        v_start_ts    := make_date(p_year, p_month, 1);
        v_end_ts      := v_start_ts + interval '1 month';
        SELECT jsonb_agg(
                   jsonb_build_object('key', d::text, 'label', d::text)
                   ORDER BY d
               )
        INTO v_columns
        FROM generate_series(1, EXTRACT(DAY FROM (v_end_ts - interval '1 day'))::int) d;

    ELSIF p_level = 4 THEN
        v_bucket_type := 'hour';
        v_start_ts    := make_timestamp(p_year, p_month, p_day, 0, 0, 0);
        v_end_ts      := v_start_ts + interval '1 day';
        SELECT jsonb_agg(
                   jsonb_build_object(
                       'key',   h::text,
                       'label', lpad(h::text, 2, '0') || ':00'
                   )
                   ORDER BY h
               )
        INTO v_columns
        FROM generate_series(0, 23) h;

    ELSE
        RAISE EXCEPTION 'Invalid level: %. Must be 1-4.', p_level;
    END IF;

    -- ========================================================================
    -- 2. Build rows for each of 7 categories
    --    Each category aggregates into buckets matching column keys.
    -- ========================================================================
    WITH

    -- ── helpers: bucket-key extraction given a timestamp ──
    bucket_for AS (
        SELECT v_bucket_type AS t
    ),

    -- ── 1. FOOD (excluding drinks) ──
    food AS (
        SELECT
            CASE v_bucket_type
                WHEN 'year'  THEN EXTRACT(YEAR  FROM consumed_at)::int::text
                WHEN 'month' THEN EXTRACT(MONTH FROM consumed_at)::int::text
                WHEN 'day'   THEN EXTRACT(DAY   FROM consumed_at)::int::text
                WHEN 'hour'  THEN EXTRACT(HOUR  FROM consumed_at)::int::text
            END AS bucket_key,
            COALESCE(SUM((nutrients_json->>'energy_kcal')::numeric), 0) AS val,
            COUNT(*) AS cnt,
            string_agg(DISTINCT food_name, ', ' ORDER BY food_name) AS detail
        FROM user_food_log
        WHERE user_id = p_user_id
          AND consumed_at >= v_start_ts
          AND consumed_at <  v_end_ts
          AND NOT (
              food_name ILIKE '%drink%' OR food_name ILIKE '%water%'
              OR food_name ILIKE '%coffee%' OR food_name ILIKE '%tea%'
              OR food_name ILIKE '%juice%' OR food_name ILIKE '%milk%'
              OR food_name ILIKE '%물%'    OR food_name ILIKE '%커피%'
              OR food_name ILIKE '%차%'    OR food_name ILIKE '%주스%'
              OR food_name ILIKE '%우유%'
          )
        GROUP BY bucket_key
    ),

    -- ── 2. EXERCISE (user_lifestyle.exercise_min) ──
    exercise AS (
        SELECT
            CASE v_bucket_type
                WHEN 'year'  THEN EXTRACT(YEAR  FROM recorded_date)::int::text
                WHEN 'month' THEN EXTRACT(MONTH FROM recorded_date)::int::text
                WHEN 'day'   THEN EXTRACT(DAY   FROM recorded_date)::int::text
                WHEN 'hour'  THEN NULL  -- lifestyle is daily granularity
            END AS bucket_key,
            COALESCE(SUM(exercise_min), 0) AS val,
            COUNT(*) FILTER (WHERE exercise_min > 0) AS cnt,
            string_agg(DISTINCT exercise_type, ', ') AS detail
        FROM user_lifestyle
        WHERE user_id = p_user_id
          AND recorded_date >= v_start_ts::date
          AND recorded_date <  v_end_ts::date
        GROUP BY bucket_key
    ),

    -- ── 3. SLEEP ──
    sleep AS (
        SELECT
            CASE v_bucket_type
                WHEN 'year'  THEN EXTRACT(YEAR  FROM recorded_date)::int::text
                WHEN 'month' THEN EXTRACT(MONTH FROM recorded_date)::int::text
                WHEN 'day'   THEN EXTRACT(DAY   FROM recorded_date)::int::text
                WHEN 'hour'  THEN NULL
            END AS bucket_key,
            ROUND(AVG(sleep_hours)::numeric, 1) AS val,
            COUNT(*) FILTER (WHERE sleep_hours IS NOT NULL) AS cnt,
            NULL::text AS detail
        FROM user_lifestyle
        WHERE user_id = p_user_id
          AND recorded_date >= v_start_ts::date
          AND recorded_date <  v_end_ts::date
        GROUP BY bucket_key
    ),

    -- ── 4. MEDICINE ──
    medicine AS (
        SELECT
            CASE v_bucket_type
                WHEN 'year'  THEN EXTRACT(YEAR  FROM created_at)::int::text
                WHEN 'month' THEN EXTRACT(MONTH FROM created_at)::int::text
                WHEN 'day'   THEN EXTRACT(DAY   FROM created_at)::int::text
                WHEN 'hour'  THEN EXTRACT(HOUR  FROM created_at)::int::text
            END AS bucket_key,
            COUNT(DISTINCT drug_name)::numeric AS val,
            COUNT(*) AS cnt,
            string_agg(DISTINCT drug_name, ', ' ORDER BY drug_name) AS detail
        FROM user_medication
        WHERE user_id = p_user_id
          AND created_at >= v_start_ts
          AND created_at <  v_end_ts
        GROUP BY bucket_key
    ),

    -- ── 5. BIOMETRICS (avg heart rate — no BP columns in schema yet) ──
    biometrics AS (
        SELECT
            CASE v_bucket_type
                WHEN 'year'  THEN EXTRACT(YEAR  FROM measured_at)::int::text
                WHEN 'month' THEN EXTRACT(MONTH FROM measured_at)::int::text
                WHEN 'day'   THEN EXTRACT(DAY   FROM measured_at)::int::text
                WHEN 'hour'  THEN EXTRACT(HOUR  FROM measured_at)::int::text
            END AS bucket_key,
            ROUND(AVG(heart_rate)::numeric, 0) AS val,
            COUNT(*) AS cnt,
            NULL::text AS detail
        FROM user_biometric
        WHERE user_id = p_user_id
          AND measured_at >= v_start_ts
          AND measured_at <  v_end_ts
          AND heart_rate IS NOT NULL
        GROUP BY bucket_key
    ),

    -- ── 6. MENTAL HEALTH (user_health_level.stress_level, 1-10 scale) ──
    mental AS (
        SELECT
            CASE v_bucket_type
                WHEN 'year'  THEN EXTRACT(YEAR  FROM measured_at)::int::text
                WHEN 'month' THEN EXTRACT(MONTH FROM measured_at)::int::text
                WHEN 'day'   THEN EXTRACT(DAY   FROM measured_at)::int::text
                WHEN 'hour'  THEN EXTRACT(HOUR  FROM measured_at)::int::text
            END AS bucket_key,
            ROUND(AVG(stress_level)::numeric, 1) AS val,
            COUNT(*) FILTER (WHERE stress_level IS NOT NULL) AS cnt,
            NULL::text AS detail
        FROM user_health_level
        WHERE user_id = p_user_id
          AND measured_at >= v_start_ts
          AND measured_at <  v_end_ts
          AND stress_level IS NOT NULL
        GROUP BY bucket_key
    ),

    -- ── 7. HYDRATION (user_food_log, drink pattern, portion_g as ml proxy) ──
    hydration AS (
        SELECT
            CASE v_bucket_type
                WHEN 'year'  THEN EXTRACT(YEAR  FROM consumed_at)::int::text
                WHEN 'month' THEN EXTRACT(MONTH FROM consumed_at)::int::text
                WHEN 'day'   THEN EXTRACT(DAY   FROM consumed_at)::int::text
                WHEN 'hour'  THEN EXTRACT(HOUR  FROM consumed_at)::int::text
            END AS bucket_key,
            COALESCE(SUM(portion_g), 0) AS val,
            COUNT(*) AS cnt,
            NULL::text AS detail
        FROM user_food_log
        WHERE user_id = p_user_id
          AND consumed_at >= v_start_ts
          AND consumed_at <  v_end_ts
          AND (
              food_name ILIKE '%drink%' OR food_name ILIKE '%water%'
              OR food_name ILIKE '%coffee%' OR food_name ILIKE '%tea%'
              OR food_name ILIKE '%juice%' OR food_name ILIKE '%milk%'
              OR food_name ILIKE '%물%'    OR food_name ILIKE '%커피%'
              OR food_name ILIKE '%차%'    OR food_name ILIKE '%주스%'
              OR food_name ILIKE '%우유%'
          )
        GROUP BY bucket_key
    )

    -- ========================================================================
    -- 3. Build the rows array — one row per category, cells keyed by bucket
    --    Value format and intensity thresholds per category below.
    -- ========================================================================
    SELECT jsonb_build_array(

        -- FOOD
        jsonb_build_object(
            'category_id',   'food',
            'category_name', 'Food & Nutrition',
            'category_icon', '/icons/food.png',
            'cells', COALESCE((
                SELECT jsonb_object_agg(
                    bucket_key,
                    jsonb_build_object(
                        'value',     to_char(val, 'FM999,999,999') || ' kcal',
                        'count',     cnt,
                        'intensity', LEAST(5, GREATEST(1,
                            CASE
                                WHEN v_bucket_type IN ('year','month') THEN (val / 50000)::int
                                WHEN v_bucket_type = 'day'             THEN (val / 500)::int
                                WHEN v_bucket_type = 'hour'            THEN (val / 200)::int
                            END
                        )),
                        'details',   CASE WHEN detail IS NOT NULL THEN jsonb_build_array(detail) ELSE '[]'::jsonb END
                    )
                )
                FROM food WHERE bucket_key IS NOT NULL
            ), '{}'::jsonb)
        ),

        -- EXERCISE
        jsonb_build_object(
            'category_id',   'exercise',
            'category_name', 'Exercise',
            'category_icon', '/icons/exercise.webp',
            'cells', COALESCE((
                SELECT jsonb_object_agg(
                    bucket_key,
                    jsonb_build_object(
                        'value',     val::text || ' min' || COALESCE(' (' || detail || ')', ''),
                        'count',     cnt,
                        'intensity', LEAST(5, GREATEST(1,
                            CASE
                                WHEN v_bucket_type IN ('year','month') THEN (val / 500)::int
                                WHEN v_bucket_type = 'day'             THEN (val / 15)::int
                                ELSE 1
                            END
                        ))
                    )
                )
                FROM exercise WHERE bucket_key IS NOT NULL AND val > 0
            ), '{}'::jsonb)
        ),

        -- SLEEP
        jsonb_build_object(
            'category_id',   'sleep',
            'category_name', 'Sleep',
            'category_icon', '/icons/Sleep.svg.png',
            'cells', COALESCE((
                SELECT jsonb_object_agg(
                    bucket_key,
                    jsonb_build_object(
                        'value', val::text || 'h',
                        'count', cnt,
                        'intensity', CASE
                            WHEN val < 5      THEN 1
                            WHEN val < 6.5    THEN 2
                            WHEN val < 8      THEN 3
                            WHEN val < 9      THEN 4
                            ELSE 5
                        END
                    )
                )
                FROM sleep WHERE bucket_key IS NOT NULL AND val IS NOT NULL
            ), '{}'::jsonb)
        ),

        -- MEDICINE
        jsonb_build_object(
            'category_id',   'medicine',
            'category_name', 'Medicine',
            'category_icon', '/icons/medicine1.webp',
            'cells', COALESCE((
                SELECT jsonb_object_agg(
                    bucket_key,
                    jsonb_build_object(
                        'value',   COALESCE(detail, val::text || ' drugs'),
                        'count',   cnt,
                        'intensity', LEAST(5, GREATEST(1, val::int))
                    )
                )
                FROM medicine WHERE bucket_key IS NOT NULL
            ), '{}'::jsonb)
        ),

        -- BIOMETRICS (avg heart rate — labeled as HR since no BP column yet)
        jsonb_build_object(
            'category_id',   'biometrics',
            'category_name', 'Biometrics',
            'category_icon', '/icons/biometrics.webp',
            'cells', COALESCE((
                SELECT jsonb_object_agg(
                    bucket_key,
                    jsonb_build_object(
                        'value', 'HR ' || val::text || ' bpm',
                        'count', cnt,
                        'intensity', CASE
                            WHEN val < 60  THEN 1
                            WHEN val < 70  THEN 2
                            WHEN val < 80  THEN 3
                            WHEN val < 90  THEN 4
                            ELSE 5
                        END
                    )
                )
                FROM biometrics WHERE bucket_key IS NOT NULL AND val IS NOT NULL
            ), '{}'::jsonb)
        ),

        -- MENTAL HEALTH (stress_level 1-10)
        jsonb_build_object(
            'category_id',   'mental',
            'category_name', 'Mental Health',
            'category_icon', '/icons/mental health.png',
            'cells', COALESCE((
                SELECT jsonb_object_agg(
                    bucket_key,
                    jsonb_build_object(
                        'value', val::text || '/10',
                        'count', cnt,
                        'intensity', LEAST(5, GREATEST(1, (val / 2)::int))
                    )
                )
                FROM mental WHERE bucket_key IS NOT NULL AND val IS NOT NULL
            ), '{}'::jsonb)
        ),

        -- HYDRATION (portion_g → ml proxy)
        jsonb_build_object(
            'category_id',   'hydration',
            'category_name', 'Hydration',
            'category_icon', '/icons/hydration.png',
            'cells', COALESCE((
                SELECT jsonb_object_agg(
                    bucket_key,
                    jsonb_build_object(
                        'value', to_char(val, 'FM999,999') || 'ml',
                        'count', cnt,
                        'intensity', CASE
                            WHEN v_bucket_type = 'day' THEN
                                CASE
                                    WHEN val < 500  THEN 1
                                    WHEN val < 1500 THEN 2
                                    WHEN val < 2500 THEN 3
                                    WHEN val < 3500 THEN 4
                                    ELSE 5
                                END
                            ELSE LEAST(5, GREATEST(1, (val / 1000)::int))
                        END
                    )
                )
                FROM hydration WHERE bucket_key IS NOT NULL AND val > 0
            ), '{}'::jsonb)
        )
    )
    INTO v_rows;

    -- ========================================================================
    -- 4. Return the complete DrilldownResponse
    -- ========================================================================
    RETURN jsonb_build_object(
        'level',   p_level,
        'columns', COALESCE(v_columns, '[]'::jsonb),
        'rows',    COALESCE(v_rows,    '[]'::jsonb)
    );
END;
$$;

COMMENT ON FUNCTION hrt_drilldown_full(BIGINT, INT, INT, INT, INT) IS
'Returns complete HRT dashboard drill-down for all 7 categories at any of 4 levels.
 Response shape matches TypeScript DrilldownResponse in frontend/hrt-dashboard/DrilldownGrid.tsx.
 Used by FastAPI /api/v1/hrt/drilldown endpoint.';
