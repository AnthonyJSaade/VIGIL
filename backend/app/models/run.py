"""Run schema — a single audit run against a demo repo."""

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class RunStatus(StrEnum):
    PENDING = "pending"
    SCANNING = "scanning"
    COMPLETED = "completed"
    FAILED = "failed"


class Run(BaseModel):
    id: str
    repo_id: str
    status: RunStatus = RunStatus.PENDING
    finding_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
