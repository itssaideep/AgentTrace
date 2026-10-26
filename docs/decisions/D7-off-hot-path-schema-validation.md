# ADR D7: Off-Hot-Path Schema Validation with Pydantic v2

## Status
Accepted

## Context
Trace generation must minimize per-span latency and CPU overhead. While Pydantic v2 (compiled via Rust `pydantic-core`) is significantly faster than v1, validating full schema models on every span start/end in the hot loop can still introduce measurable overhead (e.g. 5–20 $\mu$s per event).

## Decision
1. Pydantic models define the single source of truth for the data model in `agenttrace.schemas`.
2. Strict Pydantic validation is executed during test suites, analytical ingest (JSONL to SQLite), and trace validation tools (`agenttrace validate`).
3. The hot execution path in the tracer outputs serialized dictionary structures or uses direct serialization, deferring full model reconstruction until ingest. Write-time validation overhead will be explicitly measured in M2 before committing to any in-line validation.

## Alternatives Considered & Rejected
1. **Validating every span with full Pydantic models on the hot path**:
   - *Rejected as default*: Risky for microsecond-scale spans; overhead must be characterized empirically first in M2.
2. **Unstructured dictionaries with no formal schemas**:
   - *Rejected because*: Unchecked schemas lead to silent field mismatches, type drift, and unmaintainable downstream analysis.
