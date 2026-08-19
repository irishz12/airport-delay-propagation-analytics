"""Plotly figure builders. Each function takes a DataFrame from queries/ and
returns a go.Figure -- no metric recalculation happens here beyond what's needed
to shape data for a chart (sorting, top-N, pivoting for display)."""
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import theme

CAUSE_LABELS = {
    "carrier_delay": "Carrier Delay",
    "weather_delay": "Weather Delay",
    "nas_delay": "NAS Delay",
    "security_delay": "Security Delay",
    "late_aircraft_delay": "Late Aircraft Delay",
}


def _apply_layout(fig: go.Figure, title: str, height: int = 380, margin: dict | None = None) -> go.Figure:
    layout = dict(theme.PLOTLY_LAYOUT)
    if margin:
        layout["margin"] = margin
    fig.update_layout(**layout, title=dict(text=title, x=0, xanchor="left", font=theme.TITLE_FONT), height=height)
    fig.update_xaxes(gridcolor=theme.GRID_COLOR, zeroline=False, linecolor=theme.BORDER)
    fig.update_yaxes(gridcolor=theme.GRID_COLOR, zeroline=False, linecolor=theme.BORDER)
    return fig


def airport_performance_chart(df, top_n: int = 15) -> go.Figure:
    plot_df = df[df["meets_min_volume_threshold"]].nlargest(top_n, "delay_rate_pct")
    fig = go.Figure(
        go.Bar(
            x=plot_df["delay_rate_pct"],
            y=plot_df["airport"],
            orientation="h",
            marker_color=theme.ACCENT,
            customdata=plot_df[["total_flights", "avg_delay_minutes"]],
            hovertemplate="<b>%{y}</b><br>Delay rate: %{x:.1f}%<br>Flights: %{customdata[0]:,.0f}"
            "<br>Avg delay: %{customdata[1]:.1f} min<extra></extra>",
        )
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title="Delay Rate (%)")
    return _apply_layout(fig, f"Top {top_n} Airports by Delay Rate (≥1,000 flights/yr)")


def route_performance_chart(df, top_n: int = 15) -> go.Figure:
    plot_df = df[df["meets_min_volume_threshold"]].nlargest(top_n, "delay_rate_pct")
    fig = go.Figure(
        go.Bar(
            x=plot_df["delay_rate_pct"],
            y=plot_df["route"],
            orientation="h",
            marker_color=theme.ACCENT,
            customdata=plot_df[["total_flights", "avg_delay_minutes"]],
            hovertemplate="<b>%{y}</b><br>Delay rate: %{x:.1f}%<br>Flights: %{customdata[0]:,.0f}"
            "<br>Avg delay: %{customdata[1]:.1f} min<extra></extra>",
        )
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title="Delay Rate (%)")
    return _apply_layout(fig, f"Top {top_n} Routes by Delay Rate (≥200 flights/yr)")


def delay_cause_chart(df) -> go.Figure:
    plot_df = df.sort_values("minutes", ascending=True)
    colors = plot_df["cause"].map(theme.CAUSE_COLORS)
    labels = plot_df["cause"].map(CAUSE_LABELS)
    fig = go.Figure(
        go.Bar(
            x=plot_df["minutes"],
            y=labels,
            orientation="h",
            marker_color=colors,
            text=plot_df["pct_of_total_delay_minutes"].map(lambda p: f"{p:.1f}%"),
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>%{x:,.0f} minutes<extra></extra>",
        )
    )
    fig.update_xaxes(title="Total Delay Minutes")
    return _apply_layout(fig, "Delay-Cause Breakdown (Signal A)")


