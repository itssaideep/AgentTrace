"""Deterministic workload DAG generator with seed-isolated PRNG streams."""

from __future__ import annotations

import hashlib
import random
from typing import Literal

from agenttrace.workloads.models import TaskSpec, WorkloadDAG


def derive_task_seed(master_seed: int, task_id: str) -> int:
    """Derive an isolated, deterministic 32-bit seed for a specific task ID.

    Guarantees that task parameters are independent of concurrent scheduling order.
    """
    digest = hashlib.sha256(f"{master_seed}:{task_id}".encode()).hexdigest()
    return int(digest[:8], 16)


class WorkloadGenerator:
    """Generates parameterized, deterministic synthetic agent workload DAGs."""

    def __init__(self, master_seed: int = 42) -> None:
        self.master_seed = master_seed

    def generate_sequential(
        self,
        num_tasks: int = 10,
        base_latency_ms: float = 10.0,
        jitter_ms: float = 2.0,
        fail_probability: float = 0.0,
        max_retries: int = 0,
    ) -> WorkloadDAG:
        """Generate a strictly linear sequential chain: T0 -> T1 -> T2 ... -> Tn."""
        dag = WorkloadDAG(
            dag_id=f"seq_{self.master_seed}_{num_tasks}",
            workload_type="sequential",
            master_seed=self.master_seed,
        )

        prev_id: str | None = None
        for i in range(num_tasks):
            task_id = f"task_{i:03d}"
            task_seed = derive_task_seed(self.master_seed, task_id)
            rng = random.Random(task_seed)

            delta = rng.uniform(-jitter_ms, jitter_ms) if jitter_ms > 0 else 0.0
            delay_ms = max(0.1, base_latency_ms + delta)

            task = TaskSpec(
                task_id=task_id,
                operation_name=f"sequential_step_{i}",
                operation_type="tool_exec",
                tool_name="latency",
                tool_params={"duration_ms": round(delay_ms, 2)},
                depends_on=[prev_id] if prev_id else [],
                fail_probability=fail_probability,
                max_retries=max_retries,
            )
            dag.add_task(task)
            prev_id = task_id

        return dag

    def generate_parallel(
        self,
        num_tasks: int = 10,
        base_latency_ms: float = 10.0,
        jitter_ms: float = 2.0,
        fail_probability: float = 0.0,
    ) -> WorkloadDAG:
        """Generate a fan-out / fan-in DAG: Root -> [Parallel Workers] -> Collector."""
        dag = WorkloadDAG(
            dag_id=f"par_{self.master_seed}_{num_tasks}",
            workload_type="parallel",
            master_seed=self.master_seed,
        )

        # Root dispatcher
        root_id = "root_dispatch"
        dag.add_task(
            TaskSpec(
                task_id=root_id,
                operation_name="dispatch_workers",
                operation_type="agent_step",
                tool_name="latency",
                tool_params={"duration_ms": 1.0},
            )
        )

        worker_ids: list[str] = []
        for i in range(num_tasks):
            task_id = f"worker_{i:03d}"
            worker_ids.append(task_id)
            task_seed = derive_task_seed(self.master_seed, task_id)
            rng = random.Random(task_seed)

            delta = rng.uniform(-jitter_ms, jitter_ms) if jitter_ms > 0 else 0.0
            delay_ms = max(0.1, base_latency_ms + delta)

            dag.add_task(
                TaskSpec(
                    task_id=task_id,
                    operation_name=f"parallel_worker_{i}",
                    operation_type="tool_exec",
                    tool_name="latency",
                    tool_params={"duration_ms": round(delay_ms, 2)},
                    depends_on=[root_id],
                    fail_probability=fail_probability,
                )
            )

        # Collector aggregation node
        dag.add_task(
            TaskSpec(
                task_id="collector_aggregate",
                operation_name="aggregate_results",
                operation_type="agent_step",
                tool_name="latency",
                tool_params={"duration_ms": 2.0},
                depends_on=worker_ids,
            )
        )

        return dag

    def generate_multi_step(
        self,
        stages: int = 3,
        tasks_per_stage: int = 4,
        base_latency_ms: float = 8.0,
    ) -> WorkloadDAG:
        """Generate a multi-stage layered DAG with cross-stage data dependencies."""
        dag = WorkloadDAG(
            dag_id=f"multistep_{self.master_seed}_{stages}x{tasks_per_stage}",
            workload_type="multi_step",
            master_seed=self.master_seed,
        )

        prev_stage_ids: list[str] = []
        for s in range(stages):
            current_stage_ids: list[str] = []
            for t in range(tasks_per_stage):
                task_id = f"s{s}_t{t}"
                current_stage_ids.append(task_id)

                # Each task depends on subset of previous stage tasks deterministically
                task_seed = derive_task_seed(self.master_seed, task_id)
                rng = random.Random(task_seed)

                deps: list[str] = []
                if prev_stage_ids:
                    # Deterministically pick 1 or 2 dependencies from previous stage
                    k = min(len(prev_stage_ids), rng.choice([1, 2]))
                    deps = sorted(rng.sample(prev_stage_ids, k))

                dag.add_task(
                    TaskSpec(
                        task_id=task_id,
                        operation_name=f"stage_{s}_task_{t}",
                        operation_type="tool_exec",
                        tool_name="latency",
                        tool_params={"duration_ms": base_latency_ms},
                        depends_on=deps,
                    )
                )
            prev_stage_ids = current_stage_ids

        return dag

    def generate_cpu_intensive(
        self,
        num_tasks: int = 8,
        compute_intensity: int = 100_000,
    ) -> WorkloadDAG:
        """Generate parallel compute-bound tasks that burn CPU cycles."""
        dag = WorkloadDAG(
            dag_id=f"cpu_{self.master_seed}_{num_tasks}",
            workload_type="cpu_intensive",
            master_seed=self.master_seed,
        )

        for i in range(num_tasks):
            task_id = f"cpu_task_{i:03d}"
            dag.add_task(
                TaskSpec(
                    task_id=task_id,
                    operation_name=f"matrix_compute_{i}",
                    operation_type="tool_exec",
                    tool_name="cpu",
                    tool_params={"compute_intensity": compute_intensity},
                )
            )

        return dag

    def generate_io_intensive(
        self,
        num_tasks: int = 8,
        io_bytes: int = 65_536,
        do_fsync: bool = True,
    ) -> WorkloadDAG:
        """Generate storage-bound tasks performing explicit file writes and fsync."""
        dag = WorkloadDAG(
            dag_id=f"io_{self.master_seed}_{num_tasks}",
            workload_type="io_intensive",
            master_seed=self.master_seed,
        )

        for i in range(num_tasks):
            task_id = f"io_task_{i:03d}"
            dag.add_task(
                TaskSpec(
                    task_id=task_id,
                    operation_name=f"file_io_{i}",
                    operation_type="tool_exec",
                    tool_name="io",
                    tool_params={"io_bytes": io_bytes, "do_fsync": do_fsync},
                )
            )

        return dag

    def generate_variable_size(
        self,
        num_tasks: int = 20,
        distribution: Literal["uniform", "heavy_tailed"] = "heavy_tailed",
        base_latency_ms: float = 10.0,
    ) -> WorkloadDAG:
        """Generate variable-sized tasks to stress tail latency (p95/p99)."""
        dag = WorkloadDAG(
            dag_id=f"var_{self.master_seed}_{distribution}_{num_tasks}",
            workload_type="variable_size",
            master_seed=self.master_seed,
        )

        for i in range(num_tasks):
            task_id = f"var_task_{i:03d}"
            task_seed = derive_task_seed(self.master_seed, task_id)
            rng = random.Random(task_seed)

            if distribution == "heavy_tailed":
                # Pareto distribution with alpha=1.5
                mult = rng.paretovariate(alpha=1.5)
                delay_ms = min(200.0, base_latency_ms * mult)
            else:
                delay_ms = rng.uniform(1.0, base_latency_ms * 3.0)

            dag.add_task(
                TaskSpec(
                    task_id=task_id,
                    operation_name=f"var_step_{i}",
                    operation_type="tool_exec",
                    tool_name="latency",
                    tool_params={"duration_ms": round(delay_ms, 2)},
                )
            )

        return dag
