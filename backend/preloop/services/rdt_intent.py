"""Role Delegation Token (RDT) intent hash.

Computes a tamper-evident fingerprint of the security-critical fields in an
approval request using SHA-256 over the RFC 8785 JCS (JSON Canonicalization
Scheme) of a structured intent envelope.

The hash is stored on ApprovalRequest.intent_hash_hex at creation time.
It enables:
  - Audit trail verification: confirm no fields were altered after creation.
  - Step-up binding: a future protocol can sign the intent hash with the
    hardware key so the approval is cryptographically tied to the exact action.
  - Replay prevention: approval_request_id + account_id scope the hash to a
    single request in a single tenant.

Threat model: docs/rdt-intent-hash.md
"""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import jcs


# Fields included in the intent envelope (must not change once defined — any
# change invalidates all stored hashes).
_ENVELOPE_VERSION = 1


def build_intent_envelope(
    *,
    account_id: uuid.UUID,
    approval_request_id: uuid.UUID,
    tool_name: str,
    tool_args: Dict[str, Any],
    requested_at: datetime,
    intent_risk_tier: Optional[str] = None,
    intent_flags: Optional[list] = None,
) -> Dict[str, Any]:
    """Return the canonical intent envelope dict.

    Only JSON-primitive-compatible types are used so that jcs.canonicalize
    produces a deterministic, RFC 8785-compliant byte string.

    Envelope versions:
        v=1  Original envelope — six fields, no verifier data.
        v=2  Adds intent_risk_tier + intent_flags so the hardware signature
             commits to the assessed risk, not just the operation.
             Used when intent_risk_tier is not None.

    Args:
        account_id: Tenant scope — prevents cross-tenant hash collisions.
        approval_request_id: Unique per-request — prevents replay.
        tool_name: The tool being called.
        tool_args: The tool arguments (arbitrary JSON-compatible dict).
        requested_at: When the request was created (stored as UTC ISO 8601).
        intent_risk_tier: Risk tier from the intent verifier (optional, v=2).
        intent_flags: Flag list from the intent verifier (optional, v=2).

    Returns:
        A dict suitable for jcs.canonicalize().
    """
    # Normalise datetime to UTC with explicit offset so the string is stable.
    if requested_at.tzinfo is None:
        requested_at = requested_at.replace(tzinfo=timezone.utc)
    requested_at_utc = requested_at.astimezone(timezone.utc)
    # Drop microseconds to keep the string consistent regardless of DB precision.
    requested_at_str = requested_at_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    if intent_risk_tier is not None:
        # v=2: hardware signature commits to the verifier's risk assessment.
        return {
            "v": 2,
            "account_id": str(account_id),
            "approval_request_id": str(approval_request_id),
            "intent_flags": sorted(intent_flags or []),  # sorted for determinism
            "intent_risk_tier": intent_risk_tier,
            "requested_at": requested_at_str,
            "tool_args": tool_args,
            "tool_name": tool_name,
        }

    return {
        "v": _ENVELOPE_VERSION,
        "account_id": str(account_id),
        "approval_request_id": str(approval_request_id),
        "tool_args": tool_args,
        "tool_name": tool_name,
        "requested_at": requested_at_str,
    }


def compute_intent_hash(
    *,
    account_id: uuid.UUID,
    approval_request_id: uuid.UUID,
    tool_name: str,
    tool_args: Dict[str, Any],
    requested_at: datetime,
    intent_risk_tier: Optional[str] = None,
    intent_flags: Optional[List[str]] = None,
) -> str:
    """Return hex-encoded SHA-256 of the JCS-canonicalized intent envelope.

    When intent_risk_tier is provided the v=2 envelope is used, which binds
    the hardware signature to the verifier's risk assessment in addition to
    the operation itself.

    Args:
        account_id: Tenant scope.
        approval_request_id: Unique per-request.
        tool_name: Tool being called.
        tool_args: Tool arguments.
        requested_at: Request creation timestamp.
        intent_risk_tier: Risk tier from the intent verifier (optional, v=2).
        intent_flags: Flag list from the intent verifier (optional, v=2).

    Returns:
        64-character lowercase hex string (SHA-256 digest).
    """
    envelope = build_intent_envelope(
        account_id=account_id,
        approval_request_id=approval_request_id,
        tool_name=tool_name,
        tool_args=tool_args,
        requested_at=requested_at,
        intent_risk_tier=intent_risk_tier,
        intent_flags=intent_flags,
    )
    canonical_bytes: bytes = jcs.canonicalize(envelope)
    return hashlib.sha256(canonical_bytes).hexdigest()


def verify_intent_hash(
    stored_hex: str,
    *,
    account_id: uuid.UUID,
    approval_request_id: uuid.UUID,
    tool_name: str,
    tool_args: Dict[str, Any],
    requested_at: datetime,
    intent_risk_tier: Optional[str] = None,
    intent_flags: Optional[List[str]] = None,
) -> bool:
    """Return True if stored_hex matches a freshly computed hash.

    Args:
        stored_hex: The hash stored on the approval request.
        account_id: Tenant scope.
        approval_request_id: Unique per-request.
        tool_name: Tool being called.
        tool_args: Tool arguments.
        requested_at: Request creation timestamp.
        intent_risk_tier: Persisted risk tier; selects the v2 envelope when set.
        intent_flags: Persisted verifier flags included in the v2 envelope.

    Returns:
        True when the stored hash matches the recomputed hash; False otherwise.
    """
    expected = compute_intent_hash(
        account_id=account_id,
        approval_request_id=approval_request_id,
        tool_name=tool_name,
        tool_args=tool_args,
        requested_at=requested_at,
        intent_risk_tier=intent_risk_tier,
        intent_flags=intent_flags,
    )
    # Constant-time comparison to resist timing attacks.
    return hmac_compare(stored_hex, expected)


def hmac_compare(a: str, b: str) -> bool:
    """Constant-time string comparison."""
    import hmac as _hmac

    return _hmac.compare_digest(a.encode(), b.encode())
