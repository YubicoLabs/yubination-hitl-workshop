from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime


class EmbeddingRawRequest(BaseModel):
    """Request model for fetching raw embeddings with filtering options."""

    embedding_model_id: Optional[str] = None
    project_id: Optional[str] = None
    tracker_id: Optional[str] = None
    organization_id: Optional[str] = None
    skip: int = 0
    limit: int = 1000


class EmbeddingRawDataItem(BaseModel):
    """Individual data item in the raw embedding response."""

    issue_id: str
    project_id: str
    embedding: List[float]
    issue_title: Optional[str] = None
    issue_labels: Optional[List[str]] = None
    issue_type: Optional[str] = None
    issue_created_at: Optional[datetime] = None


class EmbeddingRawResponse(BaseModel):
    """Response model for the raw embeddings endpoint."""

    data: List[EmbeddingRawDataItem]
