"""Smoke tests for AgentTrace repository scaffold and baseline interfaces."""

from __future__ import annotations

from pathlib import Path

import agenttrace
from agenttrace.cli import create_parser
from agenttrace.config import RunConfig, TracerConfig, WorkloadConfig
from agenttrace.schemas import (
    AttributionTier,
    ClockAnchor,
    EnvironmentRecord,
    RecordType,
    RunStartRecord,
    SpanEndRecord,
    SpanStartRecord,
    SpanStatus,
)


def test_package_metadata() -> None:
    """Verify package version and import sanity."""
    assert agenttrace.__version__ == "0.1.0"


def test_cli_parser_creation() -> None:
    """Verify CLI parser configuration and command structure."""
    parser = create_parser()
    args = parser.parse_args(["run", "--config", "configs/default.toml"])
    assert args.command == "run"
    assert args.config == Path("configs/default.toml")


def test_config_models_defaults() -> None:
    """Verify configuration model defaults and nesting."""
    config = RunConfig(experiment_name="smoke_test")
    assert config.experiment_name == "smoke_test"
    assert isinstance(config.tracer, TracerConfig)
    assert config.tracer.enabled is True
    assert isinstance(config.workload, WorkloadConfig)
    assert config.workload.concurrency_limit == 4


def test_config_from_toml() -> None:
    """Verify loading and parsing configuration from TOML file."""
    config = RunConfig.from_toml("configs/default.toml")
    assert config.experiment_name == "baseline_smoke"
    assert config.tracer.buffer_size == 10000
    assert config.sampler.interval_ms == 50.0
    assert config.workload.workload_type == "sequential"
    assert config.workload.num_tasks == 10


def test_schema_roundtrip() -> None:
    """Verify Pydantic schemas serialize and deserialize without loss."""
    run_start = RunStartRecord(
        timestamp_utc_iso="2026-10-26T18:00:00Z",
        timestamp_monotonic_ns=100_000_000,
        run_id="run_smoke_001",
        experiment_name="smoke_test",
        config_hash="sha256:abc123",
        environment=EnvironmentRecord(
            os="Linux",
            os_release="6.6.87.2-microsoft-standard-WSL2",
            architecture="x86_64",
            python_version="3.12.3",
            cpu_count_logical=16,
            cpu_count_physical=8,
            total_memory_bytes=16_000_000_000,
        ),
        clock_anchor=ClockAnchor(
            utc_iso="2026-10-26T18:00:00Z",
            monotonic_ns=100_000_000,
            perf_counter_ns=100_000_000,
        ),
    )

    json_str = run_start.model_dump_json()
    reconstructed = RunStartRecord.model_validate_json(json_str)
    assert reconstructed.run_id == "run_smoke_001"
    assert reconstructed.record_type == RecordType.RUN_START

    span_start = SpanStartRecord(
        timestamp_utc_iso="2026-10-26T18:00:01Z",
        timestamp_monotonic_ns=105_000_000,
        trace_id="trace_001",
        span_id="span_001",
        task_id="task_001",
        agent_id="agent_alpha",
        operation_name="mock_tool_exec",
        operation_type="tool",
        process_id=1234,
        thread_id=5678,
        depends_on=["span_000"],
    )
    span_json = span_start.model_dump_json()
    reconstructed_span = SpanStartRecord.model_validate_json(span_json)
    assert reconstructed_span.span_id == "span_001"
    assert reconstructed_span.depends_on == ["span_000"]

    span_end = SpanEndRecord(
        timestamp_utc_iso="2026-10-26T18:00:02Z",
        timestamp_monotonic_ns=115_000_000,
        trace_id="trace_001",
        span_id="span_001",
        start_monotonic_ns=105_000_000,
        duration_ms=10.0,
        status=SpanStatus.OK,
    )
    assert span_end.status == SpanStatus.OK
    assert span_end.duration_ms == 10.0
    assert AttributionTier.TIER_1_EXCLUSIVE.value == "tier_1_exclusive"
