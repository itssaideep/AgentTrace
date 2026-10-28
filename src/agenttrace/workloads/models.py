"""Data structures for synthetic workload directed acyclic graphs (DAGs)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TaskSpec:
    """Specification of an individual task node in a synthetic workload DAG."""

    task_id: str
    operation_name: str
    operation_type: str = "tool_exec"
    tool_name: str = "latency"  # "latency", "cpu", "io", "model"
    tool_params: dict[str, Any] = field(default_factory=dict)
    parent_task_id: str | None = None
    depends_on: list[str] = field(default_factory=list)
    timeout_ms: float | None = None
    fail_probability: float = 0.0
    max_retries: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize TaskSpec to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskSpec:
        """Construct TaskSpec from dictionary."""
        return cls(
            task_id=data["task_id"],
            operation_name=data["operation_name"],
            operation_type=data.get("operation_type", "tool_exec"),
            tool_name=data.get("tool_name", "latency"),
            tool_params=data.get("tool_params", {}),
            parent_task_id=data.get("parent_task_id"),
            depends_on=data.get("depends_on", []),
            timeout_ms=data.get("timeout_ms"),
            fail_probability=data.get("fail_probability", 0.0),
            max_retries=data.get("max_retries", 0),
        )


@dataclass
class WorkloadDAG:
    """Immutable directed acyclic graph defining a synthetic workload ground truth."""

    dag_id: str
    workload_type: str
    master_seed: int
    tasks: dict[str, TaskSpec] = field(default_factory=dict)

    def add_task(self, task: TaskSpec) -> None:
        """Add a task specification to the DAG."""
        if task.task_id in self.tasks:
            raise ValueError(f"Duplicate task_id in DAG: {task.task_id}")
        self.tasks[task.task_id] = task

    def validate_acyclic(self) -> bool:
        """Verify the graph has no cycles and dependencies reference existing tasks."""
        # Check all depends_on reference existing tasks
        for task_id, task in self.tasks.items():
            for dep_id in task.depends_on:
                if dep_id not in self.tasks:
                    raise ValueError(f"Task {task_id} depends on non-existent task {dep_id}")
            if task.parent_task_id and task.parent_task_id not in self.tasks:
                raise ValueError(
                    f"Task {task_id} references non-existent parent {task.parent_task_id}"
                )

        # Cycle detection using Kahn's algorithm
        in_degree: dict[str, int] = dict.fromkeys(self.tasks, 0)
        for task in self.tasks.values():
            for _dep in task.depends_on:
                # task depends on dep means dep -> task edge
                in_degree[task.task_id] += 1

        queue = [t for t, deg in in_degree.items() if deg == 0]
        visited_count = 0

        # Build adjacency list: dep -> list of tasks that depend on it
        adj: dict[str, list[str]] = {t: [] for t in self.tasks}
        for task in self.tasks.values():
            for dep in task.depends_on:
                adj[dep].append(task.task_id)

        while queue:
            node = queue.pop(0)
            visited_count += 1
            for successor in adj[node]:
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)

        return visited_count == len(self.tasks)

    def topological_order(self) -> list[str]:
        """Return task IDs in topological execution order."""
        if not self.validate_acyclic():
            raise ValueError("Cannot topologically sort DAG containing cycles")

        in_degree: dict[str, int] = dict.fromkeys(self.tasks, 0)
        adj: dict[str, list[str]] = {t: [] for t in self.tasks}
        for task in self.tasks.values():
            for dep in task.depends_on:
                in_degree[task.task_id] += 1
                adj[dep].append(task.task_id)

        queue = sorted([t for t, deg in in_degree.items() if deg == 0])
        order: list[str] = []

        while queue:
            node = queue.pop(0)
            order.append(node)
            for successor in sorted(adj[node]):
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)

        return order

    def to_dict(self) -> dict[str, Any]:
        """Serialize complete DAG to JSON-compatible dictionary."""
        return {
            "dag_id": self.dag_id,
            "workload_type": self.workload_type,
            "master_seed": self.master_seed,
            "tasks": {t_id: task.to_dict() for t_id, task in self.tasks.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkloadDAG:
        """Reconstruct WorkloadDAG from dictionary."""
        dag = cls(
            dag_id=data["dag_id"],
            workload_type=data["workload_type"],
            master_seed=data["master_seed"],
        )
        for _t_id, t_data in data["tasks"].items():
            dag.add_task(TaskSpec.from_dict(t_data))
        return dag
