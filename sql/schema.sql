-- Airport Delay Propagation Analytics — flights table.
--
-- Mirrors the 29-column BTS Reporting Carrier On-Time Performance extract in
-- data/raw/flights_2024_*.csv (see src/download_data.py for the source field list).
-- Types were chosen from the actual observed min/max/null profile of the full
-- 7,079,061-row 2024 dataset, not assumed from the BTS documentation alone.
--
-- No natural-key uniqueness is assumed or enforced here — duplicate detection
-- on (flight_date, reporting_airline, flight_number, origin, dest, crs_dep_time)
-- is a separate validation check, not a table constraint.

DROP VIEW IF EXISTS v_turnaround_buffer_performance;
DROP VIEW IF EXISTS v_propagation_signal_comparison;
DROP VIEW IF EXISTS v_delay_cause_performance;
DROP VIEW IF EXISTS v_hour_of_day_performance;
DROP VIEW IF EXISTS v_route_performance;
DROP VIEW IF EXISTS v_airport_performance;
DROP VIEW IF EXISTS v_network_summary;
DROP TABLE IF EXISTS rotation_links;
DROP TABLE IF EXISTS flights;

CREATE TABLE flights (
    id                   BIGSERIAL PRIMARY KEY,
    flight_date          DATE        NOT NULL,
    reporting_airline    VARCHAR(2)  NOT NULL,
    tail_number          VARCHAR(10),
    flight_number        SMALLINT,
    origin               CHAR(3)     NOT NULL,
    dest                 CHAR(3)     NOT NULL,
    crs_dep_time         SMALLINT    NOT NULL,
    dep_time             SMALLINT,
    dep_delay_minutes    SMALLINT,
    taxi_out             SMALLINT,
    wheels_off           SMALLINT,
    wheels_on            SMALLINT,
    taxi_in              SMALLINT,
    crs_arr_time         SMALLINT    NOT NULL,
    arr_time             SMALLINT,
    arr_delay_minutes    SMALLINT,
    arr_del15            BOOLEAN,
    cancelled            BOOLEAN     NOT NULL,
    cancellation_code    CHAR(1),
    diverted             BOOLEAN     NOT NULL,
    crs_elapsed_time     SMALLINT,
    actual_elapsed_time  SMALLINT,
    air_time             SMALLINT,
    distance             SMALLINT    NOT NULL,
    carrier_delay        SMALLINT,
    weather_delay        SMALLINT,
    nas_delay            SMALLINT,
    security_delay       SMALLINT,
    late_aircraft_delay  SMALLINT
);


-- rotation_links — one row per current-leg flight, with its reconstructed
-- previous-leg (same Tail_Number) link. Loaded from data/processed/rotation_links.csv
-- (see src/build_rotations.py, Step 4). link_status = 'valid' marks a usable link;
-- every other value explains why it isn't (see build_rotations.py for the full
-- exclusion logic). No natural-key uniqueness is assumed here either.

CREATE TABLE rotation_links (
    id                              BIGSERIAL PRIMARY KEY,
    tail_number                     VARCHAR(10) NOT NULL,
    flight_date                     DATE        NOT NULL,
    reporting_airline                VARCHAR(2)  NOT NULL,
    flight_number                    SMALLINT,
    origin                          CHAR(3)     NOT NULL,
    dest                            CHAR(3)     NOT NULL,
    prev_flight_date                 DATE,
    prev_flight_number                SMALLINT,
    prev_dest                        CHAR(3),
    crs_dep_time                     SMALLINT    NOT NULL,
    prior_leg_arr_delay_minutes       SMALLINT,
    dep_delay_minutes                 SMALLINT,
    arr_delay_minutes                 SMALLINT,
    late_aircraft_delay               SMALLINT,   -- Signal A: BTS's own attribution, for the CURRENT leg
    scheduled_turnaround_min          REAL,        -- also used as the "available turnaround buffer"
    observed_turnaround_min           REAL,
    propagated_delay_estimate_min     REAL,        -- Signal B: MAX(0, prior_leg_arr_delay_minutes - buffer)
    link_status                      VARCHAR(40) NOT NULL
);


