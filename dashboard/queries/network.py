"""Network summary + top KPI cards.

Default: SELECT * FROM v_network_summary directly.
Filtered: identical formulas (copied from sql/schema.sql), scoped with WHERE.
"""
import pandas as pd

from db.connection import run_query
from .filters import build_where, is_default

_FILTERED_SQL = """
    WITH flight_agg AS (
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
        WHERE {where}
    ),
    rotation_agg AS (
        SELECT
            COUNT(*) FILTER (WHERE link_status = 'valid') AS signal_b_valid_links,
            ROUND(100.0 * COUNT(*) FILTER (WHERE link_status = 'valid' AND propagated_delay_estimate_min > 0)
                / NULLIF(COUNT(*) FILTER (WHERE link_status = 'valid'), 0), 2) AS signal_b_propagation_rate_pct,
            ROUND((SUM(propagated_delay_estimate_min) FILTER (WHERE link_status = 'valid'))::numeric, 0)
                AS signal_b_propagated_delay_minutes,
            ROUND((AVG(propagated_delay_estimate_min) FILTER (WHERE link_status = 'valid'))::numeric, 2)
                AS signal_b_avg_propagated_delay_minutes
        FROM rotation_links
        WHERE {where}
    )
    SELECT * FROM flight_agg CROSS JOIN rotation_agg
"""


def get_network_summary(filters: dict, min_date: str, max_date: str) -> pd.Series:
    if is_default(filters, min_date, max_date):
        df = run_query("SELECT * FROM v_network_summary")
    else:
        where, params = build_where(filters)
        df = run_query(_FILTERED_SQL.format(where=where), params)
    return df.iloc[0]
