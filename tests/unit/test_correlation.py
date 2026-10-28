"""Unit tests for CorrelationEngine and tiered resource attribution (ADR D5)."""

from __future__ import annotations

from agenttrace.correlation.engine import CorrelationEngine
from agenttrace.schemas import AttributionTier, RecordType, SpanStatus


def test_correlation_exclusive_window_tier_1() -> None:
    """Verify single non-overlapping span is classified as Tier 1 Exclusive Window."""
    trace_records = [
        {
            "record_type": RecordType.SPAN_START.value,
            "span_id": "sp_solo",
            "task_id": "task_solo",
            "process_id": 100,
            "timestamp_monotonic_ns": 1_000_000_000,
            "attributes": {},
        },
        {
            "record_type": RecordType.SPAN_END.value,
            "span_id": "sp_solo",
            "status": SpanStatus.OK.value,
            "timestamp_monotonic_ns": 1_050_000_000,
        },
    ]

    sample_records = [
        {
            "record_type": RecordType.RESOURCE_SAMPLE.value,
            "timestamp_monotonic_ns": 990_000_000,  # Before
            "process_metrics": [
                {
                    "process_id": 100,
                    "cpu_user_time_s": 1.0,
                    "cpu_system_time_s": 0.5,
                    "rss_bytes": 10_000_000,
                    "vms_bytes": 20_000_000,
                    "ctx_switches_voluntary": 10,
                    "ctx_switches_involuntary": 0,
                    "io_write_bytes": 1024,
                }
            ],
        },
        {
            "record_type": RecordType.RESOURCE_SAMPLE.value,
            "timestamp_monotonic_ns": 1_060_000_000,  # After
            "process_metrics": [
                {
                    "process_id": 100,
                    "cpu_user_time_s": 1.04,
                    "cpu_system_time_s": 0.51,
                    "rss_bytes": 10_500_000,
                    "vms_bytes": 20_000_000,
                    "ctx_switches_voluntary": 15,
                    "ctx_switches_involuntary": 0,
                    "io_write_bytes": 2048,
                }
            ],
        },
    ]

    engine = CorrelationEngine(trace_records, sample_records)
    results = engine.correlate()

    assert len(results) == 1
    res = results[0]
    assert res.span_id == "sp_solo"
    assert res.tier == AttributionTier.TIER_1_EXCLUSIVE
    assert res.delta_cpu_user_s == 0.04
    assert res.delta_cpu_system_s == 0.01
    assert res.delta_rss_bytes == 500_000
    assert res.delta_io_write_bytes == 1024
    assert res.concurrent_span_ids == []


def test_correlation_concurrent_aggregate_tier_3_no_silent_split() -> None:
    """Verify overlapping concurrent spans are strictly classified as Tier 3 without splitting."""
    trace_records = [
        # Span A: [1000ms, 1080ms]
        {
            "record_type": RecordType.SPAN_START.value,
            "span_id": "sp_A",
            "task_id": "task_A",
            "process_id": 200,
            "timestamp_monotonic_ns": 1_000_000_000,
            "attributes": {},
        },
        # Span B: [1020ms, 1070ms] (concurrent with A)
        {
            "record_type": RecordType.SPAN_START.value,
            "span_id": "sp_B",
            "task_id": "task_B",
            "process_id": 200,
            "timestamp_monotonic_ns": 1_020_000_000,
            "attributes": {},
        },
        {
            "record_type": RecordType.SPAN_END.value,
            "span_id": "sp_B",
            "status": SpanStatus.OK.value,
            "timestamp_monotonic_ns": 1_070_000_000,
        },
        {
            "record_type": RecordType.SPAN_END.value,
            "span_id": "sp_A",
            "status": SpanStatus.OK.value,
            "timestamp_monotonic_ns": 1_080_000_000,
        },
    ]

    sample_records = [
        {
            "record_type": RecordType.RESOURCE_SAMPLE.value,
            "timestamp_monotonic_ns": 990_000_000,
            "process_metrics": [
                {
                    "process_id": 200,
                    "cpu_user_time_s": 2.0,
                    "cpu_system_time_s": 0.0,
                    "rss_bytes": 1000,
                }
            ],
        },
        {
            "record_type": RecordType.RESOURCE_SAMPLE.value,
            "timestamp_monotonic_ns": 1_090_000_000,
            "process_metrics": [
                {
                    "process_id": 200,
                    "cpu_user_time_s": 2.10,
                    "cpu_system_time_s": 0.0,
                    "rss_bytes": 1000,
                }
            ],
        },
    ]

    engine = CorrelationEngine(trace_records, sample_records)
    results = engine.correlate()

    assert len(results) == 2
    res_A = next(r for r in results if r.span_id == "sp_A")
    res_B = next(r for r in results if r.span_id == "sp_B")

    # Both must be classified as Tier 3 Aggregate
    assert res_A.tier == AttributionTier.TIER_3_AGGREGATE
    assert res_B.tier == AttributionTier.TIER_3_AGGREGATE

    # Both must list each other in concurrent_span_ids
    assert "sp_B" in res_A.concurrent_span_ids
    assert "sp_A" in res_B.concurrent_span_ids
    assert res_A.confidence_label == "unsplit_concurrent_aggregate"


def test_correlation_dedicated_worker_tier_2() -> None:
    """Verify task executed in dedicated worker process is assigned Tier 2 Direct."""
    trace_records = [
        {
            "record_type": RecordType.SPAN_START.value,
            "span_id": "sp_worker",
            "task_id": "task_cpu",
            "process_id": 5555,
            "timestamp_monotonic_ns": 1_000_000_000,
            "attributes": {"dedicated_worker": True},
        },
        {
            "record_type": RecordType.SPAN_END.value,
            "span_id": "sp_worker",
            "status": SpanStatus.OK.value,
            "timestamp_monotonic_ns": 1_050_000_000,
        },
    ]

    engine = CorrelationEngine(trace_records, sample_records=[])
    results = engine.correlate()

    assert len(results) == 1
    assert results[0].tier == AttributionTier.TIER_2_DIRECT
