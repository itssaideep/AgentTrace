"""Unit tests for SQLiteTraceStore, compare_runs, and CLI analytical commands."""

import json
from pathlib import Path

from agenttrace.analysis.compare import compare_runs
from agenttrace.cli import main
from agenttrace.schemas import RecordType
from agenttrace.storage.sqlite import SQLiteTraceStore


def test_sqlite_trace_store_ingest(tmp_path: Path) -> None:
    trace_path = tmp_path / "test_trace.jsonl"
    records = [
        {
            "record_type": RecordType.SPAN_START.value,
            "span_id": "sp_1",
            "task_id": "task_1",
            "name": "exec_task",
            "timestamp_monotonic_ns": 1_000_000_000,
            "attributes": {"depends_on": []},
        },
        {
            "record_type": RecordType.SPAN_EVENT.value,
            "span_id": "sp_1",
            "name": "first_token_received",
            "timestamp_monotonic_ns": 1_020_000_000,
            "attributes": {"token_count": 1},
        },
        {
            "record_type": RecordType.SPAN_END.value,
            "span_id": "sp_1",
            "name": "exec_task",
            "status": "ok",
            "timestamp_monotonic_ns": 1_100_000_000,
            "attributes": {},
        },
        {
            "record_type": RecordType.RESOURCE_SAMPLE.value,
            "timestamp_monotonic_ns": 1_050_000_000,
            "process_metrics": [
                {
                    "process_id": 1234,
                    "cpu_user_time_s": 0.5,
                    "cpu_system_time_s": 0.1,
                    "rss_bytes": 50_000_000,
                }
            ],
            "system_metrics": {
                "system_cpu_percent": 12.5,
                "system_memory_total_bytes": 16_000_000_000,
            },
        },
    ]

    with trace_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    with SQLiteTraceStore() as store:
        count = store.ingest_jsonl(trace_path)
        assert count == 4

        spans = store.get_spans()
        assert len(spans) == 1
        assert spans[0]["span_id"] == "sp_1"
        assert spans[0]["status"] == "ok"
        assert spans[0]["duration_ns"] == 100_000_000
        assert spans[0]["duration_ms"] == 100.0

        samples = store.get_resource_samples()
        assert len(samples) == 1
        assert samples[0]["process_id"] == 1234
        assert samples[0]["rss_bytes"] == 50_000_000


def test_compare_runs_logic(tmp_path: Path) -> None:
    # Run A (sequential baseline: 2 tasks of 100ms run sequentially = 200ms)
    run_a = tmp_path / "run_a.jsonl"
    records_a = [
        {
            "record_type": RecordType.SPAN_START.value,
            "span_id": "sp_1",
            "task_id": "task_1",
            "timestamp_monotonic_ns": 0,
        },
        {
            "record_type": RecordType.SPAN_END.value,
            "span_id": "sp_1",
            "timestamp_monotonic_ns": 100_000_000,
        },
        {
            "record_type": RecordType.SPAN_START.value,
            "span_id": "sp_2",
            "task_id": "task_2",
            "timestamp_monotonic_ns": 100_000_000,
        },
        {
            "record_type": RecordType.SPAN_END.value,
            "span_id": "sp_2",
            "timestamp_monotonic_ns": 200_000_000,
        },
    ]
    with run_a.open("w", encoding="utf-8") as f:
        for r in records_a:
            f.write(json.dumps(r) + "\n")

    # Run B (parallel candidate: 2 tasks of 100ms run in parallel = 100ms)
    run_b = tmp_path / "run_b.jsonl"
    records_b = [
        {
            "record_type": RecordType.SPAN_START.value,
            "span_id": "sp_1b",
            "task_id": "task_1",
            "timestamp_monotonic_ns": 0,
        },
        {
            "record_type": RecordType.SPAN_END.value,
            "span_id": "sp_1b",
            "timestamp_monotonic_ns": 100_000_000,
        },
        {
            "record_type": RecordType.SPAN_START.value,
            "span_id": "sp_2b",
            "task_id": "task_2",
            "timestamp_monotonic_ns": 0,
        },
        {
            "record_type": RecordType.SPAN_END.value,
            "span_id": "sp_2b",
            "timestamp_monotonic_ns": 100_000_000,
        },
    ]
    with run_b.open("w", encoding="utf-8") as f:
        for r in records_b:
            f.write(json.dumps(r) + "\n")

    res = compare_runs(run_a, run_b, baseline_label="sequential", candidate_label="parallel")
    assert res.baseline_makespan_ms == 200.0
    assert res.candidate_makespan_ms == 100.0
    assert res.makespan_delta_ms == -100.0
    assert res.speedup == 2.0
    assert res.baseline_max_concurrency == 1
    assert res.candidate_max_concurrency == 2
    assert len(res.task_differentials) == 2

    md = res.summary_markdown()
    assert "Makespan (ms)" in md
    assert "2.00x" in md


def test_cli_analyze_and_compare(tmp_path: Path, capsys: None) -> None:
    trace_path = tmp_path / "trace.jsonl"
    records = [
        {
            "record_type": RecordType.SPAN_START.value,
            "span_id": "s1",
            "task_id": "t1",
            "name": "task1",
            "timestamp_monotonic_ns": 0,
        },
        {
            "record_type": RecordType.SPAN_END.value,
            "span_id": "s1",
            "name": "task1",
            "timestamp_monotonic_ns": 50_000_000,
        },
    ]
    with trace_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    rc_analyze = main(["analyze", str(trace_path)])
    assert rc_analyze == 0

    rc_compare = main(["compare", str(trace_path), str(trace_path)])
    assert rc_compare == 0
