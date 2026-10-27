"""System features and plugin detection endpoints."""

from typing import Any, Dict

from fastapi import APIRouter

from preloop.config import settings
from preloop.plugins.base import get_plugin_manager

router = APIRouter()


@router.get("/features")
def get_features() -> Dict[str, Any]:
    """Get enabled features and plugins.

    Returns information about which plugins are installed and what features
    are available in the system. This allows the frontend to dynamically
    show/hide UI sections based on backend capabilities.

    Returns:
        Dictionary with:
        - plugins: List of enabled plugin metadata
        - features: Dict of feature flags (e.g., rbac, user_management, registration, etc.)
    """
    plugin_manager = get_plugin_manager()
    result = plugin_manager.get_enabled_features()

    # Add config-based feature flags
    result["features"]["registration"] = settings.registration_enabled

    return result
