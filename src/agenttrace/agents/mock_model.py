"""Mock LLM model simulating realistic TTFT, streaming latency, and token volume."""

from __future__ import annotations

import random
from dataclasses import dataclass

from agenttrace.instrumentation.clock import Clock, MonotonicClock
from agenttrace.instrumentation.tracer import Span


@dataclass(frozen=True)
class ModelResponse:
    """Simulated response output and token metrics from mock model."""

    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    ttft_ms: float
    total_duration_ms: float


class MockModel:
    """Simulates realistic LLM latency profiles with deterministic token counts."""

    def __init__(
        self,
        base_ttft_ms: float = 30.0,
        ms_per_token: float = 1.5,
        clock: Clock | None = None,
    ) -> None:
        self.base_ttft_ms = base_ttft_ms
        self.ms_per_token = ms_per_token
        self.clock: Clock = clock or MonotonicClock()

    def generate(
        self,
        prompt: str,
        seed: int,
        span: Span | None = None,
    ) -> ModelResponse:
        """Execute simulated generation with time-to-first-token and token streaming."""
        rng = random.Random(seed)
        prompt_tokens = max(10, len(prompt.split()) * 2)
        completion_tokens = rng.randint(20, 100)

        # 1. Simulate Time-To-First-Token (TTFT)
        actual_ttft_ms = max(5.0, self.base_ttft_ms + rng.uniform(-5.0, 5.0))
        self.clock.sleep(actual_ttft_ms / 1_000.0)

        if span is not None:
            span.add_event(
                "first_token_received",
                {
                    "ttft_ms": round(actual_ttft_ms, 2),
                    "prompt_tokens": prompt_tokens,
                },
            )

        # 2. Simulate token streaming generation
        stream_duration_ms = completion_tokens * self.ms_per_token
        self.clock.sleep(stream_duration_ms / 1_000.0)

        total_duration_ms = actual_ttft_ms + stream_duration_ms
        content = f"Synthetic response [{completion_tokens} tokens, seed={seed}]"

        return ModelResponse(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            ttft_ms=round(actual_ttft_ms, 2),
            total_duration_ms=round(total_duration_ms, 2),
        )