-- ============================================================
-- Analytical views for the dashboard.
--
-- KPI definitions (consistent across every view below):
--   delay_rate_pct                       = % of completed flights with arr_del15 (arrival delay >= 15 min)
--   total_delay_minutes / avg_delay_minutes = sum / mean of arr_delay_minutes (volume-weighted total vs. per-flight)
--   signal_a_*                           = BTS's own LateAircraftDelay attribution (flights table)
--   signal_b_*                           = our independently reconstructed prior-leg signal (rotation_links table)
--   signal_b_valid_links                 = count of link_status = 'valid' rows
--   signal_b_propagation_rate_pct        = % of valid links where propagated_delay_estimate_min > 0 (per-link)
--   signal_b_propagated_delay_minutes    = SUM(propagated_delay_estimate_min) over valid links (volume-weighted total)
--   signal_b_avg_propagated_delay_minutes = AVG(propagated_delay_estimate_min) over valid links (per-link)
-- Signal A and Signal B are always kept in separate, clearly prefixed columns — never combined into one metric.
-- ============================================================

-- 1. Overall network performance (single row)
CREATE VIEW v_network_summary AS
WITH flight_metrics AS (
    SELECT
        COUNT(*) AS total_flights,
        COUNT(*) FILTER (WHERE arr_del15) AS delayed_flights,
        ROUND(100.0 * COUNT(*) FILTER (WHERE arr_del15)
            / NULLIF(COUNT(*) FILTER (WHERE arr_del15 IS NOT NULL), 0), 2) AS delay_rate_pct,
        ROUND(SUM(arr_delay_minutes), 0) AS total_delay_minutes,
        ROUND(AVG(arr_delay_minutes), 2) AS avg_delay_minutes,
        ROUND(SUM(late_aircraft_delay), 0) AS signal_a_late_aircraft_delay_minutes,
        ROUND(100.0 * SUM(late_aircraft_delay)
            / NULLIF(SUM(carrier_delay + weather_delay + nas_delay + security_delay + late_aircraft_delay), 0), 2)
            AS signal_a_late_aircraft_share_pct
    FROM flights
),
rotation_metrics AS (
    SELECT
        COUNT(*) FILTER (WHERE link_status = 'valid') AS signal_b_valid_links,
        ROUND(100.0 * COUNT(*) FILTER (WHERE link_status = 'valid' AND propagated_delay_estimate_min > 0)
            / NULLIF(COUNT(*) FILTER (WHERE link_status = 'valid'), 0), 2) AS signal_b_propagation_rate_pct,
        ROUND((SUM(propagated_delay_estimate_min) FILTER (WHERE link_status = 'valid'))::numeric, 0) AS signal_b_propagated_delay_minutes,
        ROUND((AVG(propagated_delay_estimate_min) FILTER (WHERE link_status = 'valid'))::numeric, 2) AS signal_b_avg_propagated_delay_minutes
    FROM rotation_links
)
SELECT * FROM flight_metrics CROSS JOIN rotation_metrics;


-- 2. Airport-level performance (origin airport). Threshold: meets_min_volume_threshold
--    flags airports with >= 1,000 flights/year (same threshold used in Step 3's SQL
--    analysis), so small-sample airports aren't ranked unqualified alongside hubs.
CREATE VIEW v_airport_performance AS
WITH flight_agg AS (
    SELECT
        origin AS airport,
        COUNT(*) AS total_flights,
        COUNT(*) FILTER (WHERE arr_del15) AS delayed_flights,
        ROUND(100.0 * COUNT(*) FILTER (WHERE arr_del15)
            / NULLIF(COUNT(*) FILTER (WHERE arr_del15 IS NOT NULL), 0), 2) AS delay_rate_pct,
        ROUND(SUM(arr_delay_minutes), 0) AS total_delay_minutes,
        ROUND(AVG(arr_delay_minutes), 2) AS avg_delay_minutes,
        ROUND(SUM(late_aircraft_delay), 0) AS signal_a_late_aircraft_delay_minutes,
        ROUND(100.0 * SUM(late_aircraft_delay)
            / NULLIF(SUM(carrier_delay + weather_delay + nas_delay + security_delay + late_aircraft_delay), 0), 2)
            AS signal_a_late_aircraft_share_pct
    FROM flights
    GROUP BY origin
),
rotation_agg AS (
    SELECT
        origin AS airport,
        COUNT(*) FILTER (WHERE link_status = 'valid') AS signal_b_valid_links,
        ROUND(100.0 * COUNT(*) FILTER (WHERE link_status = 'valid' AND propagated_delay_estimate_min > 0)
            / NULLIF(COUNT(*) FILTER (WHERE link_status = 'valid'), 0), 2) AS signal_b_propagation_rate_pct,
        ROUND((SUM(propagated_delay_estimate_min) FILTER (WHERE link_status = 'valid'))::numeric, 0) AS signal_b_propagated_delay_minutes,
        ROUND((AVG(propagated_delay_estimate_min) FILTER (WHERE link_status = 'valid'))::numeric, 2) AS signal_b_avg_propagated_delay_minutes
    FROM rotation_links
    GROUP BY origin
)
SELECT
    f.airport,
    f.total_flights,
    f.delayed_flights,
    f.delay_rate_pct,
    f.total_delay_minutes,
    f.avg_delay_minutes,
    f.signal_a_late_aircraft_delay_minutes,
    f.signal_a_late_aircraft_share_pct,
    COALESCE(r.signal_b_valid_links, 0) AS signal_b_valid_links,
    r.signal_b_propagation_rate_pct,
    COALESCE(r.signal_b_propagated_delay_minutes, 0) AS signal_b_propagated_delay_minutes,
    r.signal_b_avg_propagated_delay_minutes,
    (f.total_flights >= 1000) AS meets_min_volume_threshold
