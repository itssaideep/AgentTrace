# AgentTrace: Research Questions & Experimental Mapping

This document provides a disciplined mapping between theoretical research questions, empirical experiments, measurable metrics, and discussion-only analytical topics.

---

## Research Questions Table

| RQ ID | Research Question | Empirical vs Discussion | Target Experiment | Primary Metrics | Controls & Baseline |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **RQ1** | How much does concurrency improve wall-clock latency for synthetic agent workloads, and where are the diminishing returns across workload types (latency-bound, CPU-bound, mixed)? | **Empirical** | **Experiment 1 (Sequential vs Parallel)** & **Experiment 3 (Concurrency Scaling)** | Makespan (total run duration ms), speedup ($S = T_1 / T_N$), parallel efficiency ($E = S / N$), max & mean observed concurrency, p50/p95 task duration | Fixed seed, identical synthetic task definitions, warm-up discard, interleaved ABAB runs |
| **RQ2** | What is the quantitative runtime overhead (CPU time, peak RSS, latency inflation, I/O volume) introduced by workflow-level causal tracing and periodic resource sampling? | **Empirical** | **Experiment 4 (Instrumentation Overhead)** | Absolute nanoseconds per span, total makespan delta, process CPU time delta, peak RSS bytes, event-loop lag probe | 4 arms: (1) True No-Op, (2) Basic Event Logger, (3) OTel SDK file exporter, (4) AgentTrace buffered tracer + sampler (at 10ms and 50ms) |
| **RQ3** | At what concurrency levels does agent execution saturate host resources, and does semaphore queue waiting dominate task makespan before physical core saturation? | **Empirical** | **Experiment 3 (Concurrency Scaling)** | Throughput (tasks/sec), queue wait time (`queue_wait_ms`), span duration (`duration_ms`), voluntary context switches, CPU saturation knee | Fixed task count, varying concurrency limit $C \in [1, 2 \times \text{cores}]$ |
| **RQ4** | Can different synthetic agent workload patterns (CPU-bound, I/O-bound, latency-bound, variable-size) be reliably distinguished solely by their process-level and system-level resource signatures? | **Empirical** | **Experiment 2 (Workload Classification)** | CPU time per task, peak RSS delta, storage bytes written, context switch rates, voluntary vs involuntary ratio | Calibrated workloads with identical task graph shapes but varying tool kernels |
| **RQ5** | Under synthetic failure injection (timeouts, cancellations, tool exceptions), does explicit causal tracing maintain 100% trace completeness without silent data loss or corrupted dependency links? | **Empirical** | **Experiment 5 (Completeness & Fault Recovery)** | Completeness ratio ($\frac{\text{spans completed}}{\text{spans started}}$), oracle graph edge recall, orphan span count, status distribution | Ground-truth DAG oracle vs recorded trace under varying failure rates ($p \in [0.0, 0.5]$) |
| **RQ6** | What are the fundamental physical measurement limits of user-space periodic resource sampling (aliasing of short-duration spans, sampling jitter, concurrency attribution bounds)? | **Empirical** | **Experiment 6 (Measurement Limits)** | Sampler jitter standard deviation ($\sigma_{\Delta t}$), minimum attributable span duration threshold, fraction of spans falling into Tier 1 vs Tier 3 | Sweep sampling intervals $I \in [5\text{ms}, 100\text{ms}]$ against span durations $D \in [1\text{ms}, 200\text{ms}]$ |
| **RQ7** | Under what conditions would kernel-space tracing (eBPF) or cgroup v2 accounting provide information that user-space sampling physically cannot obtain? | **Discussion-only** | N/A (Synthesis in Technical Report) | Platform capability matrix findings, socket-level network attribution, non-blocking page-cache write accounting | Evaluated in M1 capability matrix; referenced against Experiment 6 findings |
| **RQ8** | To what extent do synthetic micro-benchmarks generalize to non-deterministic, production multi-agent LLM systems? | **Discussion-only** | N/A (Methodology & Threats to Validity) | Analytical bounds, token distribution realism, latency variance models | Synthesized in `docs/limitations.md` and Final Report |

---

## Discipline Rules
1. **No False Novelty**: We do not claim novelty for distributed tracing or sampling concepts; the research contribution lies strictly in **quantifying causal completeness (RQ5), honest non-apportioned attribution (RQ6), and measurement overhead (RQ2)**.
2. **Oracle Verification**: Any claim of causal correctness or completeness must be evaluated against the ground-truth DAG generator oracle.
3. **Discussion-Only Boundary**: RQ7 and RQ8 are marked **Discussion-only**; no empirical claims will be made regarding eBPF or live LLM generalization without explicit benchmark data.
