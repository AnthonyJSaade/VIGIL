"""CriticVerdict schema — the Critic agent's independent review of a patch."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class CriticVerdict(BaseModel):
    id: str
    patch_id: str
    approved: bool
    reasoning: str
    concerns: list[str] = Field(default_factory=list)
    model_used: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
