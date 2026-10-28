"""Unit tests for Clock protocols, MonotonicClock, and deterministic FakeClock."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agenttrace.instrumentation.clock import FakeClock, MonotonicClock


def test_monotonic_clock_basic() -> None:
    """Verify MonotonicClock returns strictly non-decreasing nanoseconds."""
    clock = MonotonicClock()
    t1 = clock.monotonic_ns()
    t2 = clock.monotonic_ns()
    assert t1 > 0
    assert t2 >= t1

    iso_str = clock.utc_iso()
    dt = datetime.fromisoformat(iso_str)
    assert dt.tzinfo is not None


def test_fake_clock_determinism() -> None:
    """Verify FakeClock advances accurately without sleep delays."""
    start_time = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
    clock = FakeClock(start_monotonic_ns=1_000_000_000, start_utc=start_time)

    assert clock.monotonic_ns() == 1_000_000_000
    assert clock.utc_iso() == "2026-10-28T12:00:00+00:00"

    # Advance by 50 ms
    clock.advance_ms(50.0)
    assert clock.monotonic_ns() == 1_050_000_000
    assert clock.utc_iso() == "2026-10-28T12:00:00.050000+00:00"

    # Synchronous sleep advances time without real wait
    clock.sleep(0.1)  # 100 ms
    assert clock.monotonic_ns() == 1_150_000_000
    assert clock.utc_iso() == "2026-10-28T12:00:00.150000+00:00"


@pytest.mark.asyncio
async def test_fake_clock_async_sleep() -> None:
    """Verify FakeClock async_sleep advances time."""
    clock = FakeClock(start_monotonic_ns=500_000_000)
    await clock.async_sleep(0.02)  # 20 ms
    assert clock.monotonic_ns() == 520_000_000


def test_fake_clock_negative_advance_rejected() -> None:
    """Verify monotonic invariants reject backward time jumps."""
    clock = FakeClock()
    with pytest.raises(ValueError, match="cannot move backward"):
        clock.advance_ns(-100)

    with pytest.raises(ValueError, match="cannot move backward"):
        clock.advance_ms(-5.0)

    with pytest.raises(ValueError, match="cannot be negative"):
        clock.sleep(-1.0)
