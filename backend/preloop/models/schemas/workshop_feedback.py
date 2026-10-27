"""Participant feedback input."""

from pydantic import BaseModel, ConfigDict, Field


class FeedbackInput(BaseModel):
    """Only participant answers, never caller-supplied identity."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    recommendation: int = Field(strict=True, ge=1, le=10)
    worked_well: str | None = Field(default=None, max_length=2000)
    could_improve: str | None = Field(default=None, max_length=2000)
