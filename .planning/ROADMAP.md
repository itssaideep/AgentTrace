# AgentTrace: Milestone Roadmap

## Overview & Execution Strategy
AgentTrace follows an 8-milestone roadmap designed for rigorous empirical evaluation, scientific honesty, and complete reproducibility. Each milestone concludes with strict acceptance criteria, automated tests, and reproducible commands.

---

### Milestone 1: Requirements, Environment & Feasibility (Active)
- **Goal**: Establish project skeleton, development tooling, design decisions (ADRs D1–D7), research-question mapping, empirical platform capability matrix on host hardware, and related-work matrix.
- **Deliverables**:
  - Repo skeleton with editable install and dev dependencies.
  - Passing ruff lint and pytest smoke test.
  - `docs/decisions/` ADRs D1 through D7.
  - Research questions mapped to experiments and metrics.
  - Empirically verified platform capability matrix (`scripts/probe_platform.py` -> `docs/capability-matrix.md`).
  - Related-work landscape matrix (`docs/related-work.md`).
  - Claims discipline protocol.
- **Exit Criterion**: All M1 acceptance criteria satisfied, smoke tests pass in Windows and WSL2 environments.

---

### Milestone 2: Core Tracing Subsystem
- **Goal**: High-throughput, low-overhead causal tracing engine with injectable clocks and completeness verification.
- **Deliverables**:
  - `Clock` protocol and nanosecond monotonic implementation (`MonotonicClock`, `FakeClock`).
  - Context propagation (`TraceContext`, asyncio `ContextVar` management).
  - Minimal `Tracer` with `Span` lifecycle management (`span_start`, `span_end`, `span_event`).
  - Append-only buffered JSONL `TraceWriter`.
  - True zero-overhead `NoOpTracer`.
  - Allowlist-based redaction engine with canary secret leak tests.
  - Post-run trace completeness checker.
- **Exit Criterion**: Unit and roundtrip tests pass; tracer overhead microbenchmarks complete; zero canary leaks confirmed.

---

### Milestone 3: Synthetic Workload & Agent Ecosystem
- **Goal**: Deterministic, reproducible synthetic agent workloads with known DAG ground truth.
- **Deliverables**:
  - Deterministic DAG generator supporting sequential chains, parallel fan-out/fan-in, and arbitrary dependency graphs.
  - Seed-isolated PRNG streams (independent of asyncio execution order).
  - Mock agent orchestrator and mock model with configurable TTFT, token streaming latency, and token volume.
  - Mock tool library (calibrated CPU load, synced file I/O, latency delays).
  - Fault injection framework (deterministic exceptions, timeouts, task cancellations, retry linkages).
  - Oracle comparison engine comparing recorded trace against ground-truth DAG.
- **Exit Criterion**: Recorded execution traces match oracle graph 100% under both nominal and chaotic fault-injected conditions.

---

### Milestone 4: Resource Monitoring & Attribution Engine
- **Goal**: High-frequency resource sampler with nanosecond alignment and tiered attribution.
- **Deliverables**:
  - Sampler daemon thread tracking process-tree RSS, CPU user/system times, voluntary/involuntary context switches, and system metrics.
  - Probe duration and sampling jitter telemetry.
  - Shared clock anchoring between trace stream and sampler stream.
  - Temporal join engine implementing Attribution Tiers (Tier 0 Context, Tier 1 Exclusive Window, Tier 2 Direct Process, Tier 3 Unsplit Aggregate).
- **Exit Criterion**: Synthetic single-task workloads correctly classified as Tier 1; concurrent overlapping spans strictly classified as Tier 3 without arbitrary splitting.

---

### Milestone 5: Analysis & Comparative Engine
- **Goal**: Analytical metric computation and multi-run differential analysis.
- **Deliverables**:
  - Sweep-line interval algorithm for exact maximum and instantaneous concurrency calculations.
  - Critical-path identification via topological graph traversal.
  - Latency distribution calculations (p50, p90, p95, p99, IQR) with sample size gating.
  - Run comparison engine computing makespan diffs, speedups, parallel efficiencies, and resource deltas.
  - SQLite analytical ingest for relational queries.
- **Exit Criterion**: Analytical calculations match golden traces with mathematically verified answers.

---

### Milestone 6: Offline Visualization & Reporting
- **Goal**: Self-contained, reproducible static HTML reports.
- **Deliverables**:
  - Gantt/timeline interactive visualization showing spans and dependency arrows.
  - Concurrency profile and queue wait overlays.
  - Synchronized resource utilization time-series (CPU, RSS, I/O rates).
  - Run-to-run comparison dashboards.
- **Exit Criterion**: All charts render standalone without external network access and directly trace back to raw JSONL data.

---

### Milestone 7: Experimental Evaluation (E1 – E6)
- **Goal**: Execute experimental suite with statistical rigor.
- **Deliverables**:
  - Interleaved (ABAB) execution drivers with warm-up cycles.
  - E1: Sequential vs Parallel (speedup and parallel efficiency limits).
  - E4: Instrumentation Overhead (quantifying tracer cost across 4 arms).
  - E3: Concurrency Scaling (saturation point and queue wait analysis).
  - E2: Workload Resource Signatures & Classification.
  - E5: Completeness & Fault Recovery under Chaos.
  - E6: Measurement Limits (sampling frequency vs short-span duration aliasing).
  - Claims ledger: complete audit linking every claim in documentation to verified result files.
- **Exit Criterion**: All experiment scripts produce reproducible result sets; claims ledger verified.

---

### Milestone 8: Documentation, Demo & Package Delivery
- **Goal**: Comprehensive technical reporting, clean developer experience, and interview demonstration.
- **Deliverables**:
  - Technical report summarizing findings, attribution limits, and research conclusions.
  - CLI demonstration workflows.
  - Fresh-clone reproduction verification.
