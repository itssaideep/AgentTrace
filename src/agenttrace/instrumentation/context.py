"""Asynchronous context propagation for AgentTrace workflows.

Manages execution context (trace_id, span_id, parent_span_id, task_id, agent_id)
across coroutines and worker process boundaries.
"""

from __future__ import annotations

import os
import threading
from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TraceContext:
    """Immutable context carried through async coroutines and processes."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    task_id: str
    agent_id: str
    process_id: int = os.getpid()
    thread_id: int = threading.get_ident()

    def to_dict(self) -> dict[str, Any]:
        """Serialize context for cross-process or IPC transmission."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TraceContext:
        """Reconstruct context from serialized dictionary."""
        return cls(
            trace_id=data["trace_id"],
            span_id=data["span_id"],
            parent_span_id=data.get("parent_span_id"),
            task_id=data["task_id"],
            agent_id=data["agent_id"],
            process_id=data.get("process_id", os.getpid()),
            thread_id=data.get("thread_id", threading.get_ident()),
        )


_CURRENT_CONTEXT: ContextVar[TraceContext | None] = ContextVar(
    "agenttrace_current_context",
    default=None,
)


def get_current_context() -> TraceContext | None:
    """Retrieve the current active TraceContext in the calling task/coroutine."""
    return _CURRENT_CONTEXT.get()


def set_current_context(context: TraceContext | None) -> Token[TraceContext | None]:
    """Set the active TraceContext for the current execution flow."""
    return _CURRENT_CONTEXT.set(context)


def reset_current_context(token: Token[TraceContext | None]) -> None:
    """Restore the previous TraceContext using the provided token."""
    _CURRENT_CONTEXT.reset(token)


def current_trace_id() -> str | None:
    """Convenience accessor for current trace ID."""
    ctx = get_current_context()
    return ctx.trace_id if ctx else None


def current_span_id() -> str | None:
    """Convenience accessor for current span ID."""
    ctx = get_current_context()
    return ctx.span_id if ctx else None
