from pydantic import BaseModel, Field


class VersionInfo(BaseModel):
    """Schema for returning version information."""

    server_version: str = Field(
        ..., description="Current version of the Preloop server."
    )
    min_client_version: str = Field(
        ...,
        description="Minimum required version for clients connecting to this Preloop server.",
    )
    max_client_version: str = Field(
        ...,
        description="Maximum recommended version for clients connecting to this Preloop server.",
    )
