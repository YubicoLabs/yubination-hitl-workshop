"""Authentication package for the API."""

from preloop.api.auth.jwt import (
    get_current_active_user,
    get_current_user,
    get_current_active_user_optional,  # Added optional user getter
    get_user_from_token_if_valid,  # Added for WebSocket auth
    oauth2_scheme,
)
from preloop.api.auth.router import router as auth_router

__all__ = [
    "auth_router",
    "get_current_user",
    "get_current_active_user",
    "oauth2_scheme",
    "get_current_active_user_optional",  # Added optional user getter
    "get_user_from_token_if_valid",  # Added for WebSocket auth
]
