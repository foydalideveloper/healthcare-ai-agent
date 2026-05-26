-- ============================================================================
-- Healthcare AI Agent - Migration 005: HRT Drill-Down Logic Fixes
-- Triple-H Co., Ltd. | 2026-04-24
-- Patent No. 10-2025-0145274
--
-- Fixes 6 logic bugs in the multi-dimensional HRT drill-down. All are
-- idempotent CREATE OR REPLACE statements -- safe to re-run.
--
-- Fix 1 (exercise/sleep L4 invisible):
--   user_lifestyle.recorded_date is DATE -- no hour info. Previous function
--   returned NULL bucket_key at L4 and the outer WHERE filtered rows out.
--   Now:
--     - sleep L4: uses sleep_start/sleep_end timestamps via generate_series
--       to mark every hour the user was asleep.
--     - exercise L4: pins day-level exercise_min to the hour of the first
--       voice_report that day (best proxy in absence of a workout timestamp);
--       fallback hour 0 if no voice event exists.
--
-- Fix 3 (medicine prescription window):
--   Previous code grouped by EXTRACT(... FROM created_at) so Vitamin D only
--   showed on Apr 16 + Apr 22 (the days the prescription was entered).
--   Now expands [start_date, end_date|today] via generate_series so active
--   prescriptions show on every day in range. At L4 all meds collapse to
--   hour 0 (medicine has no take-time column).
--
-- Fix 5 (biometrics composite):
--   Previous function only surfaced heart_rate. Now builds a composite
--   string "HR X · SpO₂ Y% · Glu Z · T °C" from up-to-4 metrics that have
--   data. Intensity keyed to the most clinically abnormal value (glucose >
--   SpO2 > HR).
--
-- Fix 6 (hydration pattern):
--   Previous ILIKE '%tea%' mis-classified "green tea ice cream", "tea
--   sandwich", "coffee cake" as hydration. Now uses word-boundary regex
--   for drink keywords AND excludes rows that also match a food-suffix
--   pattern (sandwich, cake, ice cream, etc.). Validated via test vectors
--   including EN + KR mixes.
--
-- Fix 9 (auth gate service-role bypass):
--   require_current_user_id() was added to the top of hrt_drilldown_full,
--   calling get_my_user_id() which returns NULL for backend service-role
--   calls (no auth.uid() in JWT context). Every dashboard fetch failed
--   42501 "Authentication is required for this operation". Fix: bypass
--   the check when auth.role() = 'service_role'. Normal end-user auth
--   still enforces the user-match predicate.
--
-- Also fixed by ingest-side change (NOT in this migration, see
-- backend/glasses_watcher/watcher.py _write_lifestyle_row):
--
-- Fix 2 (exercise double-count):
--   Two voice reports mentioning the same "45 min exercise" produced two
--   user_lifestyle rows → SUM=90. Watcher now UPSERTs on (user_id,
--   recorded_date, data_source='ai_glasses_voice') with MAX for exercise_min
--   and latest-wins for sleep fields.
-- ============================================================================

BEGIN;

-- Fix 9: let service-role backend calls through the auth gate
CREATE OR REPLACE FUNCTION public.require_current_user_id(p_user_id bigint)
 RETURNS void
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'public', 'auth', 'pg_temp'
AS $function$
declare
  v_current_user_id bigint;
begin
  -- Trusted backend calls use the service role key; they've already
  -- resolved the caller upstream and passed p_user_id explicitly.
  if auth.role() = 'service_role' then
    return;
  end if;

  v_current_user_id := public.get_my_user_id();

  if v_current_user_id is null then
    raise exception 'Authentication is required for this operation'
      using errcode = '42501';
  end if;

  if p_user_id is distinct from v_current_user_id then
    raise exception 'Requested user_id does not match authenticated user'
      using errcode = '42501';
  end if;
end;
$function$;