def hour_of_day_chart(df) -> go.Figure:
    df = df.sort_values("scheduled_dep_hour")
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=df["scheduled_dep_hour"], y=df["delay_rate_pct"], name="Delay Rate %",
            mode="lines+markers", line=dict(color=theme.ACCENT, width=2.5),
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=df["scheduled_dep_hour"], y=df["avg_delay_minutes"], name="Avg Delay (min)",
            mode="lines+markers", line=dict(color=theme.NEUTRAL_BAR, width=2, dash="dot"),
        ),
        secondary_y=True,
    )
    fig.update_xaxes(title="Scheduled Departure Hour", dtick=2)
    fig.update_yaxes(title="Delay Rate (%)", secondary_y=False)
    fig.update_yaxes(title="Avg Delay (min)", secondary_y=True)
    # Legend sits below the plot (not near the title) so it never overlaps it.
    fig.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.22, xanchor="center", x=0.5))
    return _apply_layout(fig, "Delay Rate & Average Delay by Hour of Day",
                          height=420, margin=dict(l=50, r=30, t=50, b=90))


def turnaround_buffer_chart(df) -> go.Figure:
    df = df.sort_values("bucket_order")
    fig = go.Figure(
        go.Bar(
            x=df["buffer_bucket_minutes"],
            y=df["downstream_delay_rate_pct"],
            marker_color=theme.SIGNAL_B,
            customdata=df[["n_links", "avg_prior_leg_delay_minutes"]],
            hovertemplate="<b>Buffer: %{x} min</b><br>Downstream delay rate: %{y:.1f}%"
            "<br>Links: %{customdata[0]:,.0f}<br>Avg prior-leg delay: %{customdata[1]:.1f} min<extra></extra>",
        )
    )
    fig.update_xaxes(title="Scheduled Turnaround Buffer (minutes)")
    fig.update_yaxes(title="Downstream Delay Rate (≥15min, %)")
    return _apply_layout(fig, "Turnaround Buffer vs. Downstream Delay Rate (Signal B)")


def propagation_by_hour_chart(df) -> go.Figure:
    df = df.sort_values("scheduled_dep_hour")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["scheduled_dep_hour"], y=df["signal_a_late_aircraft_share_pct"], name="Signal A (LateAircraftDelay share)",
            mode="lines+markers", line=dict(color=theme.SIGNAL_A, width=2.5),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["scheduled_dep_hour"], y=df["signal_b_propagation_rate_pct"], name="Signal B (propagation rate)",
            mode="lines+markers", line=dict(color=theme.SIGNAL_B, width=2.5),
        )
    )
    fig.update_xaxes(title="Scheduled Departure Hour", dtick=2)
    fig.update_yaxes(title="%")
    # Legend sits below the plot (not near the title) so it never overlaps it.
    fig.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.22, xanchor="center", x=0.5))
    return _apply_layout(fig, "Propagation by Hour of Day — Signal A vs. Signal B",
                          height=420, margin=dict(l=50, r=30, t=50, b=90))


def propagation_airport_comparison_chart(df, top_n: int = 10) -> go.Figure:
    """Side-by-side total vs. average propagated delay by airport -- these
    rankings surface different airports (see Step 4/5 findings)."""
    qualifying = df[df["meets_min_volume_threshold"]]
    by_total = qualifying.nlargest(top_n, "signal_b_propagated_delay_minutes")
    by_avg = qualifying.nlargest(top_n, "signal_b_avg_propagated_delay_minutes")

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("Total Propagated Delay Minutes", "Avg Propagated Delay per Link"),
        horizontal_spacing=0.15,
    )
    fig.add_trace(
        go.Bar(x=by_total["signal_b_propagated_delay_minutes"], y=by_total["airport"], orientation="h", marker_color=theme.SIGNAL_B),
        row=1, col=1,
    )
    fig.add_trace(
        go.Bar(x=by_avg["signal_b_avg_propagated_delay_minutes"], y=by_avg["airport"], orientation="h", marker_color=theme.SIGNAL_B),
        row=1, col=2,
    )
    fig.update_yaxes(autorange="reversed", row=1, col=1)
    fig.update_yaxes(autorange="reversed", row=1, col=2)
    fig.update_layout(showlegend=False)
    return _apply_layout(fig, f"Volume-Weighted Airport Propagation Ranking — Total vs. Average (Signal B, top {top_n})", height=420)
