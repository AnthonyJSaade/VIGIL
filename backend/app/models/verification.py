"""VerificationReport schema — result of running the patched code in a sandbox."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class VerificationReport(BaseModel):
    id: str
    patch_id: str
    scanner_rerun_clean: bool
    tests_passed: bool | None = None
    details: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
