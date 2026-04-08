"""Finding schema — a single vulnerability detected by a scanner."""

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class SeverityLevel(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Finding(BaseModel):
    id: str
    run_id: str
    scanner: str = "semgrep"
    rule_id: str
    severity: SeverityLevel
    message: str
    file_path: str
    start_line: int
    end_line: int
    snippet: str
    confidence: float = 1.0
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
