# AgentTrace: Experimental Methodology & Scientific Protocols

## 1. Principles of Empirical Rigor

To prevent common pitfalls in systems and agent benchmarking, AgentTrace enforces five core experimental protocols:

### 1.1 Interleaved Execution (ABAB Ordering)
Never execute experimental conditions in contiguous blocks (e.g. all Condition A followed by all Condition B). Host machine thermal throttling, background OS maintenance tasks, and dynamic memory fragmentation can falsely penalize the second block. Conditions are strictly interleaved (ABAB or randomized block design).

### 1.2 Discarding Warm-Up Runs
The first execution of each condition is designated as a warm-up cycle and discarded from analysis. This avoids JIT/import overhead, cold OS page faults, and initial disk caching skew.

### 1.3 Deterministic Seeding and Decoupled RNG
A single master seed initializes the experiment. Each task in a workload derives its own independent PRNG stream keyed by `hash(master_seed, task_id)`. This guarantees that task arguments, artificial latency delays, and injected errors remain 100% identical regardless of the order in which asynchronous tasks are scheduled by the event loop.

### 1.4 Statistical Reporting Rules
- Avoid reporting simple arithmetic means for skewed distributions (such as latency).
- Report medians accompanied by Interquartile Ranges (IQR) or 95% bootstrap confidence intervals.
- Tail percentiles ($p95, p99$) are reported only if the sample size satisfies $N \ge 100$.
- Report run-to-run variance across independent repetitions ($R \ge 5$).

### 1.5 Strict Claims Discipline
No numerical value, percentage speedup, or overhead metric may appear in project documentation or reports unless it links directly to a serialized result artifact in `experiments/results/`.

---

## 2. Standardized Experiment Protocols

### Experiment 1: Sequential vs Parallel Scaling
- **Objective**: Quantify the latency and throughput speedup of concurrent fan-out vs sequential execution across workload types.
- **Independent Variables**: Execution mode (`sequential`, `parallel`), Workload type (`latency_simulated`, `cpu_intensive`, `mixed`).
- **Controlled Variables**: Total task count ($N=50$), task parameters, host background load.
- **Metrics**: Makespan (ms), speedup ($S = T_{\text{seq}} / T_{\text{par}}$), parallel efficiency ($E = S / C$), peak RSS, process CPU time, observed concurrency profile.

### Experiment 4: Instrumentation Overhead
- **Objective**: Measure the exact cost introduced by tracing and sampling.
- **Arms**:
  1. `No-op`: Pure workload execution with a zero-overhead dummy tracer.
  2. `Basic Logger`: Simple text-line logger writing to a file.
  3. `OpenTelemetry SDK`: Standard OTel Python SDK with batch JSON file exporter.
  4. `AgentTrace`: Buffered custom tracer (10 ms flush).
  5. `AgentTrace + Sampler`: Tracer with background sampler at 50 ms and 10 ms intervals.
- **Metrics**: Total makespan delta, per-span nanosecond cost, peak RSS, event-loop lag probe (measuring delay on a 1 ms sleep timer).

### Experiment 3: Concurrency Saturation & Queueing
- **Objective**: Identify the saturation point of the host machine and measure the proportion of task lifetime spent waiting in semaphore queues.
- **Independent Variable**: Concurrency limit $C \in \{1, 2, 4, 8, 12, 16, 24, 32\}$.
- **Metrics**: Throughput (tasks/sec), queue wait time (`queue_wait_ms`), span execution time, voluntary context switches, CPU utilization knee.
