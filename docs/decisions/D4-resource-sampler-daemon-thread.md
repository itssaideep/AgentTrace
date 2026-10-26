# ADR D4: Daemon Thread Resource Sampler with Explicit Jitter Tracking

## Status
Accepted

## Context
Process and system resource counters (CPU time, memory RSS, disk I/O, context switches) must be periodically sampled alongside the execution trace on the exact same monotonic time base.

## Decision
1. Implement the initial resource sampler as a background Python daemon thread using `psutil`.
2. Explicitly measure and record probe execution duration (`sample_duration_us`) and sampling interval jitter on every tick to monitor the observer effect.
3. Design the sampler interface so it can be transitioned to an independent OS process if GIL contention during M4/M7 demands it.

## Alternatives Considered & Rejected
1. **Out-of-process sampler daemon from day 1**:
   - *Rejected because*: An external process requires cross-process IPC (pipes or shared memory), process discovery, and clock anchoring synchronization, adding substantial complexity before baseline feasibility is proven.
2. **Inline per-span sampling**:
   - *Rejected because*: Querying `psutil` or `/proc` on every `span_start` and `span_end` adds massive overhead (~100–500 $\mu$s per call), completely destroying micro-span timing.
