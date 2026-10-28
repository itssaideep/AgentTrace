"""Unit tests for background ResourceSampler and jitter telemetry."""

from __future__ import annotations

import json
import time
from pathlib import Path

from agenttrace.resources.sampler import ResourceSampler
from agenttrace.schemas import RecordType
from agenttrace.storage.writer import TraceWriter


def test_sampler_start_stop_and_metrics_capture(tmp_path: Path) -> None:
    """Verify ResourceSampler daemon thread captures periodic process metrics and stops cleanly."""
    trace_path = tmp_path / "sampler_trace.jsonl"

    with TraceWriter(output_path=trace_path, buffer_size=1, auto_flush=True) as writer:
        sampler = ResourceSampler(
            writer=writer,
            interval_ms=10.0,  # Fast 10ms sampling
            track_system=True,
            track_process_tree=False,
            run_id="run_test_sampler",
        )

        assert not sampler.is_running
        sampler.start()
        assert sampler.is_running

        # Let sampler run for ~50 ms
        time.sleep(0.06)

        sampler.stop()
        assert not sampler.is_running
        assert sampler.sample_count >= 2

    lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2

    sample_0 = json.loads(lines[0])
    assert sample_0["record_type"] == RecordType.RESOURCE_SAMPLE.value
    assert sample_0["run_id"] == "run_test_sampler"
    assert "sample_duration_us" in sample_0

    proc_metrics = sample_0["process_metrics"][0]
    assert proc_metrics["rss_bytes"] > 0
    assert proc_metrics["cpu_user_time_s"] >= 0.0

    system_metrics = sample_0["system_metrics"]
    assert system_metrics is not None
    assert system_metrics["system_memory_total_bytes"] > 0

    jitter_stats = sampler.get_jitter_stats()
    assert "mean_jitter_us" in jitter_stats
    assert "mean_probe_duration_us" in jitter_stats
