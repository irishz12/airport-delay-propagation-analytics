"""SQLAlchemy engine for the read-only Postgres connection. Credentials come from
.env — never hardcoded."""
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import os

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DB_URL = (
    f"postgresql+psycopg2://{os.environ['DB_USER']}:{os.environ.get('DB_PASSWORD', '')}"
    f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"
)
engine = create_engine(DB_URL, pool_pre_ping=True)


def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})
