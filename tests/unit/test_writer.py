"""Unit tests for append-only JSONL TraceWriter and buffering behavior."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agenttrace.storage.writer import TraceWriter


def test_writer_buffering_and_explicit_flush(tmp_path: Path) -> None:
    """Verify TraceWriter holds events in memory until flushed or buffer is full."""
    trace_path = tmp_path / "test_trace.jsonl"
    writer = TraceWriter(output_path=trace_path, buffer_size=10, auto_flush=True)

    # Write 5 records (< buffer_size 10)
    for i in range(5):
        writer.write_record({"record_id": i, "name": f"event_{i}"})

    assert writer.record_count == 5
    # File should not exist or be empty yet
    if trace_path.exists():
        assert trace_path.stat().st_size == 0

    # Explicit flush
    writer.flush()
    assert trace_path.exists()
    assert trace_path.stat().st_size > 0
    assert writer.bytes_written > 0

    lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 5
    assert json.loads(lines[0])["record_id"] == 0

    writer.close()
    assert writer.is_closed


def test_writer_automatic_flush_on_capacity(tmp_path: Path) -> None:
    """Verify TraceWriter automatically flushes when buffer_size is exceeded."""
    trace_path = tmp_path / "test_auto_flush.jsonl"
    with TraceWriter(output_path=trace_path, buffer_size=3, auto_flush=True) as writer:
        writer.write_record({"id": 1})
        writer.write_record({"id": 2})
        # Not flushed yet
        assert trace_path.stat().st_size == 0 if trace_path.exists() else True

        # 3rd record triggers buffer flush
        writer.write_record({"id": 3})
        assert trace_path.exists()
        lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3

    assert writer.is_closed


def test_writer_thread_safety(tmp_path: Path) -> None:
    """Verify TraceWriter handles concurrent writes from multiple threads safely."""
    trace_path = tmp_path / "test_threaded.jsonl"
    num_threads = 8
    records_per_thread = 50
    total_records = num_threads * records_per_thread

    with TraceWriter(output_path=trace_path, buffer_size=20, auto_flush=True) as writer:

        def worker(thread_idx: int) -> None:
            for i in range(records_per_thread):
                writer.write_record({"thread": thread_idx, "idx": i})

        with ThreadPoolExecutor(max_workers=num_threads) as pool:
            futures = [pool.submit(worker, t) for t in range(num_threads)]
            for f in futures:
                f.result()

    assert writer.record_count == total_records
    lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == total_records


def test_writer_rejects_writes_after_close(tmp_path: Path) -> None:
    """Verify attempting to write to a closed writer raises RuntimeError."""
    trace_path = tmp_path / "test_closed.jsonl"
    writer = TraceWriter(output_path=trace_path)
    writer.close()

    with pytest.raises(RuntimeError, match="Cannot write to closed"):
        writer.write_record({"event": "fail"})
