"""Synchronized resource utilization time-series plots."""

from __future__ import annotations

from typing import Any


def create_resource_figure(
    resource_samples: list[dict[str, Any]],
    t0_ns: int | None = None,
) -> Any:
    """Construct synchronized subplots for CPU user/sys, RSS, I/O, and context switches."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    if not resource_samples:
        fig = go.Figure()
        fig.update_layout(title="AgentTrace Resources: No Resource Samples Recorded")
        return fig

    # Sort samples by monotonic timestamp
    samples = sorted(resource_samples, key=lambda s: s.get("timestamp_monotonic_ns", 0))
    start_ns = t0_ns if t0_ns is not None else samples[0].get("timestamp_monotonic_ns", 0)

    times_s: list[float] = []
    rss_mb: list[float] = []
    cpu_user_s: list[float] = []
    cpu_sys_s: list[float] = []
    io_read_kb: list[float] = []
    io_write_kb: list[float] = []
    vol_ctx: list[int] = []
    invol_ctx: list[int] = []

    for s in samples:
        t_ns = s.get("timestamp_monotonic_ns", 0)
        times_s.append((t_ns - start_ns) / 1_000_000_000.0)

        # Process metrics
        rss_bytes = s.get("rss_bytes", 0) or 0
        rss_mb.append(rss_bytes / (1024.0 * 1024.0))

        cpu_user_s.append(s.get("cpu_user_s", 0.0) or 0.0)
        cpu_sys_s.append(s.get("cpu_sys_s", 0.0) or 0.0)

        r_bytes = s.get("read_bytes", 0) or 0
        w_bytes = s.get("write_bytes", 0) or 0
        io_read_kb.append(r_bytes / 1024.0)
        io_write_kb.append(w_bytes / 1024.0)

        vol_ctx.append(s.get("voluntary_ctx_switches", 0) or 0)
        invol_ctx.append(s.get("involuntary_ctx_switches", 0) or 0)

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=(
            "Resident Set Size (RSS Memory MB)",
            "Cumulative Process CPU Time (seconds)",
            "Process Disk I/O (KB)",
        ),
    )

    # Subplot 1: RSS
    fig.add_trace(
        go.Scatter(
            x=times_s,
            y=rss_mb,
            mode="lines+markers",
            line={"color": "#ab47bc", "width": 2},
            marker={"size": 4},
            name="RSS (MB)",
        ),
        row=1,
        col=1,
    )

    # Subplot 2: CPU
    fig.add_trace(
        go.Scatter(
            x=times_s,
            y=cpu_user_s,
            mode="lines",
            line={"color": "#ff9800", "width": 2},
            name="CPU User (s)",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=times_s,
            y=cpu_sys_s,
            mode="lines",
            line={"color": "#f44336", "width": 2, "dash": "dot"},
            name="CPU System (s)",
        ),
        row=2,
        col=1,
    )

    # Subplot 3: I/O
    fig.add_trace(
        go.Scatter(
            x=times_s,
            y=io_read_kb,
            mode="lines",
            line={"color": "#00bcd4", "width": 2},
            name="Disk Read (KB)",
        ),
        row=3,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=times_s,
            y=io_write_kb,
            mode="lines",
            line={"color": "#4caf50", "width": 2},
            name="Disk Write (KB)",
        ),
        row=3,
        col=1,
    )

    fig.update_layout(
        title="Synchronized Process Resource Telemetry",
        plot_bgcolor="#1e1e1e",
        paper_bgcolor="#1e1e1e",
        font={"color": "#f0f0f0", "family": "Segoe UI, Inter, sans-serif"},
        height=650,
        margin={"l": 60, "r": 40, "t": 60, "b": 45},
    )
    fig.update_xaxes(title_text="Relative Monotonic Time (seconds)", row=3, col=1)

    return fig
