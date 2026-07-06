from dataclasses import dataclass, field
from typing import Any
from datetime import datetime


@dataclass
class Job:
    job_id: str


@dataclass
class PipelineStep:
    operation: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class JobMetadata:
    job_id: str
    pipeline: list[PipelineStep]
    input_key: str
    output_key: str
    status: str
    created_at: datetime | None = None