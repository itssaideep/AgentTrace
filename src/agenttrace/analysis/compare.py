"""Differential comparison engine for multi-run performance and resource analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agenttrace.analysis.concurrency import compute_concurrency_profile
from agenttrace.analysis.critical_path import CriticalPathResult, compute_critical_path_from_spans
from agenttrace.analysis.metrics import DistributionSummary, compute_distribution
from agenttrace.storage.sqlite import SQLiteTraceStore


@dataclass
class TaskDifferential:
    """Per-task execution difference between baseline and candidate run."""

    task_id: str
    baseline_duration_ms: float
    candidate_duration_ms: float
    duration_delta_ms: float
    speedup: float


@dataclass
class RunComparisonResult:
    """Full comparative analysis between baseline (Run A) and candidate (Run B)."""

    baseline_label: str
    candidate_label: str

    baseline_makespan_ms: float
    candidate_makespan_ms: float
    makespan_delta_ms: float
    speedup: float

    baseline_max_concurrency: int
    candidate_max_concurrency: int
    baseline_mean_concurrency: float
    candidate_mean_concurrency: float

    baseline_cp: CriticalPathResult
    candidate_cp: CriticalPathResult

    baseline_distribution: DistributionSummary
    candidate_distribution: DistributionSummary

    task_differentials: list[TaskDifferential] = field(default_factory=list)

    def summary_markdown(self) -> str:
        """Format a clear Markdown summary table of comparison findings."""
        cp_diff = (
            self.candidate_cp.critical_path_duration_ms - self.baseline_cp.critical_path_duration_ms
        )
        cpr_diff = self.candidate_cp.critical_path_ratio - self.baseline_cp.critical_path_ratio
        p50_diff = self.candidate_distribution.p50 - self.baseline_distribution.p50
        p95_diff = self.candidate_distribution.p95 - self.baseline_distribution.p95

        def _row(metric: str, base: str, cand: str, diff: str) -> str:
            return f"| {metric} | {base} | {cand} | {diff} |"

        lines = [
            f"# Run Comparison: {self.baseline_label} vs {self.candidate_label}",
            "",
            "## Primary Performance Metrics",
            "| Metric | Baseline | Candidate | Delta / Ratio |",
            "| :--- | :--- | :--- | :--- |",
            _row(
                "Makespan (ms)",
                f"{self.baseline_makespan_ms:.2f}",
                f"{self.candidate_makespan_ms:.2f}",
                f"{self.makespan_delta_ms:+.2f} ms ({self.speedup:.2f}x)",
            ),
            _row(
                "Max Concurrency",
                str(self.baseline_max_concurrency),
                str(self.candidate_max_concurrency),
                f"{self.candidate_max_concurrency - self.baseline_max_concurrency:+d}",
            ),
            _row(
                "Mean Concurrency",
                f"{self.baseline_mean_concurrency:.2f}",
                f"{self.candidate_mean_concurrency:.2f}",
                f"{self.candidate_mean_concurrency - self.baseline_mean_concurrency:+.2f}",
            ),
            _row(
                "Critical Path (ms)",
                f"{self.baseline_cp.critical_path_duration_ms:.2f}",
                f"{self.candidate_cp.critical_path_duration_ms:.2f}",
                f"{cp_diff:+.2f} ms",
            ),
            _row(
                "Critical Path Ratio",
                f"{self.baseline_cp.critical_path_ratio:.3f}",
                f"{self.candidate_cp.critical_path_ratio:.3f}",
                f"{cpr_diff:+.3f}",
            ),
            _row(
                "Span Latency p50 (ms)",
                f"{self.baseline_distribution.p50:.2f}",
                f"{self.candidate_distribution.p50:.2f}",
                f"{p50_diff:+.2f} ms",
            ),
            _row(
                "Span Latency p95 (ms)",
                f"{self.baseline_distribution.p95:.2f}",
                f"{self.candidate_distribution.p95:.2f}",
                f"{p95_diff:+.2f} ms",
            ),
            "",
        ]

        if self.task_differentials:
            lines.extend(
                [
                    "## Per-Task Differentials",
                    "| Task ID | Baseline (ms) | Candidate (ms) | Delta (ms) | Speedup |",
                    "| :--- | :--- | :--- | :--- | :--- |",
                ]
            )
            for td in self.task_differentials[:20]:  # Top 20 tasks
                lines.append(
                    f"| {td.task_id} | {td.baseline_duration_ms:.2f} | "
                    f"{td.candidate_duration_ms:.2f} | {td.duration_delta_ms:+.2f} | "
                    f"{td.speedup:.2f}x |"
                )

        return "\n".join(lines)


def _load_spans_from_source(source: str | Path | list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Helper to load span records from a file path, SQLite store, or list of records."""
    if isinstance(source, list):
        # Could be raw trace records or spans
        store = SQLiteTraceStore()
        store.ingest_records(source)
        return store.get_spans()
    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(f"Source file not found: {path}")

    store = SQLiteTraceStore()
    store.ingest_jsonl(path)
    return store.get_spans()


