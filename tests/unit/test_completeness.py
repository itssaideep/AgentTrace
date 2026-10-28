"""Unit tests for TraceCompletenessChecker and causal integrity auditing."""

from __future__ import annotations

import json
from pathlib import Path

from agenttrace.analysis.completeness import TraceCompletenessChecker
from agenttrace.instrumentation.clock import FakeClock
from agenttrace.instrumentation.tracer import CoreTracer
from agenttrace.schemas import RecordType, SpanStatus
from agenttrace.storage.writer import TraceWriter


def test_completeness_checker_healthy_trace(tmp_path: Path) -> None:
    """Verify healthy trace passes all completeness and causal audits."""
    trace_path = tmp_path / "healthy.jsonl"
    clock = FakeClock()

    with TraceWriter(output_path=trace_path) as writer:
        tracer = CoreTracer(writer=writer, clock=clock)

        parent = tracer.start_span(operation_name="root_step")
        with parent:
            child1 = tracer.start_span(operation_name="child_step")
            child1.end()

            child2 = tracer.start_span(
                operation_name="dependent_step",
                depends_on=[child1.span_id],
            )
            child2.end()

    checker = TraceCompletenessChecker(trace_path)
    report = checker.check()

    assert report.is_valid is True
    assert report.completeness_percentage == 100.0
    assert report.total_spans_started == 3
    assert report.completed_spans == 3
    assert len(report.incomplete_span_ids) == 0
    assert len(report.orphan_span_ids) == 0
    assert len(report.missing_dependency_ids) == 0
    assert len(report.clock_anomalies) == 0


def test_completeness_checker_detects_incomplete_unended_span(tmp_path: Path) -> None:
    """Verify crash or unclosed span is detected and flagged as incomplete."""
    trace_path = tmp_path / "incomplete.jsonl"
    clock = FakeClock()

    with TraceWriter(output_path=trace_path) as writer:
        tracer = CoreTracer(writer=writer, clock=clock)

        span_ok = tracer.start_span(operation_name="completed_task")
        span_ok.end()

        # Simulated crash: span_start written, but process dies before span_end
        span_crashed = tracer.start_span(operation_name="crashed_task")

    checker = TraceCompletenessChecker(trace_path)
    report = checker.check()

    assert report.is_valid is False
    assert report.total_spans_started == 2
    assert report.completed_spans == 1
    assert report.completeness_percentage == 50.0
    assert report.incomplete_span_ids == [span_crashed.span_id]


def test_completeness_checker_detects_orphan_and_missing_deps(tmp_path: Path) -> None:
    """Verify checker catches references to nonexistent parents and missing depends_on."""
    trace_path = tmp_path / "broken_causality.jsonl"

    records = [
        {
            "schema_version": "1.0.0",
            "record_type": RecordType.SPAN_START.value,
            "timestamp_utc_iso": "2026-10-28T12:00:00Z",
            "timestamp_monotonic_ns": 1000,
            "trace_id": "tr_1",
            "span_id": "sp_child",
            "parent_span_id": "sp_nonexistent_parent",
            "task_id": "t1",
            "agent_id": "a1",
            "operation_name": "orphan_op",
            "operation_type": "tool",
            "process_id": 1,
            "thread_id": 1,
            "depends_on": ["sp_nonexistent_dep"],
            "attempt": 1,
            "retry_of": None,
            "queue_wait_ms": 0.0,
            "attributes": {},
        },
        {
            "schema_version": "1.0.0",
            "record_type": RecordType.SPAN_END.value,
            "timestamp_utc_iso": "2026-10-28T12:00:01Z",
            "timestamp_monotonic_ns": 2000,
            "trace_id": "tr_1",
            "span_id": "sp_child",
            "start_monotonic_ns": 1000,
            "duration_ms": 0.001,
            "status": SpanStatus.OK.value,
            "attributes": {},
        },
    ]

    with open(trace_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    checker = TraceCompletenessChecker(trace_path)
    report = checker.check()

    assert report.is_valid is False
    assert len(report.orphan_span_ids) == 1
    assert "sp_nonexistent_parent" in report.orphan_span_ids[0]
    assert len(report.missing_dependency_ids) == 1
    assert "sp_nonexistent_dep" in report.missing_dependency_ids[0]


def test_completeness_checker_detects_clock_anomaly(tmp_path: Path) -> None:
    """Verify clock reversal is detected as a clock anomaly."""
    trace_path = tmp_path / "clock_anomaly.jsonl"

    records = [
        {
            "schema_version": "1.0.0",
            "record_type": RecordType.SPAN_START.value,
            "timestamp_utc_iso": "2026-10-28T12:00:00Z",
            "timestamp_monotonic_ns": 5000,
            "trace_id": "tr_1",
            "span_id": "sp_backward",
            "parent_span_id": None,
            "task_id": "t1",
            "agent_id": "a1",
            "operation_name": "op",
            "operation_type": "tool",
            "process_id": 1,
            "thread_id": 1,
            "depends_on": [],
            "attempt": 1,
            "retry_of": None,
            "queue_wait_ms": 0.0,
            "attributes": {},
        },
        {
            "schema_version": "1.0.0",
            "record_type": RecordType.SPAN_END.value,
            "timestamp_utc_iso": "2026-10-28T12:00:01Z",
            "timestamp_monotonic_ns": 4000,  # End earlier than start
            "trace_id": "tr_1",
            "span_id": "sp_backward",
            "start_monotonic_ns": 5000,
            "duration_ms": 1.0,
            "status": SpanStatus.OK.value,
            "attributes": {},
        },
    ]

    with open(trace_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    checker = TraceCompletenessChecker(trace_path)
    report = checker.check()

    assert report.is_valid is False
    assert len(report.clock_anomalies) > 0
    assert any("end monotonic ns" in a for a in report.clock_anomalies)
