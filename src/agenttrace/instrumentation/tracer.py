"""Core tracer, Span lifecycle management, and NoOp baseline implementation."""

from __future__ import annotations

import os
import threading
import uuid
from types import TracebackType
from typing import Any, Protocol, runtime_checkable

from agenttrace.instrumentation.clock import Clock, MonotonicClock
from agenttrace.instrumentation.context import (
    TraceContext,
    get_current_context,
    reset_current_context,
    set_current_context,
)
from agenttrace.instrumentation.redaction import RedactionEngine
from agenttrace.schemas import (
    SCHEMA_VERSION,
    RecordType,
    SpanEndRecord,
    SpanEventRecord,
    SpanStartRecord,
    SpanStatus,
)
from agenttrace.storage.writer import TraceWriter


def generate_id(prefix: str = "") -> str:
    """Generate high-entropy unique identifier."""
    hex_id = uuid.uuid4().hex[:16]
    return f"{prefix}{hex_id}" if prefix else hex_id


@runtime_checkable
class SpanProtocol(Protocol):
    """Protocol defining span interaction methods."""

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a single metadata attribute on the span."""
        ...

    def add_event(self, event_name: str, payload: dict[str, Any] | None = None) -> None:
        """Record an intra-span milestone event."""
        ...

    def end(
        self,
        status: SpanStatus = SpanStatus.OK,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Explicitly end the span lifecycle."""
        ...


