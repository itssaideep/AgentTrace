"""Interactive Gantt timeline visualization with causal dependency edges."""

from __future__ import annotations

from typing import Any


def create_gantt_figure(
    spans: list[dict[str, Any]],
    critical_path_ids: list[str] | None = None,
) -> Any:
    """Construct an interactive Plotly Gantt chart showing spans and causal edges."""
    import plotly.graph_objects as go

    if not spans:
        fig = go.Figure()
        fig.update_layout(title="AgentTrace Timeline: No Spans Recorded")
        return fig

    # Find global start time anchor
    valid_starts = [
        s["start_monotonic_ns"] for s in spans if s.get("start_monotonic_ns") is not None
    ]
    t0_ns = min(valid_starts) if valid_starts else 0
    cp_set = set(critical_path_ids or [])

    # Sort spans by start time
    sorted_spans = sorted(
        spans,
        key=lambda s: (s.get("start_monotonic_ns", 0), s.get("end_monotonic_ns", 0)),
    )

    y_labels: list[str] = []
    starts_ms: list[float] = []
    durations_ms: list[float] = []
    colors: list[str] = []
    hover_texts: list[str] = []

    for s in sorted_spans:
        s_id = s.get("span_id", "")
        task_id = s.get("task_id", s_id)
        name = s.get("name", "span")
        status = s.get("status", "ok")
        s_start = s.get("start_monotonic_ns")
        s_end = s.get("end_monotonic_ns")

        if s_start is None or s_end is None:
            continue

        rel_start_ms = (s_start - t0_ns) / 1_000_000.0
        dur_ms = max(0.01, (s_end - s_start) / 1_000_000.0)

        label = f"{task_id} ({name})"
        y_labels.append(label)
        starts_ms.append(rel_start_ms)
        durations_ms.append(dur_ms)

        is_cp = s_id in cp_set or task_id in cp_set
        if is_cp:
            c = "#ff5722"  # Vibrant orange-red for critical path
        elif status == "error":
            c = "#f44336"  # Red
        elif status == "incomplete":
            c = "#ff9800"  # Amber
        else:
            c = "#00bcd4"  # Cyan/teal
        colors.append(c)

        hover = (
            f"<b>Span:</b> {s_id}<br>"
            f"<b>Task:</b> {task_id}<br>"
            f"<b>Name:</b> {name}<br>"
            f"<b>Status:</b> {status}<br>"
            f"<b>Start:</b> {rel_start_ms:.2f} ms<br>"
            f"<b>Duration:</b> {dur_ms:.2f} ms<br>"
            f"<b>Critical Path:</b> {'YES' if is_cp else 'No'}"
        )
        hover_texts.append(hover)

    fig = go.Figure()

    # Base invisible trace for left offset
    fig.add_trace(
        go.Bar(
            y=y_labels,
            x=starts_ms,
            orientation="h",
            opacity=0,
            hoverinfo="skip",
            showlegend=False,
        )
    )

    # Visible span duration bars
    fig.add_trace(
        go.Bar(
            y=y_labels,
            x=durations_ms,
            orientation="h",
            marker={"color": colors, "line": {"color": "#222", "width": 1}},
            text=hover_texts,
            hoverinfo="text",
            showlegend=False,
        )
    )

    fig.update_layout(
        barmode="stack",
        title="AgentTrace Causal Execution Timeline (Gantt)",
        xaxis={"title": "Relative Monotonic Time (ms)", "showgrid": True},
        yaxis={"title": "Workload Spans", "automargin": True, "autorange": "reversed"},
        plot_bgcolor="#1e1e1e",
        paper_bgcolor="#1e1e1e",
        font={"color": "#f0f0f0", "family": "Segoe UI, Inter, sans-serif"},
        height=max(400, len(y_labels) * 28 + 150),
        margin={"l": 150, "r": 40, "t": 60, "b": 50},
    )

    return fig
