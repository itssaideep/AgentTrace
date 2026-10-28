"""Unit tests for CoreTracer, Span lifecycle, causality, and NoOpTracer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agenttrace.instrumentation.clock import FakeClock
from agenttrace.instrumentation.redaction import RedactionEngine
from agenttrace.instrumentation.tracer import CoreTracer, NoOpTracer
from agenttrace.schemas import RecordType, SpanStatus
from agenttrace.storage.writer import TraceWriter


def test_span_lifecycle_and_duration_calculation(tmp_path: Path) -> None:
    """Verify span emits span_start and span_end with nanosecond-derived duration."""
    trace_path = tmp_path / "lifecycle.jsonl"
    clock = FakeClock(start_monotonic_ns=1_000_000_000)

    with TraceWriter(output_path=trace_path) as writer:
        tracer = CoreTracer(writer=writer, clock=clock)

        span = tracer.start_span(
            operation_name="llm_generate",
            operation_type="llm_call",
            task_id="task_1",
            agent_id="agent_writer",
        )
        assert len(tracer.get_active_spans()) == 1

        # Advance clock by 42.5 ms
        clock.advance_ms(42.5)

        span.end(status=SpanStatus.OK)
        assert len(tracer.get_active_spans()) == 0

    lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    start_data = json.loads(lines[0])
    assert start_data["record_type"] == RecordType.SPAN_START.value
    assert start_data["operation_name"] == "llm_generate"
    assert start_data["timestamp_monotonic_ns"] == 1_000_000_000

    end_data = json.loads(lines[1])
    assert end_data["record_type"] == RecordType.SPAN_END.value
    assert end_data["span_id"] == start_data["span_id"]
    assert end_data["status"] == SpanStatus.OK.value
    assert end_data["duration_ms"] == 42.5


def test_context_manager_parent_child_nesting(tmp_path: Path) -> None:
    """Verify nested spans automatically inherit parent_span_id via TraceContext."""
    trace_path = tmp_path / "nesting.jsonl"
    clock = FakeClock()

    with TraceWriter(output_path=trace_path) as writer:
        tracer = CoreTracer(writer=writer, clock=clock)

        parent_span = tracer.start_span(
            operation_name="agent_workflow",
            operation_type="workflow",
        )
        with parent_span:
            child_span = tracer.start_span(
                operation_name="tool_search",
                operation_type="tool_exec",
            )
            with child_span:
                clock.advance_ms(10.0)

    lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 4

    p_start = json.loads(lines[0])
    c_start = json.loads(lines[1])
    c_end = json.loads(lines[2])
    p_end = json.loads(lines[3])

    assert c_start["parent_span_id"] == p_start["span_id"]
    assert c_end["span_id"] == c_start["span_id"]
    assert p_end["span_id"] == p_start["span_id"]


@pytest.mark.asyncio
async def test_async_context_manager_and_exception_handling(tmp_path: Path) -> None:
    """Verify exceptions inside async with mark span as ERROR without silencing error."""
    trace_path = tmp_path / "exception.jsonl"
    clock = FakeClock()

    with TraceWriter(output_path=trace_path) as writer:
        tracer = CoreTracer(writer=writer, clock=clock)

        span = tracer.start_span(operation_name="faulty_task")
        with pytest.raises(ValueError, match="Synthetic failure"):
            async with span:
                clock.advance_ms(5.0)
                raise ValueError("Synthetic failure")

    lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    end_data = json.loads(lines[1])
    assert end_data["status"] == SpanStatus.ERROR.value
    assert end_data["error_type"] == "ValueError"
    assert "Synthetic failure" in end_data["error_message"]
    assert end_data["duration_ms"] == 5.0


def test_explicit_dependencies_and_retries(tmp_path: Path) -> None:
    """Verify depends_on and retry_of causal relations are emitted."""
    trace_path = tmp_path / "causality.jsonl"
    clock = FakeClock()

    with TraceWriter(output_path=trace_path) as writer:
        tracer = CoreTracer(writer=writer, clock=clock)

        span1 = tracer.start_span(operation_name="task_A")
        span1.end()

        # Task B explicitly depends on Task A
        span2 = tracer.start_span(
            operation_name="task_B",
            depends_on=[span1.span_id],
            attempt=2,
            retry_of="sp_old_failed",
            queue_wait_ms=12.5,
        )
        span2.end()

    lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 4

    span2_start = json.loads(lines[2])
    assert span2_start["depends_on"] == [span1.span_id]
    assert span2_start["attempt"] == 2
    assert span2_start["retry_of"] == "sp_old_failed"
    assert span2_start["queue_wait_ms"] == 12.5


def test_intra_span_event_emission(tmp_path: Path) -> None:
    """Verify span.add_event emits span_event records with sanitized payloads."""
    trace_path = tmp_path / "events.jsonl"
    clock = FakeClock()
    redactor = RedactionEngine()

    with TraceWriter(output_path=trace_path) as writer:
        tracer = CoreTracer(writer=writer, clock=clock, redactor=redactor)

        span = tracer.start_span(operation_name="model_call")
        span.add_event(
            "first_token_received",
            {"ttft_ms": 150.0, "api_key": "secret_key"},
        )
        span.end()

    lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3

    event_data = json.loads(lines[1])
    assert event_data["record_type"] == RecordType.SPAN_EVENT.value
    assert event_data["event_name"] == "first_token_received"
    assert event_data["event_payload"]["ttft_ms"] == 150.0
    assert event_data["event_payload"]["api_key"] == "[REDACTED]"


def test_noop_tracer_zero_overhead(tmp_path: Path) -> None:
    """Verify NoOpTracer produces zero writes and causes zero side effects."""
    trace_path = tmp_path / "noop.jsonl"
    noop_tracer = NoOpTracer()

    span = noop_tracer.start_span(operation_name="bench_op")
    with span:
        span.set_attribute("key", "val")
        span.add_event("event")
        span.end()

    noop_tracer.flush()
    # No file created
    assert not trace_path.exists()
