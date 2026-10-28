"""High-frequency background resource sampler with jitter and probe overhead telemetry."""

from __future__ import annotations

import os
import threading
import time
from typing import Any

import psutil

from agenttrace.instrumentation.clock import Clock, MonotonicClock
from agenttrace.schemas import (
    SCHEMA_VERSION,
    ProcessResourceMetrics,
    RecordType,
    ResourceSampleRecord,
    SystemResourceMetrics,
)
from agenttrace.storage.writer import TraceWriter


class ResourceSampler:
    """Background daemon thread sampling process and system resource counters."""

    def __init__(
        self,
        writer: TraceWriter,
        interval_ms: float = 50.0,
        clock: Clock | None = None,
        track_system: bool = True,
        track_process_tree: bool = False,
        run_id: str = "run_default",
        validate_on_write: bool = False,
    ) -> None:
        self.writer = writer
        self.interval_ms = max(5.0, interval_ms)
        self.clock: Clock = clock or MonotonicClock()
        self.track_system = track_system
        self.track_process_tree = track_process_tree
        self.run_id = run_id
        self.validate_on_write = validate_on_write

        self._process = psutil.Process(os.getpid())
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._sample_index: int = 0
        self._jitter_samples_us: list[float] = []
        self._probe_durations_us: list[float] = []
        self._lock = threading.Lock()

    @property
    def sample_count(self) -> int:
        """Total number of periodic resource samples emitted."""
        with self._lock:
            return self._sample_index

    @property
    def is_running(self) -> bool:
        """Whether the sampler background thread is actively running."""
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Start the background resource sampling daemon thread."""
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_sampling_loop,
            name="agenttrace-resource-sampler",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout_s: float = 2.0) -> None:
        """Stop the background sampling thread and flush pending samples."""
        if not self.is_running or self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=timeout_s)
        self.writer.flush()

    def _sample_process(self, proc: psutil.Process) -> ProcessResourceMetrics:
        """Sample counters for a single process."""
        cpu = proc.cpu_times()
        mem = proc.memory_info()

        ctx_vol = 0
        ctx_invol = 0
        try:
            ctx = proc.num_ctx_switches()
            ctx_vol = ctx.voluntary
            ctx_invol = ctx.involuntary
        except (AttributeError, NotImplementedError):
            pass

        io_read = None
        io_write = None
        try:
            io = proc.io_counters()
            io_read = io.read_bytes
            io_write = io.write_bytes
        except (AttributeError, NotImplementedError):
            pass

        return ProcessResourceMetrics(
            process_id=proc.pid,
            cpu_user_time_s=round(cpu.user, 4),
            cpu_system_time_s=round(cpu.system, 4),
            rss_bytes=mem.rss,
            vms_bytes=mem.vms,
            ctx_switches_voluntary=ctx_vol,
            ctx_switches_involuntary=ctx_invol,
            io_read_bytes=io_read,
            io_write_bytes=io_write,
        )

    def _sample_system(self) -> SystemResourceMetrics | None:
        """Sample host system-wide resource counters."""
        if not self.track_system:
            return None

        cpu_percent = psutil.cpu_percent(interval=None)
        cpu_times = psutil.cpu_times()
        mem = psutil.virtual_memory()

        net_sent = 0
        net_recv = 0
        try:
            net = psutil.net_io_counters()
            if net:
                net_sent = net.bytes_sent
                net_recv = net.bytes_recv
        except (AttributeError, NotImplementedError):
            pass

        return SystemResourceMetrics(
            cpu_utilization_percent=cpu_percent,
            system_cpu_user_s=round(cpu_times.user, 2),
            system_cpu_system_s=round(cpu_times.system, 2),
            system_cpu_idle_s=round(cpu_times.idle, 2),
            system_memory_used_bytes=mem.used,
            system_memory_total_bytes=mem.total,
            system_net_bytes_sent=net_sent,
            system_net_bytes_recv=net_recv,
        )

    def _run_sampling_loop(self) -> None:
        """Main sampling loop tracking jitter and probe execution overhead."""
        target_tick_ns = self.clock.monotonic_ns()

        while not self._stop_event.is_set():
            t_probe_start = self.clock.monotonic_ns()

            # Measure sampling interval jitter
            jitter_us = (t_probe_start - target_tick_ns) / 1_000.0
            self._jitter_samples_us.append(jitter_us)

            # Sample process tree
            process_metrics: list[ProcessResourceMetrics] = []
            try:
                process_metrics.append(self._sample_process(self._process))
                if self.track_process_tree:
                    for child in self._process.children(recursive=True):
                        try:
                            process_metrics.append(self._sample_process(child))
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

            system_metrics = self._sample_system()

            t_probe_end = self.clock.monotonic_ns()
            probe_duration_us = (t_probe_end - t_probe_start) / 1_000.0
            self._probe_durations_us.append(probe_duration_us)

            with self._lock:
                idx = self._sample_index
                self._sample_index += 1

            utc_iso = self.clock.utc_iso()

            if self.validate_on_write:
                record = ResourceSampleRecord(
                    timestamp_utc_iso=utc_iso,
                    timestamp_monotonic_ns=t_probe_start,
                    run_id=self.run_id,
                    sample_index=idx,
                    sample_duration_us=round(probe_duration_us, 2),
                    process_metrics=process_metrics,
                    system_metrics=system_metrics,
                )
                self.writer.write_record(record)
            else:
                proc_dicts: list[dict[str, Any]] = [p.model_dump() for p in process_metrics]
                sys_dict = system_metrics.model_dump() if system_metrics else None

                record_dict = {
                    "schema_version": SCHEMA_VERSION,
                    "record_type": RecordType.RESOURCE_SAMPLE.value,
                    "timestamp_utc_iso": utc_iso,
                    "timestamp_monotonic_ns": t_probe_start,
                    "run_id": self.run_id,
                    "sample_index": idx,
                    "sample_duration_us": round(probe_duration_us, 2),
                    "process_metrics": proc_dicts,
                    "system_metrics": sys_dict,
                }
                self.writer.write_record(record_dict)

            # Schedule next tick target
            target_tick_ns += int(self.interval_ms * 1_000_000)
            sleep_remaining_s = (target_tick_ns - self.clock.monotonic_ns()) / 1_000_000_000.0

            if sleep_remaining_s > 0:
                time.sleep(sleep_remaining_s)
            else:
                # Fallen behind schedule: reset target to now
                target_tick_ns = self.clock.monotonic_ns()

    def get_jitter_stats(self) -> dict[str, float]:
        """Return statistical summary of sampling interval jitter and probe duration."""
        if not self._jitter_samples_us:
            return {"mean_jitter_us": 0.0, "mean_probe_duration_us": 0.0}

        mean_jitter = sum(self._jitter_samples_us) / len(self._jitter_samples_us)
        mean_probe = sum(self._probe_durations_us) / len(self._probe_durations_us)
        return {
            "mean_jitter_us": round(mean_jitter, 2),
            "mean_probe_duration_us": round(mean_probe, 2),
        }
