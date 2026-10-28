# AgentTrace: Technical Report on Causal Workflow Tracing and Resource Attribution

**Authors**: AgentTrace Systems & Evaluation Team  
**Date**: October 2026  
**Status**: Completed Research Prototype (Milestones M1–M8)  
**Primary Claims Ledger**: [`.planning/STATE.md`](file:///c:/Users/Sai%20Deep/Desktop/AgentTrace/.planning/STATE.md)  
**Empirical Artifacts Directory**: [`experiments/results/`](file:///c:/Users/Sai%20Deep/Desktop/AgentTrace/experiments/results/)

---

## 1. Executive Summary & Problem Formulation

As autonomous AI agents evolve from single-prompt scripts into multi-step, multi-agent directed acyclic graphs (DAGs) coordinating tool calls, asynchronous sub-tasks, and model invocations, traditional observability tools fail in three fundamental ways:
1. **Inferring causality from timestamps**: Post-hoc inference produces false dependencies and circular graphs when async tasks interleave.
2. **Arbitrary resource attribution**: When tasks overlap within an `asyncio` loop or worker process, dividing CPU or RSS counters evenly manufactures false precision without physical causality.
3. **Unmeasured observer effect**: High-frequency tracing and polling daemons distort workload runtimes without quantifying the instrumentation overhead.

**AgentTrace** is an instrumented research prototype designed to execute controlled, reproducible synthetic agent workloads, record causal execution graphs, sample process-level and system-level resource telemetry on a shared monotonic clock, and enforce scientifically defensible attribution rules.

---

## 2. Core Architectural Principles & Invariants

AgentTrace implements seven architectural invariants that guarantee scientific validity:

### Invariant 1: Monotonic Nanosecond Clocks
- Durations are measured strictly via `time.monotonic_ns()`, completely decoupled from system wall-clock adjustments (NTP slews, leap seconds).
- Persisted UTC timestamps are recorded strictly for log human-readability at span start, never for duration arithmetic.
- Microbenchmarks demonstrate step resolution of 126–141 ns on Linux WSL2 and 200–300 ns on Windows ([`tracer_overhead_microbench.json`](file:///c:/Users/Sai%20Deep/Desktop/AgentTrace/experiments/results/tracer_overhead_microbench.json)).

### Invariant 2: Explicit Causality
- Causal dependencies (`parent_span_id`, `depends_on`, `retry_of`) are captured explicitly at invocation time and propagated via immutable `TraceContext` across asynchronous boundaries.
- Dependencies are never inferred post hoc from overlapping start/end timestamps.

### Invariant 3: Completeness Audit & Zero Silent Data Loss
- The `TraceCompletenessChecker` independently audits raw JSONL streams. Every opened span must be closed, or the trace is flagged `invalid` with incomplete and orphan spans isolated.

### Invariant 4: Honest 4-Tier Attribution
To prevent spurious attribution of process-level resources to concurrent tasks:
- **Tier 0 (Context Window)**: Unattributed temporal background telemetry.
- **Tier 1 (Exclusive Window)**: Only single active span running in process; counter deltas strictly bounded and attributed.
- **Tier 2 (Direct Dedicated)**: Process/thread-boundary dedicated worker execution.
- **Tier 3 (Unsplit Concurrent Aggregate)**: Overlapping concurrent spans are grouped and reported unsplit; arbitrary division is forbidden.

### Invariant 5: Seed-Isolated Deterministic Workloads
- PRNG streams are derived per-task via `derive_task_seed(master_seed, task_id)`. Task parameters and fault probabilities remain identical regardless of asyncio scheduling jitter.

### Invariant 6: Quantified Observer Effect
- All performance benchmarks evaluate a 4-arm ladder: Arm 0 (NoOpTracer), Arm 1 (Standard Logger), Arm 2 (AgentTrace Buffered), Arm 3 (AgentTrace Full Sampler).

### Invariant 7: Privacy by Default
- Payloads and prompts are excluded from traces by default. Canary secrets are scrubbed via `RedactionEngine` before disk emission.

---

## 3. Empirical Results & Findings

Every metric reported below is directly backed by a versioned JSON artifact in `experiments/results/`.

### 3.1 Experiment 1: Sequential vs Parallel Scaling Limits
- **Artifact**: [`exp1_seq_vs_par.json`](file:///c:/Users/Sai%20Deep/Desktop/AgentTrace/experiments/results/exp1_seq_vs_par.json)
- **Workload**: 8 tasks, 15ms nominal latency, interleaved ABAB execution (2 warmups, 5 measured runs).
- **Sequential Makespan**: Median 182.7 ms (IQR: 3.5 ms).
- **Parallel Makespan**: Median 60.6 ms (IQR: 1.7 ms).
- **Speedup**: **3.01x** ($S = T_1 / T_N$).
- **Parallel Efficiency**: **37.7%** ($E = S / N$).
- **Finding**: While ideal theoretical speedup was 8.0x, the fork-join barrier (root dispatcher + barrier aggregation collector) bounds parallel efficiency to ~38% for short-duration tasks, verifying Amdahl's Law in agent pipelines.

### 3.2 Experiment 3: Concurrency Scaling & Throughput
- **Artifact**: [`exp3_concurrency_scaling.json`](file:///c:/Users/Sai%20Deep/Desktop/AgentTrace/experiments/results/exp3_concurrency_scaling.json)
- **Workload**: 24-task parallel DAG, sweeping concurrency limit $N \in [1, 2, 4, 8, 16]$.

| Concurrency Limit ($N$) | Makespan (ms) | Mean Concurrency | Throughput (spans/s) | Speedup | Efficiency |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 391.9 | 0.99 | 66.3 | 1.00x | 100.0% |
| 2 | 213.1 | 1.84 | 122.0 | 1.84x | 92.0% |
| 4 | 120.1 | 3.29 | 216.5 | 3.26x | 81.6% |
| 8 | 72.9 | 5.50 | 356.4 | 5.37x | 67.2% |
| 16 | 57.1 | 6.89 | 455.0 | 6.86x | 42.9% |

- **Finding**: Throughput scales from 66.3 spans/s up to 455.0 spans/s. Beyond $N=8$, parallel efficiency drops sharply from 67.2% to 42.9% due to barrier serialization and thread scheduling overheads.

### 3.3 Experiment 4: Instrumentation Overhead & Observer Effect
- **Artifact**: [`exp4_tracer_overhead.json`](file:///c:/Users/Sai%20Deep/Desktop/AgentTrace/experiments/results/exp4_tracer_overhead.json)
- **Workload**: 20-task workload across 4 instrumentation arms, 5 repetitions.

| Arm | Description | Median Makespan (ms) | Overhead vs NoOp (ms) | Overhead (%) |
| :--- | :--- | :---: | :---: | :---: |
| Arm 0 | NoOpTracer | 104.4 | 0.00 | 0.00% |
| Arm 1 | Standard Python Logging | 108.0 | +3.57 | +3.42% |
| Arm 2 | AgentTrace Buffered CoreTracer | 109.3 | +4.86 | **+4.66%** |
| Arm 3 | AgentTrace + 20ms Sampler Daemon | 275.3 | +170.85 | **+163.65%** |

- **Finding**: AgentTrace's buffered CoreTracer introduces an observer effect of only **4.66%** over zero-instrumentation NoOp, competitive with standard logging (+3.42%). However, running a continuous user-space resource polling thread at 20ms intervals introduces a massive **+163.65%** runtime dilation, proving that resource sampling frequency must be carefully chosen to avoid severe observer perturbation.

### 3.4 Experiment 6: Measurement Limits & Nyquist Aliasing
- **Artifact**: [`exp6_measurement_limits.json`](file:///c:/Users/Sai%20Deep/Desktop/AgentTrace/experiments/results/exp6_measurement_limits.json)
- **Finding**: In sequential execution where tasks do not overlap, temporal window bounding captures spans with 100% precision. However, when span duration falls below sampling period ($T_{\text{span}} < \Delta t_{\text{sample}}$), instantaneous CPU rate spikes cannot be resolved from delta counters, necessitating dedicated process isolation or eBPF kernel probes.

---

## 4. Measurement Limits & Honest Attribution Manifesto

1. **Why arbitrary counter splitting is invalid**: In modern multi-threaded Python runtimes running `asyncio`, OS performance counters (such as `ru_utime`, `ru_stime`, `io_counters`) exist at the OS process or OS thread level. Multiple coroutines multiplexed onto the same OS thread physically share the same hardware registers. Splitting these counters evenly across active spans introduces artificial determinism and hides bursty bottlenecks.
2. **The eBPF boundary**: Socket-level network attribution and kernel context switch tracing without observer dilation require kernel-level probes (eBPF). As proven in our capability matrix probe, user-space unprivileged tools cannot physically trace network socket bytes per task without eBPF. AgentTrace honestly documents this boundary rather than approximating it with fake numbers.

---

## 5. Verification & Reproduction

All claims are verified cross-platform on both Windows 11 and Ubuntu 24.04 WSL2:
- Unit Test Pass Rate: **100%** (72 tests passing in 2.10s Windows / 4.64s WSL2).
- Static Type Checking: **0 errors** across 64 source files via strict `mypy`.
- Code Quality: **0 errors** via `ruff`.
- Complete reproduction executable via `python scripts/verify_reproduction.py`.
