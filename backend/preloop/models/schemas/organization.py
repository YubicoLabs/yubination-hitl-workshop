from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime


class OrganizationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    identifier: str = Field(..., max_length=100)  # Made required
    tracker_id: UUID  # Added tracker_id
    description: Optional[str] = None
    is_active: bool = True


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):  # Does not need tracker_id for update usually
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    identifier: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class Organization(OrganizationBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    # Add any related fields if necessary, e.g., projects: List["Project"] = []

    model_config = ConfigDict(from_attributes=True)
