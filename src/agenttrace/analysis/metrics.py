"""Statistical metrics and distribution calculations with sample-size gating."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class DistributionSummary:
    """Summary statistics for a continuous distribution of observations."""

    count: int
    mean: float
    std_dev: float
    min: float
    p25: float
    p50: float
    p75: float
    p90: float
    p95: float
    p99: float
    max: float
    iqr: float
    sample_size_warning: str | None = None


def compute_distribution(values: Sequence[float]) -> DistributionSummary:
    """Compute standard summary statistics and percentiles with sample size warnings.

    Interpolation uses nearest rank / linear interpolation matching NumPy default.
    """
    n = len(values)
    if n == 0:
        return DistributionSummary(
            count=0,
            mean=0.0,
            std_dev=0.0,
            min=0.0,
            p25=0.0,
            p50=0.0,
            p75=0.0,
            p90=0.0,
            p95=0.0,
            p99=0.0,
            max=0.0,
            iqr=0.0,
            sample_size_warning="Empty sample set",
        )

    sorted_vals = sorted(values)
    mean_val = sum(sorted_vals) / n
    variance = sum((x - mean_val) ** 2 for x in sorted_vals) / n if n > 1 else 0.0
    std_val = math.sqrt(variance)

    def percentile(p: float) -> float:
        if n == 1:
            return sorted_vals[0]
        k = (n - 1) * (p / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_vals[int(k)]
        d0 = sorted_vals[int(f)] * (c - k)
        d1 = sorted_vals[int(c)] * (k - f)
        return d0 + d1

    p25 = percentile(25)
    p50 = percentile(50)
    p75 = percentile(75)
    p90 = percentile(90)
    p95 = percentile(95)
    p99 = percentile(99)
    iqr = p75 - p25

    warning = None
    if n < 5:
        warning = (
            f"Sample size N={n} is below minimum recommended threshold (N=5); "
            "percentiles are estimates"
        )

    return DistributionSummary(
        count=n,
        mean=mean_val,
        std_dev=std_val,
        min=sorted_vals[0],
        p25=p25,
        p50=p50,
        p75=p75,
        p90=p90,
        p95=p95,
        p99=p99,
        max=sorted_vals[-1],
        iqr=iqr,
        sample_size_warning=warning,
    )


@dataclass(frozen=True)
class ScalingEfficiency:
    """Scaling efficiency metrics comparing parallel to baseline sequential execution."""

    concurrency_limit: int
    baseline_makespan_s: float
    parallel_makespan_s: float
    speedup: float
    parallel_efficiency: float
    theoretical_max_speedup: float


def compute_scaling_efficiency(
    baseline_makespan_s: float,
    parallel_makespan_s: float,
    concurrency_limit: int,
) -> ScalingEfficiency:
    """Compute speedup (S = T_1 / T_N) and parallel efficiency (E = S / N)."""
    if parallel_makespan_s <= 0 or baseline_makespan_s <= 0 or concurrency_limit < 1:
        return ScalingEfficiency(
            concurrency_limit=concurrency_limit,
            baseline_makespan_s=baseline_makespan_s,
            parallel_makespan_s=parallel_makespan_s,
            speedup=0.0,
            parallel_efficiency=0.0,
            theoretical_max_speedup=float(concurrency_limit),
        )

    speedup = baseline_makespan_s / parallel_makespan_s
    efficiency = speedup / concurrency_limit

    return ScalingEfficiency(
        concurrency_limit=concurrency_limit,
        baseline_makespan_s=baseline_makespan_s,
        parallel_makespan_s=parallel_makespan_s,
        speedup=speedup,
        parallel_efficiency=efficiency,
        theoretical_max_speedup=float(concurrency_limit),
    )
