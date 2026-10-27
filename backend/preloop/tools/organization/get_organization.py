"""Get organization tool implementation."""

from typing import Any, Dict, List

from pydantic import BaseModel

from preloop.tools.base import Context
from preloop.models.crud.organization import CRUDOrganization
from preloop.models.db.session import get_db_session as get_db
from preloop.models.models.organization import Organization


class ProjectResponse(BaseModel):
    """Project information in organization response."""

    id: int
    name: str
    identifier: str
    description: str = ""
    trackers: List[str] = []
    is_active: bool = True


class OrganizationResponse(BaseModel):
    """Organization response model."""

    id: int
    name: str
    identifier: str
    description: str = ""
    settings: Dict[str, Any] = {}
    projects: List[ProjectResponse] = []
    created_at: str
    updated_at: str


async def get_organization(organization: str, ctx: Context = None) -> Dict[str, Any]:
    """Get organization details.

    Args:
        organization: Organization identifier
        ctx: Optional MCP context

    Returns:
        Organization details including name, description, and projects
    """
    # Get database session
    db = next(get_db())

    crud_organization = CRUDOrganization(Organization)

    try:
        # Log operation if context is available
        if ctx:
            await ctx.info(f"Looking up organization: {organization}")

        # Get organization by identifier using CRUD operation
        org = crud_organization.get_by_identifier(db, identifier=organization)

        if not org or not org.is_active:
            return {
                "error": "not_found",
                "message": f"Organization '{organization}' not found",
            }

        # Get projects for the organization
        projects = [
            ProjectResponse(
                id=project.id,
                name=project.name,
                identifier=project.identifier,
                description=project.description or "",
                # In SpaceModels the trackers are in tracker_settings
                trackers=list(project.tracker_settings.keys())
                if project.tracker_settings
                else [],
                is_active=project.is_active,
            )
            for project in org.projects
            if project.is_active  # Only include active projects
        ]

        # Return organization details
        return OrganizationResponse(
            id=org.id,
            name=org.name,
            identifier=org.identifier,
            description=org.description or "",
            settings=org.settings or {},
            projects=projects,
            created_at=org.created_at.isoformat(),
            updated_at=org.updated_at.isoformat(),
        ).model_dump()
    finally:
        db.close()
