"""Pydantic schemas for registration tokens."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RegistrationTokenBase(BaseModel):
    """Base schema for registration token."""

    token: str = Field(..., description="The registration token value")
    user_id: UUID = Field(..., description="User ID this token is for")
    expires_at: datetime = Field(..., description="Token expiration time")


class RegistrationTokenCreate(RegistrationTokenBase):
    """Schema for creating a registration token."""

    pass


class RegistrationTokenResponse(RegistrationTokenBase):
    """Schema for registration token API responses."""

    id: UUID
    created_at: datetime
    updated_at: datetime
    used_at: Optional[datetime] = None
    is_consumed: bool = False

    model_config = ConfigDict(from_attributes=True)
