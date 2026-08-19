"""Tests for dashboard/queries/filters.py's pure WHERE-clause/default-state
helpers. No database connection is made -- SQLAlchemy's engine is created
lazily by db.connection and is never queried here (see conftest.py)."""
from queries.filters import build_where, is_default

MIN_DATE, MAX_DATE = "2024-01-01", "2024-12-31"


def test_is_default_true_for_full_range_and_no_filters():
    assert is_default({}, MIN_DATE, MAX_DATE) is True
    assert is_default({"start_date": MIN_DATE, "end_date": MAX_DATE}, MIN_DATE, MAX_DATE) is True


def test_is_default_false_when_any_filter_is_set():
    assert is_default({"airline": "AA"}, MIN_DATE, MAX_DATE) is False
    assert is_default({"airport": "ATL"}, MIN_DATE, MAX_DATE) is False
    assert is_default({"route": "ATL-JFK"}, MIN_DATE, MAX_DATE) is False
    assert is_default({"start_date": "2024-07-01"}, MIN_DATE, MAX_DATE) is False
    assert is_default({"end_date": "2024-07-31"}, MIN_DATE, MAX_DATE) is False


def test_build_where_with_no_filters_returns_true_clause():
    where, params = build_where({})
    assert where == "TRUE"
    assert params == {}


def test_build_where_combines_all_filters_with_and():
    filters = {
        "start_date": "2024-07-01", "end_date": "2024-07-31",
        "airline": "AA", "airport": "ATL", "route": "ATL-JFK",
    }
    where, params = build_where(filters)

    clauses = where.split(" AND ")
    assert "flight_date >= :start_date" in clauses
    assert "flight_date <= :end_date" in clauses
    assert "reporting_airline = :airline" in clauses
    assert "origin = :airport" in clauses
    assert "origin = :route_origin AND dest = :route_dest" in where

    assert params == {
        "start_date": "2024-07-01", "end_date": "2024-07-31",
        "airline": "AA", "airport": "ATL",
        "route_origin": "ATL", "route_dest": "JFK",
    }
