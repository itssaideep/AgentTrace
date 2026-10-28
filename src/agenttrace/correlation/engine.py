"""Temporal join engine and tiered resource attribution (Tiers 0 - 3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agenttrace.schemas import AttributionTier, RecordType


@dataclass
class AttributedResourceMetrics:
    """Resource metrics correlated to a span duration with explicit attribution tier."""

    span_id: str
    task_id: str
    tier: AttributionTier
    confidence_label: str
    concurrent_span_ids: list[str] = field(default_factory=list)
    delta_cpu_user_s: float | None = None
    delta_cpu_system_s: float | None = None
    delta_rss_bytes: int | None = None
    delta_io_write_bytes: int | None = None
    overlapping_sample_count: int = 0


class CorrelationEngine:
    """Correlates execution trace spans with background resource samples.

    Enforces ADR D5: never subdivides process aggregates among concurrent spans.
    """

    def __init__(
        self,
        trace_records: list[dict[str, Any]],
        sample_records: list[dict[str, Any]],
    ) -> None:
        self.trace_records = trace_records
        self.sample_records = sample_records

    def correlate(self) -> list[AttributedResourceMetrics]:
        """Perform temporal join between spans and samples, assigning attribution tiers."""
        # Index spans by span_id
        starts: dict[str, dict[str, Any]] = {}
        ends: dict[str, dict[str, Any]] = {}

        for r in self.trace_records:
            rec_type = r.get("record_type")
            span_id = r.get("span_id")
            if rec_type == RecordType.SPAN_START.value and span_id:
                starts[span_id] = r
            elif rec_type == RecordType.SPAN_END.value and span_id:
                ends[span_id] = r

        # Build list of closed spans with interval [start_ns, end_ns]
        spans: list[dict[str, Any]] = []
        for span_id, start_rec in starts.items():
            if span_id in ends:
                end_rec = ends[span_id]
                start_ns = start_rec["timestamp_monotonic_ns"]
                end_ns = end_rec["timestamp_monotonic_ns"]
                spans.append(
                    {
                        "span_id": span_id,
                        "task_id": start_rec.get("task_id", ""),
                        "process_id": start_rec.get("process_id"),
                        "start_ns": start_ns,
                        "end_ns": end_ns,
                        "attributes": start_rec.get("attributes", {}),
                    }
                )

        # Sort samples by monotonic timestamp
        samples = sorted(
            [
                s
                for s in self.sample_records
                if s.get("record_type") == RecordType.RESOURCE_SAMPLE.value
            ],
            key=lambda x: x.get("timestamp_monotonic_ns", 0),
        )

        attributed_list: list[AttributedResourceMetrics] = []

        for span in spans:
            s_start = span["start_ns"]
            s_end = span["end_ns"]
            s_pid = span["process_id"]

            # 1. Identify all concurrent spans overlapping with this span in the same process
            concurrent = [
                other["span_id"]
                for other in spans
                if other["process_id"] == s_pid
                and not (other["end_ns"] <= s_start or other["start_ns"] >= s_end)
            ]

            # 2. Extract overlapping resource samples
            overlapping_samples = [
                s for s in samples if s_start <= s.get("timestamp_monotonic_ns", 0) <= s_end
            ]

            # Find nearest bounding samples for counter deltas
            sample_before = None
            sample_after = None
            for s in samples:
                t = s.get("timestamp_monotonic_ns", 0)
                if t <= s_start:
                    sample_before = s
                elif t >= s_end and sample_after is None:
                    sample_after = s
                    break

            # Calculate deltas if bounding samples exist
            delta_cpu_user = None
            delta_cpu_sys = None
            delta_rss = None
            delta_io_write = None

            if sample_before and sample_after:
                before_proc = self._extract_process_metrics(sample_before, s_pid)
                after_proc = self._extract_process_metrics(sample_after, s_pid)

                if before_proc and after_proc:
                    delta_cpu_user = round(
                        max(0.0, after_proc["cpu_user_time_s"] - before_proc["cpu_user_time_s"]), 4
                    )
                    diff_sys = after_proc["cpu_system_time_s"] - before_proc["cpu_system_time_s"]
                    delta_cpu_sys = round(max(0.0, diff_sys), 4)
                    delta_rss = after_proc["rss_bytes"] - before_proc["rss_bytes"]

                    io_after = after_proc.get("io_write_bytes")
                    io_before = before_proc.get("io_write_bytes")
                    if io_after is not None and io_before is not None:
                        delta_io_write = max(0, io_after - io_before)

            # 3. Assign Attribution Tier (ADR D5)
            # Check for Tier 2: dedicated worker process
            is_dedicated_worker = span["attributes"].get("dedicated_worker", False)

            conc_ids: list[str]
            if is_dedicated_worker:
                tier = AttributionTier.TIER_2_DIRECT
                confidence = "dedicated_worker_process_boundary"
                conc_ids = []
            elif len(concurrent) == 1:
                # Only this span was active in the process during its lifetime
                tier = AttributionTier.TIER_1_EXCLUSIVE
                confidence = "exclusive_process_window_bounded_by_sampling_interval"
                conc_ids = []
            else:
                # Concurrent overlapping spans: NEVER subdivide aggregate
                tier = AttributionTier.TIER_3_AGGREGATE
                confidence = "unsplit_concurrent_aggregate"
                conc_ids = concurrent

            attributed_list.append(
                AttributedResourceMetrics(
                    span_id=span["span_id"],
                    task_id=span["task_id"],
                    tier=tier,
                    confidence_label=confidence,
                    concurrent_span_ids=conc_ids,
                    delta_cpu_user_s=delta_cpu_user,
                    delta_cpu_system_s=delta_cpu_sys,
                    delta_rss_bytes=delta_rss,
                    delta_io_write_bytes=delta_io_write,
                    overlapping_sample_count=len(overlapping_samples),
                )
            )

        return attributed_list

    def _extract_process_metrics(
        self,
        sample: dict[str, Any],
        pid: int | None,
    ) -> dict[str, Any] | None:
        """Extract process metrics matching PID from sample record."""
        proc_list: list[dict[str, Any]] = sample.get("process_metrics", [])
        if not proc_list:
            return None
        if pid is None:
            return dict(proc_list[0])
        for p in proc_list:
            if p.get("process_id") == pid:
                return dict(p)
        return dict(proc_list[0])
