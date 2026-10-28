"""Unit tests for synthetic mock tool execution and deterministic fault injection."""

from __future__ import annotations

from pathlib import Path

import pytest

from agenttrace.instrumentation.clock import FakeClock
from agenttrace.tools.mock_tools import (
    check_and_inject_fault,
    execute_cpu_tool,
    execute_io_tool,
    execute_latency_tool,
)


def test_latency_tool_with_fake_clock() -> None:
    """Verify latency tool advances fake clock by specified duration."""
    clock = FakeClock()
    t_start = clock.monotonic_ns()
    res = execute_latency_tool(duration_ms=25.0, clock=clock)
    assert res == 25.0
    assert clock.monotonic_ns() - t_start == 25_000_000


def test_cpu_tool_execution() -> None:
    """Verify CPU tool computes non-zero digest without throwing."""
    res = execute_cpu_tool(compute_intensity=5_000)
    assert isinstance(res, int)
    assert res > 0


def test_io_tool_execution(tmp_path: Path) -> None:
    """Verify I/O tool writes and reads bytes with fsync and cleans up scratch file."""
    scratch_dir = tmp_path / "io_scratch"
    bytes_written = execute_io_tool(target_dir=scratch_dir, io_bytes=16_384, do_fsync=True)
    assert bytes_written == 16_384
    # Ensure temporary file was cleaned up
    remaining_files = list(scratch_dir.glob("*.tmp"))
    assert len(remaining_files) == 0


def test_fault_injection_determinism() -> None:
    """Verify fault injection triggers deterministically based on seed."""
    # 0.0 probability never raises
    check_and_inject_fault(fail_probability=0.0, seed=12345)

    # 1.0 probability always raises
    with pytest.raises(RuntimeError, match="Injected synthetic tool fault"):
        check_and_inject_fault(fail_probability=1.0, seed=12345)

    # Same seed and probability produces identical outcome
    seed = 777
    prob = 0.5
    raised_count = 0
    for _ in range(5):
        try:
            check_and_inject_fault(fail_probability=prob, seed=seed)
        except RuntimeError:
            raised_count += 1
    # Either all 5 raised or 0 raised (pure determinism)
    assert raised_count in (0, 5)
