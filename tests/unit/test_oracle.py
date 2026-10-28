"""Unit tests for OracleVerifier comparing traces against ground-truth DAGs."""

from __future__ import annotations

from pathlib import Path

import pytest

from agenttrace.agents.executor import AsyncAgentExecutor
from agenttrace.instrumentation.clock import FakeClock
from agenttrace.instrumentation.tracer import CoreTracer
from agenttrace.schemas import RecordType, SpanStatus
from agenttrace.storage.writer import TraceWriter
from agenttrace.workloads.generator import WorkloadGenerator
from agenttrace.workloads.models import TaskSpec, WorkloadDAG
from agenttrace.workloads.oracle import OracleVerifier


@pytest.mark.asyncio
async def test_oracle_verifier_matches_nominal_execution(tmp_path: Path) -> None:
    """Verify recorded trace of DAG execution matches oracle with 100% edge recall."""
    trace_path = tmp_path / "oracle_trace.jsonl"
    clock = FakeClock()
    gen = WorkloadGenerator(master_seed=123)
    dag = gen.generate_parallel(num_tasks=4, base_latency_ms=5.0)

    with TraceWriter(output_path=trace_path) as writer:
        tracer = CoreTracer(writer=writer, clock=clock)
        executor = AsyncAgentExecutor(
            tracer=tracer,
            concurrency_limit=4,
            clock=clock,
            scratch_dir=tmp_path / "scratch",
        )
        try:
            await executor.run(dag)
        finally:
            executor.close()

    verifier = OracleVerifier(dag)
    result = verifier.verify_trace_file(trace_path)

    assert result.matched is True
    assert result.edge_recall == 1.0
    assert len(result.discrepancies) == 0
    assert result.tasks_executed == len(dag.tasks)


def test_oracle_verifier_catches_missing_task() -> None:
    """Verify oracle detects when a DAG task was never executed."""
    dag = WorkloadDAG(dag_id="test_dag", workload_type="test", master_seed=42)
    dag.add_task(TaskSpec(task_id="task_1", operation_name="op1"))
    dag.add_task(TaskSpec(task_id="task_2", operation_name="op2", depends_on=["task_1"]))

    # Records only have task_1
    records = [
        {
            "record_type": RecordType.SPAN_START.value,
            "span_id": "sp_1",
            "task_id": "task_1",
            "timestamp_monotonic_ns": 1000,
        },
        {
            "record_type": RecordType.SPAN_END.value,
            "span_id": "sp_1",
            "status": SpanStatus.OK.value,
            "timestamp_monotonic_ns": 2000,
        },
    ]

    verifier = OracleVerifier(dag)
    result = verifier.verify_records(records)

    assert result.matched is False
    assert result.tasks_executed == 1
    assert any("task_2 was never executed" in d for d in result.discrepancies)


def test_oracle_verifier_catches_causal_timing_violation() -> None:
    """Verify oracle detects when successor started before predecessor finished."""
    dag = WorkloadDAG(dag_id="test_timing", workload_type="test", master_seed=42)
    dag.add_task(TaskSpec(task_id="A", operation_name="opA"))
    dag.add_task(TaskSpec(task_id="B", operation_name="opB", depends_on=["A"]))

    # B starts at 1500ns, but A only ends at 2000ns (timing violation)
    records = [
        {
            "record_type": RecordType.SPAN_START.value,
            "span_id": "sp_A",
            "task_id": "A",
            "timestamp_monotonic_ns": 1000,
        },
        {
            "record_type": RecordType.SPAN_START.value,
            "span_id": "sp_B",
            "task_id": "B",
            "timestamp_monotonic_ns": 1500,  # Premature start!
        },
        {
            "record_type": RecordType.SPAN_END.value,
            "span_id": "sp_A",
            "status": SpanStatus.OK.value,
            "timestamp_monotonic_ns": 2000,
        },
        {
            "record_type": RecordType.SPAN_END.value,
            "span_id": "sp_B",
            "status": SpanStatus.OK.value,
            "timestamp_monotonic_ns": 2500,
        },
    ]

    verifier = OracleVerifier(dag)
    result = verifier.verify_records(records)

    assert result.matched is False
    assert any("Causal Timing Violation" in d for d in result.discrepancies)
