"""Registry for managing prompt placeholder resolvers."""

import logging
from typing import Dict, Optional

from .base import PromptResolver

logger = logging.getLogger(__name__)


class ResolverRegistry:
    """
    Registry for placeholder resolvers.

    Allows dynamic registration and lookup of resolvers by prefix.
    """

    def __init__(self):
        """Initialize the registry."""
        self._resolvers: Dict[str, PromptResolver] = {}

    def register(self, resolver: PromptResolver):
        """
        Register a resolver for its prefix.

        Args:
            resolver: Resolver instance to register

        Raises:
            ValueError: If a resolver for this prefix already exists
        """
        prefix = resolver.prefix
        if prefix in self._resolvers:
            logger.warning(
                f"Overwriting existing resolver for prefix '{prefix}' with {resolver.__class__.__name__}"
            )

        self._resolvers[prefix] = resolver
        logger.debug(
            f"Registered resolver for prefix '{prefix}': {resolver.__class__.__name__}"
        )

    def get(self, prefix: str) -> Optional[PromptResolver]:
        """
        Get a resolver for a given prefix.

        Args:
            prefix: The placeholder prefix (e.g., "project", "trigger_event")

        Returns:
            Resolver instance, or None if not found
        """
        return self._resolvers.get(prefix)

    def unregister(self, prefix: str):
        """
        Unregister a resolver.

        Args:
            prefix: The placeholder prefix to unregister
        """
        if prefix in self._resolvers:
            del self._resolvers[prefix]
            logger.debug(f"Unregistered resolver for prefix '{prefix}'")


# Global registry instance
resolver_registry = ResolverRegistry()
