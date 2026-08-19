"""Download BTS Reporting Carrier On-Time Performance data for 2024.

Source: https://www.transtats.bts.gov/Tables.asp?QO_VQ=EFD (verified live URL pattern,
verified column names against the actual downloaded CSV before writing this script).

For each month, downloads the zipped CSV to a temp file (resuming via HTTP Range
requests if interrupted), verifies the zip is complete and uncorrupted, then keeps
only the columns needed for delay-propagation analysis and writes a trimmed CSV to
data/raw/.
"""
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

YEAR = 2024
URL_TEMPLATE = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
)
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
HEADERS = {"User-Agent": "Mozilla/5.0"}
MAX_ATTEMPTS = 8

COLUMNS = [
    "FlightDate", "Reporting_Airline", "Flight_Number_Reporting_Airline", "Tail_Number",
    "Origin", "Dest",
    "CRSDepTime", "DepTime", "CRSArrTime", "ArrTime", "WheelsOff", "WheelsOn", "TaxiOut", "TaxiIn",
    "DepDelayMinutes", "ArrDelayMinutes", "ArrDel15",
    "CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay",
    "Cancelled", "CancellationCode", "Diverted",
    "CRSElapsedTime", "ActualElapsedTime", "AirTime", "Distance",
]

session = requests.Session()
retries = Retry(total=5, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retries))


def fetch_with_resume(url: str, tmp_path: Path) -> None:
    """Download url to tmp_path, resuming from the existing file size via Range."""
    total = int(session.head(url, headers=HEADERS, timeout=30).headers["Content-Length"])
    downloaded = tmp_path.stat().st_size if tmp_path.exists() else 0

    while downloaded < total:
        request_headers = {**HEADERS, "Range": f"bytes={downloaded}-"}
        with session.get(url, headers=request_headers, stream=True, timeout=60) as r:
            r.raise_for_status()
            # Server may ignore Range and resend the full file (status 200 instead of 206).
            mode = "ab" if r.status_code == 206 else "wb"
            if mode == "wb":
                downloaded = 0
            with open(tmp_path, mode) as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)

    if tmp_path.stat().st_size != total:
        raise requests.exceptions.ConnectionError("downloaded size does not match Content-Length")


def download_month(year: int, month: int) -> pd.DataFrame:
    url = URL_TEMPLATE.format(year=year, month=month)
    tmp_path = OUT_DIR / f".tmp_flights_{year}_{month:02d}.zip"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            fetch_with_resume(url, tmp_path)
            with zipfile.ZipFile(tmp_path) as zf:
                if zf.testzip() is not None:
                    raise zipfile.BadZipFile("CRC check failed on a member file")
                csv_name = next(name for name in zf.namelist() if name.endswith(".csv"))
                with zf.open(csv_name) as f:
                    df = pd.read_csv(f, usecols=COLUMNS)
            tmp_path.unlink()
            return df
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                zipfile.BadZipFile) as e:
            print(f"  attempt {attempt} failed ({e.__class__.__name__}: {e}), retrying...")
            if isinstance(e, zipfile.BadZipFile):
                tmp_path.unlink(missing_ok=True)  # corrupt bytes can't be resumed, restart clean
            time.sleep(min(5 * attempt, 60))

    raise RuntimeError(f"failed to download {year}-{month:02d} after {MAX_ATTEMPTS} attempts")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for month in range(1, 13):
        out_path = OUT_DIR / f"flights_{YEAR}_{month:02d}.csv"
        if out_path.exists():
            print(f"skip {out_path.name} (already downloaded)")
            continue
        print(f"downloading {YEAR}-{month:02d}...")
        df = download_month(YEAR, month)
        df.to_csv(out_path, index=False)
        print(f"  saved {len(df):,} rows -> {out_path.name}")


if __name__ == "__main__":
    main()
