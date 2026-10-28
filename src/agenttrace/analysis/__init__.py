"""Analytical algorithms (sweep-line concurrency, critical path, run comparison)."""

from agenttrace.analysis.compare import RunComparisonResult, TaskDifferential, compare_runs
from agenttrace.analysis.completeness import CompletenessReport, TraceCompletenessChecker
from agenttrace.analysis.concurrency import (
    ConcurrencyInterval,
    ConcurrencyProfile,
    compute_concurrency_profile,
)
from agenttrace.analysis.critical_path import (
    CriticalPathNode,
    CriticalPathResult,
    compute_critical_path,
    compute_critical_path_from_spans,
)
from agenttrace.analysis.metrics import (
    DistributionSummary,
    ScalingEfficiency,
    compute_distribution,
    compute_scaling_efficiency,
)

__all__ = [
    "CompletenessReport",
    "ConcurrencyInterval",
    "ConcurrencyProfile",
    "CriticalPathNode",
    "CriticalPathResult",
    "DistributionSummary",
    "RunComparisonResult",
    "ScalingEfficiency",
    "TaskDifferential",
    "TraceCompletenessChecker",
    "compare_runs",
    "compute_concurrency_profile",
    "compute_critical_path",
    "compute_critical_path_from_spans",
    "compute_distribution",
    "compute_scaling_efficiency",
]
