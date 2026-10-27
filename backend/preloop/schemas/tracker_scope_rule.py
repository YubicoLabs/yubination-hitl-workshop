"""Pydantic schemas for TrackerScopeRule."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from preloop.models.models.tracker_scope_rule import RuleType, ScopeType


class TrackerScopeRuleBase(BaseModel):
    """Base schema for tracker scope rules."""

    scope_type: ScopeType = Field(
        ..., description="The type of scope (ORGANIZATION or PROJECT)."
    )
    rule_type: RuleType = Field(
        ..., description="The type of rule (INCLUDE or EXCLUDE)."
    )
    identifier: str = Field(
        ...,
        description="The identifier for the scope (e.g., 'my-org' or 'my-org/my-repo').",
    )


class TrackerScopeRuleCreate(TrackerScopeRuleBase):
    """Schema for creating a new tracker scope rule."""

    pass


class TrackerScopeRuleResponse(TrackerScopeRuleBase):
    """Schema for responding with tracker scope rule details."""

    id: UUID = Field(..., description="The unique ID of the scope rule.")

    @field_serializer("id")
    def serialize_id(self, value: UUID) -> str:
        """Serialize UUID to string for JSON response."""
        return str(value)

    model_config = ConfigDict(from_attributes=True)
