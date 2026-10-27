"""Multi-protocol step-up registry.

Defines the StepUpProtocol ABC and a registry mapping protocol_id strings to
concrete implementations. New protocols are added by:
  1. Subclassing StepUpProtocol and setting protocol_id.
  2. Registering the class in STEP_UP_PROTOCOLS at the bottom of this file.

Current implementations:
  webauthn_discoverable  — FIDO2 resident-key (discoverable) ceremony [LIVE]
  piv                    — PIV/CAC smartcard [STUB]
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Dict, Optional, Tuple

from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ChallengeResult:
    """Result returned by StepUpProtocol.complete()."""

    verified: bool
    credential_name: Optional[str] = None
    credential_id_tail: Optional[str] = None
    sign_count: Optional[int] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class StepUpProtocol(ABC):
    """Abstract base for step-up verification protocols.

    Each protocol handles one challenge-response flow. The endpoint layer
    (webauthn_stepup.py) will eventually delegate begin/complete to the
    protocol selected by ApprovalWorkflow.step_up_protocol.

    Implementations must be stateless — any per-request state is stored via
    the DB (WebAuthnChallengeSession or a future equivalent).
    """

    #: Unique string identifier for this protocol. Set as a class variable.
    protocol_id: ClassVar[str]

    @abstractmethod
    def begin(
        self,
        db: Session,
        *,
        account_id: Any,
        approval_request_id: Any,
    ) -> Tuple[Dict[str, Any], bytes]:
        """Start a challenge.

        Args:
            db: Synchronous SQLAlchemy session.
            account_id: Tenant UUID.
            approval_request_id: UUID of the approval request.

        Returns:
            (options_dict, state_bytes) where options_dict is the JSON-
            serializable challenge sent to the client and state_bytes is
            the opaque server-side state to be persisted and retrieved at
            complete() time.
        """

    @abstractmethod
    def complete(
        self,
        db: Session,
        *,
        state_bytes: bytes,
        response: Dict[str, Any],
        account_id: Any,
        approval_request_id: Any,
    ) -> ChallengeResult:
        """Verify a challenge response.

        Args:
            db: Synchronous SQLAlchemy session.
            state_bytes: The state_bytes returned by begin() (retrieved from DB).
            response: The raw response dict from the client.
            account_id: Tenant UUID (for cross-tenant isolation checks).
            approval_request_id: UUID of the approval request.

        Returns:
            ChallengeResult with verified=True on success.
        """


# ---------------------------------------------------------------------------
# Concrete: WebAuthn discoverable (LIVE — full implementation in
# webauthn_stepup.py; this class is the registry entry + thin delegation)
# ---------------------------------------------------------------------------


class WebAuthnChallengeProtocol(StepUpProtocol):
    """FIDO2 discoverable-credential ceremony (resident key, no allowCredentials).

    The full business logic lives in preloop.api.endpoints.webauthn_stepup.
    This class is the authoritative registry entry and thin delegate; the
    endpoint can be refactored to call through this class in a future ticket.
    """

    protocol_id: ClassVar[str] = "webauthn_discoverable"

    def begin(
        self,
        db: Session,
        *,
        account_id: Any,
        approval_request_id: Any,
    ) -> Tuple[Dict[str, Any], bytes]:
        import uuid as _uuid

        from fido2.webauthn import UserVerificationRequirement

        from preloop.api.endpoints.webauthn_registration import fido2_server
        from preloop.models.crud.webauthn_credential import crud_webauthn_credential

        options, state = fido2_server.authenticate_begin(
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        state_bytes = json.dumps(state).encode()
        challenge_bytes = bytes(options.public_key.challenge)

        crud_webauthn_credential.create_challenge_session(
            db,
            account_id=account_id,
            approval_request_id=_uuid.UUID(str(approval_request_id)),
            fido2_state=state_bytes,
            challenge=challenge_bytes,
        )

        # Build client-facing options dict (mirrors _auth_options_to_dict)
        import base64

        def _b64url(b: bytes) -> str:
            return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

        pk = options.public_key
        options_dict: Dict[str, Any] = {
            "challenge": _b64url(bytes(pk.challenge)),
            "rpId": pk.rp_id,
            "allowCredentials": None,
            "userVerification": (
                pk.user_verification.value if pk.user_verification else "preferred"
            ),
            "timeout": pk.timeout,
        }
        return options_dict, state_bytes

    def complete(
        self,
        db: Session,
        *,
        state_bytes: bytes,
        response: Dict[str, Any],
        account_id: Any,
        approval_request_id: Any,
    ) -> ChallengeResult:
        raise NotImplementedError(
            "Use the webauthn_stepup.step_up_complete endpoint directly. "
            "The registry protocol is a routing abstraction — it does not "
            "duplicate ceremony logic. See preloop/api/endpoints/webauthn_stepup.py."
        )


# ---------------------------------------------------------------------------
# Stub: PIV / CAC smartcard
# ---------------------------------------------------------------------------


class PIVProtocol(StepUpProtocol):
    """PIV (Personal Identity Verification) smartcard challenge.

    Supports CAC, FIPS 140-2 hardware tokens via the PIV standard.
    Not yet implemented — raise NotImplementedError until a future ticket.
    """

    protocol_id: ClassVar[str] = "piv"

    def begin(
        self,
        db: Session,
        *,
        account_id: Any,
        approval_request_id: Any,
    ) -> Tuple[Dict[str, Any], bytes]:
        raise NotImplementedError(
            "PIV protocol is not yet implemented. Use webauthn_discoverable for now."
        )

    def complete(
        self,
        db: Session,
        *,
        state_bytes: bytes,
        response: Dict[str, Any],
        account_id: Any,
        approval_request_id: Any,
    ) -> ChallengeResult:
        raise NotImplementedError("PIV protocol is not yet implemented.")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

#: Map of protocol_id → protocol class. Add new protocols here.
STEP_UP_PROTOCOLS: Dict[str, type[StepUpProtocol]] = {
    WebAuthnChallengeProtocol.protocol_id: WebAuthnChallengeProtocol,
    PIVProtocol.protocol_id: PIVProtocol,
}

#: The protocol_id used when ApprovalWorkflow.step_up_protocol is NULL.
DEFAULT_PROTOCOL_ID = WebAuthnChallengeProtocol.protocol_id


def get_protocol(protocol_id: Optional[str] = None) -> StepUpProtocol:
    """Return a protocol instance for the given protocol_id.

    Args:
        protocol_id: One of the keys in STEP_UP_PROTOCOLS, or None to get
            the default (webauthn_discoverable).

    Returns:
        An instance of the matching StepUpProtocol subclass.

    Raises:
        ValueError: If protocol_id is not in the registry.
    """
    pid = protocol_id or DEFAULT_PROTOCOL_ID
    cls = STEP_UP_PROTOCOLS.get(pid)
    if cls is None:
        valid = ", ".join(sorted(STEP_UP_PROTOCOLS))
        raise ValueError(f"Unknown step-up protocol '{pid}'. Valid protocols: {valid}")
    return cls()
