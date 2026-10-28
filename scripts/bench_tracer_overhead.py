"""Tracer overhead microbenchmark evaluating per-span execution latency.

Compares:
1. NoOpTracer (zero-overhead baseline control)
2. CoreTracer with fast dictionary write path (ADR D7)
3. CoreTracer with full Pydantic model validation on write path

Outputs empirically measured nanoseconds per span and throughput to experiments/results/.
"""

from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

from agenttrace.instrumentation.clock import MonotonicClock
from agenttrace.instrumentation.tracer import CoreTracer, NoOpTracer
from agenttrace.storage.writer import TraceWriter


def bench_arm(
    arm_name: str,
    iterations: int = 20_000,
    warmup: int = 2_000,
    validate_on_write: bool = False,
    is_noop: bool = False,
) -> dict[str, Any]:
    """Execute microbenchmark for a single tracer configuration arm."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        trace_path = Path(tmp_dir) / "bench.jsonl"
        writer = TraceWriter(output_path=trace_path, buffer_size=5_000, auto_flush=True)

        if is_noop:
            tracer: Any = NoOpTracer()
        else:
            clock = MonotonicClock()
            tracer = CoreTracer(
                writer=writer,
                clock=clock,
                validate_on_write=validate_on_write,
            )

        # Warm-up phase
        for _ in range(warmup):
            span = tracer.start_span(operation_name="bench_warmup")
            span.end()

        durations_ns: list[int] = []

        # Measurement phase
        t_total_start = time.perf_counter_ns()
        for i in range(iterations):
            t_span_start = time.perf_counter_ns()
            span = tracer.start_span(
                operation_name=f"bench_op_{i}",
                attributes={"index": i, "test": True},
            )
            span.end()
            durations_ns.append(time.perf_counter_ns() - t_span_start)

        t_total_end = time.perf_counter_ns()
        tracer.flush()

        total_elapsed_ms = (t_total_end - t_total_start) / 1_000_000.0
        spans_per_second = (iterations / total_elapsed_ms) * 1_000.0 if total_elapsed_ms > 0 else 0

        mean_ns = statistics.mean(durations_ns)
        median_ns = statistics.median(durations_ns)
        p95_ns = sorted(durations_ns)[int(iterations * 0.95)]
        stdev_ns = statistics.stdev(durations_ns) if len(durations_ns) > 1 else 0

        return {
            "arm": arm_name,
            "iterations": iterations,
            "total_elapsed_ms": round(total_elapsed_ms, 2),
            "throughput_spans_per_sec": round(spans_per_second, 1),
            "mean_ns_per_span": round(mean_ns, 1),
            "median_ns_per_span": round(median_ns, 1),
            "p95_ns_per_span": round(p95_ns, 1),
            "stdev_ns_per_span": round(stdev_ns, 1),
        }


def main() -> None:
    """Run all microbenchmark arms and output verified JSON artifact."""
    iterations = 20_000
    results: list[dict[str, Any]] = [
        bench_arm("NoOpTracer (Control)", iterations=iterations, is_noop=True),
        bench_arm(
            "CoreTracer (Fast Dict, ADR D7)",
            iterations=iterations,
            validate_on_write=False,
        ),
        bench_arm(
            "CoreTracer (Strict Pydantic on Write)",
            iterations=iterations,
            validate_on_write=True,
        ),
    ]

    out_file = Path("experiments/results/tracer_overhead_microbench.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "microbenchmark": "tracer_overhead",
        "iterations_per_arm": iterations,
        "results": results,
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))
    print(f"\nMicrobenchmark saved to: {out_file}")


if __name__ == "__main__":
    main()
