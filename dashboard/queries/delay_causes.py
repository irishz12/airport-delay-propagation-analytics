"""Delay-cause breakdown -- Signal A only (BTS's cause fields have no Signal B analogue)."""
import pandas as pd

from db.connection import run_query
from .filters import build_where, is_default

_FILTERED_SQL = """
    WITH cause_totals AS (
        SELECT
            SUM(carrier_delay)       AS carrier_delay,
            SUM(weather_delay)       AS weather_delay,
            SUM(nas_delay)           AS nas_delay,
            SUM(security_delay)      AS security_delay,
            SUM(late_aircraft_delay) AS late_aircraft_delay
        FROM flights
        WHERE {where} AND carrier_delay IS NOT NULL
    )
    SELECT cause, minutes, ROUND(100.0 * minutes / SUM(minutes) OVER (), 2) AS pct_of_total_delay_minutes
    FROM (
        SELECT 'carrier_delay' AS cause, carrier_delay AS minutes FROM cause_totals UNION ALL
        SELECT 'weather_delay',            weather_delay           FROM cause_totals UNION ALL
        SELECT 'nas_delay',                nas_delay                FROM cause_totals UNION ALL
        SELECT 'security_delay',           security_delay           FROM cause_totals UNION ALL
        SELECT 'late_aircraft_delay',      late_aircraft_delay      FROM cause_totals
    ) unpivoted
    ORDER BY minutes DESC
"""


def get_delay_cause_breakdown(filters: dict, min_date: str, max_date: str) -> pd.DataFrame:
    if is_default(filters, min_date, max_date):
        return run_query("SELECT * FROM v_delay_cause_performance")
    where, params = build_where(filters)
    return run_query(_FILTERED_SQL.format(where=where), params)