FROM flight_agg f
LEFT JOIN rotation_agg r ON r.airport = f.airport;


-- 3. Route-level performance (origin-destination pair). Threshold: meets_min_volume_threshold
--    flags routes with >= 200 flights/year (same threshold used in Step 3).
CREATE VIEW v_route_performance AS
WITH flight_agg AS (
    SELECT
        origin, dest,
        COUNT(*) AS total_flights,
        COUNT(*) FILTER (WHERE arr_del15) AS delayed_flights,
        ROUND(100.0 * COUNT(*) FILTER (WHERE arr_del15)
            / NULLIF(COUNT(*) FILTER (WHERE arr_del15 IS NOT NULL), 0), 2) AS delay_rate_pct,
        ROUND(SUM(arr_delay_minutes), 0) AS total_delay_minutes,
        ROUND(AVG(arr_delay_minutes), 2) AS avg_delay_minutes,
        ROUND(SUM(late_aircraft_delay), 0) AS signal_a_late_aircraft_delay_minutes,
        ROUND(100.0 * SUM(late_aircraft_delay)
            / NULLIF(SUM(carrier_delay + weather_delay + nas_delay + security_delay + late_aircraft_delay), 0), 2)
            AS signal_a_late_aircraft_share_pct
    FROM flights
    GROUP BY origin, dest
),
rotation_agg AS (
    SELECT
        origin, dest,
        COUNT(*) FILTER (WHERE link_status = 'valid') AS signal_b_valid_links,
        ROUND(100.0 * COUNT(*) FILTER (WHERE link_status = 'valid' AND propagated_delay_estimate_min > 0)
            / NULLIF(COUNT(*) FILTER (WHERE link_status = 'valid'), 0), 2) AS signal_b_propagation_rate_pct,
        ROUND((SUM(propagated_delay_estimate_min) FILTER (WHERE link_status = 'valid'))::numeric, 0) AS signal_b_propagated_delay_minutes,
        ROUND((AVG(propagated_delay_estimate_min) FILTER (WHERE link_status = 'valid'))::numeric, 2) AS signal_b_avg_propagated_delay_minutes
    FROM rotation_links
    GROUP BY origin, dest
)
SELECT
    f.origin,
    f.dest,
    f.total_flights,
    f.delayed_flights,
    f.delay_rate_pct,
    f.total_delay_minutes,
    f.avg_delay_minutes,
    f.signal_a_late_aircraft_delay_minutes,
    f.signal_a_late_aircraft_share_pct,
    COALESCE(r.signal_b_valid_links, 0) AS signal_b_valid_links,
    r.signal_b_propagation_rate_pct,
    COALESCE(r.signal_b_propagated_delay_minutes, 0) AS signal_b_propagated_delay_minutes,
    r.signal_b_avg_propagated_delay_minutes,
    (f.total_flights >= 200) AS meets_min_volume_threshold
FROM flight_agg f
LEFT JOIN rotation_agg r ON r.origin = f.origin AND r.dest = f.dest;


