# AgentTrace: Project State & Claims Ledger

## Active Status
- **Current Milestone**: M1 (Requirements, Environment & Feasibility)
- **Status**: COMPLETED
- **Last Updated**: 2026-10-26

## Verification Summary
| Check | Windows (`.venv`, Py 3.13.14) | Linux WSL2 (`python3`, Py 3.12.3) | Notes |
| :--- | :--- | :--- | :--- |
| Editable Install (`pip install -e ".[dev]"`) | PASSED | PASSED | Succeeded on both hosts |
| Linting (`ruff check .`) | PASSED (0 errors) | PASSED (0 errors) | Formatting & typing compliant |
| Unit Smoke Tests (`pytest`) | PASSED (5 passed in 0.87s) | PASSED (5 passed in 0.85s) | Schemas, CLI, TOML config roundtrips |
| Platform Capability Matrix | VERIFIED | VERIFIED | Stored empirical probe outputs in `experiments/results/` |

## Empirical Probes
- Windows Probe: `experiments/results/capability_probe_windows.json`
- Linux WSL2 Probe: `experiments/results/capability_probe_linux.json`

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