-- Fixes 1 + 3 + 5 + 6: rewrite aggregation function
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
BEGIN
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
                     WHERE e.user_id = p_user_id
                       AND e.event_type = 'voice_report'
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
        SELECT bucket_key, COUNT(DISTINCT drug_name)::numeric AS val, COUNT(*) AS cnt,
               string_agg(DISTINCT drug_name, ', ' ORDER BY drug_name) AS detail
        FROM (
            SELECT CASE v_bucket_type
                WHEN 'year'  THEN EXTRACT(YEAR  FROM d)::int::text
                WHEN 'month' THEN EXTRACT(MONTH FROM d)::int::text
                WHEN 'day'   THEN EXTRACT(DAY   FROM d)::int::text
                WHEN 'hour'  THEN '0' END AS bucket_key,
                m.drug_name
            FROM user_medication m,
                 LATERAL generate_series(
                    GREATEST(m.start_date, (v_start_ts AT TIME ZONE 'Asia/Seoul')::date),
                    LEAST(COALESCE(m.end_date, CURRENT_DATE), (v_end_ts AT TIME ZONE 'Asia/Seoul')::date - 1),
                    interval '1 day'
                 ) d
            WHERE m.user_id = p_user_id
        ) s GROUP BY bucket_key
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
                'intensity', LEAST(5, GREATEST(1, CASE WHEN v_bucket_type IN ('year','month') THEN (val/50000)::int WHEN v_bucket_type='day' THEN (val/500)::int WHEN v_bucket_type='hour' THEN (val/200)::int END)),
                'details', CASE WHEN detail IS NOT NULL THEN jsonb_build_array(detail) ELSE '[]'::jsonb END))
                FROM food WHERE bucket_key IS NOT NULL AND cnt > 0), '{}'::jsonb)),
        jsonb_build_object('category_id','exercise','category_name','Exercise','category_icon','/icons/exercise.webp',
            'cells', COALESCE((SELECT jsonb_object_agg(bucket_key, jsonb_build_object(
                'value', val::text || ' min' || COALESCE(' (' || detail || ')', ''), 'count', cnt,
                'intensity', LEAST(5, GREATEST(1, CASE WHEN v_bucket_type IN ('year','month') THEN (val/500)::int WHEN v_bucket_type='day' THEN (val/15)::int WHEN v_bucket_type='hour' THEN GREATEST(1, (val/15)::int) END))))
                FROM exercise WHERE bucket_key IS NOT NULL AND val > 0), '{}'::jsonb)),
        jsonb_build_object('category_id','sleep','category_name','Sleep','category_icon','/icons/Sleep.svg.png',
            'cells', COALESCE((SELECT jsonb_object_agg(bucket_key, jsonb_build_object(
                'value', CASE WHEN v_bucket_type='hour' THEN 'Sleeping' ELSE ROUND(val,1)::text || 'h' END, 'count', cnt,
                'intensity', CASE WHEN v_bucket_type='hour' THEN 3 WHEN val<5 THEN 1 WHEN val<6.5 THEN 2 WHEN val<8 THEN 3 WHEN val<9 THEN 4 ELSE 5 END))
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
                'intensity', CASE WHEN v_bucket_type='day' THEN CASE WHEN val<500 THEN 1 WHEN val<1500 THEN 2 WHEN val<2500 THEN 3 WHEN val<3500 THEN 4 ELSE 5 END ELSE LEAST(5, GREATEST(1, (val/1000)::int)) END,
                'details', CASE WHEN detail IS NOT NULL THEN jsonb_build_array(detail) ELSE '[]'::jsonb END))
                FROM hydration WHERE bucket_key IS NOT NULL AND val > 0), '{}'::jsonb))
    ) INTO v_rows;

    RETURN jsonb_build_object('level', p_level, 'columns', COALESCE(v_columns, '[]'::jsonb), 'rows', COALESCE(v_rows, '[]'::jsonb));
END; $function$;

COMMIT;
