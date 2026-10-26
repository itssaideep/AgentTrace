"""Offline validation for append-only AgentTrace JSONL files."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from math import isclose
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agenttrace.schemas import (
    BaseRecord,
    RecordType,
    ResourceSampleRecord,
    RunEndRecord,
    RunStartRecord,
    SpanEndRecord,
    SpanEventRecord,
    SpanStartRecord,
)

RECORD_MODELS: dict[RecordType, type[BaseRecord]] = {
    RecordType.RUN_START: RunStartRecord,
    RecordType.SPAN_START: SpanStartRecord,
    RecordType.SPAN_END: SpanEndRecord,
    RecordType.SPAN_EVENT: SpanEventRecord,
    RecordType.RESOURCE_SAMPLE: ResourceSampleRecord,
    RecordType.RUN_END: RunEndRecord,
}


@dataclass(frozen=True)
class ValidationIssue:
    """A single actionable problem found in a trace file."""

    line_number: int
    message: str

    def __str__(self) -> str:
        return f"line {self.line_number}: {self.message}"


@dataclass
class ValidationResult:
    """Validation outcome and summary statistics for one trace file."""

    path: Path
    records_seen: int = 0
    records_validated: int = 0
    record_counts: Counter[str] = field(default_factory=Counter)
    issues: list[ValidationIssue] = field(default_factory=list)
    total_spans_started: int = 0
    total_spans_completed: int = 0

    @property
    def valid(self) -> bool:
        """Whether the trace passed schema and lifecycle validation."""

        return not self.issues

    @property
    def completeness_percentage(self) -> float:
        """Percentage of unique started spans with a matching end record."""

        if self.total_spans_started == 0:
            return 100.0 if self.valid else 0.0
        return 100.0 * self.total_spans_completed / self.total_spans_started


def _schema_error_message(error: ValidationError) -> str:
    """Render the first Pydantic error without dumping the whole payload."""

    first_error = error.errors()[0]
    location = ".".join(str(part) for part in first_error.get("loc", ()))
    message = str(first_error.get("msg", "invalid value"))
    return f"schema validation failed at {location or '<record>'}: {message}"


def _record_type(payload: dict[str, Any]) -> RecordType | None:
    """Convert a JSON record discriminator to the typed enum."""

    value = payload.get("record_type")
    if not isinstance(value, str):
        return None
    try:
        return RecordType(value)
    except ValueError:
        return None


def validate_trace(path: Path | str) -> ValidationResult:
    """Validate JSONL schemas and span lifecycle consistency.

    A valid trace contains exactly one ``run_start`` and ``run_end``, schema-
    valid records, and one matching ``span_end`` for every unique
    ``span_start``. The function never raises for malformed trace content;
    issues are returned with their source line numbers. File I/O errors are
    allowed to propagate to the CLI, where they become a user-facing error.
    """

    trace_path = Path(path)
    result = ValidationResult(path=trace_path)
    starts: dict[str, tuple[int, SpanStartRecord]] = {}
    ends: dict[str, tuple[int, SpanEndRecord]] = {}
    events: list[tuple[int, SpanEventRecord]] = []
    run_records: list[tuple[int, str]] = []
    run_start_lines: list[int] = []
    run_end_lines: list[int] = []

    with trace_path.open("r", encoding="utf-8") as trace_file:
        for line_number, line in enumerate(trace_file, start=1):
            if not line.strip():
                continue
            result.records_seen += 1

            try:
                payload = json.loads(line)
            except json.JSONDecodeError as error:
                result.issues.append(
                    ValidationIssue(line_number, f"invalid JSON: {error.msg}")
                )
                continue
            if not isinstance(payload, dict):
                result.issues.append(
                    ValidationIssue(line_number, "record must be a JSON object")
                )
                continue

            record_type = _record_type(payload)
            if record_type is None:
                result.issues.append(
                    ValidationIssue(
                        line_number,
                        f"unknown record_type: {payload.get('record_type')!r}",
                    )
                )
                continue
            result.record_counts[record_type.value] += 1

            model = RECORD_MODELS[record_type]
            try:
                record = model.model_validate(payload)
            except ValidationError as error:
                result.issues.append(
                    ValidationIssue(line_number, _schema_error_message(error))
                )
                continue
            result.records_validated += 1

            if isinstance(record, RunStartRecord):
                run_start_lines.append(line_number)
                run_records.append((line_number, record.run_id))
            elif isinstance(record, RunEndRecord):
                run_end_lines.append(line_number)
                run_records.append((line_number, record.run_id))
            elif isinstance(record, ResourceSampleRecord):
                run_records.append((line_number, record.run_id))
            elif isinstance(record, SpanStartRecord):
                if record.span_id in starts:
                    result.issues.append(
                        ValidationIssue(
                            line_number,
                            f"duplicate span_start for span_id {record.span_id!r}",
                        )
                    )
                else:
                    starts[record.span_id] = (line_number, record)
            elif isinstance(record, SpanEndRecord):
                if record.span_id in ends:
                    result.issues.append(
                        ValidationIssue(
                            line_number,
                            f"duplicate span_end for span_id {record.span_id!r}",
                        )
                    )
                else:
                    ends[record.span_id] = (line_number, record)
            elif isinstance(record, SpanEventRecord):
                events.append((line_number, record))

    if len(run_start_lines) != 1:
        result.issues.append(
            ValidationIssue(
                run_start_lines[0] if run_start_lines else 0,
                f"expected exactly one run_start, found {len(run_start_lines)}",
            )
        )
    if len(run_end_lines) != 1:
        result.issues.append(
            ValidationIssue(
                run_end_lines[0] if run_end_lines else 0,
                f"expected exactly one run_end, found {len(run_end_lines)}",
            )
        )
    if len(run_start_lines) == 1 and len(run_end_lines) == 1:
        if run_end_lines[0] < run_start_lines[0]:
            result.issues.append(
                ValidationIssue(run_end_lines[0], "run_end appears before run_start")
            )

    run_ids = {run_id for _, run_id in run_records}
    if len(run_ids) > 1:
        result.issues.append(
            ValidationIssue(0, f"records contain multiple run_id values: {sorted(run_ids)}")
        )

    result.total_spans_started = len(starts)
    result.total_spans_completed = len(starts.keys() & ends.keys())

    for span_id, (line_number, start) in starts.items():
        if span_id not in ends:
            result.issues.append(
                ValidationIssue(line_number, f"span {span_id!r} has no matching span_end")
            )
            continue

        end_line, end = ends[span_id]
        if end.trace_id != start.trace_id:
            result.issues.append(
                ValidationIssue(
                    end_line,
                    f"span {span_id!r} has mismatched trace_id between start and end",
                )
            )
        if end.start_monotonic_ns != start.timestamp_monotonic_ns:
            result.issues.append(
                ValidationIssue(
                    end_line,
                    f"span {span_id!r} span_end.start_monotonic_ns does not match span_start",
                )
            )
        if end.timestamp_monotonic_ns < start.timestamp_monotonic_ns:
            result.issues.append(
                ValidationIssue(end_line, f"span {span_id!r} ends before it starts")
            )
        expected_duration_ms = (
            end.timestamp_monotonic_ns - start.timestamp_monotonic_ns
        ) / 1_000_000
        if not isclose(end.duration_ms, expected_duration_ms, rel_tol=1e-9, abs_tol=0.001):
            result.issues.append(
                ValidationIssue(
                    end_line,
                    f"span {span_id!r} duration_ms does not match monotonic timestamps",
                )
            )

    for span_id, (line_number, _) in ends.items():
        if span_id not in starts:
            result.issues.append(
                ValidationIssue(line_number, f"span_end has no matching span_start for {span_id!r}")
            )

    for line_number, event in events:
        if event.span_id not in starts:
            result.issues.append(
                ValidationIssue(
                    line_number,
                    f"span_event references unknown span_id {event.span_id!r}",
                )
            )

    return result
