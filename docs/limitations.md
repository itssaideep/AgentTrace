# AgentTrace: System Limitations & Privacy Boundaries

## 1. Physical Measurement Limitations

### 1.1 Sampling Interval Aliasing (Short-Span Blind Spot)
A periodic sampler operating at interval $\Delta t_{\text{sample}}$ (e.g. 50 ms) cannot observe intra-interval resource fluctuations. If a tool executes in 5 ms and completes between two sampling ticks, its immediate CPU or memory delta is indistinguishable from zero or folded into the surrounding window. 
- *Mitigation*: We rely on cumulative counters (cumulative user/system CPU seconds, total bytes read/written) rather than instantaneous rates. Furthermore, Experiment 6 explicitly characterizes this boundary.

### 1.2 Concurrency Attribution Impossibility (Tier 3)
When multiple tasks run concurrently within the same OS process and event loop, standard operating systems do not provide per-coroutine hardware or CPU counter separation. Dividing a 100 ms process CPU burst evenly among 5 active coroutines is statistically dishonest.
- *Mitigation*: AgentTrace assigns `tier_3_aggregate` to concurrent overlapping spans, reporting aggregate consumption without arbitrary division.

### 1.3 Page Cache & Storage I/O Counter Caveats
Modern OS kernels buffer file writes in the page cache. A tool writing 64 KB of data may return in microseconds without dirty pages being immediately flushed to non-volatile storage.
- *Mitigation*: Process-level `io_counters()` are documented as tracking logical `write()` syscall volume (`write_chars` on Linux), while physical disk commits require explicit `os.fsync()`.

### 1.4 Network Attribution Scope
In user space without root eBPF socket filters, per-process socket attribution is not exposed by standard OS interfaces. Network metrics are strictly labeled as **system-wide only**.

### 1.5 Synthetic Workloads vs Production LLMs
Synthetic workloads use calibrated latency, deterministic token generators, and synthetic compute kernels. While this enables exact reproducibility, it does not capture real-world LLM non-determinism (variable token generation times, network jitter to cloud APIs, prompt-dependent hallucinations). All findings must be explicitly framed as synthetic benchmark results.

---

## 2. Privacy & Security Boundaries

### 2.1 Allowlist Attribute Capture
To prevent accidental data exfiltration or credential leaks:
- Span attributes default to execution metadata (durations, task IDs, status codes, payload sizes).
- Payload recording is strictly opt-in (`record_payloads = false` by default).
- Key names containing sensitive tokens (`"api_key"`, `"secret"`, `"password"`, `"token"`, `"authorization"`) are automatically redacted before disk serialization.

### 2.2 Permissions
AgentTrace runs entirely with standard, unprivileged user permissions. It does not require `root` or `sudo` access, eBPF module loading, or system firewall modifications.
