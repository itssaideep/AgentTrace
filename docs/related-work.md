# Related Work & Landscape Analysis

*Milestone 1 Baseline: No claims of novelty are asserted at this stage. This document contextualizes AgentTrace against existing distributed tracing, agent observability, kernel profiling, and workload characterization literature.*

---

## 1. Landscape Comparison Matrix

| System / Field | Focus & Scope | Causal Model | Resource Attribution | Observer Effect Quantified? | Completeness Guarantees |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Dapper / Zipkin / Jaeger** | Microservices, distributed network RPCs | Parent-child spans propagated via HTTP/gRPC headers | None (infrastructure metrics collected separately via Prometheus/host agents) | Head-based sampling (e.g. 0.01% sample rate to mitigate overhead) | Lossy by design (probabilistic sampling) |
| **OpenTelemetry (OTel)** | Vendor-neutral industry standard for traces, metrics, logs | Hierarchical parent-child spans; span links (weak causality) | Process/host metrics emitted as independent metric timeseries; no automatic span attribution | High SDK overhead for fine-grained spans; overhead rarely treated as an explicit experimental arm | Best-effort; batch processors drop events on queue overflow |
| **OTel GenAI Semantic Conventions** | Standardized attributes for LLM calls (`gen_ai.system`, token counts) | Parent-child workflow spans | None (focus on token billing and latency) | Not quantified | Best-effort |
| **LangSmith / Langfuse / Phoenix** | Application-level LLM and agent observability platforms | Execution tree of prompts, agent runs, and tool calls | API cost and token accounting; no OS/process resource attribution | Substantial (HTTP payload serialization per run; live dashboard overhead) | Spans may be lost if background HTTP worker fails or process crashes |
| **Linux `perf` / eBPF (BCC, bpftrace)** | Kernel and hardware performance counters | Stack traces and call chains (inferential causality from program counter) | Process, thread, and cgroup hardware counters (cycles, instructions, cache misses, context switches) | Low overhead (nanoseconds in kernel), but high setup complexity; requires root privileges | Kernel buffers drop on high-frequency ring buffer overflow |
| **Agent Workload Characterization Literature** | Benchmark suites (SWE-bench, GAIA, AgentBench) | Task success / benchmark score | None or coarse wall-clock makespan | Ignored | Evaluates task correctness, not execution traces |
| **AgentTrace (This Project)** | Empirical research testbed for synthetic agent workflows | **Explicit DAG dependencies (`depends_on`, `retry_of`, parent-child) verified against oracle** | **Honest tiered attribution (Tiers 0–3); monotonic nanosecond process/system sampling; no silent splitting** | **Dedicated experimental arm (E4); zero-overhead no-op mode; event-loop lag probe** | **Zero silent loss: spans tracked through start/end; completeness checker flags missing ends** |

---

## 2. Thematic Analysis of Adjacent Fields

### 2.1 Distributed Tracing (Dapper, OpenTelemetry)
- **Strengths**: Established standard vocabulary (trace, span, context propagation), ubiquitous wire protocols (W3C TraceContext).
- **Gaps for Agent Systems**:
  - Focuses on synchronous or request-response RPCs across network boundaries.
  - Causality in agent workflows is dynamic and non-tree-like: a task may depend on multiple asynchronous predecessor tasks (`depends_on` directed acyclic graphs). Standard `parent_span_id` enforces a strict tree, while span links are typically non-causal annotations.
  - Head-based sampling drops the vast majority of traces to protect production systems, which is incompatible with scientific workload characterization where every execution event must be accounted for.

### 2.2 LLM & Agent Observability (LangSmith, Langfuse, Phoenix, OpenInference)
- **Strengths**: Domain-specific abstractions for prompts, token usage, embeddings, and agent chain-of-thought steps.
- **Gaps for Systems Research**:
  - Prioritize developer user experience, live web dashboards, and prompt debugging over low-level systems telemetry.
  - Complete absence of OS-level and hardware resource attribution (CPU time, RSS growth, I/O wait, context switching).
  - Heavy serialization and network export payloads perturb micro-benchmarks, creating severe observer effects.

### 2.3 Kernel Profiling & Tracing (Linux `perf`, eBPF)
- **Strengths**: Microsecond-accurate hardware counter accounting; kernel-level attribution across cgroups and threads.
- **Gaps for Agent Developers**:
  - Requires root privileges (`CAP_SYS_ADMIN`), custom kernel headers, and complex compilation toolchains (as verified in our WSL2 capability probe).
  - Lacks high-level workflow context: a thread context switch cannot be easily mapped back to a specific LLM agent's sub-goal or tool invocation without extensive user-space uprobe instrumentation.

### 2.4 Agent Workload Characterization Literature
- **Current State**: Academic research on AI agents predominantly evaluates reasoning capability, tool-use correctness, and benchmark completion rates (e.g., SWE-bench, AgentBench, WebArena).
- **Open Questions**: There is sparse empirical literature systematically characterizing how agent concurrency patterns impact systems resources, where event-loop bottlenecks occur, and how resource attribution should be handled when multiple agent tasks overlap concurrently in the same process.
