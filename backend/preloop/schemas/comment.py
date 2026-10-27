"""Comment schemas for request and response validation."""

from typing import Dict, List, Optional, Any
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, ValidationInfo


class CommentBase(BaseModel):
    """Base model for comment data."""

    body: str = Field(..., description="Comment text")
    meta_data: Optional[Dict] = Field(
        default=None, description="Additional comment metadata"
    )


class CommentCreate(CommentBase):
    """Model for creating a new comment."""

    pass


class CommentResponse(CommentBase):
    """Response model for comment data."""

    id: str = Field(..., description="Comment unique identifier")
    issue_id: str = Field(..., description="Issue ID this comment belongs to")
    author: Optional[str] = Field(default=None, description="Comment author")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: Optional[str] = Field(default=None, description="Last update timestamp")
    score: Optional[float] = Field(
        None, description="Similarity score for search results (if applicable)"
    )

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def format_datetime_fields_to_str(
        cls, v: Any, info: ValidationInfo
    ) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        if isinstance(v, str):
            return v
        raise TypeError(
            f"Field '{info.field_name}' must be a datetime object or a string, got {type(v).__name__}"
        )

    model_config = {"from_attributes": True}


class CommentList(BaseModel):
    """Response model for a list of comments with pagination details."""

    items: List[CommentResponse]
    total: int
    limit: int
    offset: int


class CommentSearchResults(BaseModel):
    """Response model for comment search results."""

    items: List[CommentResponse] = Field(..., description="Search result items")
    total: int = Field(..., description="Total number of matching comments")
    query: str = Field(..., description="Search query used")
