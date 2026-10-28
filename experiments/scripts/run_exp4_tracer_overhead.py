"""Experiment 4: Instrumentation Overhead and Observer Effect across 4 Tracer Arms."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

import psutil

from agenttrace.agents.executor import AsyncAgentExecutor
from agenttrace.instrumentation.clock import MonotonicClock
from agenttrace.instrumentation.tracer import CoreTracer, NoOpTracer
from agenttrace.resources.sampler import ResourceSampler
from agenttrace.storage.writer import TraceWriter
from agenttrace.workloads.generator import WorkloadGenerator


class LoggingTracerArm:
    """Arm 1: Standard Python logging writing messages to a file."""

    def __init__(self, log_path: Path) -> None:
        self.logger = logging.getLogger(f"arm1_{id(self)}")
        self.logger.setLevel(logging.INFO)
        handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
        self.logger.addHandler(handler)
        self.handler = handler

    def start_span(self, operation_name: str, **kwargs: Any) -> Any:
        logger = self.logger

        class LoggingSpanContext:
            def __enter__(self) -> LoggingSpanContext:
                logger.info(f"START {operation_name} {kwargs}")
                return self

            def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
                logger.info(f"END {operation_name} error={exc_val}")

            def end(self, status: str = "ok", error: Exception | None = None) -> None:
                logger.info(f"END {operation_name} status={status} error={error}")

            def add_event(self, event_name: str, **attrs: Any) -> None:
                logger.info(f"EVENT {event_name} {attrs}")

        return LoggingSpanContext()

    def flush(self) -> None:
        self.handler.flush()

    def close(self) -> None:
        self.handler.close()
        self.logger.removeHandler(self.handler)


async def execute_workload(
    tracer: Any,
    dag: Any,
    concurrency_limit: int,
    clock: MonotonicClock,
) -> tuple[float, float, int]:
    proc = psutil.Process()
    cpu_before = proc.cpu_times()
    rss_before = proc.memory_info().rss
    t_start = clock.monotonic_ns()

    executor = AsyncAgentExecutor(tracer=tracer, clock=clock, concurrency_limit=concurrency_limit)
    await executor.run(dag)

    t_end = clock.monotonic_ns()
    cpu_after = proc.cpu_times()
    rss_after = proc.memory_info().rss

    duration_ms = (t_end - t_start) / 1_000_000.0
    cpu_user_s = cpu_after.user - cpu_before.user
    rss_delta_bytes = max(0, rss_after - rss_before)

    return duration_ms, cpu_user_s, rss_delta_bytes


async def main() -> int:
    outdir = Path("experiments/results")
    outdir.mkdir(parents=True, exist_ok=True)
    temp_dir = outdir / "temp_exp4"
    temp_dir.mkdir(parents=True, exist_ok=True)

    print("Running Experiment 4: Instrumentation Overhead across 4 Arms...")

    clock = MonotonicClock()
    gen = WorkloadGenerator(master_seed=100)
    num_tasks = 20
    repetitions = 5

    results: dict[str, list[dict[str, Any]]] = {
        "arm0_noop": [],
        "arm1_logging": [],
        "arm2_agenttrace_buffered": [],
        "arm3_agenttrace_full_sampler": [],
    }

    # Interleaved repetitions
    for r in range(repetitions):
        dag = gen.generate_parallel(num_tasks=num_tasks, base_latency_ms=5.0)

        # Arm 0: NoOp
        noop = NoOpTracer()
        dur0, cpu0, rss0 = await execute_workload(noop, dag, 4, clock)
        results["arm0_noop"].append(
            {"duration_ms": dur0, "cpu_user_s": cpu0, "rss_delta_bytes": rss0}
        )

        # Arm 1: Basic Python logging
        log_path = temp_dir / f"logging_run_{r}.log"
        log_tracer = LoggingTracerArm(log_path)
        dur1, cpu1, rss1 = await execute_workload(log_tracer, dag, 4, clock)
        log_tracer.close()
        results["arm1_logging"].append(
            {"duration_ms": dur1, "cpu_user_s": cpu1, "rss_delta_bytes": rss1}
        )

        # Arm 2: AgentTrace buffered
        trace_path2 = temp_dir / f"at_buf_run_{r}.jsonl"
        with TraceWriter(trace_path2, buffer_size=100) as writer2:
            at_tracer = CoreTracer(writer=writer2, clock=clock)
            dur2, cpu2, rss2 = await execute_workload(at_tracer, dag, 4, clock)
        results["arm2_agenttrace_buffered"].append(
            {"duration_ms": dur2, "cpu_user_s": cpu2, "rss_delta_bytes": rss2}
        )

        # Arm 3: AgentTrace buffered + Sampler daemon
        trace_path3 = temp_dir / f"at_full_run_{r}.jsonl"
        with TraceWriter(trace_path3, buffer_size=100) as writer3:
            full_tracer = CoreTracer(writer=writer3, clock=clock)
            sampler = ResourceSampler(writer=writer3, interval_ms=20, clock=clock)
            sampler.start()
            try:
                dur3, cpu3, rss3 = await execute_workload(full_tracer, dag, 4, clock)
            finally:
                sampler.stop()
        results["arm3_agenttrace_full_sampler"].append(
            {"duration_ms": dur3, "cpu_user_s": cpu3, "rss_delta_bytes": rss3}
        )

        print(
            f"  Repetition {r + 1}/{repetitions}: "
            f"NoOp={dur0:.1f}ms, Log={dur1:.1f}ms, AT={dur2:.1f}ms, "
            f"AT+Sampler={dur3:.1f}ms"
        )

    # Aggregate medians
    def _median(vals: list[float]) -> float:
        s = sorted(vals)
        return s[len(s) // 2]

    summary = {
        arm: {
            "median_duration_ms": _median([x["duration_ms"] for x in samples]),
            "median_cpu_user_s": _median([x["cpu_user_s"] for x in samples]),
            "median_rss_delta_kb": _median([x["rss_delta_bytes"] / 1024.0 for x in samples]),
            "overhead_vs_noop_ms": _median([x["duration_ms"] for x in samples])
            - _median([x["duration_ms"] for x in results["arm0_noop"]]),
            "overhead_percent": (
                (
                    _median([x["duration_ms"] for x in samples])
                    - _median([x["duration_ms"] for x in results["arm0_noop"]])
                )
                / _median([x["duration_ms"] for x in results["arm0_noop"]])
            )
            * 100.0,
        }
        for arm, samples in results.items()
    }

    final_payload = {
        "experiment": "E4_instrumentation_overhead",
        "parameters": {
            "num_tasks": num_tasks,
            "repetitions": repetitions,
            "concurrency_limit": 4,
            "sampler_interval_ms": 20,
        },
        "summary": summary,
        "raw_samples": results,
    }

    result_file = outdir / "exp4_tracer_overhead.json"
    with result_file.open("w", encoding="utf-8") as f:
        json.dump(final_payload, f, indent=2)

    # Clean up temp
    for p in temp_dir.glob("*"):
        try:
            p.unlink()
        except OSError:
            pass
    try:
        temp_dir.rmdir()
    except OSError:
        pass

    pct = summary["arm2_agenttrace_buffered"]["overhead_percent"]
    print(f"Completed E4: AgentTrace buffered overhead: {pct:.2f}%")
    print(f"Saved results to {result_file}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
