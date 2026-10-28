"""Asynchronous agent workflow executor orchestrating synthetic DAG tasks."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from agenttrace.agents.mock_model import MockModel
from agenttrace.instrumentation.clock import Clock, FakeClock, MonotonicClock
from agenttrace.instrumentation.tracer import CoreTracer, NoOpTracer
from agenttrace.schemas import SpanStatus
from agenttrace.tools.mock_tools import (
    check_and_inject_fault,
    execute_cpu_tool,
    execute_io_tool,
)
from agenttrace.workloads.generator import derive_task_seed
from agenttrace.workloads.models import TaskSpec, WorkloadDAG


class AsyncAgentExecutor:
    """Executes a WorkloadDAG with semaphore concurrency limits and causal tracing."""

    def __init__(
        self,
        tracer: CoreTracer | NoOpTracer,
        concurrency_limit: int = 4,
        clock: Clock | None = None,
        scratch_dir: Path | str = "experiments/results/scratch",
        thread_pool_workers: int = 4,
    ) -> None:
        self.tracer = tracer
        self.concurrency_limit = max(1, concurrency_limit)
        self.clock: Clock = clock or MonotonicClock()
        self.scratch_dir = Path(scratch_dir)
        self.scratch_dir.mkdir(parents=True, exist_ok=True)
        self.model = MockModel(clock=self.clock)
        self.thread_pool = ThreadPoolExecutor(max_workers=thread_pool_workers)

    async def execute_task(
        self,
        dag: WorkloadDAG,
        task: TaskSpec,
        semaphore: asyncio.Semaphore,
        task_events: dict[str, asyncio.Event],
        completed_spans: dict[str, str],
    ) -> None:
        """Execute a single task node with dependency waiting, queue timing, and retries."""
        # 1. Wait for all predecessor dependencies to complete
        for dep_id in task.depends_on:
            if dep_id in task_events:
                await task_events[dep_id].wait()

        task_seed = derive_task_seed(dag.master_seed, task.task_id)
        max_attempts = max(1, task.max_retries + 1)
        prior_span_id: str | None = None

        try:
            for attempt in range(1, max_attempts + 1):
                # 2. Measure queue wait time
                t_queue_enter = self.clock.monotonic_ns()
                async with semaphore:
                    t_queue_exit = self.clock.monotonic_ns()
                    queue_wait_ms = max(
                        0.0,
                        (t_queue_exit - t_queue_enter) / 1_000_000.0,
                    )

                    # 3. Start traced span
                    span = self.tracer.start_span(
                        operation_name=task.operation_name,
                        operation_type=task.operation_type,
                        task_id=task.task_id,
                        agent_id="synthetic_agent",
                        depends_on=[
                            completed_spans[dep]
                            for dep in task.depends_on
                            if dep in completed_spans
                        ],
                        attempt=attempt,
                        retry_of=prior_span_id,
                        queue_wait_ms=round(queue_wait_ms, 2),
                        attributes={
                            "task_id": task.task_id,
                            "tool_name": task.tool_name,
                            "attempt": attempt,
                        },
                    )

                    attempt_span_id = getattr(span, "span_id", "")
                    prior_span_id = attempt_span_id

                    try:
                        # Check fault injection
                        check_and_inject_fault(task.fail_probability, task_seed + attempt)

                        # Execute tool
                        await self._run_tool(task, span)

                        span.end(status=SpanStatus.OK)
                        if attempt_span_id:
                            completed_spans[task.task_id] = attempt_span_id
                        break  # Success, exit retry loop
                    except Exception as e:
                        span.end(
                            status=SpanStatus.ERROR,
                            error_type=e.__class__.__name__,
                            error_message=str(e),
                        )
                        if attempt == max_attempts:
                            # Final attempt failed
                            break
        finally:
            # Signal dependent tasks that this task has finished execution
            task_events[task.task_id].set()

    async def _run_tool(self, task: TaskSpec, span: Any) -> None:
        """Run tool kernel according to task specification."""
        params = task.tool_params
        loop = asyncio.get_running_loop()

        if task.tool_name == "latency":
            duration_ms = float(params.get("duration_ms", 10.0))
            if isinstance(self.clock, FakeClock):
                self.clock.sleep(duration_ms / 1_000.0)
            else:
                await asyncio.sleep(duration_ms / 1_000.0)
        elif task.tool_name == "cpu":
            intensity = int(params.get("compute_intensity", 100_000))
            await loop.run_in_executor(self.thread_pool, execute_cpu_tool, intensity)
        elif task.tool_name == "io":
            io_bytes = int(params.get("io_bytes", 65_536))
            do_fsync = bool(params.get("do_fsync", True))
            await loop.run_in_executor(
                self.thread_pool,
                execute_io_tool,
                self.scratch_dir,
                io_bytes,
                do_fsync,
            )
        elif task.tool_name == "model":
            prompt = str(params.get("prompt", "Analyze agent workload trace"))
            seed = int(params.get("seed", 42))
            self.model.generate(prompt=prompt, seed=seed, span=span)

    async def run(self, dag: WorkloadDAG) -> None:
        """Execute complete WorkloadDAG with all tasks concurrently managed."""
        if not dag.validate_acyclic():
            raise ValueError(f"DAG {dag.dag_id} contains cycles or invalid dependencies")

        semaphore = asyncio.Semaphore(self.concurrency_limit)
        task_events: dict[str, asyncio.Event] = {task_id: asyncio.Event() for task_id in dag.tasks}
        completed_spans: dict[str, str] = {}

        coros = [
            self.execute_task(
                dag=dag,
                task=task,
                semaphore=semaphore,
                task_events=task_events,
                completed_spans=completed_spans,
            )
            for task in dag.tasks.values()
        ]

        await asyncio.gather(*coros)
        self.tracer.flush()

    def close(self) -> None:
        """Clean up thread pool executors."""
        self.thread_pool.shutdown(wait=False)
