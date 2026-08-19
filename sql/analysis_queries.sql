-- Airport Delay Propagation Analytics — core SQL analysis.
--
-- Source of truth: the `flights` table (7,079,061 rows, 2024, loaded via
-- src/load_to_postgres.py). All delay-cause columns (carrier_delay,
-- weather_delay, nas_delay, security_delay, late_aircraft_delay) are non-null
-- only for flights with arr_delay_minutes >= 15, per BTS's own reporting rule.
--
-- Propagation signal note: everything under section 10 uses BTS's own
-- LateAircraftDelay attribution (Signal A) — a same-flight field BTS computes
-- with a methodology we don't control. It is not proof that a specific prior
-- flight caused the delay. A cross-aircraft signal reconstructed from
-- Tail_Number rotations (Signal B) is a separate, later step and is not built
-- here. Section 11 uses only same-flight fields for the same reason.


-- ============================================================
-- 1. Overall flight volume
-- ============================================================
SELECT
    COUNT(*)                        AS total_flights,
    COUNT(DISTINCT tail_number)     AS distinct_aircraft,
    COUNT(DISTINCT reporting_airline) AS distinct_carriers,
    COUNT(DISTINCT origin)          AS distinct_origin_airports,
    MIN(flight_date)                AS first_date,
    MAX(flight_date)                AS last_date
FROM flights;

-- Monthly volume trend
SELECT
    DATE_TRUNC('month', flight_date)::date AS month,
    COUNT(*)                               AS flights
FROM flights
GROUP BY 1
ORDER BY 1;


-- ============================================================
-- 2. Delay rate (arrival delay >= 15 min), among flights that arrived
-- ============================================================
SELECT
    COUNT(*) FILTER (WHERE arr_del15)          AS delayed_flights,
    COUNT(*) FILTER (WHERE arr_del15 IS NOT NULL) AS completed_flights,
    ROUND(100.0 * COUNT(*) FILTER (WHERE arr_del15)
        / COUNT(*) FILTER (WHERE arr_del15 IS NOT NULL), 2) AS delay_rate_pct
FROM flights;


-- ============================================================
-- 3. Average and median arrival delay (completed flights only)
-- ============================================================
SELECT
    ROUND(AVG(arr_delay_minutes), 2) AS avg_arr_delay_minutes,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY arr_delay_minutes) AS median_arr_delay_minutes,
    ROUND(AVG(arr_delay_minutes) FILTER (WHERE arr_delay_minutes > 0), 2) AS avg_delay_minutes_when_late
FROM flights
WHERE arr_delay_minutes IS NOT NULL;


-- ============================================================
-- 4. Cancellation rate, overall and by BTS cancellation reason
-- ============================================================
SELECT
    COUNT(*) FILTER (WHERE cancelled) AS cancelled_flights,
    COUNT(*)                          AS total_flights,
    ROUND(100.0 * COUNT(*) FILTER (WHERE cancelled) / COUNT(*), 3) AS cancellation_rate_pct
FROM flights;

SELECT
    cancellation_code,
    CASE cancellation_code
        WHEN 'A' THEN 'Carrier'
        WHEN 'B' THEN 'Weather'
        WHEN 'C' THEN 'National Air System'
        WHEN 'D' THEN 'Security'
    END AS reason,
    COUNT(*) AS cancelled_flights
FROM flights
WHERE cancelled
GROUP BY cancellation_code
ORDER BY cancelled_flights DESC;


-- ============================================================
-- 5. Delay-cause contribution: share of total delay-minutes by BTS cause,
--    among flights with a cause breakdown (arrival delay >= 15 min)
-- ============================================================
WITH cause_totals AS (
    SELECT
        SUM(carrier_delay)       AS carrier,
        SUM(weather_delay)       AS weather,
        SUM(nas_delay)           AS nas,
        SUM(security_delay)      AS security,
        SUM(late_aircraft_delay) AS late_aircraft
    FROM flights
    WHERE carrier_delay IS NOT NULL
),
unpivoted AS (
    SELECT 'carrier_delay'       AS cause, carrier       AS minutes FROM cause_totals UNION ALL
    SELECT 'weather_delay',            weather                     FROM cause_totals UNION ALL
    SELECT 'nas_delay',                nas                         FROM cause_totals UNION ALL
    SELECT 'security_delay',           security                    FROM cause_totals UNION ALL
    SELECT 'late_aircraft_delay',      late_aircraft               FROM cause_totals
)
SELECT
    cause,
    minutes,
    ROUND(100.0 * minutes / SUM(minutes) OVER (), 2) AS pct_of_total_delay_minutes
FROM unpivoted
ORDER BY minutes DESC;


-- ============================================================
-- 6. Airport-level delay patterns (origin airport, min 1,000 flights/year
--    to avoid noisy small-sample airports)
-- ============================================================
SELECT
    origin,
    COUNT(*) AS flights,
    ROUND(100.0 * COUNT(*) FILTER (WHERE arr_del15)
        / COUNT(*) FILTER (WHERE arr_del15 IS NOT NULL), 2) AS delay_rate_pct,
    ROUND(AVG(arr_delay_minutes), 2) AS avg_arr_delay_minutes,
    ROUND(100.0 * SUM(late_aircraft_delay)
        / NULLIF(SUM(carrier_delay + weather_delay + nas_delay + security_delay + late_aircraft_delay), 0), 2)
        AS late_aircraft_share_pct
