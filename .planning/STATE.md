# AgentTrace: Project State & Claims Ledger

## Active Status
- **Current Milestone**: M2 (Core Tracing Subsystem)
- **Status**: COMPLETED
- **Last Updated**: 2026-10-28

## Verification Summary
| Check | Windows (`.venv`, Py 3.13.14) | Linux WSL2 (`python3`, Py 3.12.3) | Notes |
| :--- | :--- | :--- | :--- |
| Test Suite (`pytest`) | PASSED (34 passed in 1.37s) | PASSED (34 passed) | Clock, context, redaction, tracer, writer, completeness |
| Linting & Formatting (`ruff`) | PASSED (0 errors) | PASSED (0 errors) | Codebase clean |
| Static Typing (`mypy`) | PASSED (0 errors in 31 files) | PASSED (0 errors) | Strict type checking compliant |
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