def compare_runs(
    baseline_source: str | Path | list[dict[str, Any]],
    candidate_source: str | Path | list[dict[str, Any]],
    baseline_label: str = "baseline",
    candidate_label: str = "candidate",
) -> RunComparisonResult:
    """Perform differential comparison between baseline and candidate trace runs."""
    spans_a = _load_spans_from_source(baseline_source)
    spans_b = _load_spans_from_source(candidate_source)

    prof_a = compute_concurrency_profile(spans_a)
    prof_b = compute_concurrency_profile(spans_b)

    cp_a = compute_critical_path_from_spans(spans_a, observed_makespan_ns=prof_a.makespan_ns)
    cp_b = compute_critical_path_from_spans(spans_b, observed_makespan_ns=prof_b.makespan_ns)

    durations_a = [s["duration_ms"] for s in spans_a if s.get("duration_ms") is not None]
    durations_b = [s["duration_ms"] for s in spans_b if s.get("duration_ms") is not None]

    dist_a = compute_distribution(durations_a)
    dist_b = compute_distribution(durations_b)

    makespan_a_ms = prof_a.makespan_ms
    makespan_b_ms = prof_b.makespan_ms
    makespan_delta_ms = makespan_b_ms - makespan_a_ms
    speedup = (makespan_a_ms / makespan_b_ms) if makespan_b_ms > 0 else 1.0

    # Per-task matching
    tasks_a = {s["task_id"]: s["duration_ms"] for s in spans_a if s.get("task_id")}
    tasks_b = {s["task_id"]: s["duration_ms"] for s in spans_b if s.get("task_id")}

    differentials: list[TaskDifferential] = []
    common_tasks = set(tasks_a.keys()) & set(tasks_b.keys())
    for tid in sorted(common_tasks):
        da = tasks_a[tid] or 0.0
        db = tasks_b[tid] or 0.0
        delta = db - da
        task_speedup = (da / db) if db > 0 else 1.0
        differentials.append(
            TaskDifferential(
                task_id=tid,
                baseline_duration_ms=da,
                candidate_duration_ms=db,
                duration_delta_ms=delta,
                speedup=task_speedup,
            )
        )

    return RunComparisonResult(
        baseline_label=baseline_label,
        candidate_label=candidate_label,
        baseline_makespan_ms=makespan_a_ms,
        candidate_makespan_ms=makespan_b_ms,
        makespan_delta_ms=makespan_delta_ms,
        speedup=speedup,
        baseline_max_concurrency=prof_a.max_concurrency,
        candidate_max_concurrency=prof_b.max_concurrency,
        baseline_mean_concurrency=prof_a.mean_concurrency,
        candidate_mean_concurrency=prof_b.mean_concurrency,
        baseline_cp=cp_a,
        candidate_cp=cp_b,
        baseline_distribution=dist_a,
        candidate_distribution=dist_b,
        task_differentials=differentials,
    )
