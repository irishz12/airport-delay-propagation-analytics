"""Export the 7 approved Step-5 views, plus minimal aggregated data for Page 3's
airport/route/airline/month filters, to CSV under powerbi/data/ for Power BI Service
(no local Postgres connection is available from the browser on macOS).

No PostgreSQL schema, view, metric, or methodology is changed here. The two Page 3
exports below are new *ad hoc* SELECTs only for this export (not persisted as
views) — every metric in them reuses the exact same formulas already defined in
sql/schema.sql, just grouped at a finer grain than the existing views support.

The raw 7M-row flights/rotation_links tables are never exported — Page 3's exports
are pre-aggregated in SQL to keep file sizes small.
"""
import io
from pathlib import Path

import psycopg2

DB_NAME = "airport_delays"
OUT_DIR = Path(__file__).resolve().parent.parent / "powerbi" / "data"

VIEWS = [
    "v_network_summary",
    "v_airport_performance",
    "v_route_performance",
    "v_hour_of_day_performance",
    "v_delay_cause_performance",
    "v_propagation_signal_comparison",
    "v_turnaround_buffer_performance",
]

# Grain: (origin, dest, reporting_airline, month) — the finest grain needed to
# support the airport, route, airline, and month filters together on Page 3.
# Metric formulas copied verbatim from v_airport_performance / v_route_performance.
PAGE3_FLIGHT_METRICS = """
    WITH flight_agg AS (
        SELECT
            origin, dest, reporting_airline,
            DATE_TRUNC('month', flight_date)::date AS month,
            COUNT(*) AS total_flights,
            COUNT(*) FILTER (WHERE arr_del15) AS delayed_flights,
            ROUND(100.0 * COUNT(*) FILTER (WHERE arr_del15)
                / NULLIF(COUNT(*) FILTER (WHERE arr_del15 IS NOT NULL), 0), 2) AS delay_rate_pct,
            ROUND(AVG(arr_delay_minutes), 2) AS avg_delay_minutes,
            ROUND(SUM(arr_delay_minutes), 0) AS total_delay_minutes,
            COUNT(*) FILTER (WHERE cancelled) AS cancelled_flights,
            ROUND(100.0 * COUNT(*) FILTER (WHERE cancelled) / COUNT(*), 3) AS cancellation_rate_pct,
            ROUND(SUM(late_aircraft_delay), 0) AS signal_a_late_aircraft_delay_minutes,
            ROUND(100.0 * SUM(late_aircraft_delay)
                / NULLIF(SUM(carrier_delay + weather_delay + nas_delay + security_delay + late_aircraft_delay), 0), 2)
                AS signal_a_late_aircraft_share_pct
        FROM flights
        GROUP BY 1, 2, 3, 4
    ),
    rotation_agg AS (
        SELECT
            origin, dest, reporting_airline,
            DATE_TRUNC('month', flight_date)::date AS month,
            COUNT(*) FILTER (WHERE link_status = 'valid') AS signal_b_valid_links,
            ROUND(100.0 * COUNT(*) FILTER (WHERE link_status = 'valid' AND propagated_delay_estimate_min > 0)
                / NULLIF(COUNT(*) FILTER (WHERE link_status = 'valid'), 0), 2) AS signal_b_propagation_rate_pct,
            ROUND((SUM(propagated_delay_estimate_min) FILTER (WHERE link_status = 'valid'))::numeric, 0)
                AS signal_b_propagated_delay_minutes,
            ROUND((AVG(propagated_delay_estimate_min) FILTER (WHERE link_status = 'valid'))::numeric, 2)
                AS signal_b_avg_propagated_delay_minutes
        FROM rotation_links
        GROUP BY 1, 2, 3, 4
    )
    SELECT
        f.origin, f.dest, f.reporting_airline, f.month,
        f.total_flights, f.delayed_flights, f.delay_rate_pct, f.avg_delay_minutes, f.total_delay_minutes,
        f.cancelled_flights, f.cancellation_rate_pct,
        f.signal_a_late_aircraft_delay_minutes, f.signal_a_late_aircraft_share_pct,
        COALESCE(r.signal_b_valid_links, 0) AS signal_b_valid_links,
        r.signal_b_propagation_rate_pct,
        COALESCE(r.signal_b_propagated_delay_minutes, 0) AS signal_b_propagated_delay_minutes,
        r.signal_b_avg_propagated_delay_minutes
    FROM flight_agg f
    LEFT JOIN rotation_agg r
        ON r.origin = f.origin AND r.dest = f.dest
       AND r.reporting_airline = f.reporting_airline AND r.month = f.month
"""

# Grain: (origin, reporting_airline, month, buffer_bucket) — turnaround happens at
# the origin airport, so "dest" isn't a meaningful dimension here (and dropping it
# keeps this export ~5x smaller). Bucket boundaries copied verbatim from
# v_turnaround_buffer_performance.
PAGE3_TURNAROUND_BUFFER = """
    WITH bucketed AS (
        SELECT
            origin, reporting_airline,
            DATE_TRUNC('month', flight_date)::date AS month,
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
        origin, reporting_airline, month, bucket_order,
        CASE bucket_order
            WHEN 0 THEN '<=0 (no scheduled buffer)' WHEN 1 THEN '0-30' WHEN 2 THEN '30-45' WHEN 3 THEN '45-60'
            WHEN 4 THEN '60-90' WHEN 5 THEN '90-120' ELSE '120+'
        END AS buffer_bucket_minutes,
        COUNT(*) AS n_links,
        ROUND(AVG(prior_leg_arr_delay_minutes), 2) AS avg_prior_leg_delay_minutes,
        ROUND(AVG(dep_delay_minutes), 2) AS avg_current_dep_delay_minutes,
        ROUND(100.0 * COUNT(*) FILTER (WHERE dep_delay_minutes >= 15) / COUNT(*), 2) AS downstream_delay_rate_pct
    FROM bucketed
    GROUP BY origin, reporting_airline, month, bucket_order
"""


def export(cur, query: str, out_path: Path) -> None:
    buffer = io.StringIO()
    cur.copy_expert(f"COPY ({query}) TO STDOUT WITH (FORMAT csv, HEADER true)", buffer)
    buffer.seek(0)
    row_count = buffer.getvalue().count("\n") - 1
    out_path.write_text(buffer.getvalue())
    print(f"exported {out_path.name} ({row_count:,} rows)")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = psycopg2.connect(dbname=DB_NAME)
    with conn.cursor() as cur:
        for view in VIEWS:
            export(cur, f"SELECT * FROM {view}", OUT_DIR / f"{view}.csv")
        export(cur, PAGE3_FLIGHT_METRICS, OUT_DIR / "page3_flight_metrics.csv")
        export(cur, PAGE3_TURNAROUND_BUFFER, OUT_DIR / "page3_turnaround_buffer.csv")
    conn.close()


if __name__ == "__main__":
    main()
