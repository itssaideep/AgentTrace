"""Unit tests for offline HTML report and Plotly visualization generation."""

import json
from pathlib import Path

from agenttrace.analysis.concurrency import compute_concurrency_profile
from agenttrace.cli import main
from agenttrace.schemas import RecordType
from agenttrace.visualization.concurrency import create_concurrency_figure
from agenttrace.visualization.report import generate_trace_html_report
from agenttrace.visualization.resources import create_resource_figure
from agenttrace.visualization.timeline import create_gantt_figure


def test_gantt_figure_generation() -> None:
    spans = [
        {
            "span_id": "sp_1",
            "task_id": "task_1",
            "name": "exec_1",
            "status": "ok",
            "start_monotonic_ns": 1_000_000,
            "end_monotonic_ns": 5_000_000,
        },
        {
            "span_id": "sp_2",
            "task_id": "task_2",
            "name": "exec_2",
            "status": "ok",
            "start_monotonic_ns": 2_000_000,
            "end_monotonic_ns": 8_000_000,
        },
    ]

    fig = create_gantt_figure(spans, critical_path_ids=["sp_1"])
    assert fig is not None
    assert len(fig.data) == 2  # Invisible offset bar + visible duration bar


def test_concurrency_figure_generation() -> None:
    spans = [
        {"span_id": "s1", "start_monotonic_ns": 0, "end_monotonic_ns": 100_000_000},
        {"span_id": "s2", "start_monotonic_ns": 50_000_000, "end_monotonic_ns": 150_000_000},
    ]
    prof = compute_concurrency_profile(spans)
    fig = create_concurrency_figure(prof, concurrency_limit=4)
    assert fig is not None
    assert len(fig.data) == 1
    assert fig.data[0].mode == "lines"


def test_resource_figure_generation() -> None:
    samples = [
        {
            "timestamp_monotonic_ns": 100_000_000,
            "rss_bytes": 50 * 1024 * 1024,
            "cpu_user_s": 0.1,
            "cpu_sys_s": 0.05,
            "read_bytes": 1024,
            "write_bytes": 2048,
        },
        {
            "timestamp_monotonic_ns": 200_000_000,
            "rss_bytes": 60 * 1024 * 1024,
            "cpu_user_s": 0.25,
            "cpu_sys_s": 0.1,
            "read_bytes": 2048,
            "write_bytes": 4096,
        },
    ]
    fig = create_resource_figure(samples)
    assert fig is not None
    assert len(fig.data) == 5  # RSS, CPU User, CPU Sys, Read, Write


def test_full_html_report_generation(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    report_path = tmp_path / "report.html"

    records = [
        {
            "record_type": RecordType.SPAN_START.value,
            "span_id": "sp_1",
            "task_id": "task_1",
            "name": "generate_code",
            "timestamp_monotonic_ns": 1_000_000_000,
        },
        {
            "record_type": RecordType.SPAN_END.value,
            "span_id": "sp_1",
            "name": "generate_code",
            "status": "ok",
            "timestamp_monotonic_ns": 1_250_000_000,
        },
        {
            "record_type": RecordType.RESOURCE_SAMPLE.value,
            "timestamp_monotonic_ns": 1_100_000_000,
            "process_metrics": [
                {
                    "process_id": 999,
                    "cpu_user_time_s": 0.4,
                    "cpu_system_time_s": 0.05,
                    "rss_bytes": 45_000_000,
                }
            ],
        },
    ]

    with trace_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    out = generate_trace_html_report(trace_path, report_path)
    assert out.is_file()
    content = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "AgentTrace Performance & Attribution Report" in content
    assert "Makespan" in content
    assert "Critical Path" in content
    assert "generate_code" in content

    # Test CLI invocation
    cli_out = tmp_path / "cli_report.html"
    rc = main(["report", str(trace_path), "-o", str(cli_out)])
    assert rc == 0
    assert cli_out.is_file()
