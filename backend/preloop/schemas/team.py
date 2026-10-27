"""Team management schemas for request and response validation."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class TeamBase(BaseModel):
    """Base team schema with common attributes."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)


class TeamCreate(TeamBase):
    """Schema for creating a new team."""

    pass


class TeamUpdate(BaseModel):
    """Schema for updating a team."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)


class TeamMemberAdd(BaseModel):
    """Schema for adding a member to a team."""

    user_id: UUID
    role: Optional[str] = Field(None, max_length=50)


class TeamMemberUpdate(BaseModel):
    """Schema for updating a team member's role."""

    role: Optional[str] = Field(None, max_length=50)


class TeamMemberResponse(BaseModel):
    """Response schema for team member data."""

    id: UUID
    team_id: UUID
    user_id: UUID
    role: Optional[str]
    added_at: datetime
    added_by: Optional[UUID]

    # Nested user info
    username: str
    email: str
    full_name: Optional[str]

    @field_serializer("id", "team_id", "user_id")
    def serialize_uuid(self, value: UUID) -> str:
        """Serialize UUID to string for JSON response."""
        return str(value)

    @field_serializer("added_by")
    def serialize_added_by(self, value: Optional[UUID]) -> Optional[str]:
        """Serialize UUID to string for JSON response."""
        return str(value) if value is not None else None

    model_config = ConfigDict(from_attributes=True)


class TeamResponse(BaseModel):
    """Response schema for team data."""

    id: UUID
    account_id: UUID
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    roles: Optional[List[dict]] = None

    @field_serializer("id", "account_id")
    def serialize_uuid(self, value: UUID) -> str:
        """Serialize UUID to string for JSON response."""
        return str(value)

    model_config = ConfigDict(from_attributes=True)


class TeamDetailResponse(TeamResponse):
    """Detailed response schema for team with members."""

    members: List[TeamMemberResponse] = []

    model_config = ConfigDict(from_attributes=True)


class TeamListResponse(BaseModel):
    """Response schema for paginated team list."""

    teams: List[TeamResponse]
    total: int
    skip: int
    limit: int