-- 4. Time-of-day performance (scheduled departure hour, local time at origin)
CREATE VIEW v_hour_of_day_performance AS
WITH flight_agg AS (
    SELECT
        (crs_dep_time / 100) % 24 AS scheduled_dep_hour,
        COUNT(*) AS total_flights,
        COUNT(*) FILTER (WHERE arr_del15) AS delayed_flights,
        ROUND(100.0 * COUNT(*) FILTER (WHERE arr_del15)
            / NULLIF(COUNT(*) FILTER (WHERE arr_del15 IS NOT NULL), 0), 2) AS delay_rate_pct,
        ROUND(AVG(arr_delay_minutes), 2) AS avg_delay_minutes,
        ROUND(SUM(late_aircraft_delay), 0) AS signal_a_late_aircraft_delay_minutes,
        ROUND(100.0 * SUM(late_aircraft_delay)
            / NULLIF(SUM(carrier_delay + weather_delay + nas_delay + security_delay + late_aircraft_delay), 0), 2)
            AS signal_a_late_aircraft_share_pct
    FROM flights
    GROUP BY 1
),
rotation_agg AS (
    SELECT
        (crs_dep_time / 100) % 24 AS scheduled_dep_hour,
        COUNT(*) FILTER (WHERE link_status = 'valid') AS signal_b_valid_links,
        ROUND(100.0 * COUNT(*) FILTER (WHERE link_status = 'valid' AND propagated_delay_estimate_min > 0)
            / NULLIF(COUNT(*) FILTER (WHERE link_status = 'valid'), 0), 2) AS signal_b_propagation_rate_pct,
        ROUND((SUM(propagated_delay_estimate_min) FILTER (WHERE link_status = 'valid'))::numeric, 0) AS signal_b_propagated_delay_minutes,
        ROUND((AVG(propagated_delay_estimate_min) FILTER (WHERE link_status = 'valid'))::numeric, 2) AS signal_b_avg_propagated_delay_minutes
    FROM rotation_links
    GROUP BY 1
)
SELECT
    f.scheduled_dep_hour,
    f.total_flights,
    f.delayed_flights,
    f.delay_rate_pct,
    f.avg_delay_minutes,
    f.signal_a_late_aircraft_delay_minutes,
    f.signal_a_late_aircraft_share_pct,
    COALESCE(r.signal_b_valid_links, 0) AS signal_b_valid_links,
    r.signal_b_propagation_rate_pct,
    COALESCE(r.signal_b_propagated_delay_minutes, 0) AS signal_b_propagated_delay_minutes,
    r.signal_b_avg_propagated_delay_minutes
FROM flight_agg f
LEFT JOIN rotation_agg r ON r.scheduled_dep_hour = f.scheduled_dep_hour
ORDER BY f.scheduled_dep_hour;


