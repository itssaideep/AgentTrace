"""Unit tests for WorkloadDAG data models and WorkloadGenerator."""

from __future__ import annotations

import pytest

from agenttrace.workloads.generator import WorkloadGenerator, derive_task_seed
from agenttrace.workloads.models import TaskSpec, WorkloadDAG


def test_seed_isolation_and_determinism() -> None:
    """Verify task seeds derived from master seed are deterministic and order-independent."""
    s1 = derive_task_seed(master_seed=42, task_id="task_005")
    s2 = derive_task_seed(master_seed=42, task_id="task_005")
    s3 = derive_task_seed(master_seed=42, task_id="task_006")
    s4 = derive_task_seed(master_seed=99, task_id="task_005")

    assert s1 == s2
    assert s1 != s3
    assert s1 != s4


def test_sequential_dag_structure() -> None:
    """Verify sequential DAG produces linear chain of dependencies."""
    gen = WorkloadGenerator(master_seed=100)
    dag = gen.generate_sequential(num_tasks=5, base_latency_ms=10.0)

    assert dag.validate_acyclic() is True
    assert len(dag.tasks) == 5
    order = dag.topological_order()
    assert order == ["task_000", "task_001", "task_002", "task_003", "task_004"]

    assert dag.tasks["task_000"].depends_on == []
    assert dag.tasks["task_001"].depends_on == ["task_000"]
    assert dag.tasks["task_004"].depends_on == ["task_003"]


def test_parallel_fanout_fanin_structure() -> None:
    """Verify parallel DAG creates root dispatcher, worker fan-out, and collector."""
    gen = WorkloadGenerator(master_seed=100)
    dag = gen.generate_parallel(num_tasks=4, base_latency_ms=15.0)

    assert dag.validate_acyclic() is True
    # 1 root + 4 workers + 1 collector = 6 tasks
    assert len(dag.tasks) == 6

    assert "root_dispatch" in dag.tasks
    assert "collector_aggregate" in dag.tasks

    for i in range(4):
        worker_id = f"worker_{i:03d}"
        assert dag.tasks[worker_id].depends_on == ["root_dispatch"]

    assert len(dag.tasks["collector_aggregate"].depends_on) == 4


def test_multi_step_dag_structure() -> None:
    """Verify multi-step DAG generates layered dependency stages."""
    gen = WorkloadGenerator(master_seed=100)
    dag = gen.generate_multi_step(stages=3, tasks_per_stage=3)

    assert dag.validate_acyclic() is True
    assert len(dag.tasks) == 9
    order = dag.topological_order()
    assert len(order) == 9


def test_cpu_and_io_dags() -> None:
    """Verify CPU and I/O workload DAG construction."""
    gen = WorkloadGenerator()
    cpu_dag = gen.generate_cpu_intensive(num_tasks=4, compute_intensity=50_000)
    assert len(cpu_dag.tasks) == 4
    assert cpu_dag.tasks["cpu_task_000"].tool_name == "cpu"

    io_dag = gen.generate_io_intensive(num_tasks=3, io_bytes=4096)
    assert len(io_dag.tasks) == 3
    assert io_dag.tasks["io_task_000"].tool_name == "io"


def test_cycle_detection_in_dag() -> None:
    """Verify Kahn's algorithm detects circular dependencies in DAG."""
    dag = WorkloadDAG(dag_id="cyclic", workload_type="test", master_seed=42)
    t1 = TaskSpec(task_id="A", operation_name="opA", depends_on=["B"])
    t2 = TaskSpec(task_id="B", operation_name="opB", depends_on=["A"])
    dag.add_task(t1)
    dag.add_task(t2)

    assert dag.validate_acyclic() is False
    with pytest.raises(ValueError, match="cycles"):
        dag.topological_order()
