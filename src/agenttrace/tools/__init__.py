"""Mock tools (CPU-bound, I/O-bound, latency, failure injection)."""

from agenttrace.tools.mock_tools import (
    check_and_inject_fault,
    execute_cpu_tool,
    execute_io_tool,
    execute_latency_tool,
)

__all__ = [
    "check_and_inject_fault",
    "execute_cpu_tool",
    "execute_io_tool",
    "execute_latency_tool",
]
