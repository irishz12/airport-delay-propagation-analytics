"""Turnaround-buffer performance -- downstream delay rate by scheduled-buffer bucket,
restricted to links where the prior leg was actually delayed."""
import pandas as pd

from db.connection import run_query
from .filters import build_where, is_default

_FILTERED_SQL = """
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
        WHERE {where} AND link_status = 'valid' AND prior_leg_arr_delay_minutes > 0
    )
    SELECT
        bucket_order,
        CASE bucket_order
            WHEN 0 THEN '<=0 (no scheduled buffer)' WHEN 1 THEN '0-30' WHEN 2 THEN '30-45' WHEN 3 THEN '45-60'
            WHEN 4 THEN '60-90' WHEN 5 THEN '90-120' ELSE '120+'
        END AS buffer_bucket_minutes,
        COUNT(*) AS n_links,
        ROUND(AVG(prior_leg_arr_delay_minutes), 2) AS avg_prior_leg_delay_minutes,
        ROUND(100.0 * COUNT(*) FILTER (WHERE dep_delay_minutes >= 15) / COUNT(*), 2) AS downstream_delay_rate_pct
    FROM bucketed
    GROUP BY bucket_order
    ORDER BY bucket_order
"""


def get_turnaround_buffer_performance(filters: dict, min_date: str, max_date: str) -> pd.DataFrame:
    if is_default(filters, min_date, max_date):
        return run_query("SELECT * FROM v_turnaround_buffer_performance ORDER BY bucket_order")
    where, params = build_where(filters)
    return run_query(_FILTERED_SQL.format(where=where), params)
