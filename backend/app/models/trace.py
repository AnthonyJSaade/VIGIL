"""TraceEvent schema — a single step in the Hunter -> Surgeon -> Critic -> Verifier pipeline."""

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class AgentRole(StrEnum):
    HUNTER = "hunter"
    SURGEON = "surgeon"
    CRITIC = "critic"
    VERIFIER = "verifier"


class TraceAction(StrEnum):
    SCAN_STARTED = "scan_started"
    FINDING_DISCOVERED = "finding_discovered"
    SCAN_COMPLETED = "scan_completed"
    PATCH_PROPOSED = "patch_proposed"
    REVIEW_STARTED = "review_started"
    REVIEW_REJECTED = "review_rejected"
    PATCH_RETRIED = "patch_retried"
    REVIEW_APPROVED = "review_approved"
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_COMPLETED = "verification_completed"


class TraceEvent(BaseModel):
    id: str
    run_id: str
    role: AgentRole
    action: TraceAction
    payload: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
