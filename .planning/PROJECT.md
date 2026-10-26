# AgentTrace: Project Context & Scope

## 1. Problem Statement
Autonomous AI agent systems compose asynchronous LLM invocations, dynamic tool invocations (blocking I/O, heavy computation), and complex dependency graphs (sequential steps, fan-out/fan-in parallel tasks, retries). Existing observability tooling (e.g., standard APM, LangSmith, Phoenix) predominantly focuses on trace visualization, cost accounting, and LLM prompt/completion tracking. However, they lack:
1. Causal fidelity: Workflows often lack explicit dependency graphs, causing causality to be weakly inferred from timestamp overlap.
2. Honest resource attribution: Concurrently executed agent spans share process memory and CPU counters, leading tools to either ignore resource consumption or silently and erroneously subdivide process-level metrics.
3. Rigorous observer effect measurement: Tracing overhead itself perturbs micro-task durations and async event-loop scheduling.

AgentTrace is an instrumented research prototype that executes controlled, reproducible synthetic agent workloads, records explicit causality (DAG dependencies, parent-child, retries), samples process-level and system-level resource metrics, joins them on a nanosecond monotonic time base using honest attribution rules, and quantifies its own measurement overhead and physical limits.

## 2. Core Non-Negotiable Requirements
1. **Trustworthy timing**: Durations derive strictly from `time.monotonic_ns()`. One shared time base across threads and worker processes. UTC wall-clock timestamps are restricted to run-level anchoring.
2. **Explicit causality**: Parent-child, data dependencies (`depends_on`), and retry linkages (`retry_of`) are emitted directly by the workflow DAG generator, never inferred post hoc.
3. **No silent data loss**: Every started span terminates in an explicit status (`ok`, `error`, `timeout`, `cancelled`) or is detected and flagged as `incomplete`.
4. **Honest attribution**: Every resource metric carries a scope label (`process` vs `system`) and an attribution tier (Tiers 0–3). Overlapping metrics are never apportioned without direct hardware or kernel isolation.
5. **Strict reproducibility**: Master seed with isolated per-task deterministic PRNG streams; hardware and environment captured at run start; raw event streams preserved intact.
6. **Measurable overhead**: Zero-overhead no-op tracing mode; overhead quantified as a dedicated experimental arm (Experiment 4).
7. **Privacy by default**: Only metadata, sizes, and operational attributes are retained. Payload capture is strictly opt-in; canary secret injection tests verify zero leakage.

## 3. Technology Stack & Environment
- **Runtime**: Python 3.11+ (tested on Python 3.12.3 in WSL2 Ubuntu 24.04 and Python 3.13.14 on Windows host).
- **Core Libraries**: `psutil`, `pydantic` v2, standard library `tomllib`, `argparse`.
- **Analysis**: `numpy`, `pandas`, standard library `sqlite3`.
- **Quality Gates**: `ruff` (linter/formatter), `mypy` (strict static typing), `pytest`, `pytest-asyncio`, `hypothesis`.
- **Visuals**: Static self-contained HTML (Plotly) for offline reproducible review.
