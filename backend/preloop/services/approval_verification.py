"""Historical assertion and intent checks, not full RDT or WebAuthn policy validation."""

import base64
import hashlib
import hmac
import json
import uuid
from typing import Any

from fido2.cbor import decode as cbor_decode
from fido2.cose import CoseKey
from sqlalchemy.orm import Session

from preloop.models import models
from preloop.models.crud.webauthn_credential import crud_webauthn_credential
from preloop.services.rdt_intent import verify_intent_hash


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))


def _check_signature(
    public_key_cbor: bytes,
    authenticator_data: bytes,
    client_data_json: bytes,
    signature: bytes,
) -> bool:
    try:
        key_dict = cbor_decode(public_key_cbor)
        cose_key = CoseKey.parse(key_dict)
        signed_data = authenticator_data + hashlib.sha256(client_data_json).digest()
        cose_key.verify(signed_data, signature)
        return True
    except Exception:
        return False


def _check_challenge_binding(
    client_data_json: bytes,
    intent_hash_hex: str,
    challenge_nonce: bytes,
) -> bool:
    try:
        client_data: dict[str, Any] = json.loads(client_data_json)
        b64_challenge: str = client_data.get("challenge", "")
        extracted = _b64url_decode(b64_challenge)
        expected = hashlib.sha256(
            bytes.fromhex(intent_hash_hex) + challenge_nonce
        ).digest()
        return hmac.compare_digest(extracted, expected)
    except Exception:
        return False


def verify_stored_binding(
    req: models.ApprovalRequest, credential: models.UserWebAuthnCredential | None
) -> dict[str, bool]:
    """Check stored signature, intent-derived challenge and canonical intent."""
    signature_valid = credential is not None and _check_signature(
        credential.public_key_cbor,
        req.step_up_authenticator_data,
        req.step_up_client_data_json,
        req.step_up_signature,
    )
    intent_hex = req.intent_hash_hex
    challenge_bound = _check_challenge_binding(
        req.step_up_client_data_json, intent_hex, req.step_up_challenge_nonce
    )
    # (C) Intent integrity
    intent_intact = False
    if intent_hex:
        try:
            intent_intact = verify_intent_hash(
                intent_hex,
                account_id=req.account_id,
                approval_request_id=req.id,
                tool_name=req.tool_name,
                tool_args=req.tool_args or {},
                requested_at=req.requested_at,
                intent_risk_tier=getattr(req, "intent_risk_tier", None),
                intent_flags=getattr(req, "intent_flags", None),
            )
        except Exception:
            intent_intact = False

    return dict(
        signature_valid=signature_valid,
        challenge_bound=challenge_bound,
        intent_intact=intent_intact,
    )


def resolve_credential(
    db: Session, account_id: uuid.UUID, req: models.ApprovalRequest
) -> models.UserWebAuthnCredential | None:
    """Resolve historical evidence without relaxing a present full identifier."""
    if req.account_id != account_id:
        return None
    full_id = getattr(req, "step_up_credential_id", None)
    envelope = getattr(req, "rdt_envelope", None)
    envelope_id = None
    if isinstance(envelope, dict) and "credential_id" in envelope:
        try:
            value = envelope["credential_id"]
            if not isinstance(value, str) or not value:
                return None
            envelope_id = base64.b64decode(value, validate=True)
            if not envelope_id:
                return None
        except (ValueError, TypeError):
            return None
    tail = getattr(req, "step_up_key_id_tail", None)
    if full_id is not None:
        if not isinstance(full_id, bytes) or not full_id:
            return None
        if envelope_id is not None and envelope_id != full_id:
            return None
    elif envelope_id is not None:
        full_id = envelope_id
        if (
            tail is not None
            and tail != (base64.urlsafe_b64encode(full_id).rstrip(b"=").decode()[-8:])
        ):
            return None
    if full_id is not None:
        credential = crud_webauthn_credential.get_by_credential_id(
            db, credential_id=full_id, account_id=account_id, include_retired=True
        )
        if credential is None or credential.account_id != account_id:
            return None
        return credential if credential.credential_id == full_id else None
    if not isinstance(tail, str) or len(tail) != 8:
        return None
    candidates = [
        c
        for c in crud_webauthn_credential.list_by_account(
            db, account_id=account_id, include_retired=True
        )
        if c.account_id == account_id
        and base64.urlsafe_b64encode(c.credential_id).rstrip(b"=").decode()[-8:] == tail
    ]
    return candidates[0] if len(candidates) == 1 else None
