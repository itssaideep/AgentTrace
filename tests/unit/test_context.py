"""Unit tests for TraceContext propagation and coroutine task isolation."""

from __future__ import annotations

import asyncio

import pytest

from agenttrace.instrumentation.context import (
    TraceContext,
    current_span_id,
    current_trace_id,
    get_current_context,
    reset_current_context,
    set_current_context,
)


def test_context_immutability_and_serialization() -> None:
    """Verify TraceContext is immutable and serializes roundtrip."""
    ctx = TraceContext(
        trace_id="tr_100",
        span_id="sp_200",
        parent_span_id="sp_050",
        task_id="task_A",
        agent_id="agent_planner",
    )

    data = ctx.to_dict()
    assert data["trace_id"] == "tr_100"
    assert data["span_id"] == "sp_200"
    assert data["parent_span_id"] == "sp_050"

    reconstructed = TraceContext.from_dict(data)
    assert reconstructed == ctx


@pytest.mark.asyncio
async def test_context_propagation_across_coroutines() -> None:
    """Verify TraceContext propagates correctly down async call chains."""
    ctx = TraceContext(
        trace_id="tr_root",
        span_id="sp_root",
        parent_span_id=None,
        task_id="task_root",
        agent_id="agent_main",
    )
    token = set_current_context(ctx)

    try:
        assert current_trace_id() == "tr_root"
        assert current_span_id() == "sp_root"

        async def subtask(expected_span: str) -> str:
            assert current_trace_id() == "tr_root"
            assert current_span_id() == expected_span
            return "ok"

        res = await subtask("sp_root")
        assert res == "ok"
    finally:
        reset_current_context(token)

    assert get_current_context() is None


@pytest.mark.asyncio
async def test_context_isolation_under_concurrency() -> None:
    """Verify concurrent coroutines maintain isolated contexts without leaking."""

    async def worker(trace_id: str, span_id: str) -> tuple[str | None, str | None]:
        ctx = TraceContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=None,
            task_id="task_w",
            agent_id="agent_w",
        )
        token = set_current_context(ctx)
        try:
            await asyncio.sleep(0.01)
            return current_trace_id(), current_span_id()
        finally:
            reset_current_context(token)

    results = await asyncio.gather(
        worker("tr_worker_1", "sp_worker_1"),
        worker("tr_worker_2", "sp_worker_2"),
        worker("tr_worker_3", "sp_worker_3"),
    )

    assert results[0] == ("tr_worker_1", "sp_worker_1")
    assert results[1] == ("tr_worker_2", "sp_worker_2")
    assert results[2] == ("tr_worker_3", "sp_worker_3")
    assert get_current_context() is None
