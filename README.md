# AgentTrace

AgentTrace is an instrumented research prototype for running synthetic AI agent workloads, recording workflow-level causal traces with explicitly recorded dependencies, sampling process-level and system-level resource metrics on a shared monotonic clock, and enforcing scientifically defensible resource attribution without pretending that shared process counters can be arbitrarily split across concurrent tasks.

---

## Core Invariants & Architectural Principles

AgentTrace implements seven invariants designed to prevent common benchmarking fallacies:

1. **Trustworthy Timing**: Durations come strictly from `time.monotonic_ns()`. Clocks are verified shared across worker processes. UTC is used only as human-readable run anchors.
2. **Explicit Causality**: Parent-child, `depends_on`, and `retry_of` DAG relations are captured explicitly at runtime; causality is never inferred post hoc from timestamps.
3. **No Silent Data Loss**: Complete trace audit via `TraceCompletenessChecker` guarantees every started span is completed or isolated.
4. **Honest 4-Tier Attribution**: Prevents spurious attribution of process-level resources to concurrent tasks:
   - **Tier 0 (Context Window)**: Unattributed temporal background telemetry.
   - **Tier 1 (Exclusive Window)**: Only single active span running in process; counter deltas strictly bounded and attributed.
   - **Tier 2 (Direct Dedicated)**: Dedicated worker process/thread boundary counters.
   - **Tier 3 (Unsplit Concurrent Aggregate)**: Overlapping concurrent spans are grouped and reported unsplit; arbitrary division is forbidden.
5. **Strict Reproducibility**: Seed-isolated per-task PRNG streams (`derive_task_seed`) guarantee deterministic task parameters independent of asyncio scheduling order.
6. **Measurable Overhead**: Quantified observer effect via 4-arm ladder: NoOpTracer, Standard Logging, AgentTrace Buffered, AgentTrace + Sampler.
7. **Privacy by Default**: Payloads and prompts are excluded from traces by default. Canary secrets are scrubbed via `RedactionEngine`.

---

## Technical Report & Claims Ledger

- **Full Technical Report**: [`docs/technical-report.md`](file:///c:/Users/Sai%20Deep/Desktop/AgentTrace/docs/technical-report.md)
- **Claims Ledger & Verification Matrix**: [`.planning/STATE.md`](file:///c:/Users/Sai%20Deep/Desktop/AgentTrace/.planning/STATE.md)
- **Empirical Results Directory**: [`experiments/results/`](file:///c:/Users/Sai%20Deep/Desktop/AgentTrace/experiments/results/)

---

## Quickstart & Verification

### 1. Installation

Requires Python 3.11+ (tested on Windows 11 and Ubuntu 24.04 WSL2):

```bash
# Create virtual environment
python -m venv .venv

# Activate (Linux / WSL2)
source .venv/bin/activate

# Activate (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Install package with all dependencies (dev, viz, baseline)
pip install -e ".[all]"
```

### 2. Verify Fresh-Clone Reproduction

Run the automated reproduction verification script (runs linting, typing, 72 unit tests, empirical artifact integrity, and demo workflow):

```bash
python scripts/verify_reproduction.py
```

### 3. Run End-to-End Demo Workflow

Generates synthetic workloads, executes with causal tracing and resource sampling, performs analytical graph solves, and generates an interactive offline HTML report:

```bash
python scripts/demo_workflow.py
```

---

## CLI Reference

AgentTrace exposes a unified command-line interface:

### `agenttrace analyze`
Performs sweep-line concurrency analysis, critical path PERT/CPM graph solving, and latency distribution calculation:
```bash
agenttrace analyze experiments/results/demo_par_trace.jsonl
```

### `agenttrace compare`
Performs differential multi-run analysis comparing makespans, speedup, concurrency, critical path changes, and per-task deltas:
```bash
agenttrace compare run1.jsonl run2.jsonl -o comparison_report.md
```

### `agenttrace report`
Generates a self-contained, interactive offline HTML report with Gantt timeline, concurrency step curves, synchronized resource subplots, and span table:
```bash
agenttrace report experiments/results/demo_par_trace.jsonl -o report.html
```

### `agenttrace validate`
Audits a trace stream for schema compliance, lifecycle bounds, and causal completeness:
```bash
agenttrace validate experiments/results/demo_par_trace.jsonl
```

### `agenttrace probe`
Probes platform capabilities (clock resolution, PSI pressure stalls, cgroup v2, eBPF availability):
```bash
agenttrace probe
```

---

## Experimental Suite

All empirical findings in the Technical Report can be reproduced with dedicated runners:

```bash
# E1: Sequential vs Parallel Scaling Limits (speedup and parallel efficiency)
python experiments/scripts/run_exp1_seq_vs_par.py

# E3: Concurrency Scaling & Queue Wait Saturation
python experiments/scripts/run_exp3_concurrency_scaling.py

# E4: Instrumentation Overhead & Observer Effect (4-arm ladder)
python experiments/scripts/run_exp4_tracer_overhead.py

# E6: Measurement Limits & Nyquist Aliasing Analysis
python experiments/scripts/run_exp6_measurement_limits.py
```

---

## Repository Layout

```text
configs/                 Example TOML run configurations
docs/                    Architecture, ADRs (D1–D7), and Technical Report
  decisions/             Architectural Decision Records
  technical-report.md    Publication-grade technical report
experiments/
  results/               Permanent empirical result artifacts (*.json)
  scripts/               Experimental execution drivers (E1, E3, E4, E6)
scripts/
  demo_workflow.py       End-to-end demo execution workflow
  verify_reproduction.py Automated reproduction gate script
  probe_platform.py      Platform capability & clock resolution probe
src/agenttrace/
  agents/                AsyncAgentExecutor, MockModel, and queue wait profiling
  analysis/              Sweep-line concurrency, critical path PERT/CPM, compare
  correlation/           CorrelationEngine enforcing 4-tier honest attribution
  instrumentation/       CoreTracer, NoOpTracer, MonotonicClock, RedactionEngine
  resources/             ResourceSampler daemon thread (CPU, RSS, I/O, jitter)
  storage/               TraceWriter (append-only JSONL) and SQLiteTraceStore
  tools/                 Synthetic calibrated CPU, synced I/O, latency, faults
  visualization/         Gantt timeline, concurrency curves, offline HTML reports
  workloads/             TaskSpec, WorkloadDAG, seed-isolated WorkloadGenerator
  cli.py                 CLI entrypoint (analyze, compare, report, validate)
tests/                   Unit tests for all subsystems (72 tests, 100% pass)
.planning/               PROJECT.md, REQUIREMENTS.md, ROADMAP.md, STATE.md
```

---

## License

MIT License. Designed and evaluated for reproducible systems research.
