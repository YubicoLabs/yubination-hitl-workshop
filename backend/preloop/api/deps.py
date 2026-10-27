"""Dependency injection hooks for the API."""

from typing import Any


class NoopBudgetEnforcer:
    """Default no-op budget enforcer for OSS."""

    def enforce_or_raise(self, *args: Any, **kwargs: Any) -> None:
        pass


def get_budget_enforcer() -> Any:
    """Dependency hook for enterprise budget enforcement."""
    return NoopBudgetEnforcer()
