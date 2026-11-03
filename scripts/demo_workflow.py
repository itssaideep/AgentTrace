"""AgentTrace: End-to-End Demonstration Workflow.

This script executes the entire AgentTrace lifecycle:
1. Generates synthetic multi-agent workloads with seed isolation.
2. Runs instrumented execution with CoreTracer and ResourceSampler.
3. Audits trace completeness and causal invariants.
4. Performs sweep-line concurrency and critical path analysis.
5. Ingests into SQLite analytical database.
6. Generates self-contained offline HTML reports.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from agenttrace.agents.executor import AsyncAgentExecutor
from agenttrace.analysis.compare import compare_runs
from agenttrace.analysis.completeness import TraceCompletenessChecker
from agenttrace.analysis.concurrency import compute_concurrency_profile
from agenttrace.analysis.critical_path import compute_critical_path_from_spans
from agenttrace.analysis.metrics import compute_distribution
from agenttrace.instrumentation.clock import MonotonicClock
from agenttrace.instrumentation.tracer import CoreTracer
from agenttrace.resources.sampler import ResourceSampler
from agenttrace.storage.sqlite import SQLiteTraceStore
from agenttrace.storage.writer import TraceWriter
from agenttrace.visualization.report import generate_trace_html_report
from agenttrace.workloads.generator import WorkloadGenerator


async def run_demo() -> int:
    results_dir = Path("experiments/results")
    results_dir.mkdir(parents=True, exist_ok=True)

    seq_trace_path = results_dir / "demo_seq_trace.jsonl"
    par_trace_path = results_dir / "demo_par_trace.jsonl"
    report_path = results_dir / "demo_report.html"

    # TraceWriter is append-only by design.  The demo owns these fixed output
    # paths, so clear previous demo artifacts before starting a new run rather
    # than accidentally combining multiple executions into one analysis.
    seq_trace_path.unlink(missing_ok=True)
    par_trace_path.unlink(missing_ok=True)

    clock = MonotonicClock()
    gen = WorkloadGenerator(master_seed=42)

    print("=================================================================")
    print("        AgentTrace: End-to-End System Demonstration             ")
    print("=================================================================\n")

    # 1. Generate Workloads
    num_workers = 6
    print(f"[Step 1] Generating synthetic workloads with seed isolation (N={num_workers})...")
    dag_seq = gen.generate_sequential(num_tasks=num_workers, base_latency_ms=10.0)
    dag_par = gen.generate_parallel(num_tasks=num_workers, base_latency_ms=10.0)
    print(f"  - Sequential DAG: {len(dag_seq.tasks)} tasks")
    print(f"  - Parallel DAG:   {len(dag_par.tasks)} tasks\n")

    # 2. Execute Sequential Baseline
    print("[Step 2] Executing Sequential Baseline...")
    with TraceWriter(seq_trace_path) as writer:
        tracer = CoreTracer(writer=writer, clock=clock)
        executor = AsyncAgentExecutor(tracer=tracer, clock=clock, concurrency_limit=1)
        await executor.run(dag_seq)
    print(f"  Wrote sequential trace: {seq_trace_path}")

    # 3. Execute Parallel Candidate with Resource Sampler
    print("\n[Step 3] Executing Parallel Workload with Resource Sampler daemon...")
    with TraceWriter(par_trace_path) as writer:
        tracer = CoreTracer(writer=writer, clock=clock)
        sampler = ResourceSampler(writer=writer, interval_ms=15, clock=clock)
        sampler.start()
        try:
            executor = AsyncAgentExecutor(tracer=tracer, clock=clock, concurrency_limit=num_workers)
            await executor.run(dag_par)
        finally:
            sampler.stop()
    print(f"  Wrote parallel trace: {par_trace_path}")

    # 4. Completeness & Integrity Audit
    print("\n[Step 4] Auditing Trace Completeness...")
    report = TraceCompletenessChecker(par_trace_path).check()
    print(f"  - Completeness: {report.completeness_percentage:.1f}%")
    print(f"  - Total Spans Completed: {report.completed_spans}/{report.total_spans_started}")
    print(f"  - Incomplete Spans: {len(report.incomplete_span_ids)}")
    print(f"  - Orphan Spans: {len(report.orphan_span_ids)}")
    assert report.is_valid, "Trace completeness audit failed!"

    # 5. Relational SQLite Ingest & Analytics
    print("\n[Step 5] Ingesting into SQLite Analytical Store...")
    with SQLiteTraceStore() as store:
        count = store.ingest_jsonl(par_trace_path)
        spans = store.get_spans()
        samples = store.get_resource_samples()
        print(f"  - Ingested records: {count}")
        print(f"  - Completed spans:  {len(spans)}")
        print(f"  - Resource samples: {len(samples)}")

    # 6. Concurrency & Critical Path Solvers
    print("\n[Step 6] Running Analytical Solvers...")
    concurrency = compute_concurrency_profile(spans)
    cp = compute_critical_path_from_spans(spans, observed_makespan_ns=concurrency.makespan_ns)
    durations = [s["duration_ms"] for s in spans if s.get("duration_ms") is not None]
    dist = compute_distribution(durations)

    print(f"  - Makespan:              {concurrency.makespan_ms:.2f} ms")
    print(f"  - Max Concurrency:       {concurrency.max_concurrency}")
    print(f"  - Mean Concurrency:      {concurrency.mean_concurrency:.2f}")
    print(
        f"  - Critical Path:         {cp.critical_path_duration_ms:.2f} ms "
        f"(Ratio: {cp.critical_path_ratio:.3f})"
    )
    print(f"  - Critical Path Chain:   {' -> '.join(cp.critical_path)}")
    print(f"  - Span Latency (p50):    {dist.p50:.2f} ms")

    # 7. Differential Run Comparison
    print("\n[Step 7] Comparing Sequential vs Parallel Runs...")
    comparison = compare_runs(
        seq_trace_path,
        par_trace_path,
        baseline_label="Sequential (N=1)",
        candidate_label=f"Parallel (N={num_workers})",
    )
    print(f"  - Sequential Makespan:   {comparison.baseline_makespan_ms:.2f} ms")
    print(f"  - Parallel Makespan:     {comparison.candidate_makespan_ms:.2f} ms")
    print(f"  - Speedup Achieved:      {comparison.speedup:.2f}x")

    # 8. Interactive Offline HTML Report Generation
    print("\n[Step 8] Generating Self-Contained Offline HTML Report...")
    out_html = generate_trace_html_report(par_trace_path, report_path)
    print(f"  - Generated interactive report: {out_html}")
    print(f"  - File size: {out_html.stat().st_size:,} bytes")

    print("\n=================================================================")
    print("      AgentTrace Workflow Demonstration Completed Successfully!  ")
    print("=================================================================\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_demo()))
