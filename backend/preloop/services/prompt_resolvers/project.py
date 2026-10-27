"""Resolver for project-related placeholders."""

import logging
from typing import Optional

from preloop.models.crud import crud_project

from .base import PromptResolver, ResolverContext

logger = logging.getLogger(__name__)


class ProjectResolver(PromptResolver):
    """
    Resolver for project data from the database.

    Handles placeholders like:
    - {{project.name}}
    - {{project.description}}
    - {{project.identifier}}
    """

    @property
    def prefix(self) -> str:
        """Return the prefix this resolver handles."""
        return "project"

    async def resolve(self, path: str, context: ResolverContext) -> Optional[str]:
        """
        Resolve project placeholders.

        Args:
            path: Path after the prefix (e.g., "name", "description")
            context: Resolver context

        Returns:
            Resolved value or None
        """
        # Try to get project identifier from trigger event
        project_id = None
        project_identifier = None

        # Check if event has project information
        if context.trigger_event_data:
            payload = context.trigger_event_data.get("payload", {})
            project_id = payload.get("project_id")
            project_identifier = payload.get("project_identifier")

        # Query project from database using CRUD layer
        project = None
        if project_id:
            project = crud_project.get(context.db, id=project_id)
        elif project_identifier:
            project = crud_project.get_by_identifier(
                context.db, identifier=project_identifier
            )

        if not project:
            self.logger.warning(
                f"Could not find project for resolution (id={project_id}, identifier={project_identifier})"
            )
            return None

        # Resolve the requested field
        if path == "name":
            return project.name
        elif path == "description":
            return project.description or ""
        elif path == "identifier":
            return project.identifier
        elif path == "organization":
            return project.organization
        elif path == "id":
            return str(project.id)
        else:
            self.logger.warning(f"Unknown project field: {path}")
            return None
