# ADR D5: Tiered Resource Attribution with Honest Confidence Labels

## Status
Accepted

## Context
When multiple asynchronous agent spans run concurrently in the same process, OS-level process counters (e.g., cumulative CPU user time, RSS increase) cannot be physically separated between overlapping spans. Many existing tools either ignore resource metrics entirely or silently divide the aggregate counter equally among active tasks.

## Decision
Adopt a strict 4-tier resource attribution model where every span-to-resource mapping carries an explicit methodology label and confidence bound:
- **Tier 0 (Context Only)**: The resource samples that overlapped the span duration, reported purely as background context with zero attribution claimed.
- **Tier 1 (Exclusive Window)**: The span ran in complete isolation within the process (no other active spans). Counter deltas over its execution window are defensibly attributable to this span within the sampling interval error bound ($\pm \Delta t_{\text{sample}}$).
- **Tier 2 (Direct Isolation)**: The span ran in a dedicated OS worker process or dedicated thread with dedicated hardware/OS counters measured at span boundaries.
- **Tier 3 (Aggregate Only)**: Spans overlapped concurrently. The total resource delta over the concurrent window is reported against the set of active spans and **never silently divided or apportioned**.

## Alternatives Considered & Rejected
1. **Evenly dividing resource deltas among overlapping spans**:
   - *Rejected because*: Highly deceptive. An I/O-bound sleeping task running alongside a CPU-heavy data task would be falsely assigned 50% of the CPU consumption.
2. **Statistical regression attribution (e.g. Shapley values / linear models)**:
   - *Rejected for v1*: Requires massive datasets, strong independence assumptions, and introduces model uncertainty. It remains an exploratory research topic rather than a sound foundational measurement rule.
