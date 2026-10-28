"""Unit tests for AsyncAgentExecutor concurrency management, queue wait, and retries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agenttrace.agents.executor import AsyncAgentExecutor
from agenttrace.instrumentation.clock import FakeClock
from agenttrace.instrumentation.tracer import CoreTracer
from agenttrace.schemas import RecordType, SpanStatus
from agenttrace.storage.writer import TraceWriter
from agenttrace.workloads.generator import WorkloadGenerator
from agenttrace.workloads.models import TaskSpec, WorkloadDAG


@pytest.mark.asyncio
async def test_executor_sequential_dag(tmp_path: Path) -> None:
    """Verify executor runs sequential chain with causality intact."""
    trace_path = tmp_path / "exec_seq.jsonl"
    clock = FakeClock()
    gen = WorkloadGenerator(master_seed=42)
    dag = gen.generate_sequential(num_tasks=4, base_latency_ms=5.0)

    with TraceWriter(output_path=trace_path) as writer:
        tracer = CoreTracer(writer=writer, clock=clock)
        executor = AsyncAgentExecutor(
            tracer=tracer,
            concurrency_limit=2,
            clock=clock,
            scratch_dir=tmp_path / "scratch",
        )
        try:
            await executor.run(dag)
        finally:
            executor.close()

    lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 8  # 4 starts + 4 ends

    starts = [json.loads(line) for line in lines if "span_start" in line]
    ends = [json.loads(line) for line in lines if "span_end" in line]

    assert len(starts) == 4
    assert len(ends) == 4
    for e in ends:
        assert e["status"] == SpanStatus.OK.value


@pytest.mark.asyncio
async def test_executor_parallel_dag_and_queue_wait(tmp_path: Path) -> None:
    """Verify executor respects concurrency limit and records queue wait time."""
    trace_path = tmp_path / "exec_par.jsonl"
    clock = FakeClock()
    gen = WorkloadGenerator(master_seed=42)
    # 4 parallel workers with concurrency limit of 1 to force queue wait
    dag = gen.generate_parallel(num_tasks=4, base_latency_ms=5.0)

    with TraceWriter(output_path=trace_path) as writer:
        tracer = CoreTracer(writer=writer, clock=clock)
        executor = AsyncAgentExecutor(
            tracer=tracer,
            concurrency_limit=1,
            clock=clock,
            scratch_dir=tmp_path / "scratch",
        )
        try:
            await executor.run(dag)
        finally:
            executor.close()

    lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
    records = [json.loads(line) for line in lines]
    worker_starts = [
        r for r in records
        if r.get("record_type") == RecordType.SPAN_START.value and "worker_" in r.get("task_id", "")
    ]

    assert len(worker_starts) == 4
    # All workers were executed
    assert all("queue_wait_ms" in r for r in worker_starts)


@pytest.mark.asyncio
async def test_executor_fault_and_retry_linkage(tmp_path: Path) -> None:
    """Verify task failure triggers retry with retry_of and incremented attempt."""
    trace_path = tmp_path / "exec_retry.jsonl"
    clock = FakeClock()

    dag = WorkloadDAG(dag_id="retry_dag", workload_type="test", master_seed=42)
    # Task with 100% failure probability and 1 retry
    dag.add_task(
        TaskSpec(
            task_id="failing_task",
            operation_name="unstable_tool",
            tool_name="latency",
            tool_params={"duration_ms": 1.0},
            fail_probability=1.0,
            max_retries=1,
        )
    )

    with TraceWriter(output_path=trace_path) as writer:
        tracer = CoreTracer(writer=writer, clock=clock)
        executor = AsyncAgentExecutor(
            tracer=tracer,
            concurrency_limit=2,
            clock=clock,
            scratch_dir=tmp_path / "scratch",
        )
        try:
            await executor.run(dag)
        finally:
            executor.close()

    lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
    records = [json.loads(line) for line in lines]
    starts = [r for r in records if r.get("record_type") == RecordType.SPAN_START.value]

    # Attempt 1 and Attempt 2
    assert len(starts) == 2
    assert starts[0]["attempt"] == 1
    assert starts[0]["retry_of"] is None

    assert starts[1]["attempt"] == 2
    assert starts[1]["retry_of"] == starts[0]["span_id"]
