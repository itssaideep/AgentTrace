# AgentTrace: Trace Data Model & Schema Specification

## Schema Version: 1.0.0

All events in AgentTrace are serialized as JSON Lines (`.jsonl`). Each record is an autonomous, self-describing JSON object conforming to Pydantic v2 schemas defined in `src/agenttrace/schemas.py`.

---

## 1. Common Envelope (`BaseRecord`)

Every record carries standard timing and schema metadata:

| Field | Type | Description |
| :--- | :--- | :--- |
| `schema_version` | `str` | Semantic version of trace format (e.g., `"1.0.0"`) |
| `record_type` | `str` | Record discriminator: `run_start`, `span_start`, `span_end`, `span_event`, `resource_sample`, `run_end` |
| `timestamp_utc_iso` | `str` | ISO 8601 UTC timestamp for human reference |
| `timestamp_monotonic_ns` | `int` | Nanoseconds from host monotonic clock (`time.monotonic_ns()`). Used for all duration calculations. |

---

## 2. Record Types

### 2.1 `run_start`
Emitted at the initiation of an experiment run.
- `run_id`: Unique string identifier (`run_<uuid>`).
- `experiment_name`: Name of experiment (e.g. `"exp1_seq_vs_par"`).
- `config_hash`: SHA-256 hash of configuration TOML.
- `environment`: Snapshot of host CPU count, architecture, Python version, memory total, git commit hash, and dirty status.
- `clock_anchor`: Initial pairing of `utc_iso`, `monotonic_ns`, and `perf_counter_ns`.

### 2.2 `span_start`
Emitted the instant a span begins execution.
- `trace_id`: Identifier for the root workflow execution.
- `span_id`: Unique span identifier.
- `parent_span_id`: Parent span ID for structural nesting (or `null` if root).
- `task_id`: Identifier of the logical task within the workload DAG.
- `agent_id`: Identifier of the agent entity executing the task.
- `operation_name`: Descriptive operation name (e.g. `"tool_cpu_matrix"`).
- `operation_type`: Category (`agent_step`, `llm_call`, `tool_exec`, `internal`).
- `process_id`: OS process ID.
- `thread_id`: OS thread ID.
- `depends_on`: List of predecessor `span_id`s required by data/control dependency.
- `attempt`: 1-indexed retry attempt number.
- `retry_of`: Span ID of the prior failed attempt (or `null`).
- `queue_wait_ms`: Time spent waiting on semaphore queue before execution began.
- `attributes`: Key-value metadata dictionary (payload-free by default).

### 2.3 `span_end`
Emitted upon completion, error, timeout, or cancellation of a span.
- `trace_id`: Trace identifier.
- `span_id`: Span identifier matching a previous `span_start`.
- `start_monotonic_ns`: Copied start timestamp for fast non-stateful duration audits.
- `duration_ms`: Exact duration derived strictly as `(end_monotonic_ns - start_monotonic_ns) / 1e6`.
- `status`: Execution outcome: `"ok"`, `"error"`, `"timeout"`, `"cancelled"`. (Note: `"incomplete"` is derived by the post-run checker if `span_end` is missing).
- `error_type`: Exception class name if failed.
- `error_message`: Sanitized error description.

### 2.4 `run_end`
Emitted when an experiment run finishes. Interrupted traces may omit the
derived summary, but must still identify the run:
- `run_id`: Identifier matching the `run_start` record.
- `summary`: Optional derived `RunSummary` object.

### 2.5 `resource_sample`
Emitted periodically by the resource sampler daemon.
- `run_id`: Run identifier.
- `sample_index`: Monotonically increasing sample counter.
- `sample_duration_us`: Time taken by the sampler to query OS counters (observer effect tracking).
- `process_metrics`: List of per-process metrics:
  - `process_id`: PID.
  - `cpu_user_time_s`: Cumulative user mode CPU seconds.
  - `cpu_system_time_s`: Cumulative kernel mode CPU seconds.
  - `rss_bytes`: Resident set size in bytes.
  - `vms_bytes`: Virtual memory size in bytes.
  - `ctx_switches_voluntary`: Voluntary context switches.
  - `ctx_switches_involuntary`: Preemptions.
  - `io_read_bytes` / `io_write_bytes`: Cumulative process disk counters.
- `system_metrics`: System-wide CPU utilization, memory used/total, network bytes sent/recv.

---

## 3. Attribution Tiers (D5)

Every correlated span-to-resource record assigned during analysis carries one of four explicit tiers:
1. `tier_0_context`: Samples overlapping the span window, reported without causal attribution.
2. `tier_1_exclusive`: Single active span in the process; deltas over the window are bounded by sampling interval.
3. `tier_2_direct`: Dedicated worker process/thread boundaries measured directly.
4. `tier_3_aggregate`: Concurrent overlapping spans sharing an aggregate delta, reported unsplit.
