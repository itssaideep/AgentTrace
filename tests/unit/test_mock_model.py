"""Unit tests for MockModel TTFT simulation and token streaming latency."""

from __future__ import annotations

from pathlib import Path

from agenttrace.agents.mock_model import MockModel
from agenttrace.instrumentation.clock import FakeClock
from agenttrace.instrumentation.tracer import CoreTracer
from agenttrace.storage.writer import TraceWriter


def test_mock_model_generation_and_ttft_event(tmp_path: Path) -> None:
    """Verify MockModel emits first_token_received span event with accurate TTFT."""
    trace_path = tmp_path / "model_trace.jsonl"
    clock = FakeClock()

    with TraceWriter(output_path=trace_path) as writer:
        tracer = CoreTracer(writer=writer, clock=clock)
        model = MockModel(base_ttft_ms=20.0, ms_per_token=1.0, clock=clock)

        span = tracer.start_span(operation_name="llm_step", operation_type="llm_call")
        resp = model.generate(prompt="What is causal tracing?", seed=42, span=span)
        span.end()

    assert resp.prompt_tokens > 0
    assert resp.completion_tokens > 0
    assert resp.total_tokens == resp.prompt_tokens + resp.completion_tokens
    assert resp.ttft_ms >= 15.0
    assert resp.total_duration_ms > resp.ttft_ms


def test_mock_model_seed_determinism() -> None:
    """Verify identical seeds produce identical token counts."""
    clock = FakeClock()
    model = MockModel(clock=clock)

    r1 = model.generate(prompt="hello world", seed=999)
    r2 = model.generate(prompt="hello world", seed=999)

    assert r1.completion_tokens == r2.completion_tokens
    assert r1.content == r2.content
