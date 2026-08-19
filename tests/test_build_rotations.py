"""Tests for build_links() in src/build_rotations.py -- the core rotation-link
reconstruction and Signal B propagation-estimate calculation. Pure function:
takes a DataFrame with pre-computed UTC timestamp columns (the output of
add_utc_timestamps(), not exercised here) and returns one, no DB/network
involved.

Each test tail number is self-contained so link_status assertions can't be
affected by rows from other tail numbers.
"""
import pandas as pd

from build_rotations import build_links

T0 = pd.Timestamp("2024-06-01 12:00", tz="UTC")

BASE_COLUMNS = [
    "tail_number", "flight_date", "flight_number", "origin", "dest",
    "arr_delay_minutes", "cancelled", "diverted",
    "dep_utc_scheduled", "dep_utc_actual", "arr_utc_scheduled", "arr_utc_actual",
]


def _leg(tail, flight_number, origin, dest, dep_sched, dep_actual, arr_sched, arr_actual,
         arr_delay_minutes=0, cancelled=False, diverted=False):
    return dict(zip(BASE_COLUMNS, [
        tail, dep_sched.date(), flight_number, origin, dest,
        arr_delay_minutes, cancelled, diverted,
        dep_sched, dep_actual, arr_sched, arr_actual,
    ]))


def _status(df, tail, flight_number):
    row = df[(df["tail_number"] == tail) & (df["flight_number"] == flight_number)].iloc[0]
    return row


def test_valid_link_on_time_no_propagation():
    # T1: on-time first leg, 60-min scheduled/observed turnaround -> valid, no propagation.
    rows = [
        _leg("T1", 1, "ATL", "JFK", T0, T0, T0 + pd.Timedelta(hours=2), T0 + pd.Timedelta(hours=2)),
        _leg("T1", 2, "JFK", "BOS", T0 + pd.Timedelta(hours=3), T0 + pd.Timedelta(hours=3),
             T0 + pd.Timedelta(hours=4), T0 + pd.Timedelta(hours=4)),
    ]
    df = build_links(pd.DataFrame(rows))
    row = _status(df, "T1", 2)
    assert row["link_status"] == "valid"
    assert row["scheduled_turnaround_min"] == 60
    assert row["propagated_delay_estimate_min"] == 0


def test_propagation_estimate_clips_at_zero_when_buffer_covers_delay():
    # Prior leg arrives 20 min late, but the scheduled buffer (60 min) covers it.
    rows = [
        _leg("T2", 1, "ATL", "JFK", T0, T0, T0 + pd.Timedelta(hours=2),
             T0 + pd.Timedelta(hours=2, minutes=20), arr_delay_minutes=20),
        _leg("T2", 2, "JFK", "BOS", T0 + pd.Timedelta(hours=3), T0 + pd.Timedelta(hours=3, minutes=20),
             T0 + pd.Timedelta(hours=4), T0 + pd.Timedelta(hours=4, minutes=20)),
    ]
    df = build_links(pd.DataFrame(rows))
    row = _status(df, "T2", 2)
    assert row["link_status"] == "valid"
    assert row["prior_leg_arr_delay_minutes"] == 20
    assert row["scheduled_turnaround_min"] == 60
    assert row["propagated_delay_estimate_min"] == 0


def test_propagation_estimate_is_delay_minus_buffer_when_delay_exceeds_buffer():
    # Prior leg arrives 90 min late; scheduled buffer is only 45 min -> propagated = 45.
    rows = [
        _leg("T3", 1, "ATL", "ORD", T0, T0, T0 + pd.Timedelta(hours=2),
             T0 + pd.Timedelta(hours=2, minutes=90), arr_delay_minutes=90),
        _leg("T3", 2, "ORD", "DEN", T0 + pd.Timedelta(hours=2, minutes=45),
             T0 + pd.Timedelta(hours=4, minutes=20),
             T0 + pd.Timedelta(hours=5), T0 + pd.Timedelta(hours=6, minutes=30)),
    ]
    df = build_links(pd.DataFrame(rows))
    row = _status(df, "T3", 2)
    assert row["link_status"] == "valid"
    assert row["prior_leg_arr_delay_minutes"] == 90
    assert row["scheduled_turnaround_min"] == 45
    assert row["propagated_delay_estimate_min"] == 45


