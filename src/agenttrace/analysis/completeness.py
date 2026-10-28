"""Trace stream completeness checker and causal validation engine.

Ensures zero silent data loss, audits paired span_start and span_end records,
verifies causal parent-child/depends_on DAG references, and flags incomplete spans.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agenttrace.schemas import RecordType, SpanStatus


@dataclass
class CompletenessReport:
    """Detailed audit report produced from inspecting a raw trace stream."""

    total_records: int = 0
    total_spans_started: int = 0
    total_spans_ended: int = 0
    completed_spans: int = 0
    incomplete_span_ids: list[str] = field(default_factory=list)
    orphan_span_ids: list[str] = field(default_factory=list)
    missing_dependency_ids: list[str] = field(default_factory=list)
    clock_anomalies: list[str] = field(default_factory=list)
    status_breakdown: dict[str, int] = field(default_factory=dict)
    completeness_percentage: float = 0.0
    is_valid: bool = False

    def summary(self) -> str:
        """Return formatted human-readable summary."""
        return (
            f"Trace Completeness: {self.completeness_percentage:.2f}% "
            f"({self.completed_spans}/{self.total_spans_started} spans closed)\n"
            f"Incomplete: {len(self.incomplete_span_ids)}, "
            f"Orphans: {len(self.orphan_span_ids)}, "
            f"Missing Deps: {len(self.missing_dependency_ids)}, "
            f"Clock Anomalies: {len(self.clock_anomalies)}\n"
            f"Status Counts: {self.status_breakdown}"
        )


class TraceCompletenessChecker:
    """Audits raw JSONL trace files for lifecycle completeness and causal validity."""

    def __init__(self, trace_file: Path | str) -> None:
        self.trace_file = Path(trace_file)

    def check(self) -> CompletenessReport:
        """Parse trace file and verify every started span is closed without causal breakage."""
        if not self.trace_file.exists():
            raise FileNotFoundError(f"Trace file does not exist: {self.trace_file}")

        starts: dict[str, dict[str, Any]] = {}
        ends: dict[str, dict[str, Any]] = {}
        status_counts: dict[str, int] = {}
        clock_anomalies: list[str] = []
        total_records = 0

        with open(self.trace_file, encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line_str = line.strip()
                if not line_str:
                    continue

                total_records += 1
                try:
                    data = json.loads(line_str)
                except json.JSONDecodeError as e:
                    clock_anomalies.append(f"Line {line_no}: JSON parse error: {e}")
                    continue

                record_type = data.get("record_type")
                span_id = data.get("span_id")

                if record_type == RecordType.SPAN_START.value:
                    starts[span_id] = data
                elif record_type == RecordType.SPAN_END.value:
                    ends[span_id] = data
                    status = data.get("status", SpanStatus.OK.value)
                    status_counts[status] = status_counts.get(status, 0) + 1

                    # Monotonic clock duration validation
                    start_ns = data.get("start_monotonic_ns")
                    end_ns = data.get("timestamp_monotonic_ns")
                    duration_ms = data.get("duration_ms", 0.0)

                    if start_ns is not None and end_ns is not None:
                        if end_ns < start_ns:
                            clock_anomalies.append(
                                f"Span {span_id}: end monotonic ns ({end_ns}) < "
                                f"start monotonic ns ({start_ns})"
                            )
                        computed_ms = (end_ns - start_ns) / 1_000_000.0
                        if abs(computed_ms - duration_ms) > 0.001:
                            clock_anomalies.append(
                                f"Span {span_id}: duration_ms mismatch "
                                f"(recorded={duration_ms}, computed={computed_ms})"
                            )

        # Completeness audit
        incomplete_spans: list[str] = []
        for span_id in starts:
            if span_id not in ends:
                incomplete_spans.append(span_id)

        # Causal DAG dependency audit
        orphan_spans: list[str] = []
        missing_dependencies: list[str] = []

        for span_id, start_rec in starts.items():
            parent_id = start_rec.get("parent_span_id")
            if parent_id and parent_id not in starts:
                orphan_spans.append(
                    f"Span {span_id} references non-existent parent {parent_id}"
                )

            depends_on = start_rec.get("depends_on", [])
            for dep_id in depends_on:
                if dep_id not in starts:
                    missing_dependencies.append(
                        f"Span {span_id} depends on non-existent span {dep_id}"
                    )

        total_started = len(starts)
        total_ended = len(ends)
        completed = total_started - len(incomplete_spans)
        pct = (completed / total_started * 100.0) if total_started > 0 else 100.0
        is_valid = (
            len(incomplete_spans) == 0
            and len(orphan_spans) == 0
            and len(missing_dependencies) == 0
            and len(clock_anomalies) == 0
        )

        return CompletenessReport(
            total_records=total_records,
            total_spans_started=total_started,
            total_spans_ended=total_ended,
            completed_spans=completed,
            incomplete_span_ids=incomplete_spans,
            orphan_span_ids=orphan_spans,
            missing_dependency_ids=missing_dependencies,
            clock_anomalies=clock_anomalies,
            status_breakdown=status_counts,
            completeness_percentage=pct,
            is_valid=is_valid,
        )
