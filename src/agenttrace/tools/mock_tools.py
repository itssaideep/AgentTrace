"""Calibrated synthetic mock tools for CPU, I/O, latency, and fault injection."""

from __future__ import annotations

import hashlib
import os
import random
import time
from pathlib import Path

from agenttrace.instrumentation.clock import Clock, MonotonicClock


def execute_latency_tool(duration_ms: float, clock: Clock | None = None) -> float:
    """Simulate non-blocking latency delay."""
    effective_clock = clock or MonotonicClock()
    effective_clock.sleep(duration_ms / 1_000.0)
    return duration_ms


def execute_cpu_tool(compute_intensity: int = 100_000) -> int:
    """Burn real CPU user-mode cycles via calibrated hashing.

    Guaranteed to register on OS user CPU time counters without allocating large memory.
    """
    data = b"agenttrace_calibrated_cpu_kernel"
    h = hashlib.sha256(data)
    for _ in range(compute_intensity):
        h.update(data)
    # Return integer sum of digest to prevent dead-code elimination
    return sum(h.digest())


def execute_io_tool(
    target_dir: Path | str,
    io_bytes: int = 65_536,
    do_fsync: bool = True,
) -> int:
    """Execute synced file write and read inside a controlled directory.

    Enforces os.fsync() to bypass OS page cache and register on storage counters.
    """
    directory = Path(target_dir)
    directory.mkdir(parents=True, exist_ok=True)
    temp_file = directory / f"scratch_io_{time.monotonic_ns()}_{os.getpid()}.tmp"

    payload = b"X" * io_bytes
    try:
        # Write phase
        with open(temp_file, "wb") as f:
            f.write(payload)
            f.flush()
            if do_fsync:
                os.fsync(f.fileno())

        # Read phase
        with open(temp_file, "rb") as f:
            read_back = f.read()
            if len(read_back) != io_bytes:
                raise OSError(f"I/O tool read size mismatch: {len(read_back)} != {io_bytes}")

        return io_bytes
    finally:
        if temp_file.exists():
            temp_file.unlink()


def check_and_inject_fault(fail_probability: float, seed: int) -> None:
    """Deterministically trigger synthetic tool exceptions based on seed."""
    if fail_probability <= 0.0:
        return
    rng = random.Random(seed)
    if rng.random() < fail_probability:
        raise RuntimeError(
            f"Injected synthetic tool fault [fail_prob={fail_probability}, seed={seed}]"
        )
