"""Unit tests for statistical distributions and scaling efficiency."""

from agenttrace.analysis.metrics import compute_distribution, compute_scaling_efficiency


def test_distribution_summary_exact() -> None:
    # Set of numbers 1 to 100
    vals = list(range(1, 101))
    dist = compute_distribution(vals)

    assert dist.count == 100
    assert dist.min == 1.0
    assert dist.max == 100.0
    assert dist.mean == 50.5
    assert dist.p50 == 50.5
    assert dist.p25 == 25.75
    assert dist.p75 == 75.25
    assert dist.sample_size_warning is None


def test_distribution_small_sample_warning() -> None:
    vals = [10.0, 20.0, 30.0]
    dist = compute_distribution(vals)

    assert dist.count == 3
    assert dist.p50 == 20.0
    assert dist.sample_size_warning is not None
    assert "below minimum recommended threshold" in dist.sample_size_warning


def test_scaling_efficiency() -> None:
    # Baseline makespan 10.0s, parallel with 4 workers finishes in 3.0s
    # Speedup = 10.0 / 3.0 = 3.333
    # Parallel efficiency = 3.333 / 4 = 0.8333
    eff = compute_scaling_efficiency(
        baseline_makespan_s=10.0,
        parallel_makespan_s=3.0,
        concurrency_limit=4,
    )
    assert abs(eff.speedup - (10.0 / 3.0)) < 1e-4
    assert abs(eff.parallel_efficiency - ((10.0 / 3.0) / 4.0)) < 1e-4
    assert eff.theoretical_max_speedup == 4.0
