"""Empirical Platform Capability Probe for AgentTrace.

Probes the active host environment across:
1. Monotonic clock precision and cross-process comparability
2. Process-level and system-level CPU counters
3. Memory and RSS metrics
4. Storage I/O counters and page-cache behavior
5. Network counter attribution scope
6. Context switch tracking
7. Linux /proc and PSI (Pressure Stall Information) availability
8. eBPF accessibility and kernel support
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import psutil


def probe_clock_worker(pipe: Any, start_sync: Any) -> None:
    """Worker process to sample monotonic clock relative to parent sync point."""
    start_sync.wait()
    t_mono = time.monotonic_ns()
    t_perf = time.perf_counter_ns()
    pipe.send({"pid": os.getpid(), "monotonic_ns": t_mono, "perf_counter_ns": t_perf})


def probe_clock() -> dict[str, Any]:
    """Measure clock resolution and cross-process comparability."""
    # Measure resolution (smallest non-zero delta)
    deltas: list[int] = []
    prev = time.monotonic_ns()
    for _ in range(10_000):
        curr = time.monotonic_ns()
        if curr != prev:
            deltas.append(curr - prev)
            prev = curr

    min_delta_ns = min(deltas) if deltas else 0
    p50_delta_ns = sorted(deltas)[len(deltas) // 2] if deltas else 0

    # Cross-process monotonic clock comparison
    sync_event = mp.Event()
    parent_conn, child_conn = mp.Pipe()
    p = mp.Process(target=probe_clock_worker, args=(child_conn, sync_event))
    p.start()

    t_parent_before = time.monotonic_ns()
    sync_event.set()
    child_data = parent_conn.recv()
    t_parent_after = time.monotonic_ns()
    p.join(timeout=2.0)

    t_child_mono = child_data["monotonic_ns"]
    monotonic_within_bounds = t_parent_before <= t_child_mono <= t_parent_after

    return {
        "clock_source": "time.monotonic_ns",
        "min_step_resolution_ns": min_delta_ns,
        "median_step_resolution_ns": p50_delta_ns,
        "cross_process_monotonic_shared": monotonic_within_bounds,
        "parent_before_ns": t_parent_before,
        "child_ns": t_child_mono,
        "parent_after_ns": t_parent_after,
        "delta_ns_from_before": t_child_mono - t_parent_before,
    }


def probe_process_cpu_and_ctx() -> dict[str, Any]:
    """Probe CPU times and context switch counters."""
    proc = psutil.Process()
    cpu_times = proc.cpu_times()
    ctx_dict: dict[str, Any]
    try:
        ctx = proc.num_ctx_switches()
        ctx_dict = {"voluntary": ctx.voluntary, "involuntary": ctx.involuntary}
    except (AttributeError, NotImplementedError) as e:
        ctx_dict = {"error": str(e)}

    affinity = list(proc.cpu_affinity()) if hasattr(proc, "cpu_affinity") else None
    return {
        "user_s": cpu_times.user,
        "system_s": cpu_times.system,
        "children_user_s": getattr(cpu_times, "children_user", None),
        "children_system_s": getattr(cpu_times, "children_system", None),
        "ctx_switches": ctx_dict,
        "cpu_affinity": affinity,
    }


def probe_memory() -> dict[str, Any]:
    """Probe memory counters at process and system levels."""
    proc = psutil.Process()
    mem_info = proc.memory_info()
    sys_mem = psutil.virtual_memory()

    return {
        "process_rss_bytes": mem_info.rss,
        "process_vms_bytes": mem_info.vms,
        "process_shared_bytes": getattr(mem_info, "shared", None),
        "system_total_bytes": sys_mem.total,
        "system_available_bytes": sys_mem.available,
        "system_used_bytes": sys_mem.used,
    }


def probe_storage_io() -> dict[str, Any]:
    """Probe storage counters and verify process vs system attribution."""
    proc = psutil.Process()
    try:
        io_before = proc.io_counters()
        io_available = True
        io_fields = [attr for attr in dir(io_before) if not attr.startswith("_")]
    except (AttributeError, NotImplementedError):
        io_available = False
        io_fields = []
        io_before = None

    # Write a small file to check if process io_counters track disk writes
    test_file = Path("experiments/scratch_probe.tmp")
    test_file.parent.mkdir(parents=True, exist_ok=True)
    payload = b"X" * 65536
    with open(test_file, "wb") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())

    if io_available and io_before:
        io_after = proc.io_counters()
        delta_write_bytes = io_after.write_bytes - io_before.write_bytes
    else:
        delta_write_bytes = None

    if test_file.exists():
        test_file.unlink()

    return {
        "io_counters_supported": io_available,
        "supported_fields": io_fields,
        "delta_write_bytes_observed": delta_write_bytes,
        "scope": "process-level (where supported by OS)",
        "caveat": "Page cache buffers writes; explicit fsync() required to trigger disk bytes.",
    }


def probe_network_io() -> dict[str, Any]:
    """Probe network counters."""
    net_sys = psutil.net_io_counters()
    return {
        "system_net_io_supported": net_sys is not None,
        "scope": "system-wide only",
        "per_process_supported": False,
        "caveat": "User-space process lacks per-socket packet counters without eBPF.",
    }


def probe_linux_proc_and_psi() -> dict[str, Any]:
    """Probe Linux /proc and Pressure Stall Information (PSI)."""
    if platform.system() != "Linux":
        return {"status": "skipped", "reason": f"OS is {platform.system()}"}

    proc_stat = Path("/proc/self/stat").exists()
    proc_io = Path("/proc/self/io").exists()

    psi_cpu = Path("/proc/pressure/cpu")
    psi_io = Path("/proc/pressure/io")
    psi_mem = Path("/proc/pressure/memory")

    psi_available = psi_cpu.exists() and psi_io.exists() and psi_mem.exists()
    psi_sample = None
    if psi_available:
        try:
            psi_sample = psi_cpu.read_text().strip()
        except Exception as e:
            psi_sample = f"read_error: {e}"

    cgroup_v2 = Path("/sys/fs/cgroup/cgroup.controllers").exists()

    return {
        "/proc/self/stat": proc_stat,
        "/proc/self/io": proc_io,
        "psi_available": psi_available,
        "psi_cpu_sample": psi_sample,
        "cgroup_v2_available": cgroup_v2,
    }


def probe_ebpf() -> dict[str, Any]:
    """Check availability and permission for eBPF tracing."""
    if platform.system() != "Linux":
        return {
            "verdict": "UNAVAILABLE",
            "reason": f"Non-Linux host ({platform.system()})",
            "feasible_in_v1": False,
        }

    # Check bpftool
    bpftool_path = subprocess.run(["which", "bpftool"], capture_output=True, text=True)
    has_bpftool = bpftool_path.returncode == 0

    # Check debugfs / tracefs
    tracefs = Path("/sys/kernel/tracing").exists() or Path("/sys/kernel/debug/tracing").exists()

    # Check root privileges for bpf syscall
    geteuid_fn = getattr(os, "geteuid", None)
    is_root = geteuid_fn() == 0 if geteuid_fn is not None else False

    # WSL2 detection
    is_wsl = "microsoft" in platform.uname().release.lower()

    if tracefs and is_wsl:
        verdict = "FEASIBLE_WITH_ROOT"
    elif is_root:
        verdict = "AVAILABLE"
    else:
        verdict = "PERMISSION_RESTRICTED"

    return {
        "is_wsl2": is_wsl,
        "kernel_release": platform.uname().release,
        "has_bpftool": has_bpftool,
        "tracefs_mounted": tracefs,
        "is_root": is_root,
        "verdict": verdict,
        "feasible_in_v1": False,
        "rationale": (
            "WSL2 default user lacks CAP_BPF/CAP_SYS_ADMIN without elevated sudo. "
            "eBPF introduces non-portable root daemon requirements."
        ),
    }


def main() -> None:
    """Run all probes and output verified JSON result."""
    mp.freeze_support()
    report: dict[str, Any] = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "clock": probe_clock(),
        "cpu_and_ctx": probe_process_cpu_and_ctx(),
        "memory": probe_memory(),
        "storage_io": probe_storage_io(),
        "network_io": probe_network_io(),
        "linux_proc": probe_linux_proc_and_psi(),
        "ebpf": probe_ebpf(),
    }

    out_dir = Path("experiments/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"capability_probe_{platform.system().lower()}.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    sys.stdout.write(f"Capability probe saved to {out_file}\n")
    sys.stdout.write(json.dumps(report, indent=2))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