-- 5. Delay-cause performance — Signal A only (BTS's cause breakdown has no Signal B analogue)
CREATE VIEW v_delay_cause_performance AS
WITH cause_totals AS (
    SELECT
        SUM(carrier_delay)       AS carrier_delay,
        SUM(weather_delay)       AS weather_delay,
        SUM(nas_delay)           AS nas_delay,
        SUM(security_delay)      AS security_delay,
        SUM(late_aircraft_delay) AS late_aircraft_delay
    FROM flights
    WHERE carrier_delay IS NOT NULL
)
SELECT cause, minutes, ROUND(100.0 * minutes / SUM(minutes) OVER (), 2) AS pct_of_total_delay_minutes
FROM (
    SELECT 'carrier_delay' AS cause, carrier_delay AS minutes FROM cause_totals UNION ALL
    SELECT 'weather_delay',            weather_delay           FROM cause_totals UNION ALL
    SELECT 'nas_delay',                nas_delay                FROM cause_totals UNION ALL
    SELECT 'security_delay',           security_delay           FROM cause_totals UNION ALL
    SELECT 'late_aircraft_delay',      late_aircraft_delay      FROM cause_totals
) unpivoted
ORDER BY minutes DESC;


-- 6. Propagation performance — Signal A vs. Signal B validation (single row).
--    Coverage/correlation/agreement figures as reported at the end of Step 4.
CREATE VIEW v_propagation_signal_comparison AS
SELECT
    COUNT(*) FILTER (WHERE link_status = 'valid') AS signal_b_valid_links,
    COUNT(*) FILTER (WHERE link_status = 'valid' AND late_aircraft_delay IS NOT NULL) AS signal_a_defined_links,
    ROUND(100.0 * COUNT(*) FILTER (WHERE link_status = 'valid' AND late_aircraft_delay IS NOT NULL)
        / NULLIF(COUNT(*) FILTER (WHERE link_status = 'valid'), 0), 2) AS signal_a_coverage_pct,
    ROUND(CORR(prior_leg_arr_delay_minutes, late_aircraft_delay)
        FILTER (WHERE link_status = 'valid' AND late_aircraft_delay IS NOT NULL)::numeric, 3)
        AS corr_raw_prior_delay_vs_signal_a,
    ROUND(CORR(propagated_delay_estimate_min, late_aircraft_delay)
        FILTER (WHERE link_status = 'valid' AND late_aircraft_delay IS NOT NULL)::numeric, 3)
        AS corr_buffer_adjusted_estimate_vs_signal_a,
    COUNT(*) FILTER (WHERE link_status = 'valid' AND COALESCE(late_aircraft_delay, 0) > 0
        AND propagated_delay_estimate_min > 0) AS both_signals_present,
    COUNT(*) FILTER (WHERE link_status = 'valid' AND COALESCE(late_aircraft_delay, 0) = 0
        AND propagated_delay_estimate_min = 0) AS both_signals_absent,
    COUNT(*) FILTER (WHERE link_status = 'valid' AND COALESCE(late_aircraft_delay, 0) = 0
        AND propagated_delay_estimate_min > 0) AS signal_b_only,
    COUNT(*) FILTER (WHERE link_status = 'valid' AND COALESCE(late_aircraft_delay, 0) > 0
        AND propagated_delay_estimate_min = 0) AS signal_a_only,
    ROUND(100.0 * (
        COUNT(*) FILTER (WHERE link_status = 'valid' AND COALESCE(late_aircraft_delay, 0) > 0 AND propagated_delay_estimate_min > 0)
        + COUNT(*) FILTER (WHERE link_status = 'valid' AND COALESCE(late_aircraft_delay, 0) = 0 AND propagated_delay_estimate_min = 0)
    ) / NULLIF(COUNT(*) FILTER (WHERE link_status = 'valid'), 0), 2) AS agreement_rate_pct
FROM rotation_links;


-- 7. Turnaround-buffer performance — downstream delay rate by scheduled-buffer bucket,
--    restricted to links where the prior leg was actually delayed (buffer effect is
--    only meaningful when there's upstream delay to potentially absorb).
--    scheduled_turnaround_min <= 0 (schedule itself had no real padding, e.g. back-to-back
--    or overlapping scheduled times) gets its own bucket rather than being folded into
--    "0-30" — it's a materially different, more extreme population (see Step 5 validation).
CREATE VIEW v_turnaround_buffer_performance AS
WITH bucketed AS (
    SELECT
        CASE
            WHEN scheduled_turnaround_min <= 0   THEN 0
            WHEN scheduled_turnaround_min <= 30  THEN 1
            WHEN scheduled_turnaround_min <= 45  THEN 2
            WHEN scheduled_turnaround_min <= 60  THEN 3
            WHEN scheduled_turnaround_min <= 90  THEN 4
            WHEN scheduled_turnaround_min <= 120 THEN 5
            ELSE 6
        END AS bucket_order,
        prior_leg_arr_delay_minutes,
        dep_delay_minutes
    FROM rotation_links
    WHERE link_status = 'valid' AND prior_leg_arr_delay_minutes > 0
)
SELECT
    bucket_order,
    CASE bucket_order
        WHEN 0 THEN '<=0 (no scheduled buffer)' WHEN 1 THEN '0-30' WHEN 2 THEN '30-45' WHEN 3 THEN '45-60'
        WHEN 4 THEN '60-90' WHEN 5 THEN '90-120' ELSE '120+'
    END AS buffer_bucket_minutes,
    COUNT(*) AS n_links,
    ROUND(AVG(prior_leg_arr_delay_minutes), 2) AS avg_prior_leg_delay_minutes,
    ROUND(AVG(dep_delay_minutes), 2) AS avg_current_dep_delay_minutes,
    ROUND(100.0 * COUNT(*) FILTER (WHERE dep_delay_minutes >= 15) / COUNT(*), 2) AS downstream_delay_rate_pct
FROM bucketed
GROUP BY bucket_order
ORDER BY bucket_order;
