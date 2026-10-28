"""Sweep-line interval algorithm for exact instantaneous and maximum concurrency."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ConcurrencyInterval:
    """An interval of time during which concurrency level remains constant."""

    start_monotonic_ns: int
    end_monotonic_ns: int
    concurrency_level: int
    active_span_ids: tuple[str, ...]

    @property
    def duration_ns(self) -> int:
        return self.end_monotonic_ns - self.start_monotonic_ns

    @property
    def duration_ms(self) -> float:
        return self.duration_ns / 1_000_000.0


@dataclass
class ConcurrencyProfile:
    """Summary and temporal profile of concurrency over a trace."""

    max_concurrency: int
    mean_concurrency: float
    makespan_ns: int
    total_span_duration_ns: int
    intervals: list[ConcurrencyInterval] = field(default_factory=list)
    time_at_level_ms: dict[int, float] = field(default_factory=dict)

    @property
    def makespan_ms(self) -> float:
        return self.makespan_ns / 1_000_000.0

    @property
    def total_span_duration_ms(self) -> float:
        return self.total_span_duration_ns / 1_000_000.0


def compute_concurrency_profile(spans: list[dict[str, Any]]) -> ConcurrencyProfile:
    """Compute exact concurrency profile across a set of spans using a sweep-line algorithm.

    Each span dict is expected to contain:
      - 'span_id': str
      - 'start_monotonic_ns': int (or 'start_ns')
      - 'end_monotonic_ns': int (or 'end_ns')

    Interval semantics:
      Spans are treated as half-open intervals [start, end).
      When an end and a start coincide at the exact same nanosecond, the end occurs
      first so that sequential hand-offs [t1, t2) and [t2, t3) do not falsely count as
      concurrency 2.
    """
    valid_spans: list[tuple[str, int, int]] = []
    total_span_duration = 0

    for s in spans:
        span_id = str(s.get("span_id", ""))
        start_ns = (
            s.get("start_monotonic_ns")
            if s.get("start_monotonic_ns") is not None
            else s.get("start_ns")
        )
        end_ns = (
            s.get("end_monotonic_ns") if s.get("end_monotonic_ns") is not None else s.get("end_ns")
        )

        if start_ns is not None and end_ns is not None:
            start_val = int(start_ns)
            end_val = int(end_ns)
            if end_val >= start_val:
                valid_spans.append((span_id, start_val, end_val))
                total_span_duration += end_val - start_val

    if not valid_spans:
        return ConcurrencyProfile(
            max_concurrency=0,
            mean_concurrency=0.0,
            makespan_ns=0,
            total_span_duration_ns=0,
            intervals=[],
            time_at_level_ms={},
        )

    # Global trace envelope
    min_start_ns = min(s[1] for s in valid_spans)
    max_end_ns = max(s[2] for s in valid_spans)
    makespan_ns = max_end_ns - min_start_ns

    # Sweep-line events:
    # Event format: (timestamp_ns, event_type, span_id)
    # event_type: -1 for end event, +1 for start event.
    # Sorting order ensures -1 comes before +1 when timestamps are identical.
    events: list[tuple[int, int, str]] = []
    for s_id, start_ns, end_ns in valid_spans:
        events.append((start_ns, 1, s_id))
        events.append((end_ns, -1, s_id))

    # Sort events by timestamp ascending; if equal, -1 before +1
    events.sort(key=lambda e: (e[0], e[1]))

    intervals: list[ConcurrencyInterval] = []
    time_at_level_ns: dict[int, int] = {}
    current_active_spans: set[str] = set()
    max_concurrency = 0

    prev_time_ns = events[0][0]

    # Process events in groups of identical timestamp
    i = 0
    n = len(events)
    while i < n:
        curr_time_ns = events[i][0]

        # Record interval between previous event time and current event time if time elapsed
        if curr_time_ns > prev_time_ns:
            level = len(current_active_spans)
            duration_ns = curr_time_ns - prev_time_ns
            intervals.append(
                ConcurrencyInterval(
                    start_monotonic_ns=prev_time_ns,
                    end_monotonic_ns=curr_time_ns,
                    concurrency_level=level,
                    active_span_ids=tuple(sorted(current_active_spans)),
                )
            )
            time_at_level_ns[level] = time_at_level_ns.get(level, 0) + duration_ns
            prev_time_ns = curr_time_ns

        # Apply all events at this exact timestamp
        while i < n and events[i][0] == curr_time_ns:
            _, event_type, s_id = events[i]
            if event_type == 1:
                current_active_spans.add(s_id)
            else:
                current_active_spans.discard(s_id)
            i += 1

        level = len(current_active_spans)
        if level > max_concurrency:
            max_concurrency = level

    # Calculate time-weighted mean concurrency:
    # integral(C(t) dt) / makespan
    # Note that mathematically, integral(C(t) dt) across all spans equals sum(duration_i)
    mean_concurrency = (
        (total_span_duration / makespan_ns) if makespan_ns > 0 else float(max_concurrency)
    )

    time_at_level_ms = {
        level: ns_val / 1_000_000.0 for level, ns_val in sorted(time_at_level_ns.items())
    }

    return ConcurrencyProfile(
        max_concurrency=max_concurrency,
        mean_concurrency=mean_concurrency,
        makespan_ns=makespan_ns,
        total_span_duration_ns=total_span_duration,
        intervals=intervals,
        time_at_level_ms=time_at_level_ms,
    )
