"""Tests for offline JSONL trace validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agenttrace.cli import main
from agenttrace.validation import validate_trace


def _record_lines(*records: dict[str, Any]) -> str:
    return "\n".join(json.dumps(record) for record in records) + "\n"


def _valid_records() -> tuple[dict[str, Any], ...]:
    return (
        {
            "record_type": "run_start",
            "schema_version": "1.0.0",
            "timestamp_utc_iso": "2026-10-26T18:00:00Z",
            "timestamp_monotonic_ns": 100,
            "run_id": "run_001",
            "experiment_name": "validation_test",
            "config_hash": "sha256:test",
            "environment": {
                "os": "Windows",
                "os_release": "11",
                "architecture": "AMD64",
                "python_version": "3.13.0",
                "cpu_count_logical": 4,
                "cpu_count_physical": 4,
                "total_memory_bytes": 1_000_000,
            },
            "clock_anchor": {
                "utc_iso": "2026-10-26T18:00:00Z",
                "monotonic_ns": 100,
                "perf_counter_ns": 100,
            },
        },
        {
            "record_type": "span_start",
            "schema_version": "1.0.0",
            "timestamp_utc_iso": "2026-10-26T18:00:00Z",
            "timestamp_monotonic_ns": 100,
            "trace_id": "trace_001",
            "span_id": "span_001",
            "task_id": "task_001",
            "agent_id": "agent_001",
            "operation_name": "test",
            "operation_type": "internal",
            "process_id": 1,
            "thread_id": 1,
        },
        {
            "record_type": "span_end",
            "schema_version": "1.0.0",
            "timestamp_utc_iso": "2026-10-26T18:00:00Z",
            "timestamp_monotonic_ns": 2_100,
            "trace_id": "trace_001",
            "span_id": "span_001",
            "start_monotonic_ns": 100,
            "duration_ms": 0.002,
            "status": "ok",
        },
        {
            "record_type": "run_end",
            "schema_version": "1.0.0",
            "timestamp_utc_iso": "2026-10-26T18:00:00Z",
            "timestamp_monotonic_ns": 2_100,
            "run_id": "run_001",
        },
    )


def test_valid_trace_passes(tmp_path: Path) -> None:
    """A complete schema-valid trace is accepted."""
    trace_path = tmp_path / "valid.jsonl"
    trace_path.write_text(_record_lines(*_valid_records()), encoding="utf-8")

    result = validate_trace(trace_path)

    assert result.valid
    assert result.records_validated == 4
    assert result.completeness_percentage == 100.0


def test_missing_end_is_reported_and_cli_returns_failure(tmp_path: Path, capsys: Any) -> None:
    """Missing lifecycle records are visible to both API and CLI users."""
    trace_path = tmp_path / "incomplete.jsonl"
    trace_path.write_text(_record_lines(*_valid_records()[:2]), encoding="utf-8")

    result = validate_trace(trace_path)
    exit_code = main(["validate", str(trace_path)])
    output = capsys.readouterr()

    assert not result.valid
    assert result.completeness_percentage == 0.0
    assert exit_code == 1
    assert "no matching span_end" in output.out


def test_orphan_end_is_reported(tmp_path: Path) -> None:
    """An end record cannot silently create a completed unknown span."""
    records = _valid_records()
    orphan_end = dict(records[2], span_id="span_missing")
    trace_path = tmp_path / "orphan-end.jsonl"
    trace_path.write_text(
        _record_lines(records[0], records[1], records[2], orphan_end, records[3]),
        encoding="utf-8",
    )

    result = validate_trace(trace_path)

    assert not result.valid
    assert any("no matching span_start" in str(issue) for issue in result.issues)


def test_malformed_and_unknown_records_are_reported(tmp_path: Path) -> None:
    """Malformed JSON and unsupported discriminators do not crash validation."""
    trace_path = tmp_path / "malformed.jsonl"
    trace_path.write_text(
        '{"record_type":"unknown"}\nnot-json\n[1, 2, 3]\n',
        encoding="utf-8",
    )

    result = validate_trace(trace_path)

    assert not result.valid
    assert len(result.issues) == 5
    assert any("unknown record_type" in str(issue) for issue in result.issues)
    assert any("invalid JSON" in str(issue) for issue in result.issues)
    assert any("JSON object" in str(issue) for issue in result.issues)
