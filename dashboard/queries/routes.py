"""Route-level performance (origin-destination pair)."""
import pandas as pd

from db.connection import run_query
from .filters import build_where, is_default

_FILTERED_SQL = """
    WITH flight_agg AS (
        SELECT
            origin, dest,
            COUNT(*) AS total_flights,
            ROUND(100.0 * COUNT(*) FILTER (WHERE arr_del15)
                / NULLIF(COUNT(*) FILTER (WHERE arr_del15 IS NOT NULL), 0), 2) AS delay_rate_pct,
            ROUND(AVG(arr_delay_minutes), 2) AS avg_delay_minutes,
            ROUND(100.0 * SUM(late_aircraft_delay)
                / NULLIF(SUM(carrier_delay + weather_delay + nas_delay + security_delay + late_aircraft_delay), 0), 2)
                AS signal_a_late_aircraft_share_pct
        FROM flights
        WHERE {where}
        GROUP BY origin, dest
    ),
    rotation_agg AS (
        SELECT
            origin, dest,
            ROUND(100.0 * COUNT(*) FILTER (WHERE link_status = 'valid' AND propagated_delay_estimate_min > 0)
                / NULLIF(COUNT(*) FILTER (WHERE link_status = 'valid'), 0), 2) AS signal_b_propagation_rate_pct
        FROM rotation_links
        WHERE {where}
        GROUP BY origin, dest
    )
    SELECT
        f.origin, f.dest, f.total_flights, f.delay_rate_pct, f.avg_delay_minutes,
        f.signal_a_late_aircraft_share_pct, r.signal_b_propagation_rate_pct,
        (f.total_flights >= 200) AS meets_min_volume_threshold
    FROM flight_agg f
    LEFT JOIN rotation_agg r ON r.origin = f.origin AND r.dest = f.dest
"""


def get_route_performance(filters: dict, min_date: str, max_date: str) -> pd.DataFrame:
    if is_default(filters, min_date, max_date):
        df = run_query("SELECT * FROM v_route_performance")
    else:
        where, params = build_where(filters)
        df = run_query(_FILTERED_SQL.format(where=where), params)
    df["origin"] = df["origin"].str.strip()
    df["dest"] = df["dest"].str.strip()
    df["route"] = df["origin"] + " → " + df["dest"]
    return df
