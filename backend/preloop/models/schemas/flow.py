from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class GitCloneRepository(BaseModel):
    """Configuration for a single repository to clone."""

    tracker_id: UUID = Field(description="ID of the tracker (GitHub/GitLab) to use")
    project_id: Optional[UUID] = Field(
        default=None,
        description="Project ID to clone. If None, uses repository_url or trigger event",
    )
    repository_url: Optional[str] = Field(
        default=None,
        description="Repository URL to clone. If None, resolved from project or trigger",
    )
    clone_path: str = Field(
        default="workspace",
        description="Relative path where repository should be cloned",
    )
    branch: Optional[str] = Field(
        default=None, description="Branch to clone. If None, uses default branch"
    )

    @field_serializer("tracker_id", "project_id")
    def serialize_uuids(self, value: Optional[UUID]) -> Optional[str]:
        """Serialize UUID fields to strings."""
        return str(value) if value is not None else None


class GitCloneConfig(BaseModel):
    """Configuration for git clone operations before agent execution."""

    enabled: bool = Field(default=False, description="Whether git clone is enabled")
    repositories: List[GitCloneRepository] = Field(
        default_factory=list, description="List of repositories to clone"
    )
    git_user_name: Optional[str] = Field(
        default="Preloop", description="Name to use for git commits"
    )
    git_user_email: Optional[str] = Field(
        default="git@preloop.ai", description="Email to use for git commits"
    )
    source_branch: Optional[str] = Field(
        default="main", description="Branch to checkout for base code"
    )
    target_branch: Optional[str] = Field(
        default=None,
        description="Branch to create for commits (auto-generated if empty)",
    )
    create_pull_request: Optional[bool] = Field(
        default=False, description="Whether to create a Pull Request / Merge Request"
    )
    pull_request_title: Optional[str] = Field(
        default=None, description="Title for the Pull/Merge Request"
    )
    pull_request_description: Optional[str] = Field(
        default=None, description="Description for the Pull/Merge Request"
    )


class CustomCommands(BaseModel):
    """Configuration for custom commands (admin-only)."""

    enabled: bool = Field(
        default=False, description="Whether custom commands are enabled"
    )
    commands: List[str] = Field(
        default_factory=list,
        description="List of shell commands to execute before agent starts",
    )


class WebhookConfig(BaseModel):
    """Configuration for webhook triggers."""

    webhook_secret: str = Field(
        description="Secure token for authenticating webhook requests (auto-generated)"
    )


class FlowBase(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    trigger_event_source: Optional[str] = None
    # Event types that trigger this flow (e.g., ['pull_request_created', 'pull_request_updated'])
    trigger_event_types: Optional[List[str]] = None
    trigger_organization_id: Optional[UUID] = None
    # Project IDs that can trigger this flow (empty/None = all projects in org)
    trigger_project_ids: Optional[List[UUID]] = None
    trigger_config: Optional[Dict[str, Any]] = None
    webhook_config: Optional[WebhookConfig] = None
    prompt_template: Optional[str] = None
    ai_model_id: Optional[UUID] = None
    agent_type: Optional[str] = "openhands"
    agent_config: Optional[Dict[str, Any]] = None
    allowed_mcp_servers: Optional[List[str]] = None
    allowed_mcp_tools: Optional[List[Dict[str, Any]]] = None
    git_clone_config: Optional[GitCloneConfig] = None
    custom_commands: Optional[CustomCommands] = None
    is_preset: Optional[bool] = False
    is_enabled: Optional[bool] = True
    account_id: Optional[UUID] = None
    # Template tracking fields
    source_preset_id: Optional[UUID] = None
    source_prompt_hash: Optional[str] = None
    source_tools_hash: Optional[str] = None
    prompt_customized: Optional[bool] = False
    tools_customized: Optional[bool] = False
    preset_update_available: Optional[bool] = False

    @field_validator("trigger_project_ids", mode="before")
    @classmethod
    def normalize_empty_project_ids(cls, v):
        """Normalize empty list to None so the DB stores NULL (wildcard)."""
        if isinstance(v, list) and len(v) == 0:
            return None
        return v


class FlowCreate(FlowBase):
    name: str
    # For webhook triggers, these can be None
    # trigger_event_source and trigger_event_type are set to 'webhook' on creation
    prompt_template: str
    agent_type: str = "openhands"
    agent_config: Dict[str, Any]
    allowed_mcp_servers: List[str] = []
    allowed_mcp_tools: List[Dict[str, Any]] = []


class FlowUpdate(FlowBase):
    pass


class FlowResponse(FlowBase):
    id: UUID
    account_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    # Template tracking - expose in response for UI to show update notifications
    source_preset_id: Optional[UUID] = None
    prompt_customized: bool = False
    tools_customized: bool = False
    preset_update_available: bool = False
    execution_stats: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer(
        "id",
        "account_id",
        "ai_model_id",
        "trigger_organization_id",
        "source_preset_id",
    )
    def serialize_uuids(self, value: Optional[UUID]) -> Optional[str]:
        """Serialize UUID fields to strings."""
        return str(value) if value is not None else None

    @field_serializer("trigger_project_ids")
    def serialize_uuid_list(self, value: Optional[List[UUID]]) -> Optional[List[str]]:
        """Serialize UUID list fields to string list."""
        return [str(v) for v in value] if value is not None else None
