"""Configuration models and loaders for AgentTrace runs and experiments."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class TracerConfig(BaseModel):
    """Tracer-specific configuration."""

    enabled: bool = True
    buffer_size: int = 10_000
    flush_interval_ms: float = 100.0
    record_payloads: bool = False
    redact_keys: list[str] = Field(
        default_factory=lambda: ["api_key", "secret", "password", "token", "authorization"]
    )


class SamplerConfig(BaseModel):
    """Resource sampler configuration."""

    enabled: bool = True
    interval_ms: float = 50.0
    track_process_tree: bool = True
    track_system: bool = True


class WorkloadConfig(BaseModel):
    """Synthetic workload configuration."""

    workload_type: str = "sequential"
    num_tasks: int = 10
    concurrency_limit: int = 4
    base_latency_ms: float = 10.0
    jitter_ms: float = 2.0
    compute_intensity: int = 100_000
    io_bytes: int = 4096
    failure_rate: float = 0.0
    seed: int = 42


class RunConfig(BaseModel):
    """Top-level configuration for an AgentTrace execution run."""

    experiment_name: str = "default"
    run_id: str | None = None
    output_dir: Path = Path("experiments/results")
    seed: int = 42
    tracer: TracerConfig = Field(default_factory=TracerConfig)
    sampler: SamplerConfig = Field(default_factory=SamplerConfig)
    workload: WorkloadConfig = Field(default_factory=WorkloadConfig)

    @classmethod
    def from_toml(cls, toml_path: Path | str) -> RunConfig:
        """Load and parse a RunConfig from a TOML file."""
        path = Path(toml_path)
        with path.open("rb") as f:
            data: dict[str, Any] = tomllib.load(f)
        return cls(**data)
