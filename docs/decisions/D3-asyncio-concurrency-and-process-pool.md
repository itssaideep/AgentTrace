# ADR D3: Asyncio Orchestration with Dedicated Worker Pools

## Status
Accepted

## Context
Real-world AI agent frameworks orchestrate network calls (LLM APIs) asynchronously, execute heavy data processing (CPU-bound) in worker processes, and perform local disk operations using blocking I/O threads. If CPU-bound work runs inside the main async event loop, the entire loop freezes, distorting every monotonic duration and timer in the process.

## Decision
1. Orchestrate agent workflows and fan-out/fan-in tasks using Python's `asyncio` loop.
2. Execute CPU-intensive synthetic tools via a `ProcessPoolExecutor` (separate OS processes).
3. Execute blocking file I/O operations in a thread pool (`asyncio.to_thread` / `ThreadPoolExecutor`).
4. Propagate trace context (`trace_id`, `parent_span_id`, task metadata) across process boundaries via explicit parameter passing.

## Alternatives Considered & Rejected
1. **Multi-threading only**:
   - *Rejected because*: The Python Global Interpreter Lock (GIL) serializes CPU-bound bytecode execution across threads, rendering true CPU concurrency benchmarks meaningless and severely distorting monotonic latency.
2. **Synchronous multi-process only (e.g. Celery / multiprocessing queue)**:
   - *Rejected because*: Modern agent frameworks (LangGraph, AutoGen, CrewAI) are inherently async-first. Eliminating asyncio would make the synthetic agent testbed completely unrepresentative of realistic agent architectures.
