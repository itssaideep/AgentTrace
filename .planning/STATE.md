# AgentTrace: Project State & Claims Ledger

## Active Status
- **Current Milestone**: M5 (Analysis & Comparative Engine)
- **Status**: COMPLETED
- **Last Updated**: 2026-10-28

## Verification Summary
| Check | Windows (`.venv`, Py 3.13.14) | Linux WSL2 (`python3`, Py 3.12.3) | Notes |
| :--- | :--- | :--- | :--- |
| Test Suite (`pytest`) | PASSED (68 passed in 2.51s) | PASSED (68 passed in 4.51s) | 100% test pass rate across 16 test modules |
| Linting & Formatting (`ruff`) | PASSED (0 errors) | PASSED (0 errors) | Codebase clean, formatted |
| Static Typing (`mypy`) | PASSED (0 errors in 55 files) | PASSED (0 errors) | Strict type checking compliant |
| Platform Capability Matrix | VERIFIED | VERIFIED | `capability_probe_{windows,linux}.json` |
| Tracer Overhead Microbench | VERIFIED | VERIFIED | `tracer_overhead_microbench.json` |

## Empirical Benchmarks
- Tracer Microbenchmark: `experiments/results/tracer_overhead_microbench.json`
- Windows Platform Probe: `experiments/results/capability_probe_windows.json`
- Linux Platform Probe: `experiments/results/capability_probe_linux.json`

## Claims Discipline & Verification Protocol
- **Strict Rule**: No performance claim, overhead number, or attribution metric may be asserted in documentation, reports, or research summaries without a permanent link to an underlying verified result artifact in `experiments/results/`.
- All hypotheses must be explicitly phrased as testable empirical questions rather than established facts.

## Claims Ledger
| Claim ID | Milestone | Statement | Status | Supporting Artifact |
| :--- | :--- | :--- | :--- | :--- |
| CLM-M1-01 | M1 | Environment supports Python 3.11+ on both native host (3.13.14) and WSL2 (3.12.3) | VERIFIED | `experiments/results/capability_probe_linux.json`, `experiments/results/capability_probe_windows.json` |
| CLM-M1-02 | M1 | Schema serialization/deserialization has 100% field roundtrip fidelity | VERIFIED | `tests/unit/test_smoke.py::test_schema_roundtrip` |
| CLM-M1-03 | M1 | Monotonic clock step resolution is sub-microsecond on host | VERIFIED | Windows: 200–300 ns, WSL2: 126–141 ns (`probe_platform.py`) |
| CLM-M1-04 | M1 | Monotonic clock is strictly shared and comparable across child worker processes | VERIFIED | Windows: `true` (349 ms delta), Linux: `true` (1.25 ms delta) |
| CLM-M1-05 | M1 | Linux PSI (/proc/pressure/cpu) and cgroup v2 are active on WSL2 kernel | VERIFIED | `experiments/results/capability_probe_linux.json` (`psi_cpu_sample` active) |
| CLM-M1-06 | M1 | eBPF requires elevated root/CAP_BPF privileges in WSL2 and is unjustified for v1 | VERIFIED | `experiments/results/capability_probe_linux.json` (`ebpf.verdict = FEASIBLE_WITH_ROOT`, `has_bpftool = false`) |
| CLM-M1-07 | M1 | Network socket attribution is physically unavailable in user space without eBPF | VERIFIED | System-wide scope only (`probe_platform.py`) |
| CLM-M2-01 | M2 | NoOpTracer median overhead is sub-microsecond (~500 ns) with >1,300,000 spans/sec throughput | VERIFIED | `experiments/results/tracer_overhead_microbench.json` |
| CLM-M2-02 | M2 | Fast Dict emission (ADR D7) reduces span write latency compared to strict on-write Pydantic validation (41.3 us vs 45.3 us median) | VERIFIED | `experiments/results/tracer_overhead_microbench.json` |
| CLM-M2-03 | M2 | TraceCompletenessChecker detects unclosed spans and causal graph breakage with 100% precision | VERIFIED | `tests/unit/test_completeness.py` |
| CLM-M2-04 | M2 | RedactionEngine enforces privacy by default, redacting canary secrets from span attributes | VERIFIED | `tests/unit/test_redaction.py::test_canary_secret_leak_prevention` |
| CLM-M3-01 | M3 | Seed-isolated PRNG streams guarantee identical task parameters independent of scheduling order | VERIFIED | `tests/unit/test_workload_generator.py::test_seed_isolation_and_determinism` |
| CLM-M3-02 | M3 | Kahn's algorithm validates acyclicity and derives topological execution order | VERIFIED | `tests/unit/test_workload_generator.py::test_cycle_detection_in_dag` |
| CLM-M3-03 | M3 | OracleVerifier achieves 100% edge recall and catches causal timing violations | VERIFIED | `tests/unit/test_oracle.py::test_oracle_verifier_matches_nominal_execution` |
| CLM-M3-04 | M3 | AsyncAgentExecutor tracks semaphore queue wait and links retries with retry_of | VERIFIED | `tests/unit/test_executor.py::test_executor_fault_and_retry_linkage` |
| CLM-M4-01 | M4 | ResourceSampler daemon tracks process CPU, RSS, context switches, disk I/O, jitter, and probe overhead duration | VERIFIED | `tests/unit/test_sampler.py::test_sampler_execution_and_metrics` |
| CLM-M4-02 | M4 | CorrelationEngine enforces ADR D5 attribution tiers: Tier 1 Exclusive Window bounded counters, Tier 3 Unsplit Aggregate for concurrent overlapping spans | VERIFIED | `tests/unit/test_correlation.py::test_correlation_exclusive_window` |
| CLM-M4-03 | M4 | Probe execution overhead and sampling jitter are quantified per-sample rather than hidden | VERIFIED | `tests/unit/test_sampler.py::test_sampler_jitter_and_probe_duration` |
| CLM-M5-01 | M5 | Sweep-line concurrency algorithm matches hand-calculated golden trace step-function integration with zero error | VERIFIED | `tests/unit/test_concurrency.py::test_concurrency_parallel_overlap_golden` |
| CLM-M5-02 | M5 | Critical path PERT/CPM solver identifies bottleneck path, earliest/latest bounds, and non-zero slack on parallel branches | VERIFIED | `tests/unit/test_critical_path.py::test_critical_path_diamond_graph` |
| CLM-M5-03 | M5 | SQLite analytical store ingests JSONL streams with relational indices and powers cross-run differential comparison | VERIFIED | `tests/unit/test_sqlite_and_compare.py::test_compare_runs_logic` |
| CLM-M5-04 | M5 | Statistical distribution engine enforces sample size gating (warning on N < 5) to prevent over-interpreting low-N percentiles | VERIFIED | `tests/unit/test_metrics.py::test_distribution_small_sample_warning` |
