"""Makes src/ and dashboard/ importable without installing them as packages
(mirrors how the project's own scripts are actually run), and sets dummy DB
credentials so importing dashboard.queries.filters never needs a real .env
file or a live PostgreSQL connection -- SQLAlchemy's create_engine() is lazy
and doesn't connect until a query is actually run, which these tests never do.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "dashboard"))

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
