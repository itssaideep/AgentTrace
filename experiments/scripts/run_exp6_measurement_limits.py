"""Experiment 6: Measurement Limits and Sampling Aliasing Analysis."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from agenttrace.agents.executor import AsyncAgentExecutor
from agenttrace.correlation.engine import CorrelationEngine
from agenttrace.instrumentation.clock import MonotonicClock
from agenttrace.instrumentation.tracer import CoreTracer
from agenttrace.resources.sampler import ResourceSampler
from agenttrace.storage.writer import TraceWriter
from agenttrace.workloads.generator import WorkloadGenerator


async def run_duration_sweep(
    task_duration_ms: float,
    sampler_interval_ms: int,
    trace_path: Path,
    clock: MonotonicClock,
) -> dict[str, Any]:
    gen = WorkloadGenerator(master_seed=300)
    # Generate 15 sequential tasks
    dag = gen.generate_sequential(
        num_tasks=15,
        base_latency_ms=task_duration_ms,
        jitter_ms=0.0,
    )

    with TraceWriter(trace_path, buffer_size=50) as writer:
        tracer = CoreTracer(writer=writer, clock=clock)
        sampler = ResourceSampler(writer=writer, interval_ms=sampler_interval_ms, clock=clock)
        sampler.start()
        try:
            executor = AsyncAgentExecutor(tracer=tracer, clock=clock, concurrency_limit=1)
            await executor.run(dag)
        finally:
            sampler.stop()

    # Read records and run correlation engine
    records: list[dict[str, Any]] = []
    with trace_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    corr_engine = CorrelationEngine(trace_records=records, sample_records=records)
    results = corr_engine.correlate()

    spans_with_samples = sum(1 for r in results if r.overlapping_sample_count > 0)
    total_spans = len(results)
    coverage_pct = (spans_with_samples / total_spans * 100.0) if total_spans > 0 else 0.0

    return {
        "task_duration_ms": task_duration_ms,
        "sampler_interval_ms": sampler_interval_ms,
        "duration_to_interval_ratio": task_duration_ms / sampler_interval_ms,
        "total_spans": total_spans,
        "spans_with_samples": spans_with_samples,
        "coverage_percentage": coverage_pct,
        "aliased_spans_percentage": 100.0 - coverage_pct,
    }


async def main() -> int:
    outdir = Path("experiments/results")
    outdir.mkdir(parents=True, exist_ok=True)
    temp_dir = outdir / "temp_exp6"
    temp_dir.mkdir(parents=True, exist_ok=True)

    print("Running Experiment 6: Measurement Limits and Sampling Aliasing...")

    clock = MonotonicClock()
    sampler_interval_ms = 20
    test_durations = [2.0, 5.0, 10.0, 20.0, 40.0, 80.0]

    sweep_results: list[dict[str, Any]] = []

    for dur in test_durations:
        trace_path = temp_dir / f"limits_{int(dur)}ms.jsonl"
        res = await run_duration_sweep(dur, sampler_interval_ms, trace_path, clock)
        sweep_results.append(res)
        print(
            f"  Span Duration={dur}ms (Ratio={res['duration_to_interval_ratio']:.2f}): "
            f"Observed Coverage={res['coverage_percentage']:.1f}% "
            f"(Aliased={res['aliased_spans_percentage']:.1f}%)"
        )

    payload = {
        "experiment": "E6_measurement_limits",
        "description": (
            "Quantifying resource sample aliasing when task duration "
            "is shorter than sampling interval"
        ),
        "sampler_interval_ms": sampler_interval_ms,
        "results": sweep_results,
    }

    result_file = outdir / "exp6_measurement_limits.json"
    with result_file.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    # Clean up temp
    for p in temp_dir.glob("*.jsonl"):
        try:
            p.unlink()
        except OSError:
            pass
    try:
        temp_dir.rmdir()
    except OSError:
        pass

    print(f"Completed E6: Results saved to {result_file}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
