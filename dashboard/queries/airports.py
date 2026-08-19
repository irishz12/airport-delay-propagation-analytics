"""Airport-level performance (origin airport)."""
import pandas as pd

from db.connection import run_query
from .filters import build_where, is_default

_FILTERED_SQL = """
    WITH flight_agg AS (
        SELECT
            origin AS airport,
            COUNT(*) AS total_flights,
            ROUND(100.0 * COUNT(*) FILTER (WHERE arr_del15)
                / NULLIF(COUNT(*) FILTER (WHERE arr_del15 IS NOT NULL), 0), 2) AS delay_rate_pct,
            ROUND(AVG(arr_delay_minutes), 2) AS avg_delay_minutes,
            ROUND(100.0 * SUM(late_aircraft_delay)
                / NULLIF(SUM(carrier_delay + weather_delay + nas_delay + security_delay + late_aircraft_delay), 0), 2)
                AS signal_a_late_aircraft_share_pct
        FROM flights
        WHERE {where}
        GROUP BY origin
    ),
    rotation_agg AS (
        SELECT
            origin AS airport,
            ROUND(100.0 * COUNT(*) FILTER (WHERE link_status = 'valid' AND propagated_delay_estimate_min > 0)
                / NULLIF(COUNT(*) FILTER (WHERE link_status = 'valid'), 0), 2) AS signal_b_propagation_rate_pct,
            COALESCE((SUM(propagated_delay_estimate_min) FILTER (WHERE link_status = 'valid'))::numeric, 0)
                AS signal_b_propagated_delay_minutes,
            ROUND((AVG(propagated_delay_estimate_min) FILTER (WHERE link_status = 'valid'))::numeric, 2)
                AS signal_b_avg_propagated_delay_minutes
        FROM rotation_links
        WHERE {where}
        GROUP BY origin
    )
    SELECT
        f.airport, f.total_flights, f.delay_rate_pct, f.avg_delay_minutes, f.signal_a_late_aircraft_share_pct,
        r.signal_b_propagation_rate_pct, r.signal_b_propagated_delay_minutes, r.signal_b_avg_propagated_delay_minutes,
        (f.total_flights >= 1000) AS meets_min_volume_threshold
    FROM flight_agg f
    LEFT JOIN rotation_agg r ON r.airport = f.airport
"""


def get_airport_performance(filters: dict, min_date: str, max_date: str) -> pd.DataFrame:
    if is_default(filters, min_date, max_date):
        df = run_query("SELECT * FROM v_airport_performance")
    else:
        where, params = build_where(filters)
        df = run_query(_FILTERED_SQL.format(where=where), params)
    df["airport"] = df["airport"].str.strip()
    return df
