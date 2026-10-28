"""Ground-truth DAG oracle verifier for validating trace correctness."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agenttrace.schemas import RecordType
from agenttrace.workloads.models import WorkloadDAG


@dataclass
class OracleComparisonResult:
    """Outcome of verifying a recorded trace stream against ground-truth DAG."""

    matched: bool
    tasks_defined: int
    tasks_executed: int
    edges_defined: int
    edges_verified: int
    edge_recall: float
    discrepancies: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Formatted human-readable verification summary."""
        status = "PASSED" if self.matched else "FAILED"
        return (
            f"Oracle Verification: {status}\n"
            f"Tasks: {self.tasks_executed}/{self.tasks_defined}\n"
            f"Edges Verified: {self.edges_verified}/{self.edges_defined} "
            f"(Recall: {self.edge_recall:.1%})\n"
            f"Discrepancies: {len(self.discrepancies)}"
        )


class OracleVerifier:
    """Validates recorded execution traces against ground-truth WorkloadDAG specification."""

    def __init__(self, dag: WorkloadDAG) -> None:
        self.dag = dag

    def verify_trace_file(self, trace_file: Path | str) -> OracleComparisonResult:
        """Verify a JSONL trace file against the ground-truth DAG."""
        records: list[dict[str, Any]] = []
        with open(trace_file, encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str:
                    records.append(json.loads(line_str))
        return self.verify_records(records)

    def verify_records(self, records: list[dict[str, Any]]) -> OracleComparisonResult:
        """Verify list of parsed event records against ground truth."""
        discrepancies: list[str] = []

        # Index records by span_id and task_id
        starts_by_span: dict[str, dict[str, Any]] = {}
        ends_by_span: dict[str, dict[str, Any]] = {}
        spans_by_task: dict[str, list[dict[str, Any]]] = {}

        for r in records:
            rec_type = r.get("record_type")
            span_id = r.get("span_id")
            task_id = r.get("task_id")

            if rec_type == RecordType.SPAN_START.value and span_id:
                starts_by_span[span_id] = r
                if task_id:
                    spans_by_task.setdefault(task_id, []).append(r)
            elif rec_type == RecordType.SPAN_END.value and span_id:
                ends_by_span[span_id] = r

        # 1. Task Coverage Audit
        tasks_defined = len(self.dag.tasks)
        tasks_executed = 0

        for task_id in self.dag.tasks:
            if task_id not in spans_by_task:
                discrepancies.append(f"DAG Task {task_id} was never executed in trace")
            else:
                tasks_executed += 1

        # 2. Dependency Edge Audit
        edges_defined = 0
        edges_verified = 0

        for task_id, task_spec in self.dag.tasks.items():
            for dep_task_id in task_spec.depends_on:
                edges_defined += 1

                dep_spans = spans_by_task.get(dep_task_id, [])
                succ_spans = spans_by_task.get(task_id, [])

                if not dep_spans:
                    discrepancies.append(
                        f"Edge {dep_task_id} -> {task_id}: predecessor {dep_task_id} missing"
                    )
                    continue

                if not succ_spans:
                    discrepancies.append(
                        f"Edge {dep_task_id} -> {task_id}: successor {task_id} missing"
                    )
                    continue

                # Causal timing check: predecessor must end before successor starts
                latest_dep_span_id = dep_spans[-1]["span_id"]
                first_succ_span = succ_spans[0]

                dep_end = ends_by_span.get(latest_dep_span_id)
                succ_start_ns = first_succ_span.get("timestamp_monotonic_ns", 0)

                if not dep_end:
                    discrepancies.append(
                        f"Edge {dep_task_id} -> {task_id}: predecessor span {latest_dep_span_id} "
                        f"has no span_end record"
                    )
                    continue

                dep_end_ns = dep_end.get("timestamp_monotonic_ns", 0)
                if dep_end_ns > succ_start_ns:
                    discrepancies.append(
                        f"Causal Timing Violation: {dep_task_id} ended at {dep_end_ns}ns, "
                        f"but dependent {task_id} started earlier at {succ_start_ns}ns"
                    )
                else:
                    edges_verified += 1

        edge_recall = (edges_verified / edges_defined) if edges_defined > 0 else 1.0
        matched = (len(discrepancies) == 0) and (tasks_executed == tasks_defined)

        return OracleComparisonResult(
            matched=matched,
            tasks_defined=tasks_defined,
            tasks_executed=tasks_executed,
            edges_defined=edges_defined,
            edges_verified=edges_verified,
            edge_recall=edge_recall,
            discrepancies=discrepancies,
        )
