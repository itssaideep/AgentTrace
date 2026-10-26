# Platform Capability Matrix

*Last empirically verified: 2026-10-26*  
*Sources: `experiments/results/capability_probe_linux.json`, `experiments/results/capability_probe_windows.json`*

## Summary of Environments Tested
1. **Linux (WSL2 Ubuntu 24.04 LTS)**: Kernel `6.6.87.2-microsoft-standard-WSL2`, Python `3.12.3`, x86_64, 16 logical cores.
2. **Windows 11 Host**: Build `10.0.26220`, Python `3.13.14`, AMD64, 16 logical cores.

---

## Detailed Metric Capability & Availability

| Metric / Capability | Linux WSL2 Status | Windows Status | How Obtained | Caveats & Attributability |
| :--- | :--- | :--- | :--- | :--- |
| **Monotonic Clock Resolution** | 126–141 ns | 200–300 ns | `time.monotonic_ns()` | Sub-microsecond step resolution. Monotonic durations never slip backward on either OS. |
| **Cross-Process Monotonic Clock** | **Identical & Shared** (`delta: 1.25 ms`) | **Identical & Shared** (`delta: 349 ms`) | Child worker process pipe sync | Verified empirically: `parent_before <= child <= parent_after`. Worker processes share the exact same monotonic time base. |
| **Process CPU Times (User/Sys)** | Available (`user`, `system`) | Available (`user`, `system`) | `psutil.Process().cpu_times()` | Millisecond/tick resolution. On Linux, `children_user/children_system` available after waitpid. |
| **Context Switches** | Available (`voluntary` & `involuntary`) | Partial (`voluntary` only, involuntary=0) | `psutil.Process().num_ctx_switches()` | Linux tracks involuntary preemptions due to CPU contention. Windows does not expose thread preemptions to user-space process counters. |
| **Process Memory (RSS / VMS)** | Available (`rss`, `vms`, `shared`) | Available (`rss`, `vms`) | `psutil.Process().memory_info()` | RSS measures resident physical pages. `shared` is uniquely available on Linux (`/proc/self/statm`). |
| **System CPU & Memory** | Available | Available | `psutil.cpu_times()`, `psutil.virtual_memory()` | System-wide scope only. Cannot be apportioned to individual async spans without isolation. |
| **Storage I/O Counters** | Available (`read_bytes`, `write_bytes`, `read_chars`, `write_chars`) | Available (`read_bytes`, `write_bytes`, `other_bytes`) | `psutil.Process().io_counters()` | **Major Caveat**: Page cache buffers writes. In WSL2 / Linux, `write_chars` reflects logical `write()` syscall volume, while `write_bytes` reflects physical disk block commits (only incremented when page cache flushes or `os.fsync()` is called). |
| **Network Counters** | Available (System-wide) | Available (System-wide) | `psutil.net_io_counters()` | **Scope: System-wide only**. User-space processes cannot attribute network packets to specific agent spans without eBPF socket filters or cgroup net_cls tagging. |
| **Linux `/proc/self/stat`** | Available (`True`) | Not Applicable | Direct filesystem read | Exposes exact kernel jiffies, priority, scheduling policies. |
| **Linux `/proc/self/io`** | Available (`True`) | Not Applicable | Direct filesystem read | Kernel-level accounting for `rchar`, `wchar`, `syscr`, `syscw`, `read_bytes`, `write_bytes`, `cancelled_write_bytes`. |
| **Linux PSI (Pressure Stall Information)** | Available (`True`) | Not Applicable | `/proc/pressure/{cpu,io,memory}` | Real-time saturation pressure. Verified on WSL2 kernel: exposes `some avg10/avg60/avg300` stalls. |
| **Linux cgroup v2** | Available (`True`) | Not Applicable | `/sys/fs/cgroup/` | Unified hierarchy mounted. Enables container-level resource bounding. |

---

## eBPF Feasibility Assessment under Setup

| Factor | Observed State (WSL2) | Impact on AgentTrace v1 |
| :--- | :--- | :--- |
| **Kernel Support** | Linux 6.6.87.2-microsoft-standard-WSL2 | Kernel has BPF subsystems compiled in. |
| **TraceFS Mounting** | `/sys/kernel/tracing` mounted | Tracing infrastructure exists in kernel. |
| **bpftool Tooling** | Not installed (`has_bpftool = False`) | Requires manual package installation. |
| **Process Permissions** | Default WSL2 non-root user (`is_root = False`) | `CAP_BPF` and `CAP_SYS_ADMIN` missing without root sudo. |
| **v1 Verdict** | **OUT OF SCOPE / NOT JUSTIFIED FOR v1** | **Decision**: Retain user-space instrumentation. eBPF requires root privileges, custom kernel headers, and background daemon loaders, which violates our core requirement: **a single, unprivileged CLI command runnable on standard developer machines**. eBPF will only be revisited if Experiment 6 reveals irrecoverable measurement gaps. |
