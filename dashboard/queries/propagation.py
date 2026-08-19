"""Signal A vs. Signal B validation (correlation, agreement, coverage)."""
import pandas as pd

from db.connection import run_query
from .filters import build_where, is_default

_FILTERED_SQL = """
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
    FROM rotation_links
    WHERE {where}
"""


def get_propagation_comparison(filters: dict, min_date: str, max_date: str) -> pd.Series:
    if is_default(filters, min_date, max_date):
        df = run_query("SELECT * FROM v_propagation_signal_comparison")
    else:
        where, params = build_where(filters)
        df = run_query(_FILTERED_SQL.format(where=where), params)
    return df.iloc[0]
