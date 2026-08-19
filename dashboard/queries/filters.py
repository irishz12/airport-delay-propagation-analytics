"""Shared filter-option queries and WHERE-clause building.

flights and rotation_links share the same column names for every filterable
dimension (flight_date, reporting_airline, origin, dest), so one WHERE builder
covers both tables -- no joins or Power BI-style relationships needed.
"""
from db.connection import run_query


def get_filter_options() -> dict:
    bounds = run_query("SELECT MIN(flight_date) AS min_date, MAX(flight_date) AS max_date FROM flights").iloc[0]
    airlines = run_query("SELECT DISTINCT reporting_airline FROM flights ORDER BY 1")["reporting_airline"].tolist()
    airports = sorted(run_query("SELECT airport FROM v_airport_performance")["airport"].str.strip().tolist())
    routes = run_query(
        "SELECT origin, dest FROM v_route_performance WHERE meets_min_volume_threshold ORDER BY origin, dest"
    )
    route_options = [
        {"label": f"{o.strip()} → {d.strip()}", "value": f"{o.strip()}-{d.strip()}"}
        for o, d in zip(routes["origin"], routes["dest"])
    ]
    return {
        "min_date": str(bounds["min_date"]),
        "max_date": str(bounds["max_date"]),
        "airlines": airlines,
        "airports": airports,
        "routes": route_options,
    }


def is_default(filters: dict, min_date: str, max_date: str) -> bool:
    """True when no filter narrows the data below the full unfiltered dataset --
    the view-based (fast) query path is used in this case."""
    return (
        filters.get("start_date", min_date) == min_date
        and filters.get("end_date", max_date) == max_date
        and not filters.get("airline")
        and not filters.get("airport")
        and not filters.get("route")
    )


def build_where(filters: dict) -> tuple[str, dict]:
    clauses = []
    params = {}
    if filters.get("start_date"):
        clauses.append("flight_date >= :start_date")
        params["start_date"] = filters["start_date"]
    if filters.get("end_date"):
        clauses.append("flight_date <= :end_date")
        params["end_date"] = filters["end_date"]
    if filters.get("airline"):
        clauses.append("reporting_airline = :airline")
        params["airline"] = filters["airline"]
    if filters.get("airport"):
        clauses.append("origin = :airport")
        params["airport"] = filters["airport"]
    if filters.get("route"):
        origin, dest = filters["route"].split("-")
        clauses.append("origin = :route_origin AND dest = :route_dest")
        params["route_origin"] = origin
        params["route_dest"] = dest
    return (" AND ".join(clauses) if clauses else "TRUE"), params
