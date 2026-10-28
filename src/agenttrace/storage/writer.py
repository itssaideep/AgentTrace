"""Append-only buffered JSON Lines stream writer for AgentTrace.

Ensures high-throughput disk writes, crash-resilience, and thread-safe event buffering.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class TraceWriter:
    """Thread-safe, append-only buffered JSONL stream writer."""

    def __init__(
        self,
        output_path: Path | str,
        buffer_size: int = 1_000,
        auto_flush: bool = True,
    ) -> None:
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.buffer_size = max(1, buffer_size)
        self.auto_flush = auto_flush

        self._buffer: list[str] = []
        self._lock = threading.Lock()
        self._record_count: int = 0
        self._bytes_written: int = 0
        self._is_closed: bool = False

    @property
    def record_count(self) -> int:
        """Total number of records accepted by the writer."""
        with self._lock:
            return self._record_count

    @property
    def bytes_written(self) -> int:
        """Total bytes committed to disk."""
        with self._lock:
            return self._bytes_written

    @property
    def is_closed(self) -> bool:
        """Whether the writer has been closed."""
        with self._lock:
            return self._is_closed

    def write_record(self, record: BaseModel | dict[str, Any]) -> None:
        """Serialize and buffer an event record.

        Flushes to disk if buffer capacity is reached.
        """
        if isinstance(record, BaseModel):
            line = record.model_dump_json() + "\n"
        elif isinstance(record, dict):
            line = json.dumps(record, separators=(",", ":")) + "\n"
        else:
            raise TypeError(f"Unsupported record type: {type(record)}")

        with self._lock:
            if self._is_closed:
                raise RuntimeError("Cannot write to closed TraceWriter")

            self._buffer.append(line)
            self._record_count += 1

            if self.auto_flush and len(self._buffer) >= self.buffer_size:
                self._flush_unlocked()

    def flush(self) -> None:
        """Synchronously commit all buffered records to disk."""
        with self._lock:
            if not self._is_closed:
                self._flush_unlocked()

    def _flush_unlocked(self) -> None:
        """Internal flush without acquiring lock (caller must hold self._lock)."""
        if not self._buffer:
            return

        payload = "".join(self._buffer)
        with open(self.output_path, "a", encoding="utf-8") as f:
            f.write(payload)
            f.flush()

        self._bytes_written += len(payload.encode("utf-8"))
        self._buffer.clear()

    def close(self) -> None:
        """Flush remaining buffer and close the writer."""
        with self._lock:
            if not self._is_closed:
                self._flush_unlocked()
                self._is_closed = True

    def __enter__(self) -> TraceWriter:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
