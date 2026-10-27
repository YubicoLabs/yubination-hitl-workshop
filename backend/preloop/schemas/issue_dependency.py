from typing import List, Optional
from pydantic import BaseModel, Field


class DependencyRequest(BaseModel):
    issue_ids: List[str] = Field(
        ..., description="A list of issue IDs to analyze for dependencies."
    )
    model_id: Optional[str] = Field(
        None, description="Optional AI Model ID to use for detection."
    )


class DependencyPair(BaseModel):
    source_issue_id: str = Field(
        ..., description="The ID of the issue that must be completed first."
    )
    dependent_issue_id: str = Field(
        ..., description="The ID of the issue that depends on the source issue."
    )
    reason: str = Field(..., description="A brief explanation of the dependency.")
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="The model's confidence in this dependency."
    )
    issue_key: Optional[str] = Field(None, description="The key of the source issue.")
    dependency_key: Optional[str] = Field(
        None, description="The key of the dependent issue."
    )
    is_committed: bool = Field(
        False, description="Indicates if the relationship is committed by the user."
    )
    comes_from_tracker: bool = Field(
        False,
        description="Indicates if the relationship comes from an external tracker.",
    )


class DependencyResponse(BaseModel):
    dependencies: List[DependencyPair]


class CommitDependenciesRequest(BaseModel):
    dependencies: List[DependencyPair]


class ExtendScanRequest(BaseModel):
    issue_ids: List[str] = Field(
        ..., description="The ID of the issues to start the scan from."
    )
    extend_by: int = Field(
        ..., gt=0, description="The number of new issues to include in the scan."
    )
