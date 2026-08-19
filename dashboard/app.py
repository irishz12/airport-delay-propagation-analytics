"""Airport Delay Propagation Analytics -- Plotly Dash dashboard.

Reads exclusively from the approved PostgreSQL views/tables (see db/connection.py,
queries/). Nothing here modifies the database. Run from this directory:
    python app.py
"""
import dash
from dash import Input, Output, dcc, html

from components import charts, kpis, theme
from components import filters as filter_components
from queries import airports, delay_causes, filters as query_filters, hourly, network, propagation, routes, turnaround

TAB_STYLE = {
    "padding": "14px 22px", "fontWeight": "500", "border": "none", "borderBottom": "2px solid transparent",
    "color": theme.MUTED_TEXT, "backgroundColor": "transparent",
}
TAB_SELECTED_STYLE = {
    "padding": "14px 22px", "fontWeight": "600", "border": "none",
    "borderBottom": f"2px solid {theme.ACCENT}", "color": theme.TEXT, "backgroundColor": "transparent",
}
GRAPH_CONFIG = {"displayModeBar": False}

FILTER_OPTIONS = query_filters.get_filter_options()
MIN_DATE, MAX_DATE = FILTER_OPTIONS["min_date"], FILTER_OPTIONS["max_date"]

app = dash.Dash(__name__, title="Airport Delay Propagation Analytics")
server = app.server

TABS = [
    ("airport", "Airport Performance"),
    ("route", "Route Performance"),
    ("causes", "Delay Causes"),
    ("hourly", "Hour-of-Day"),
    ("turnaround", "Turnaround Analysis"),
    ("propagation", "Propagation Analysis"),
    ("network", "Network Summary"),
]

app.layout = html.Div(
    [
        html.Header(
            [
                html.H1("Airport Delay Propagation Analytics"),
                html.P(
                    "BTS 2024 domestic flights — Signal A (BTS LateAircraftDelay) vs. Signal B "
                    "(independently reconstructed prior-leg propagation estimate)."
                ),
            ],
            className="app-header",
        ),
        filter_components.filter_bar(FILTER_OPTIONS),
        html.Div(id="kpi-row-container"),
        dcc.Tabs(
            id="tabs",
            value=TABS[0][0],
            children=[
                dcc.Tab(label=label, value=key, style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE)
                for key, label in TABS
            ],
        ),
        dcc.Loading(html.Div(id="tab-content"), type="circle"),
    ],
    className="app-container",
)


def _filters_from_inputs(start_date, end_date, airline, airport, route) -> dict:
    return {"start_date": start_date, "end_date": end_date, "airline": airline, "airport": airport, "route": route}


def _chart(fig) -> html.Div:
    return html.Div(dcc.Graph(figure=fig, config=GRAPH_CONFIG), className="chart-card")


@app.callback(
    Output("filter-date-range", "start_date"),
    Output("filter-date-range", "end_date"),
    Output("filter-airline", "value"),
    Output("filter-airport", "value"),
    Output("filter-route", "value"),
    Input("filter-reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_filters(_n_clicks):
    return MIN_DATE, MAX_DATE, None, None, None


@app.callback(
    Output("kpi-row-container", "children"),
    Input("filter-date-range", "start_date"),
    Input("filter-date-range", "end_date"),
    Input("filter-airline", "value"),
    Input("filter-airport", "value"),
    Input("filter-route", "value"),
)
def update_kpi_row(start_date, end_date, airline, airport, route):
    filters = _filters_from_inputs(start_date, end_date, airline, airport, route)
    summary = network.get_network_summary(filters, MIN_DATE, MAX_DATE)
    return kpis.top_kpi_row(summary)


@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "value"),
    Input("filter-date-range", "start_date"),
    Input("filter-date-range", "end_date"),
    Input("filter-airline", "value"),
    Input("filter-airport", "value"),
    Input("filter-route", "value"),
)
def update_tab_content(tab, start_date, end_date, airline, airport, route):
    filters = _filters_from_inputs(start_date, end_date, airline, airport, route)

    if tab == "airport":
        df = airports.get_airport_performance(filters, MIN_DATE, MAX_DATE)
        return _chart(charts.airport_performance_chart(df))

    if tab == "route":
        df = routes.get_route_performance(filters, MIN_DATE, MAX_DATE)
        return _chart(charts.route_performance_chart(df))

    if tab == "causes":
        df = delay_causes.get_delay_cause_breakdown(filters, MIN_DATE, MAX_DATE)
        return _chart(charts.delay_cause_chart(df))

    if tab == "hourly":
        df = hourly.get_hour_of_day_performance(filters, MIN_DATE, MAX_DATE)
        return _chart(charts.hour_of_day_chart(df))

    if tab == "turnaround":
        df = turnaround.get_turnaround_buffer_performance(filters, MIN_DATE, MAX_DATE)
        return _chart(charts.turnaround_buffer_chart(df))

    if tab == "propagation":
        comparison = propagation.get_propagation_comparison(filters, MIN_DATE, MAX_DATE)
        hourly_df = hourly.get_hour_of_day_performance(filters, MIN_DATE, MAX_DATE)
        airport_df = airports.get_airport_performance(filters, MIN_DATE, MAX_DATE)
        return html.Div(
            [
                kpis.signal_comparison_panel(comparison),
                _chart(charts.propagation_by_hour_chart(hourly_df)),
                _chart(charts.propagation_airport_comparison_chart(airport_df)),
            ]
        )

    if tab == "network":
        summary = network.get_network_summary(filters, MIN_DATE, MAX_DATE)
        return kpis.network_summary_panel(summary)

    return html.Div("Unknown tab")


if __name__ == "__main__":
    app.run(debug=True)
