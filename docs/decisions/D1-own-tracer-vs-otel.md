# ADR D1: Minimal Custom Tracer with OpenTelemetry-Compatible Data Model

## Status
Accepted

## Context
AgentTrace requires high-throughput, low-latency span emission for micro-tasks (down to 1–5 ms), explicit tracking of both `span_start` and `span_end` events for completeness checking, explicit non-tree DAG dependencies (`depends_on`), and complete control over serialization to quantify tracer overhead (Experiment 4).

## Decision
Implement our own minimal, zero-dependency core tracer in `agenttrace.instrumentation`, maintaining conceptual alignment with OpenTelemetry semantic conventions. OpenTelemetry's Python SDK is incorporated strictly as an optional baseline comparison arm in Experiment 4.

## Alternatives Considered & Rejected
1. **Adopting the official OpenTelemetry Python SDK as the core engine**:
   - *Rejected because*: The standard OTel SDK is heavyweight, incurs substantial per-span allocations and lock contention, batches exports asynchronously in a manner that obscures true overhead, lacks first-class `span_start` persistence for crash-completeness verification, and makes explicit DAG dependency tracking cumbersome (OTel links are non-causal annotations).
2. **Third-party agent observability SDKs (e.g., Langfuse, Phoenix)**:
   - *Rejected because*: Highly opinionated, network-bound (HTTP/REST endpoints), designed for prompt tracking rather than systems resource attribution, and introduce uncontrollable external dependencies.
