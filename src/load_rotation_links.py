"""Bulk-load data/processed/rotation_links.csv (from src/build_rotations.py, Step 4)
into the local PostgreSQL `rotation_links` table via COPY (no row-by-row inserts).

Run sql/schema.sql first to (re)create the table.

Same nullable-Int64 cast as load_to_postgres.py: pandas writes nullable numeric
columns as e.g. "23.0", which COPY's CSV parser rejects for an integer column.
"""
import io
from pathlib import Path

import pandas as pd
import psycopg2

DB_NAME = "airport_delays"
CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "rotation_links.csv"

INT_COLUMNS = [
    "flight_number", "prev_flight_number", "crs_dep_time",
    "prior_leg_arr_delay_minutes", "dep_delay_minutes", "arr_delay_minutes", "late_aircraft_delay",
]

SQL_COLUMNS = [
    "tail_number", "flight_date", "reporting_airline", "flight_number", "origin", "dest",
    "prev_flight_date", "prev_flight_number", "prev_dest", "crs_dep_time",
    "prior_leg_arr_delay_minutes", "dep_delay_minutes", "arr_delay_minutes", "late_aircraft_delay",
    "scheduled_turnaround_min", "observed_turnaround_min", "propagated_delay_estimate_min", "link_status",
]


def main():
    df = pd.read_csv(CSV_PATH)
    for col in INT_COLUMNS:
        df[col] = df[col].astype("Int64")

    buffer = io.StringIO()
    df.to_csv(buffer, index=False, na_rep="")
    buffer.seek(0)

    conn = psycopg2.connect(dbname=DB_NAME)
    with conn, conn.cursor() as cur:
        cur.copy_expert(
            f"COPY rotation_links ({', '.join(SQL_COLUMNS)}) FROM STDIN WITH (FORMAT csv, HEADER true, NULL '')",
            buffer,
        )
        print(f"loaded {CSV_PATH.name} ({cur.rowcount:,} rows)")
    conn.close()


if __name__ == "__main__":
    main()
