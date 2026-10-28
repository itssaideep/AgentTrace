"""Concurrency profile step-function visualization."""

from __future__ import annotations

from typing import Any

from agenttrace.analysis.concurrency import ConcurrencyProfile


def create_concurrency_figure(
    profile: ConcurrencyProfile,
    concurrency_limit: int | None = None,
) -> Any:
    """Construct an interactive Plotly step-function chart of instantaneous concurrency."""
    import plotly.graph_objects as go

    if not profile.intervals:
        fig = go.Figure()
        fig.update_layout(title="AgentTrace Concurrency: No Intervals Recorded")
        return fig

    t0_ns = profile.intervals[0].start_monotonic_ns

    x_times_ms: list[float] = []
    y_levels: list[int] = []

    # Build step points for exact step-function representation
    for interval in profile.intervals:
        t_start_ms = (interval.start_monotonic_ns - t0_ns) / 1_000_000.0
        t_end_ms = (interval.end_monotonic_ns - t0_ns) / 1_000_000.0

        x_times_ms.extend([t_start_ms, t_end_ms])
        y_levels.extend([interval.concurrency_level, interval.concurrency_level])

    fig = go.Figure()

    # Instantaneous concurrency step-curve
    fig.add_trace(
        go.Scatter(
            x=x_times_ms,
            y=y_levels,
            mode="lines",
            line={"color": "#00e676", "width": 2.5, "shape": "hv"},
            fill="tozeroy",
            fillcolor="rgba(0, 230, 118, 0.15)",
            name="Active Spans",
            hoverinfo="x+y",
        )
    )

    # Time-weighted mean concurrency horizontal line
    fig.add_hline(
        y=profile.mean_concurrency,
        line_dash="dot",
        line_color="#29b6f6",
        annotation_text=f"Mean: {profile.mean_concurrency:.2f}",
        annotation_position="bottom right",
    )

    # Concurrency limit bound
    if concurrency_limit:
        fig.add_hline(
            y=concurrency_limit,
            line_dash="dash",
            line_color="#ff1744",
            annotation_text=f"Limit ({concurrency_limit})",
            annotation_position="top left",
        )

    fig.update_layout(
        title="Instantaneous Concurrency Profile (Sweep-Line)",
        xaxis={"title": "Relative Monotonic Time (ms)", "showgrid": True},
        yaxis={"title": "Active Concurrent Spans", "showgrid": True, "dtick": 1},
        plot_bgcolor="#1e1e1e",
        paper_bgcolor="#1e1e1e",
        font={"color": "#f0f0f0", "family": "Segoe UI, Inter, sans-serif"},
        height=320,
        margin={"l": 60, "r": 40, "t": 50, "b": 45},
    )

    return fig
