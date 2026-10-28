"""Experiment 1: Sequential vs Parallel Execution and Scaling Efficiency."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from agenttrace.agents.executor import AsyncAgentExecutor
from agenttrace.analysis.concurrency import compute_concurrency_profile
from agenttrace.analysis.critical_path import compute_critical_path_from_spans
from agenttrace.analysis.metrics import compute_distribution, compute_scaling_efficiency
from agenttrace.instrumentation.clock import MonotonicClock
from agenttrace.instrumentation.tracer import CoreTracer
from agenttrace.storage.sqlite import SQLiteTraceStore
from agenttrace.storage.writer import TraceWriter
from agenttrace.workloads.generator import WorkloadGenerator


async def run_single_dag(dag: Any, concurrency_limit: int, trace_file: Path) -> dict[str, Any]:
    clock = MonotonicClock()
    with TraceWriter(trace_file) as writer:
        tracer = CoreTracer(writer=writer, clock=clock)
        executor = AsyncAgentExecutor(
            tracer=tracer, clock=clock, concurrency_limit=concurrency_limit
        )
        await executor.run(dag)

    # Ingest and analyze
    store = SQLiteTraceStore()
    store.ingest_jsonl(trace_file)
    spans = store.get_spans()

    prof = compute_concurrency_profile(spans)
    cp = compute_critical_path_from_spans(spans, observed_makespan_ns=prof.makespan_ns)

    return {
        "makespan_ms": prof.makespan_ms,
        "max_concurrency": prof.max_concurrency,
        "mean_concurrency": prof.mean_concurrency,
        "critical_path_duration_ms": cp.critical_path_duration_ms,
        "critical_path_ratio": cp.critical_path_ratio,
        "span_count": len(spans),
    }


async def main() -> int:
    outdir = Path("experiments/results")
    outdir.mkdir(parents=True, exist_ok=True)
    temp_trace_dir = outdir / "temp_exp1_traces"
    temp_trace_dir.mkdir(parents=True, exist_ok=True)

    gen = WorkloadGenerator(master_seed=42)

    # Test cases: Latency-bound (delay 10ms per task, 8 parallel tasks)
    num_tasks = 8
    task_delay_ms = 15.0

    print(f"Running Experiment 1 (Sequential vs Parallel, {num_tasks} tasks)...")

    # Interleaved runs: 3 warm-ups, 5 measured runs per arm
    warmups = 2
    measured_runs = 5

    seq_makespans: list[float] = []
    par_makespans: list[float] = []

    # Warm-up cycles
    for w in range(warmups):
        dag_seq = gen.generate_sequential(num_tasks=num_tasks, base_latency_ms=task_delay_ms)
        dag_par = gen.generate_parallel(num_tasks=num_tasks, base_latency_ms=task_delay_ms)
        await run_single_dag(dag_seq, 1, temp_trace_dir / f"warmup_seq_{w}.jsonl")
        await run_single_dag(dag_par, num_tasks, temp_trace_dir / f"warmup_par_{w}.jsonl")

    # Interleaved ABAB measured executions
    for r in range(measured_runs):
        dag_seq = gen.generate_sequential(num_tasks=num_tasks, base_latency_ms=task_delay_ms)
        dag_par = gen.generate_parallel(num_tasks=num_tasks, base_latency_ms=task_delay_ms)

        res_seq = await run_single_dag(dag_seq, 1, temp_trace_dir / f"seq_run_{r}.jsonl")
        res_par = await run_single_dag(dag_par, num_tasks, temp_trace_dir / f"par_run_{r}.jsonl")

        seq_makespans.append(res_seq["makespan_ms"])
        par_makespans.append(res_par["makespan_ms"])
        print(
            f"  Repetition {r + 1}/{measured_runs}: "
            f"Seq={res_seq['makespan_ms']:.1f}ms, Par={res_par['makespan_ms']:.1f}ms"
        )

    # Statistical aggregation
    dist_seq = compute_distribution(seq_makespans)
    dist_par = compute_distribution(par_makespans)

    scaling = compute_scaling_efficiency(
        baseline_makespan_s=dist_seq.p50 / 1000.0,
        parallel_makespan_s=dist_par.p50 / 1000.0,
        concurrency_limit=num_tasks,
    )

    result_data = {
        "experiment": "E1_sequential_vs_parallel",
        "parameters": {
            "num_tasks": num_tasks,
            "repetitions": measured_runs,
            "warmup_runs": warmups,
            "nominal_task_duration_ms": task_delay_ms,
        },
        "sequential": {
            "makespan_p50_ms": dist_seq.p50,
            "makespan_p95_ms": dist_seq.p95,
            "makespan_iqr_ms": dist_seq.iqr,
            "samples_ms": seq_makespans,
        },
        "parallel": {
            "makespan_p50_ms": dist_par.p50,
            "makespan_p95_ms": dist_par.p95,
            "makespan_iqr_ms": dist_par.iqr,
            "samples_ms": par_makespans,
        },
        "scaling_metrics": {
            "speedup": scaling.speedup,
            "parallel_efficiency": scaling.parallel_efficiency,
            "theoretical_max_speedup": scaling.theoretical_max_speedup,
        },
    }

    result_file = outdir / "exp1_seq_vs_par.json"
    with result_file.open("w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2)

    # Clean up temp traces
    for p in temp_trace_dir.glob("*.jsonl"):
        try:
            p.unlink()
        except OSError:
            pass
    try:
        temp_trace_dir.rmdir()
    except OSError:
        pass

    print(
        f"Completed E1: Speedup={scaling.speedup:.2f}x "
        f"(Efficiency={scaling.parallel_efficiency * 100:.1f}%)"
    )
    print(f"Saved results to {result_file}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
