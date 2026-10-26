# AgentTrace: Requirements & Scope Definition

## Scope Tiers (MoSCoW)

### Tier 1: Must Have (Core Research Foundation - M1 to M5)
- **Core Tracer**: Minimal, lightweight tracer with injectable monotonic clock (`time.monotonic_ns()`), context propagation, and explicit zero-overhead no-op mode.
- **Append-Only JSONL Store**: Crash-resilient, schema-versioned raw event streams (`run_start`, `span_start`, `span_end`, `span_event`, `resource_sample`, `run_end`).
- **Schema Validation**: Pydantic v2 schemas defining records and models, strictly validated during ingest and unit testing.
- **Mock Agent Ecosystem**:
  - Mock model with calibrated time-to-first-token (TTFT), per-token latency, and deterministic token counts.
  - Mock tools: artificial latency, CPU-bound intensive math, synced disk I/O, and payload size variations.
  - Fault injection engine: deterministic error rates, timeouts, cancellations, and retries.
- **Workload Generator**: Deterministic workflow DAG specifications (sequential, parallel fan-out/fan-in, multi-step dependency DAG, CPU-heavy, I/O-heavy, variable-size).
- **Resource Sampler**: Daemon thread sampling process-tree (`psutil.Process`) and system-wide resource counters with probe duration tracking (measuring observer effect).
- **Correlation Engine**: Temporal join between span lifecycle and resource samples, assigning explicit attribution tiers (Tier 0 Context, Tier 1 Exclusive Window, Tier 2 Direct Process, Tier 3 Unsplit Aggregate).
- **Analysis Engine**: Sweep-line algorithm for exact max and mean concurrent span calculations, critical path identification, latency distributions (p50, p90, p95, IQR), and throughput.
- **Experiments**:
  - E1: Sequential vs Parallel (speedup, parallel efficiency, resource scaling).
  - E4: Instrumentation Overhead (no-op, basic log, AgentTrace, AgentTrace+sampler).
  - E3: Concurrency Scaling (saturation point, queue wait vs run duration).
- **CLI**: Standard library `argparse` CLI offering `run`, `compare`, `probe`, and `validate`.

### Tier 2: Should Have (Analytical Depth & Publication Quality - M6 & M7)
- **SQLite Analytical Ingest**: Fast structured SQL joins over raw JSONL runs.
- **Plotly Static HTML Reports**: Self-contained, offline interactive visual reports (timelines, DAG dependency charts, resource time-series, run comparison diffs).
- **Experiment 2**: Workload Classification (resource signatures across classes).
- **Experiment 5**: Completeness and Correlation under Chaos (ground-truth DAG oracle vs recorded trace under high fault injection).
- **Experiment 6**: Measurement Limits & Horizon (sampling frequency vs short-span duration aliasing, concurrent attribution limits).
- **Comprehensive Related-Work Review & Technical Report**.

### Tier 3: Could Have (Extensions)
- Multi-agent workload simulation (multiple `agent_id` instances exchanging message spans).
- Optional real-LLM adapter (LiteLLM / OpenAI API hook with payload redaction).
- Docker containerization for strict cgroup resource isolation.
- Extended Linux `/proc` extraction (PSI - Pressure Stall Information, cgroup v2 metrics).
- Standard OpenTelemetry format exporter.
- Apache Parquet storage for massive multi-run analytical queries.

### Tier 4: Won't Have (Out of Scope for v1)
- eBPF in-kernel tracing (evaluated in M1 capability matrix; deferred unless E6 demonstrates insurmountable user-space aliasing).
- Distributed multi-host tracing.
- Authentication, authorization, or multi-tenant database.
- Live web dashboard or background WebSocket daemon (static self-contained HTML reports are favored for scientific reproducibility).
- Cloud deployment infrastructure.
