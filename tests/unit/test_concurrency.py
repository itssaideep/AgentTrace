"""Unit tests for sweep-line concurrency algorithm."""

from agenttrace.analysis.concurrency import compute_concurrency_profile


def test_concurrency_empty() -> None:
    profile = compute_concurrency_profile([])
    assert profile.max_concurrency == 0
    assert profile.mean_concurrency == 0.0
    assert profile.makespan_ns == 0
    assert len(profile.intervals) == 0


def test_concurrency_sequential_handoff() -> None:
    # Two strictly sequential spans: [100, 200) and [200, 300)
    spans = [
        {"span_id": "s1", "start_monotonic_ns": 100, "end_monotonic_ns": 200},
        {"span_id": "s2", "start_monotonic_ns": 200, "end_monotonic_ns": 300},
    ]
    profile = compute_concurrency_profile(spans)
    assert profile.max_concurrency == 1
    assert profile.makespan_ns == 200
    assert profile.total_span_duration_ns == 200
    assert profile.mean_concurrency == 1.0


def test_concurrency_parallel_overlap_golden() -> None:
    # Golden test:
    # Span 1: [100, 300) -> duration 200
    # Span 2: [150, 250) -> duration 100
    # Span 3: [120, 280) -> duration 160
    #
    # Time breakdown:
    # [100, 120): s1 (concurrency 1, dur 20)
    # [120, 150): s1, s3 (concurrency 2, dur 30)
    # [150, 250): s1, s2, s3 (concurrency 3, dur 100)
    # [250, 280): s1, s3 (concurrency 2, dur 30)
    # [280, 300): s1 (concurrency 1, dur 20)
    #
    # Makespan = 300 - 100 = 200
    # Integral C(t) dt = 1*20 + 2*30 + 3*100 + 2*30 + 1*20 = 20 + 60 + 300 + 60 + 20 = 460
    # Mean concurrency = 460 / 200 = 2.3
    # Total span duration = 200 + 100 + 160 = 460
    spans = [
        {"span_id": "s1", "start_monotonic_ns": 100, "end_monotonic_ns": 300},
        {"span_id": "s2", "start_monotonic_ns": 150, "end_monotonic_ns": 250},
        {"span_id": "s3", "start_monotonic_ns": 120, "end_monotonic_ns": 280},
    ]

    profile = compute_concurrency_profile(spans)
    assert profile.max_concurrency == 3
    assert profile.makespan_ns == 200
    assert profile.total_span_duration_ns == 460
    assert abs(profile.mean_concurrency - 2.3) < 1e-9

    assert len(profile.intervals) == 5
    assert profile.intervals[0].concurrency_level == 1
    assert profile.intervals[1].concurrency_level == 2
    assert profile.intervals[2].concurrency_level == 3
    assert profile.intervals[3].concurrency_level == 2
    assert profile.intervals[4].concurrency_level == 1