def test_no_prior_flight_for_first_leg_of_a_tail_number():
    rows = [
        _leg("T4", 1, "ATL", "JFK", T0, T0, T0 + pd.Timedelta(hours=2), T0 + pd.Timedelta(hours=2)),
    ]
    df = build_links(pd.DataFrame(rows))
    row = _status(df, "T4", 1)
    assert row["link_status"] == "excluded_no_prior_flight"


def test_prior_leg_cancelled_excludes_the_link():
    rows = [
        _leg("T5", 1, "ATL", "JFK", T0, T0, T0 + pd.Timedelta(hours=2), T0 + pd.Timedelta(hours=2),
             cancelled=True),
        _leg("T5", 2, "JFK", "BOS", T0 + pd.Timedelta(hours=3), T0 + pd.Timedelta(hours=3),
             T0 + pd.Timedelta(hours=4), T0 + pd.Timedelta(hours=4)),
    ]
    df = build_links(pd.DataFrame(rows))
    row = _status(df, "T5", 2)
    assert row["link_status"] == "excluded_prior_cancelled"


def test_current_leg_cancelled_excludes_the_link():
    rows = [
        _leg("T6", 1, "ATL", "JFK", T0, T0, T0 + pd.Timedelta(hours=2), T0 + pd.Timedelta(hours=2)),
        _leg("T6", 2, "JFK", "BOS", T0 + pd.Timedelta(hours=3), T0 + pd.Timedelta(hours=3),
             T0 + pd.Timedelta(hours=4), T0 + pd.Timedelta(hours=4), cancelled=True),
    ]
    df = build_links(pd.DataFrame(rows))
    row = _status(df, "T6", 2)
    assert row["link_status"] == "excluded_current_cancelled"


def test_airport_mismatch_excludes_the_link():
    # Prior leg lands at LAX, but the next leg departs from SFO -- not the same aircraft's chain.
    rows = [
        _leg("T7", 1, "ATL", "LAX", T0, T0, T0 + pd.Timedelta(hours=2), T0 + pd.Timedelta(hours=2)),
        _leg("T7", 2, "SFO", "BOS", T0 + pd.Timedelta(hours=3), T0 + pd.Timedelta(hours=3),
             T0 + pd.Timedelta(hours=4), T0 + pd.Timedelta(hours=4)),
    ]
    df = build_links(pd.DataFrame(rows))
    row = _status(df, "T7", 2)
    assert row["link_status"] == "excluded_airport_mismatch"


def test_short_turnaround_is_flagged_suspicious():
    # Observed turnaround of 5 minutes is below the 15-minute plausibility floor.
    rows = [
        _leg("T8", 1, "ATL", "JFK", T0, T0, T0 + pd.Timedelta(hours=2), T0 + pd.Timedelta(hours=2)),
        _leg("T8", 2, "JFK", "BOS", T0 + pd.Timedelta(hours=2, minutes=5), T0 + pd.Timedelta(hours=2, minutes=5),
             T0 + pd.Timedelta(hours=3), T0 + pd.Timedelta(hours=3)),
    ]
    df = build_links(pd.DataFrame(rows))
    row = _status(df, "T8", 2)
    assert row["link_status"] == "suspicious_short_turnaround"


def test_long_turnaround_is_flagged_suspicious():
    # Observed turnaround of 37 hours is above the 36-hour plausibility ceiling.
    rows = [
        _leg("T9", 1, "ATL", "JFK", T0, T0, T0 + pd.Timedelta(hours=2), T0 + pd.Timedelta(hours=2)),
        _leg("T9", 2, "JFK", "BOS", T0 + pd.Timedelta(hours=39), T0 + pd.Timedelta(hours=39),
             T0 + pd.Timedelta(hours=40), T0 + pd.Timedelta(hours=40)),
    ]
    df = build_links(pd.DataFrame(rows))
    row = _status(df, "T9", 2)
    assert row["link_status"] == "suspicious_long_turnaround"
