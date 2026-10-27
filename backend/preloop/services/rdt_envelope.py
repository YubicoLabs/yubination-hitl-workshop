"""Construct stored RDT display envelopes.

Actual assertion/intent verification lives in approval_verification.
The whole display envelope is not signed by the step-up ceremony.
"""

import base64
from datetime import datetime, timezone
from typing import Optional, Dict, Any


def construct_rdt_envelope(
    action_class: str,
    operation: str,
    context: Dict[str, Any],
    reasoning: str,
    approver_id: str,
    timestamp: Optional[str] = None,
    credential_id: Optional[bytes] = None,
    credential_name: Optional[str] = None,
    signature: Optional[bytes] = None,
    authenticator_data: Optional[bytes] = None,
    client_data_json: Optional[bytes] = None,
) -> Dict[str, Any]:
    """Construct an RDT envelope (Phase A: JSON format).

    Args:
        action_class: One of: read, write, delete, deploy, spend, admin, privacy
        operation: Human-readable operation description
        context: Operation-specific context (tool name, service, version, etc.)
        reasoning: Justification for the operation
        approver_id: User UUID who approved
        timestamp: Server-recorded ISO-8601 display label (defaults to now).
        credential_id: WebAuthn credential.rawId (optional, added after step-up)
        credential_name: Human-readable credential name (optional, added after step-up)
        signature: WebAuthn response.signature bytes (optional, added after step-up)
        authenticator_data: WebAuthn response.authenticatorData bytes (optional)
        client_data_json: WebAuthn response.clientDataJSON bytes (optional)

    Returns:
        RDT envelope dict (ready for JSON serialization or JSONB storage)
    """
    envelope = {
        "version": "preloop-rdt-v1",
        "action_class": action_class,
        "operation": operation,
        "context": context,
        "reasoning": reasoning,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "approver_id": str(approver_id),
    }

    # Add WebAuthn fields if provided (populated after step-up completes)
    if credential_id is not None:
        envelope["credential_id"] = base64.b64encode(credential_id).decode("ascii")
    if credential_name is not None:
        envelope["credential_name"] = credential_name
    if signature is not None:
        envelope["signature"] = base64.b64encode(signature).decode("ascii")
    if authenticator_data is not None:
        envelope["authenticator_data"] = base64.b64encode(authenticator_data).decode(
            "ascii"
        )
    if client_data_json is not None:
        envelope["client_data_json"] = base64.b64encode(client_data_json).decode(
            "ascii"
        )

    return envelope
