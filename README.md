# AgentTrace

An instrumented research prototype for synthetic agent workloads, causal workflow tracing, and honest resource attribution.

## Core Purpose

AgentTrace provides an empirically rigorous testbed to investigate:
1. **Causal Workflow Tracing**: Recording explicit directed acyclic graphs (DAGs) of execution, parent-child relations, explicit data dependencies (`depends_on`), and retries—without inferring causality from timestamps.
2. **Honest Resource Attribution**: Correlating monotonic process-level and system-level resource counters (CPU time, memory RSS, I/O counters, context switches) with concurrent agent tasks under strict attribution tiers (exclusive windows vs concurrent unapportioned aggregates).
3. **Workload Characterization**: Comparing latency, concurrency, throughput, and resource signatures across sequential, parallel fan-out, multi-step dependent, CPU-bound, and I/O-bound agent patterns.
4. **Observer Effect & Measurement Limits**: Quantifying tracer overhead, sampling jitter, and the limits of user-space tracing without eBPF.

## Core Requirements & Principles

1. **Trustworthy Timing**: Nanosecond monotonic clock (`time.monotonic_ns()`) for all durations across processes and threads. UTC wall-clock is used strictly for human-readable run anchors.
2. **Explicit Causality**: Graph edges (`parent_span_id`, `depends_on`, `retry_of`) are emitted directly by the workflow engine, never inferred post hoc.
3. **No Silent Loss**: Spans transition through explicit lifecycle states (`ok`, `error`, `timeout`, `cancelled`) or are flagged as `incomplete`.
4. **Honest Attribution**: Tiered resource attribution (Tier 0 Context, Tier 1 Exclusive Window, Tier 2 Dedicated Worker/Process, Tier 3 Unsplit Aggregate). Overlapping concurrency metrics are never arbitrarily divided.
5. **Reproducibility**: Master seed with deterministic per-task RNG streams; full environment capture and config snapshot per run.
6. **Measurable Overhead**: Configurable zero-overhead no-op mode; dedicated instrumentation overhead benchmark (Experiment 4).
7. **Privacy by Default**: Allowlist-based metadata capture; zero payload/secret retention.

## Repository Layout

```
agenttrace/
├── configs/               # Experiment and workload TOML configuration files
├── docs/                  # Architecture, schemas, methodology, capability matrix, and ADRs
│   └── decisions/         # Architecture Decision Records (D1 - D7)
├── src/agenttrace/        # Main source package
│   ├── instrumentation/   # Tracer, monotonic clock, context propagation, redaction
│   ├── baselines/         # Basic logging and standard OpenTelemetry comparison arms
│   ├── workloads/         # DAG generator, synthetic task specs, deterministic seeding
│   ├── agents/            # Mock agent orchestrators
│   ├── tools/             # Mock CPU, I/O, latency, and fault-injection tools
│   ├── resources/         # High-resolution process and system samplers
│   ├── correlation/       # Temporal join engine and attribution tier assigner
│   ├── storage/           # Append-only JSONL event stream and SQLite analytical ingest
│   ├── analysis/          # Sweep-line concurrency, critical path, statistical aggregations
│   └── visualization/     # Standalone Plotly HTML reports
├── tests/                 # Unit and integration test suites
├── experiments/           # Experiment drivers, configs, and verified results
└── .planning/             # GSD planning artifacts (PROJECT.md, REQUIREMENTS.md, ROADMAP.md, STATE.md)
```

## Quickstart

```bash
# Clone and setup environment
python -m venv .venv
source .venv/bin/activate  # Or on Windows: .\.venv\Scripts\Activate.ps1

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run test suite
pytest

# Run linting
ruff check .
```
