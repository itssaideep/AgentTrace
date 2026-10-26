# ADR D6: Explicit Causal Relations and Ground-Truth DAG Oracle

## Status
Accepted

## Context
Standard distributed tracing uses a single parent-child hierarchy (`parent_span_id`). In agent workloads, execution relationships are richer:
1. Structural nesting (e.g., an Agent step containing a Tool invocation).
2. Data or control flow dependencies (e.g., Task C cannot start until Tasks A and B complete, even though they share the same parent).
3. Retry linkages (e.g., Attempt 2 is a retry of Attempt 1).
Inferring causality purely from timestamp overlap or sequence is prone to false positives under concurrency.

## Decision
1. Record causality as three explicit, orthogonal relations on spans:
   - `parent_span_id`: Structural nesting.
   - `depends_on`: List of predecessor span IDs whose output or completion was explicitly required.
   - `retry_of`: The span ID of the prior failed attempt, paired with an integer `attempt` counter.
2. Synthetic workloads are generated from an explicit DAG specification (the Ground-Truth Oracle). Every recorded trace is formally verified against this oracle graph in Experiment 5 and unit tests.

## Alternatives Considered & Rejected
1. **Inferring dependencies post-hoc from timestamps**:
   - *Rejected because*: Concurrency makes chronological ordering ambiguous. Two independent parallel tasks will appear sequentially related or causally entangled purely by coincidence.
2. **Conflating parent-child and data dependencies**:
   - *Rejected because*: Causes directed acyclic graphs to be distorted into artificial deep trees, making critical-path analysis mathematically incorrect.
