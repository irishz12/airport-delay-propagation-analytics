"""Bulk-load the 12 trimmed 2024 BTS CSVs (data/raw/) into the local PostgreSQL
`flights` table via COPY (no row-by-row inserts).

Run sql/schema.sql first to (re)create the table. Raw CSVs in data/raw/ are only
read here, never modified.

COPY's CSV parser rejects "0.0" for an integer column and doesn't understand
BTS's 0.0/1.0 float encoding of flags, so each file is cast to nullable pandas
dtypes (Int64 / boolean) before being streamed to COPY as an in-memory CSV buffer.
"""
import io
from pathlib import Path

import pandas as pd
import psycopg2

DB_NAME = "airport_delays"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

INT_COLUMNS = [
    "Flight_Number_Reporting_Airline", "CRSDepTime", "DepTime", "DepDelayMinutes",
    "TaxiOut", "WheelsOff", "WheelsOn", "TaxiIn", "CRSArrTime", "ArrTime",
    "ArrDelayMinutes", "CRSElapsedTime", "ActualElapsedTime", "AirTime", "Distance",
    "CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay",
]
BOOL_COLUMNS = ["ArrDel15", "Cancelled", "Diverted"]

# Order matches data/raw CSV column order; only the naming is SQL-style (snake_case).
SQL_COLUMNS = [
    "flight_date", "reporting_airline", "tail_number", "flight_number", "origin", "dest",
    "crs_dep_time", "dep_time", "dep_delay_minutes", "taxi_out", "wheels_off", "wheels_on",
    "taxi_in", "crs_arr_time", "arr_time", "arr_delay_minutes", "arr_del15", "cancelled",
    "cancellation_code", "diverted", "crs_elapsed_time", "actual_elapsed_time", "air_time",
    "distance", "carrier_delay", "weather_delay", "nas_delay", "security_delay",
    "late_aircraft_delay",
]


def prepare_buffer(csv_path: Path) -> io.StringIO:
    df = pd.read_csv(csv_path, dtype={"CancellationCode": "string"})
    for col in INT_COLUMNS:
        df[col] = df[col].astype("Int64")
    for col in BOOL_COLUMNS:
        df[col] = df[col].astype("Int64") == 1  # nullable Int64 -> nullable boolean, NA preserved

    buffer = io.StringIO()
    df.to_csv(buffer, index=False, na_rep="")
    buffer.seek(0)
    return buffer


def main():
    conn = psycopg2.connect(dbname=DB_NAME)
    with conn, conn.cursor() as cur:
        for csv_path in sorted(DATA_DIR.glob("flights_2024_*.csv")):
            buffer = prepare_buffer(csv_path)
            cur.copy_expert(
                f"COPY flights ({', '.join(SQL_COLUMNS)}) FROM STDIN WITH (FORMAT csv, HEADER true, NULL '')",
                buffer,
            )
            print(f"loaded {csv_path.name} ({cur.rowcount:,} rows)")
    conn.close()


if __name__ == "__main__":
    main()
