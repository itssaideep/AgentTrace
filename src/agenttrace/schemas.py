"""Trace data model and schema definitions for AgentTrace records."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0.0"


class SpanStatus(StrEnum):
    """Execution status of a traced span."""

    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    INCOMPLETE = "incomplete"


class AttributionTier(StrEnum):
    """Resource attribution confidence and methodology tier (D5)."""

    TIER_0_CONTEXT = "tier_0_context"       # Overlapping window, no attribution claimed
    TIER_1_EXCLUSIVE = "tier_1_exclusive"   # Single active span in process, counter delta bounded
    TIER_2_DIRECT = "tier_2_direct"         # Dedicated worker thread/process boundary counters
    TIER_3_AGGREGATE = "tier_3_aggregate"   # Concurrent overlapping spans, reported unsplit


class RecordType(StrEnum):
    """Family of the trace record."""

    RUN_START = "run_start"
    SPAN_START = "span_start"
    SPAN_END = "span_end"
    SPAN_EVENT = "span_event"
    RESOURCE_SAMPLE = "resource_sample"
    RUN_END = "run_end"


class BaseRecord(BaseModel):
    """Base model for all versioned JSONL event records."""

    schema_version: str = Field(default=SCHEMA_VERSION)
    record_type: RecordType
    timestamp_utc_iso: str
    timestamp_monotonic_ns: int


class ClockAnchor(BaseModel):
    """Initial clock pairing anchor at run inception."""

    utc_iso: str
    monotonic_ns: int
    perf_counter_ns: int


class EnvironmentRecord(BaseModel):
    """Host environment snapshot for run reproducibility."""

    os: str
    os_release: str
    architecture: str
    python_version: str
    cpu_count_logical: int
    cpu_count_physical: int | None
    total_memory_bytes: int
    git_commit_hash: str | None = None
    git_dirty: bool | None = None
    wsl_detected: bool = False


class RunStartRecord(BaseRecord):
    """Emitted at the initiation of an experiment run."""

    record_type: RecordType = RecordType.RUN_START
    run_id: str
    experiment_name: str
    config_hash: str
    environment: EnvironmentRecord
    clock_anchor: ClockAnchor


class SpanStartRecord(BaseRecord):
    """Emitted when a span begins execution."""

    record_type: RecordType = RecordType.SPAN_START
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    task_id: str
    agent_id: str
    operation_name: str
    operation_type: str
    process_id: int
    thread_id: int
    depends_on: list[str] = Field(default_factory=list)
    attempt: int = 1
    retry_of: str | None = None
    queue_wait_ms: float = 0.0
    attributes: dict[str, Any] = Field(default_factory=dict)


class SpanEndRecord(BaseRecord):
    """Emitted when a span finishes or is terminated."""

    record_type: RecordType = RecordType.SPAN_END
    trace_id: str
    span_id: str
    start_monotonic_ns: int
    duration_ms: float
    status: SpanStatus
    error_type: str | None = None
    error_message: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class SpanEventRecord(BaseRecord):
    """Emitted for ad-hoc intra-span events (retry attempts, warnings, checkpoints)."""

    record_type: RecordType = RecordType.SPAN_EVENT
    trace_id: str
    span_id: str
    event_name: str
    event_payload: dict[str, Any] = Field(default_factory=dict)


class ProcessResourceMetrics(BaseModel):
    """Process-level resource metrics (current process and optionally tree)."""

    process_id: int
    cpu_user_time_s: float
    cpu_system_time_s: float
    rss_bytes: int
    vms_bytes: int
    ctx_switches_voluntary: int
    ctx_switches_involuntary: int
    io_read_bytes: int | None = None
    io_write_bytes: int | None = None


class SystemResourceMetrics(BaseModel):
    """System-wide resource metrics."""

    cpu_utilization_percent: float
    system_cpu_user_s: float
    system_cpu_system_s: float
    system_cpu_idle_s: float
    system_memory_used_bytes: int
    system_memory_total_bytes: int
    system_net_bytes_sent: int
    system_net_bytes_recv: int


class ResourceSampleRecord(BaseRecord):
    """Periodic resource sample capturing process and system metrics."""

    record_type: RecordType = RecordType.RESOURCE_SAMPLE
    run_id: str
    sample_index: int
    sample_duration_us: float  # Sampler probe execution time (observer effect tracking)
    process_metrics: list[ProcessResourceMetrics]
    system_metrics: SystemResourceMetrics | None = None


class RunSummary(BaseModel):
    """Derived run summary generated after run execution."""

    run_id: str
    experiment_name: str
    total_duration_ms: float
    total_spans_started: int
    total_spans_completed: int
    status_counts: dict[str, int]
    max_observed_concurrency: int
    mean_observed_concurrency: float
    completeness_percentage: float
    peak_rss_bytes: int
    total_process_cpu_time_s: float


class RunEndRecord(BaseRecord):
    """Emitted when an experiment run finishes.

    The summary is optional so interrupted runs can still be represented and
    diagnosed by the offline validator.
    """

    record_type: RecordType = RecordType.RUN_END
    run_id: str
    summary: RunSummary | None = None