FROM flights
GROUP BY origin
HAVING COUNT(*) >= 1000
ORDER BY delay_rate_pct DESC
LIMIT 20;


-- ============================================================
-- 7. Route-level delay patterns (origin-destination pairs, min 200 flights/year)
-- ============================================================
SELECT
    origin,
    dest,
    COUNT(*) AS flights,
    ROUND(100.0 * COUNT(*) FILTER (WHERE arr_del15)
        / COUNT(*) FILTER (WHERE arr_del15 IS NOT NULL), 2) AS delay_rate_pct,
    ROUND(AVG(arr_delay_minutes), 2) AS avg_arr_delay_minutes
FROM flights
GROUP BY origin, dest
HAVING COUNT(*) >= 200
ORDER BY delay_rate_pct DESC
LIMIT 20;


-- ============================================================
-- 8. Day-of-week patterns
-- ============================================================
SELECT
    EXTRACT(ISODOW FROM flight_date)::int AS iso_day_of_week,  -- 1=Monday .. 7=Sunday
    TRIM(TO_CHAR(flight_date, 'Day'))     AS day_name,
    COUNT(*) AS flights,
    ROUND(100.0 * COUNT(*) FILTER (WHERE arr_del15)
        / COUNT(*) FILTER (WHERE arr_del15 IS NOT NULL), 2) AS delay_rate_pct,
    ROUND(AVG(arr_delay_minutes), 2) AS avg_arr_delay_minutes
FROM flights
GROUP BY 1, 2
ORDER BY 1;


-- ============================================================
-- 9. Hour-of-day patterns (scheduled departure hour, local time at origin)
-- ============================================================
SELECT
    (crs_dep_time / 100) % 24 AS scheduled_dep_hour,
    COUNT(*) AS flights,
    ROUND(100.0 * COUNT(*) FILTER (WHERE arr_del15)
        / COUNT(*) FILTER (WHERE arr_del15 IS NOT NULL), 2) AS delay_rate_pct,
    ROUND(AVG(arr_delay_minutes), 2) AS avg_arr_delay_minutes,
    ROUND(AVG(late_aircraft_delay), 2) AS avg_late_aircraft_delay_minutes
FROM flights
GROUP BY 1
ORDER BY 1;


-- ============================================================
-- 10. LateAircraftDelay patterns — Signal A (BTS's own attribution)
-- ============================================================

-- 10a. Share of delayed flights where LateAircraftDelay is the single
--      largest cause (not just present, but dominant)
WITH causes AS (
    SELECT
        late_aircraft_delay,
        GREATEST(carrier_delay, weather_delay, nas_delay, security_delay, late_aircraft_delay) AS max_cause_minutes
    FROM flights
    WHERE carrier_delay IS NOT NULL
)
SELECT
    COUNT(*) FILTER (WHERE late_aircraft_delay = max_cause_minutes AND late_aircraft_delay > 0) AS late_aircraft_dominant_flights,
    COUNT(*) AS total_delayed_flights,
    ROUND(100.0 * COUNT(*) FILTER (WHERE late_aircraft_delay = max_cause_minutes AND late_aircraft_delay > 0)
        / COUNT(*), 2) AS pct_late_aircraft_dominant
FROM causes;

-- 10b. LateAircraftDelay's share of total attributed delay-minutes, by scheduled departure hour
SELECT
    (crs_dep_time / 100) % 24 AS scheduled_dep_hour,
    ROUND(100.0 * SUM(late_aircraft_delay)
        / NULLIF(SUM(carrier_delay + weather_delay + nas_delay + security_delay + late_aircraft_delay), 0), 2)
        AS late_aircraft_share_pct,
    ROUND(AVG(late_aircraft_delay), 2) AS avg_late_aircraft_delay_minutes
FROM flights
WHERE carrier_delay IS NOT NULL
GROUP BY 1
ORDER BY 1;


-- ============================================================
-- 11. Initial delay vs. downstream-delay indicators
--     Same-flight fields only (dep_delay -> arr_delay). This is NOT the
--     cross-aircraft "prior leg" signal (Signal B) — that requires the
--     Tail_Number rotation reconstruction, a separate later step.
-- ============================================================

-- 11a. How strongly does a flight's own departure delay correlate with its
--      own arrival delay?
SELECT
    CORR(dep_delay_minutes, arr_delay_minutes) AS dep_arr_delay_correlation,
    COUNT(*) AS flights_used
FROM flights
WHERE dep_delay_minutes IS NOT NULL AND arr_delay_minutes IS NOT NULL;

-- 11b. Among flights that departed late, how much of that delay is recovered
--      in the air by arrival?
SELECT
    ROUND(AVG(dep_delay_minutes - arr_delay_minutes), 2) AS avg_minutes_recovered_in_flight,
    ROUND(100.0 * COUNT(*) FILTER (WHERE arr_delay_minutes < dep_delay_minutes)
        / COUNT(*), 2) AS pct_flights_recovering_time
FROM flights
WHERE dep_delay_minutes IS NOT NULL
  AND arr_delay_minutes IS NOT NULL
  AND dep_delay_minutes > 0;
