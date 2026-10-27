from pydantic import BaseModel, ConfigDict, Field
from typing import List

from .issue import IssueResponse


class DuplicateIssuePair(BaseModel):
    """Represents a pair of issues that are potential duplicates."""

    issue1: IssueResponse = Field(
        ..., description="The first issue in the duplicate pair."
    )
    issue2: IssueResponse = Field(
        ..., description="The second issue in the duplicate pair."
    )
    similarity: float = Field(
        ..., description="The similarity score between the two issues."
    )

    model_config = ConfigDict(from_attributes=True)


class ProjectDuplicatesResponse(BaseModel):
    """Response model for the project duplicates endpoint."""

    project_ids: List[str] = Field(
        ..., description="The IDs of the projects that were scanned."
    )
    model_id_used: str = Field(
        ..., description="The ID of the embedding model used for the similarity search."
    )
    threshold_used: float = Field(
        ..., description="The similarity threshold used for detecting duplicates."
    )
    duplicates: List[DuplicateIssuePair] = Field(
        ..., description="A list of potential duplicate issue pairs."
    )

    model_config = ConfigDict(from_attributes=True)