class Span:
    """Represents a discrete, causally-tracked operation in an agent workflow."""

    def __init__(
        self,
        tracer: CoreTracer,
        trace_id: str,
        span_id: str,
        task_id: str,
        agent_id: str,
        operation_name: str,
        operation_type: str,
        start_monotonic_ns: int,
        parent_span_id: str | None = None,
        depends_on: list[str] | None = None,
        attempt: int = 1,
        retry_of: str | None = None,
        queue_wait_ms: float = 0.0,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        self.tracer = tracer
        self.trace_id = trace_id
        self.span_id = span_id
        self.task_id = task_id
        self.agent_id = agent_id
        self.operation_name = operation_name
        self.operation_type = operation_type
        self.start_monotonic_ns = start_monotonic_ns
        self.parent_span_id = parent_span_id
        self.depends_on: list[str] = list(depends_on) if depends_on else []
        self.attempt = attempt
        self.retry_of = retry_of
        self.queue_wait_ms = queue_wait_ms
        self.attributes: dict[str, Any] = dict(attributes) if attributes else {}

        self.status: SpanStatus = SpanStatus.OK
        self.error_type: str | None = None
        self.error_message: str | None = None
        self.is_ended: bool = False
        self._token: Any = None

    def set_attribute(self, key: str, value: Any) -> None:
        """Store an attribute on the span (sanitized upon write)."""
        if self.is_ended:
            return
        self.attributes[key] = value

    def add_event(self, event_name: str, payload: dict[str, Any] | None = None) -> None:
        """Record an ad-hoc intra-span event."""
        if self.is_ended:
            return
        self.tracer._emit_event(self, event_name, payload or {})

    def end(
        self,
        status: SpanStatus = SpanStatus.OK,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Terminate span execution and emit span_end event."""
        if self.is_ended:
            return

        self.status = status
        self.error_type = error_type
        self.error_message = error_message
        self.is_ended = True

        self.tracer._end_span(self)

    def __enter__(self) -> Span:
        ctx = TraceContext(
            trace_id=self.trace_id,
            span_id=self.span_id,
            parent_span_id=self.parent_span_id,
            task_id=self.task_id,
            agent_id=self.agent_id,
            process_id=os.getpid(),
            thread_id=threading.get_ident(),
        )
        self._token = set_current_context(ctx)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            if exc_val is not None:
                exc_name = exc_val.__class__.__name__
                if "Cancelled" in exc_name:
                    status = SpanStatus.CANCELLED
                elif "Timeout" in exc_name:
                    status = SpanStatus.TIMEOUT
                else:
                    status = SpanStatus.ERROR
                self.end(status=status, error_type=exc_name, error_message=str(exc_val))
            else:
                self.end(status=self.status)
        finally:
            if self._token is not None:
                reset_current_context(self._token)

    async def __aenter__(self) -> Span:
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.__exit__(exc_type, exc_val, exc_tb)


class CoreTracer:
    """Lightweight, low-overhead causal tracer recording explicit span graphs."""

    def __init__(
        self,
        writer: TraceWriter,
        clock: Clock | None = None,
        redactor: RedactionEngine | None = None,
        trace_id: str | None = None,
        validate_on_write: bool = False,
    ) -> None:
        self.writer = writer
        self.clock: Clock = clock or MonotonicClock()
        self.redactor: RedactionEngine = redactor or RedactionEngine()
        self.default_trace_id: str = trace_id or generate_id("tr_")
        self.validate_on_write: bool = validate_on_write

        self._active_spans: dict[str, Span] = {}
        self._lock = threading.Lock()

    def start_span(
        self,
        operation_name: str,
        operation_type: str = "tool_exec",
        task_id: str | None = None,
        agent_id: str | None = None,
        parent_span_id: str | None = None,
        trace_id: str | None = None,
        depends_on: list[str] | None = None,
        attempt: int = 1,
        retry_of: str | None = None,
        queue_wait_ms: float = 0.0,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        """Create and start a new causally tracked Span."""
        current_ctx = get_current_context()

        effective_trace_id = trace_id or (
            current_ctx.trace_id if current_ctx else self.default_trace_id
        )
        effective_parent_id = parent_span_id or (
            current_ctx.span_id if current_ctx else None
        )
        effective_task_id = task_id or (
            current_ctx.task_id if current_ctx else generate_id("task_")
        )
        effective_agent_id = agent_id or (
            current_ctx.agent_id if current_ctx else "default_agent"
        )

        span_id = generate_id("sp_")
        now_ns = self.clock.monotonic_ns()
        utc_iso = self.clock.utc_iso()

        sanitized_attrs = self.redactor.sanitize(attributes)

        span = Span(
            tracer=self,
            trace_id=effective_trace_id,
            span_id=span_id,
            task_id=effective_task_id,
            agent_id=effective_agent_id,
            operation_name=operation_name,
            operation_type=operation_type,
            start_monotonic_ns=now_ns,
            parent_span_id=effective_parent_id,
            depends_on=depends_on,
            attempt=attempt,
            retry_of=retry_of,
            queue_wait_ms=queue_wait_ms,
            attributes=sanitized_attrs,
        )

        with self._lock:
            self._active_spans[span_id] = span

        # Fast JSON emission adhering to ADR D7
        if self.validate_on_write:
            record = SpanStartRecord(
                timestamp_utc_iso=utc_iso,
                timestamp_monotonic_ns=now_ns,
                trace_id=span.trace_id,
                span_id=span.span_id,
                parent_span_id=span.parent_span_id,
                task_id=span.task_id,
                agent_id=span.agent_id,
                operation_name=span.operation_name,
                operation_type=span.operation_type,
                process_id=os.getpid(),
                thread_id=threading.get_ident(),
                depends_on=span.depends_on,
                attempt=span.attempt,
                retry_of=span.retry_of,
                queue_wait_ms=span.queue_wait_ms,
                attributes=sanitized_attrs,
            )
            self.writer.write_record(record)
        else:
            record_dict = {
                "schema_version": SCHEMA_VERSION,
                "record_type": RecordType.SPAN_START.value,
                "timestamp_utc_iso": utc_iso,
                "timestamp_monotonic_ns": now_ns,
                "trace_id": span.trace_id,
                "span_id": span.span_id,
                "parent_span_id": span.parent_span_id,
                "task_id": span.task_id,
                "agent_id": span.agent_id,
                "operation_name": span.operation_name,
                "operation_type": span.operation_type,
                "process_id": os.getpid(),
                "thread_id": threading.get_ident(),
                "depends_on": span.depends_on,
                "attempt": span.attempt,
                "retry_of": span.retry_of,
                "queue_wait_ms": span.queue_wait_ms,
                "attributes": sanitized_attrs,
            }
            self.writer.write_record(record_dict)

        return span

    def _end_span(self, span: Span) -> None:
        """Internal callback when a span terminates."""
        now_ns = self.clock.monotonic_ns()
        utc_iso = self.clock.utc_iso()
        duration_ms = max(0.0, (now_ns - span.start_monotonic_ns) / 1_000_000.0)

        with self._lock:
            self._active_spans.pop(span.span_id, None)

        sanitized_attrs = self.redactor.sanitize(span.attributes)

        if self.validate_on_write:
            record = SpanEndRecord(
                timestamp_utc_iso=utc_iso,
                timestamp_monotonic_ns=now_ns,
                trace_id=span.trace_id,
                span_id=span.span_id,
                start_monotonic_ns=span.start_monotonic_ns,
                duration_ms=duration_ms,
                status=span.status,
                error_type=span.error_type,
                error_message=span.error_message,
                attributes=sanitized_attrs,
            )
            self.writer.write_record(record)
        else:
            record_dict = {
                "schema_version": SCHEMA_VERSION,
                "record_type": RecordType.SPAN_END.value,
                "timestamp_utc_iso": utc_iso,
                "timestamp_monotonic_ns": now_ns,
                "trace_id": span.trace_id,
                "span_id": span.span_id,
                "start_monotonic_ns": span.start_monotonic_ns,
                "duration_ms": duration_ms,
                "status": span.status.value,
                "error_type": span.error_type,
                "error_message": span.error_message,
                "attributes": sanitized_attrs,
            }
            self.writer.write_record(record_dict)

    def _emit_event(self, span: Span, event_name: str, payload: dict[str, Any]) -> None:
        """Internal callback when an intra-span event is emitted."""
        now_ns = self.clock.monotonic_ns()
        utc_iso = self.clock.utc_iso()
        sanitized_payload = self.redactor.sanitize(payload)

        if self.validate_on_write:
            record = SpanEventRecord(
                timestamp_utc_iso=utc_iso,
                timestamp_monotonic_ns=now_ns,
                trace_id=span.trace_id,
                span_id=span.span_id,
                event_name=event_name,
                event_payload=sanitized_payload,
            )
            self.writer.write_record(record)
        else:
            record_dict = {
                "schema_version": SCHEMA_VERSION,
                "record_type": RecordType.SPAN_EVENT.value,
                "timestamp_utc_iso": utc_iso,
                "timestamp_monotonic_ns": now_ns,
                "trace_id": span.trace_id,
                "span_id": span.span_id,
                "event_name": event_name,
                "event_payload": sanitized_payload,
            }
            self.writer.write_record(record_dict)

    def get_active_spans(self) -> list[Span]:
        """Return snapshot of currently unclosed active spans."""
        with self._lock:
            return list(self._active_spans.values())

    def flush(self) -> None:
        """Flush the underlying trace writer buffer."""
        self.writer.flush()


class NoOpSpan:
    """Dummy span implementation incurring zero memory and I/O overhead."""

    def __init__(self) -> None:
        self.status = SpanStatus.OK

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def add_event(self, event_name: str, payload: dict[str, Any] | None = None) -> None:
        pass

    def end(
        self,
        status: SpanStatus = SpanStatus.OK,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        pass

    def __enter__(self) -> NoOpSpan:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass

    async def __aenter__(self) -> NoOpSpan:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


class NoOpTracer:
    """True zero-overhead tracer arm for Experiment 4 baseline measurements."""

    def __init__(self) -> None:
        self._noop_span = NoOpSpan()

    def start_span(self, *args: Any, **kwargs: Any) -> NoOpSpan:
        return self._noop_span

    def flush(self) -> None:
        pass
