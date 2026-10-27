"""Resolver for account-related placeholders."""

import logging
from typing import Optional

from preloop.models.crud import crud_account, crud_user

from .base import PromptResolver, ResolverContext

logger = logging.getLogger(__name__)


class AccountResolver(PromptResolver):
    """
    Resolver for account data from the database.

    Handles placeholders like:
    - {{account.email}} - Primary user's email
    - {{account.name}} - Organization name
    - {{account.id}} - Account ID
    """

    @property
    def prefix(self) -> str:
        """Return the prefix this resolver handles."""
        return "account"

    async def resolve(self, path: str, context: ResolverContext) -> Optional[str]:
        """
        Resolve account placeholders.

        Args:
            path: Path after the prefix (e.g., "email", "name")
            context: Resolver context

        Returns:
            Resolved value or None
        """
        # Try to get account ID from trigger event
        account_id = context.trigger_event_data.get("account_id")

        if not account_id:
            self.logger.warning("No account_id in trigger event data")
            return None

        # Query account from database using CRUD layer
        account = crud_account.get(context.db, id=account_id)

        if not account:
            self.logger.warning(f"Could not find account with id={account_id}")
            return None

        # Resolve the requested field
        if path == "email":
            # Get email from primary user
            if account.primary_user_id:
                primary_user = crud_user.get(
                    context.db, id=str(account.primary_user_id)
                )
                if primary_user:
                    return primary_user.email
            self.logger.warning(f"No primary user found for account {account_id}")
            return None
        elif path == "name":
            return account.organization_name or ""
        elif path == "id":
            return str(account.id)
        else:
            self.logger.warning(f"Unknown account field: {path}")
            return None
