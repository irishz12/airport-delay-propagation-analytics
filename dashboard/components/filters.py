"""Filter bar: Date, Airline, Airport, Route."""
from dash import dcc, html


def filter_bar(options: dict) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Label("Date Range"),
                    dcc.DatePickerRange(
                        id="filter-date-range",
                        min_date_allowed=options["min_date"],
                        max_date_allowed=options["max_date"],
                        start_date=options["min_date"],
                        end_date=options["max_date"],
                        display_format="YYYY-MM-DD",
                    ),
                ],
                className="filter-group",
            ),
            html.Div(
                [
                    html.Label("Airline"),
                    dcc.Dropdown(
                        id="filter-airline",
                        options=[{"label": a, "value": a} for a in options["airlines"]],
                        placeholder="All airlines",
                        clearable=True,
                    ),
                ],
                className="filter-group",
            ),
            html.Div(
                [
                    html.Label("Airport"),
                    html.Span("(flight origin)", className="filter-caption"),
                    dcc.Dropdown(
                        id="filter-airport",
                        options=[{"label": a, "value": a} for a in options["airports"]],
                        placeholder="All airports",
                        clearable=True,
                    ),
                ],
                className="filter-group",
            ),
            html.Div(
                [
                    html.Label("Route"),
                    dcc.Dropdown(
                        id="filter-route",
                        options=options["routes"],
                        placeholder="All routes",
                        clearable=True,
                    ),
                ],
                className="filter-group",
            ),
            html.Button("Reset Filters", id="filter-reset", n_clicks=0, className="reset-button"),
        ],
        className="filter-bar",
    )
