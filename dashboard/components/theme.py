"""Shared color/typography constants -- Minimalism & Swiss Style direction
(restrained, single accent, monochrome UI chrome; color is reserved for
signal semantics, never used decoratively).

ACCENT and SIGNAL_A are intentionally the same color -- there is exactly one
accent in this system, and BTS's LateAircraftDelay (Signal A) is styled with
it. SIGNAL_B (amber) is the only other color in the app, reserved strictly for
the reconstructed propagation estimate so the two signals stay visually
distinct wherever they appear together. Everything else is text/border
neutrals."""

PAGE_BG = "#FAFAFA"
CARD_BG = "#FFFFFF"
BORDER = "#E5E7EB"
TEXT = "#0F172A"
MUTED_TEXT = "#64748B"
WARNING = "#B91C1C"

ACCENT = "#1E3A8A"       # the one restrained accent (deep indigo) -- UI chrome, primary charts
SIGNAL_A = ACCENT         # BTS LateAircraftDelay
SIGNAL_B = "#B45309"       # reconstructed propagation estimate (muted amber)
NEUTRAL_BAR = "#94A3B8"     # de-emphasized chart elements

# Delay-cause palette: a single-hue sequential scale (dark -> light), same
# family as ACCENT, rather than mixed hues -- reads as one deliberate palette.
# late_aircraft_delay stays exactly on ACCENT/SIGNAL_A.
CAUSE_COLORS = {
    "late_aircraft_delay": ACCENT,   # indigo-900
    "carrier_delay": "#1D4ED8",       # blue-700
    "nas_delay": "#2563EB",            # blue-600
    "weather_delay": "#60A5FA",         # blue-400
    "security_delay": "#93C5FD",         # blue-300
}

FONT_FAMILY = "'Fira Sans', -apple-system, sans-serif"
MONO_FONT_FAMILY = "'Fira Code', monospace"

PLOTLY_LAYOUT = dict(
    paper_bgcolor=CARD_BG,
    plot_bgcolor=CARD_BG,
    font=dict(family=FONT_FAMILY, color=TEXT, size=13),
    margin=dict(l=50, r=30, t=50, b=40),
    hoverlabel=dict(bgcolor=CARD_BG, bordercolor=BORDER, font=dict(family=FONT_FAMILY, color=TEXT)),
)

TITLE_FONT = dict(size=15, color=TEXT)

GRID_COLOR = "#F1F5F9"  # applied via update_xaxes/update_yaxes so it reaches every
                         # axis in multi-axis/subplot figures, not just the first
