"""KPI card components."""
import math

from dash import dash_table, html

from . import theme


def _fmt(value, spec: str, suffix: str = "") -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    return f"{value:{spec}}{suffix}"


def _kpi_card(label: str, value: str, accent: str = theme.TEXT) -> html.Div:
    return html.Div(
        [
            html.Div(label, className="kpi-label"),
            html.Div(value, className="kpi-value", style={"color": accent}),
        ],
        className="kpi-card",
    )


def top_kpi_row(summary) -> html.Div:
    return html.Div(
        [
            _kpi_card("Total Flights", _fmt(summary["total_flights"], ",.0f")),
            _kpi_card("Delayed Flights", _fmt(summary["delayed_flights"], ",.0f")),
            _kpi_card("Delay Rate", _fmt(summary["delay_rate_pct"], ".1f", "%")),
            _kpi_card("Avg Delay", _fmt(summary["avg_delay_minutes"], ".1f", " min")),
        ],
        className="kpi-row",
    )


def network_summary_panel(summary) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.H3("Overall Network"),
                    html.Div(
                        [
                            _kpi_card("Total Flights", _fmt(summary["total_flights"], ",.0f")),
                            _kpi_card("Delayed Flights", _fmt(summary["delayed_flights"], ",.0f")),
                            _kpi_card("Delay Rate", _fmt(summary["delay_rate_pct"], ".2f", "%")),
                            _kpi_card("Avg Delay", _fmt(summary["avg_delay_minutes"], ".2f", " min")),
                            _kpi_card("Total Delay Minutes", _fmt(summary["total_delay_minutes"], ",.0f")),
                        ],
                        className="kpi-row",
                    ),
                ]
            ),
            html.Div(
                [
                    html.H3("Signal A — BTS LateAircraftDelay", style={"color": theme.SIGNAL_A}),
                    html.Div(
                        [
                            _kpi_card(
                                "Late-Aircraft Delay Minutes",
                                _fmt(summary["signal_a_late_aircraft_delay_minutes"], ",.0f"),
                                theme.SIGNAL_A,
                            ),
                            _kpi_card(
                                "Late-Aircraft Share",
                                _fmt(summary["signal_a_late_aircraft_share_pct"], ".2f", "%"),
                                theme.SIGNAL_A,
                            ),
                        ],
                        className="kpi-row",
                    ),
                ]
            ),
            html.Div(
                [
                    html.H3("Signal B — Reconstructed Propagation Estimate", style={"color": theme.SIGNAL_B}),
                    html.Div(
                        [
                            _kpi_card("Valid Links", _fmt(summary["signal_b_valid_links"], ",.0f"), theme.SIGNAL_B),
                            _kpi_card(
                                "Propagation Rate",
                                _fmt(summary["signal_b_propagation_rate_pct"], ".2f", "%"),
                                theme.SIGNAL_B,
                            ),
                            _kpi_card(
                                "Propagated Delay Minutes (Total)",
                                _fmt(summary["signal_b_propagated_delay_minutes"], ",.0f"),
                                theme.SIGNAL_B,
                            ),
                            _kpi_card(
                                "Avg Propagated Delay (per link)",
                                _fmt(summary["signal_b_avg_propagated_delay_minutes"], ".2f", " min"),
                                theme.SIGNAL_B,
                            ),
                        ],
                        className="kpi-row",
                    ),
                ]
            ),
        ],
        className="network-summary-panel",
    )


def signal_comparison_panel(summary) -> html.Div:
    """2x2 breakdown + coverage/correlation/agreement stats from
    v_propagation_signal_comparison (or its filtered equivalent)."""
    matrix_data = [
        {
            "": "Signal A: LateAircraftDelay present",
            "Signal B: propagated delay present": _fmt(summary["both_signals_present"], ",.0f"),
            "Signal B: absent": _fmt(summary["signal_a_only"], ",.0f"),
        },
        {
            "": "Signal A: absent",
            "Signal B: propagated delay present": _fmt(summary["signal_b_only"], ",.0f"),
            "Signal B: absent": _fmt(summary["both_signals_absent"], ",.0f"),
        },
    ]
    return html.Div(
        [
            html.H3("Signal A vs. Signal B — Agreement Matrix"),
            dash_table.DataTable(
                data=matrix_data,
                columns=[{"name": c, "id": c} for c in ["", "Signal B: propagated delay present", "Signal B: absent"]],
                style_cell={
                    "fontFamily": theme.FONT_FAMILY, "padding": "12px 16px", "textAlign": "center",
                    "border": f"1px solid {theme.BORDER}", "color": theme.TEXT,
                },
                style_header={"fontWeight": "600", "backgroundColor": theme.PAGE_BG, "border": f"1px solid {theme.BORDER}"},
                style_data_conditional=[{"if": {"column_id": ""}, "textAlign": "left", "fontWeight": "600"}],
            ),
            html.Div(
                [
                    _kpi_card("Signal A Coverage", _fmt(summary["signal_a_coverage_pct"], ".1f", "%"), theme.SIGNAL_A),
                    _kpi_card("Correlation (raw prior delay vs. Signal A)", _fmt(summary["corr_raw_prior_delay_vs_signal_a"], ".3f")),
                    _kpi_card("Correlation (buffer-adjusted vs. Signal A)", _fmt(summary["corr_buffer_adjusted_estimate_vs_signal_a"], ".3f")),
                    _kpi_card(
                        "Agreement Rate",
                        _fmt(summary["agreement_rate_pct"], ".1f", "%"),
                    ),
                ],
                className="kpi-row",
            ),
            html.P(
                "Agreement rate is dominated by the 'both absent' majority class — the "
                "matrix above gives the more informative per-cell breakdown.",
                className="chart-note",
            ),
        ],
        className="network-summary-panel",
    )
