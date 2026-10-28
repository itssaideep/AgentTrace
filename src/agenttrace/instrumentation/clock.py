"""Clock abstraction and monotonic time provider for AgentTrace.

Enforces nanosecond monotonic clocks for duration measurement and provides
deterministic fake clocks for testing without sleeping.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Protocol for time providers ensuring monotonic nanosecond durations."""

    def monotonic_ns(self) -> int:
        """Return monotonic time in nanoseconds."""
        ...

    def utc_iso(self) -> str:
        """Return current UTC wall-clock time as an ISO 8601 string."""
        ...

    def sleep(self, duration_s: float) -> None:
        """Synchronously pause execution or advance simulation time."""
        ...

    async def async_sleep(self, duration_s: float) -> None:
        """Asynchronously pause execution or advance simulation time."""
        ...


class MonotonicClock:
    """Production clock backed by host OS monotonic nanoseconds."""

    def monotonic_ns(self) -> int:
        """Return host OS monotonic nanoseconds."""
        return time.monotonic_ns()

    def utc_iso(self) -> str:
        """Return current UTC wall-clock timestamp."""
        return datetime.now(UTC).isoformat()

    def sleep(self, duration_s: float) -> None:
        """Sleep using system time."""
        time.sleep(duration_s)

    async def async_sleep(self, duration_s: float) -> None:
        """Sleep using asyncio event loop."""
        await asyncio.sleep(duration_s)


class FakeClock:
    """Deterministic, controllable clock for unit and property-based testing."""

    def __init__(
        self,
        start_monotonic_ns: int = 1_000_000_000,
        start_utc: datetime | None = None,
    ) -> None:
        self._current_monotonic_ns: int = start_monotonic_ns
        self._start_monotonic_ns: int = start_monotonic_ns
        self._start_utc: datetime = start_utc or datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)

    def monotonic_ns(self) -> int:
        """Return current simulated monotonic nanoseconds."""
        return self._current_monotonic_ns

    def utc_iso(self) -> str:
        """Derive current simulated UTC timestamp."""
        elapsed_ns = self._current_monotonic_ns - self._start_monotonic_ns
        current_time = self._start_utc + timedelta(microseconds=elapsed_ns // 1_000)
        return current_time.isoformat()

    def advance_ns(self, delta_ns: int) -> None:
        """Advance simulated time by nanoseconds."""
        if delta_ns < 0:
            raise ValueError("Monotonic clock cannot move backward in time")
        self._current_monotonic_ns += delta_ns

    def advance_ms(self, delta_ms: float) -> None:
        """Advance simulated time by milliseconds."""
        if delta_ms < 0:
            raise ValueError("Monotonic clock cannot move backward in time")
        self.advance_ns(int(delta_ms * 1_000_000))

    def sleep(self, duration_s: float) -> None:
        """Advance simulated time synchronously without blocking execution."""
        if duration_s < 0:
            raise ValueError("Sleep duration cannot be negative")
        self.advance_ns(int(duration_s * 1_000_000_000))

    async def async_sleep(self, duration_s: float) -> None:
        """Advance simulated time asynchronously and yield control to the loop."""
        self.sleep(duration_s)
        await asyncio.sleep(0)
