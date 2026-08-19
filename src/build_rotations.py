"""Reconstruct aircraft rotations from the `flights` table to build an independent
"prior-leg delay" signal (Signal B), and compare it against BTS's own
LateAircraftDelay attribution (Signal A).

Timezone handling (why we don't do "naive local-clock subtraction"):
Local departure/arrival clock fields alone can't be ordered or subtracted safely
across airports in different time zones, and a delayed flight's *actual* local
clock time doesn't tell us which calendar day it rolled into. Instead we localize
only ONE timestamp per flight — the scheduled departure, in the origin airport's
IANA timezone (via `airportsdata`), correctly handling DST for the actual date —
and derive everything else with plain UTC arithmetic using BTS's own
DepDelayMinutes / CRSElapsedTime / ActualElapsedTime fields, which BTS already
computes as true elapsed minutes (not naive clock differences):

    dep_utc_scheduled = localize(flight_date + CRSDepTime, origin tz) -> UTC
    dep_utc_actual     = dep_utc_scheduled + DepDelayMinutes
    arr_utc_scheduled  = dep_utc_scheduled + CRSElapsedTime
    arr_utc_actual      = dep_utc_actual + ActualElapsedTime

Rotation grouping: we group by Tail_Number and sort by true UTC time (not
bucketed per calendar date) specifically so overnight rotations are linked
correctly — a flight departing 23:50 and the next one at 00:40 the following
date is still an immediate rotation and would be wrongly split by a strict
per-calendar-date grouping.

Every current-leg row gets a `link_status`; rows are never silently dropped.
"""
import io
from pathlib import Path

import airportsdata
import numpy as np
import pandas as pd
import psycopg2

DB_NAME = "airport_delays"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "rotation_links.csv"

MIN_TURNAROUND_MIN = 15     # below this, a same-aircraft turnaround is physically implausible
MAX_TURNAROUND_MIN = 36 * 60  # above this, likely a broken chain (missed rotation, data gap)

QUERY = """
    SELECT tail_number, flight_date, reporting_airline, flight_number, origin, dest,
           crs_dep_time, crs_elapsed_time, actual_elapsed_time,
           dep_delay_minutes, arr_delay_minutes, cancelled, diverted, late_aircraft_delay
    FROM flights
    WHERE tail_number IS NOT NULL
"""


def load_flights() -> pd.DataFrame:
    conn = psycopg2.connect(dbname=DB_NAME)
    buffer = io.StringIO()
    with conn.cursor() as cur:
        cur.copy_expert(f"COPY ({QUERY}) TO STDOUT WITH (FORMAT csv, HEADER true)", buffer)
    conn.close()
    buffer.seek(0)
    df = pd.read_csv(buffer, parse_dates=["flight_date"])
    # COPY renders booleans as text 't'/'f', which pandas reads as plain strings
    # (any non-empty string is truthy) rather than inferring bool -- convert explicitly.
    df["cancelled"] = df["cancelled"] == "t"
    df["diverted"] = df["diverted"] == "t"
    return df


def localize_to_utc(naive_dt: pd.Series, tz_series: pd.Series) -> pd.Series:
    """Localize a naive datetime Series to UTC using a per-row IANA timezone,
    grouping by the small number of distinct timezones for vectorized speed."""
    result = pd.Series(pd.NaT, index=naive_dt.index, dtype="datetime64[ns, UTC]")
    for tz_name, idx in tz_series.groupby(tz_series).groups.items():
        localized = naive_dt.loc[idx].dt.tz_localize(tz_name, ambiguous="NaT", nonexistent="NaT")
        result.loc[idx] = localized.dt.tz_convert("UTC")
    return result


