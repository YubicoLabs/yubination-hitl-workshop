"""Deployment-wide protection for workshop configuration endpoints."""

from fastapi import HTTPException, status

from preloop.config import settings


def require_configuration_unlocked() -> None:
    """Reject public configuration changes before their handlers run."""
    if settings.workshop_configuration_locked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workshop tools and approval policies are configured for this exercise.",
        )
