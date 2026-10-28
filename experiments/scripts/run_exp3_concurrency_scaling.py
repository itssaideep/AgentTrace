"""Experiment 3: Concurrency Scaling and Queue Wait Saturation Analysis."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from agenttrace.agents.executor import AsyncAgentExecutor
from agenttrace.analysis.concurrency import compute_concurrency_profile
from agenttrace.analysis.metrics import compute_distribution, compute_scaling_efficiency
from agenttrace.instrumentation.clock import MonotonicClock
from agenttrace.instrumentation.tracer import CoreTracer
from agenttrace.storage.sqlite import SQLiteTraceStore
from agenttrace.storage.writer import TraceWriter
from agenttrace.workloads.generator import WorkloadGenerator


async def run_scaling_level(
    concurrency_limit: int,
    num_tasks: int,
    trace_path: Path,
    clock: MonotonicClock,
) -> dict[str, Any]:
    gen = WorkloadGenerator(master_seed=200)
    dag = gen.generate_parallel(num_tasks=num_tasks, base_latency_ms=10.0)

    with TraceWriter(trace_path, buffer_size=100) as writer:
        tracer = CoreTracer(writer=writer, clock=clock)
        executor = AsyncAgentExecutor(
            tracer=tracer, clock=clock, concurrency_limit=concurrency_limit
        )
        await executor.run(dag)

    store = SQLiteTraceStore()
    store.ingest_jsonl(trace_path)
    spans = store.get_spans()

    prof = compute_concurrency_profile(spans)

    # Extract queue wait times from span attributes
    queue_waits_ms: list[float] = []
    for s in spans:
        raw_attrs = s.get("attributes_json", "{}")
        attrs = json.loads(raw_attrs) if isinstance(raw_attrs, str) else raw_attrs
        qw = attrs.get("queue_wait_ms")
        if qw is not None:
            queue_waits_ms.append(float(qw))

    qw_dist = compute_distribution(queue_waits_ms)

    return {
        "concurrency_limit": concurrency_limit,
        "makespan_ms": prof.makespan_ms,
        "max_concurrency": prof.max_concurrency,
        "mean_concurrency": prof.mean_concurrency,
        "queue_wait_p50_ms": qw_dist.p50,
        "queue_wait_p95_ms": qw_dist.p95,
        "throughput_spans_per_sec": (len(spans) / (prof.makespan_ms / 1000.0))
        if prof.makespan_ms > 0
        else 0.0,
    }


async def main() -> int:
    outdir = Path("experiments/results")
    outdir.mkdir(parents=True, exist_ok=True)
    temp_dir = outdir / "temp_exp3"
    temp_dir.mkdir(parents=True, exist_ok=True)

    print("Running Experiment 3: Concurrency Scaling & Queue Wait Saturation...")

    clock = MonotonicClock()
    num_tasks = 24
    concurrency_levels = [1, 2, 4, 8, 16]

    results: list[dict[str, Any]] = []

    for limit in concurrency_levels:
        trace_path = temp_dir / f"scale_{limit}.jsonl"
        res = await run_scaling_level(limit, num_tasks, trace_path, clock)
        results.append(res)
        print(
            f"  Concurrency={limit}: Makespan={res['makespan_ms']:.1f}ms, "
            f"QueueWait p95={res['queue_wait_p95_ms']:.2f}ms, "
            f"Throughput={res['throughput_spans_per_sec']:.1f} spans/s"
        )

    # Compute speedups relative to baseline N=1
    baseline_ms = results[0]["makespan_ms"]
    for r in results:
        lim = r["concurrency_limit"]
        scaling = compute_scaling_efficiency(
            baseline_makespan_s=baseline_ms / 1000.0,
            parallel_makespan_s=r["makespan_ms"] / 1000.0,
            concurrency_limit=lim,
        )
        r["speedup"] = scaling.speedup
        r["parallel_efficiency"] = scaling.parallel_efficiency

    payload = {
        "experiment": "E3_concurrency_scaling",
        "parameters": {
            "num_tasks": num_tasks,
            "levels_swept": concurrency_levels,
        },
        "results": results,
    }

    result_file = outdir / "exp3_concurrency_scaling.json"
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

    print(f"Completed E3: Results saved to {result_file}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
