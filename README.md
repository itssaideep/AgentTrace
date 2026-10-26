# AgentTrace

AgentTrace is a Python research prototype for measuring synthetic agent
workloads, recording explicit workflow causality, and reporting resource
usage without pretending that shared process counters can be precisely split
between concurrent tasks.

## Why AgentTrace?

Agent workflows combine asynchronous model calls, tool execution, retries, and
dependency graphs. AgentTrace is designed to study those workflows with:

- **Explicit causal edges**: parent-child, `depends_on`, and retry links are
  emitted by the workflow rather than inferred from timestamps.
- **Monotonic timing**: durations use `time.monotonic_ns()`; UTC timestamps are
  retained only as human-readable run anchors.
- **Honest resource attribution**: overlapping spans are reported as shared
  aggregates unless a dedicated process or exclusive window provides stronger
  evidence.
- **Reproducibility**: configurations, seeds, environment information, and
  raw event streams are intended to support repeatable experiments.
- **Privacy by default**: payload capture is disabled by default and sensitive
  attribute names are redacted.

## Project status

The repository is currently at the **Milestone 1 scaffold** stage. The
following pieces are available today:

- Pydantic v2 trace and configuration models
- TOML configuration loading
- Platform capability probing with `psutil`
- JSONL trace schema and lifecycle validation
- CLI argument structure and a working `validate` command
- Smoke tests, linting, and static type checking

The tracer, workload executor, resource sampler, correlation engine, analysis
engine, and report generation are planned subsystems and are not complete yet.

## Requirements

- Python 3.11 or newer
- Windows, Linux, or WSL2

## Setup

Create and activate a virtual environment, then install the package with its
development dependencies:

```bash
python -m venv .venv

# Linux/macOS/WSL2
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

pip install -e ".[dev]"
```

Optional dependency groups:

```bash
pip install -e ".[viz]"       # Plotly reporting dependencies
pip install -e ".[baseline]"  # OpenTelemetry comparison dependencies
pip install -e ".[all]"       # All optional dependencies
```

## Usage

### Validate a trace

Trace files are append-only JSONL files with one JSON object per line. The
validator checks Pydantic schemas, run boundaries, matching span lifecycle
records, trace IDs, monotonic durations, duplicate records, and orphan events.

```bash
agenttrace validate path/to/trace.jsonl
```

The command prints a summary and returns a nonzero exit status when validation
fails. It can also be run without an installed console script:

```bash
python -m agenttrace.cli validate path/to/trace.jsonl
```

### Load the default configuration

```python
from agenttrace.config import RunConfig

config = RunConfig.from_toml("configs/default.toml")
print(config.workload.workload_type)
```

### Probe platform capabilities

The platform probe records clock, CPU, memory, I/O, network, Linux `/proc`,
PSI, cgroup, and eBPF capability information:

```bash
python scripts/probe_platform.py
```

Results are written to `experiments/results/capability_probe_<platform>.json`.
These result files are evidence for platform claims and should be regenerated
when the execution environment changes.

The `run`, `compare`, and `probe` console subcommands currently expose the
planned CLI surface while their full execution workflows are being built.

## Development checks

Run the project checks from the repository root:

```bash
pytest
ruff check .
mypy src tests scripts
python -m compileall -q src tests scripts
```

## Repository layout

```text
configs/                 Example TOML run configurations
docs/                    Architecture, schema, methodology, and ADRs
experiments/results/     Verified platform probe artifacts
scripts/                 Standalone platform and experiment utilities
src/agenttrace/
  agents/                Mock agent orchestration (planned)
  analysis/              Metrics and statistical analysis (planned)
  baselines/             Comparison instrumentation (planned)
  correlation/           Temporal joins and attribution (planned)
  instrumentation/       Tracing and context propagation (planned)
  resources/              Process and system sampling (planned)
  storage/                JSONL and SQLite storage (planned)
  tools/                  Synthetic CPU, I/O, and fault tools (planned)
  workloads/              Deterministic DAG workloads (planned)
  cli.py                 Command-line interface
  config.py              Pydantic configuration models
  schemas.py             Pydantic trace schemas
  validation.py          Offline JSONL trace validation
tests/                    Unit and smoke tests
.planning/                Requirements, roadmap, and project state
```

