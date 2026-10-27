"""Application WebAuthn context checks beyond the library signature verifier."""

import json
from typing import Any
from fido2.webauthn import AuthenticatorData


def validate_ceremony_context(
    client_data: Any,
    auth_data: AuthenticatorData,
    *,
    backup_eligible: bool | None = None,
) -> None:
    """Accept same-origin ceremonies and consistent signed backup flags.

    Legacy credentials without a stored BE value have unknown backup eligibility;
    do not invent one. All newly registered credentials persist the signed value.
    """
    context = json.loads(bytes(client_data))
    if context.get("crossOrigin", False) is not False or "topOrigin" in context:
        raise ValueError("Cross-origin passkey ceremonies are not supported.")
    be = bool(auth_data.flags & AuthenticatorData.FLAG.BE)
    bs = bool(auth_data.flags & AuthenticatorData.FLAG.BS)
    if bs and not be:
        raise ValueError("Invalid backup-state flags.")
    if backup_eligible is not None and be != backup_eligible:
        raise ValueError("Credential backup eligibility changed.")