def add_utc_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    tz_map = {code: info["tz"] for code, info in airportsdata.load("IATA").items()}
    df["origin_tz"] = df["origin"].map(tz_map)

    # BTS uses "2400" for midnight at the end of the scheduled day (== 00:00 next day).
    is_2400 = df["crs_dep_time"] == 2400
    hhmm = df["crs_dep_time"].where(~is_2400, 0)
    dep_naive = (
        df["flight_date"] + pd.to_timedelta(is_2400.astype(int), unit="D")
        + pd.to_timedelta(hhmm // 100, unit="h") + pd.to_timedelta(hhmm % 100, unit="m")
    )

    df["dep_utc_scheduled"] = localize_to_utc(dep_naive, df["origin_tz"])
    df["arr_utc_scheduled"] = df["dep_utc_scheduled"] + pd.to_timedelta(df["crs_elapsed_time"], unit="m")
    df["dep_utc_actual"] = df["dep_utc_scheduled"] + pd.to_timedelta(df["dep_delay_minutes"], unit="m")
    df["arr_utc_actual"] = df["dep_utc_actual"] + pd.to_timedelta(df["actual_elapsed_time"], unit="m")
    return df


def build_links(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["tail_number", "dep_utc_scheduled"], na_position="first").reset_index(drop=True)

    prev_cols = ["flight_date", "flight_number", "origin", "dest", "arr_delay_minutes",
                 "cancelled", "diverted", "arr_utc_scheduled", "arr_utc_actual"]
    grouped = df.groupby("tail_number", sort=False)
    for col in prev_cols:
        df[f"prev_{col}"] = grouped[col].shift(1)

    df["scheduled_turnaround_min"] = (df["dep_utc_scheduled"] - df["prev_arr_utc_scheduled"]).dt.total_seconds() / 60
    df["observed_turnaround_min"] = (df["dep_utc_actual"] - df["prev_arr_utc_actual"]).dt.total_seconds() / 60

    conditions = [
        df["prev_flight_date"].isna(),
        df["prev_cancelled"].astype(bool),
        df["cancelled"].astype(bool),
        df["prev_diverted"].astype(bool),
        df["diverted"].astype(bool),
        df["prev_dest"] != df["origin"],
        df["dep_utc_scheduled"].isna() | df["prev_arr_utc_scheduled"].isna(),
        df["dep_utc_actual"].isna() | df["prev_arr_utc_actual"].isna(),
        df["observed_turnaround_min"] < 0,
        df["observed_turnaround_min"] < MIN_TURNAROUND_MIN,
        df["observed_turnaround_min"] > MAX_TURNAROUND_MIN,
    ]
    choices = [
        "excluded_no_prior_flight",
        "excluded_prior_cancelled",
        "excluded_current_cancelled",
        "excluded_prior_diverted",
        "excluded_current_diverted",
        "excluded_airport_mismatch",
        "excluded_missing_scheduled_times",
        "excluded_missing_actual_times",
        "invalid_negative_turnaround",
        "suspicious_short_turnaround",
        "suspicious_long_turnaround",
    ]
    df["link_status"] = np.select(conditions, choices, default="valid")

    df["prior_leg_arr_delay_minutes"] = df["prev_arr_delay_minutes"]
    df["available_turnaround_buffer_min"] = df["scheduled_turnaround_min"]
    # Simple, transparent estimate: upstream delay that exceeds the scheduled buffer.
    # Not a model — assumes turnaround otherwise proceeds on pace, ignores crew/gate
    # constraints and any recovery en route. This is Signal B.
    df["propagated_delay_estimate_min"] = (
        df["prior_leg_arr_delay_minutes"] - df["available_turnaround_buffer_min"]
    ).clip(lower=0)

    return df


OUTPUT_COLUMNS = [
    "tail_number", "flight_date", "reporting_airline", "flight_number", "origin", "dest",
    "prev_flight_date", "prev_flight_number", "prev_dest",
    "crs_dep_time", "prior_leg_arr_delay_minutes", "dep_delay_minutes", "arr_delay_minutes",
    "late_aircraft_delay", "scheduled_turnaround_min", "observed_turnaround_min",
    "propagated_delay_estimate_min", "link_status",
]


def compare_signals(valid: pd.DataFrame) -> None:
    """Signal A (BTS LateAircraftDelay) vs Signal B (our reconstructed prior-leg
    signal), on valid links only. A only exists for flights BTS itself found
    delayed >=15min; B is computable for every valid link."""
    print("\n=== Signal A vs Signal B ===")
    has_a = valid["late_aircraft_delay"].notna()
    print(f"valid links where Signal A is defined: {has_a.sum():,} ({has_a.mean() * 100:.2f}%)")

    subset = valid[has_a]
    corr_raw = subset["prior_leg_arr_delay_minutes"].corr(subset["late_aircraft_delay"])
    corr_est = subset["propagated_delay_estimate_min"].corr(subset["late_aircraft_delay"])
    print(f"correlation(prior-leg arrival delay, Signal A): {corr_raw:.3f}  (n={len(subset):,})")
    print(f"correlation(buffer-adjusted estimate, Signal A): {corr_est:.3f}")

    a_present = valid["late_aircraft_delay"].fillna(0) > 0
    b_present = valid["propagated_delay_estimate_min"] > 0
    total = len(valid)
    tp, fp, fn, tn = (a_present & b_present).sum(), (~a_present & b_present).sum(), \
        (a_present & ~b_present).sum(), (~a_present & ~b_present).sum()
    print(f"agreement rate (both present or both absent): {(tp + tn) / total * 100:.2f}%")
    print(f"  both present:                 {tp:,}")
    print(f"  both absent:                  {tn:,}")
    print(f"  B present, A absent (B-only): {fp:,}")
    print(f"  A present, B absent (A-only): {fn:,}")


def analyze_downstream_vs_prior(valid: pd.DataFrame) -> None:
    print("\n=== Downstream delay vs. prior-leg delay ===")
    bins = [-np.inf, 0, 15, 30, 60, 120, np.inf]
    labels = ["<=0", "1-15", "15-30", "30-60", "60-120", "120+"]
    bucketed = valid.assign(prior_delay_bucket=pd.cut(valid["prior_leg_arr_delay_minutes"], bins=bins, labels=labels))
    summary = bucketed.groupby("prior_delay_bucket", observed=True).agg(
        n=("dep_delay_minutes", "size"),
        avg_current_dep_delay=("dep_delay_minutes", "mean"),
        avg_current_arr_delay=("arr_delay_minutes", "mean"),
        pct_current_delayed_15=("arr_delay_minutes", lambda s: (s >= 15).mean() * 100),
    ).round(2)
    print(summary)
    corr = valid["prior_leg_arr_delay_minutes"].corr(valid["dep_delay_minutes"])
    print(f"correlation(prior-leg arrival delay, current-leg departure delay): {corr:.3f}")


def analyze_buffer_effect(valid: pd.DataFrame) -> None:
    print("\n=== Effect of scheduled turnaround buffer (prior leg delayed >0 min only) ===")
    delayed_prior = valid[valid["prior_leg_arr_delay_minutes"] > 0]
    bins = [0, 30, 45, 60, 90, 120, np.inf]
    labels = ["<30", "30-45", "45-60", "60-90", "90-120", "120+"]
    bucketed = delayed_prior.assign(
        buffer_bucket=pd.cut(delayed_prior["available_turnaround_buffer_min"], bins=bins, labels=labels)
    )
    summary = bucketed.groupby("buffer_bucket", observed=True).agg(
        n=("dep_delay_minutes", "size"),
        avg_prior_delay=("prior_leg_arr_delay_minutes", "mean"),
        avg_current_dep_delay=("dep_delay_minutes", "mean"),
        pct_current_delayed_15=("dep_delay_minutes", lambda s: (s >= 15).mean() * 100),
    ).round(2)
    print(summary)


def analyze_by_hour(valid: pd.DataFrame) -> None:
    print("\n=== Propagation by scheduled departure hour ===")
    bucketed = valid.assign(dep_hour=(valid["crs_dep_time"] // 100) % 24)
    summary = bucketed.groupby("dep_hour").agg(
        n=("propagated_delay_estimate_min", "size"),
        avg_propagated_estimate=("propagated_delay_estimate_min", "mean"),
        pct_with_propagated_delay=("propagated_delay_estimate_min", lambda s: (s > 0).mean() * 100),
    ).round(2)
    print(summary)


def analyze_by_airport(valid: pd.DataFrame, min_n: int = 500) -> None:
    print(f"\n=== Propagation by airport (min {min_n} valid links), top 15 ===")
    summary = valid.groupby("origin").agg(
        n=("propagated_delay_estimate_min", "size"),
        avg_propagated_estimate=("propagated_delay_estimate_min", "mean"),
        pct_with_propagated_delay=("propagated_delay_estimate_min", lambda s: (s > 0).mean() * 100),
    ).round(2)
    summary = summary[summary["n"] >= min_n].sort_values("avg_propagated_estimate", ascending=False)
    print(summary.head(15))


def analyze_by_route(valid: pd.DataFrame, min_n: int = 100) -> None:
    print(f"\n=== Propagation by route (min {min_n} valid links), top 15 ===")
    summary = valid.groupby(["origin", "dest"]).agg(
        n=("propagated_delay_estimate_min", "size"),
        avg_propagated_estimate=("propagated_delay_estimate_min", "mean"),
        pct_with_propagated_delay=("propagated_delay_estimate_min", lambda s: (s > 0).mean() * 100),
    ).round(2)
    summary = summary[summary["n"] >= min_n].sort_values("avg_propagated_estimate", ascending=False)
    print(summary.head(15))


def main():
    print("loading flights from Postgres...")
    df = load_flights()
    total_flights_with_tail = len(df)

    print("computing UTC timestamps...")
    df = add_utc_timestamps(df)

    print("reconstructing rotations...")
    df = build_links(df)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df[OUTPUT_COLUMNS].to_csv(OUT_PATH, index=False)
    print(f"saved {len(df):,} rows -> {OUT_PATH.relative_to(OUT_PATH.parent.parent.parent)}")
    print(f"flights with a usable tail_number: {total_flights_with_tail:,}")
    print(df["link_status"].value_counts())

    valid = df[df["link_status"] == "valid"]
    print(f"\nvalid links: {len(valid):,} "
          f"({len(valid) / total_flights_with_tail * 100:.2f}% of tail-known flights, "
          f"{len(valid) / len(df) * 100:.2f}% of all flights loaded)")

    compare_signals(valid)
    analyze_downstream_vs_prior(valid)
    analyze_buffer_effect(valid)
    analyze_by_hour(valid)
    analyze_by_airport(valid)
    analyze_by_route(valid)


if __name__ == "__main__":
    main()
