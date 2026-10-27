"""Shared base64url helpers and WebAuthn object builders for WebAuthn endpoints."""

import base64
from typing import Any, Dict

from fido2.cbor import decode as cbor_decode
from fido2.cose import CoseKey
from fido2.webauthn import AttestedCredentialData


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))


def acd_from_stored(
    credential_id: bytes, public_key_cbor: bytes, aaguid: bytes
) -> AttestedCredentialData:
    """Reconstruct AttestedCredentialData from stored credential bytes."""
    key_dict = cbor_decode(public_key_cbor)
    cose_key = CoseKey.parse(key_dict)
    return AttestedCredentialData.create(aaguid, credential_id, cose_key)


def auth_options_to_dict(options: Any) -> Dict[str, Any]:
    """Serialize fido2 authenticate_begin() options to a JSON-serialisable dict."""
    pk = options.public_key
    allow_creds = None
    if pk.allow_credentials:
        allow_creds = [
            {"type": "public-key", "id": b64url_encode(bytes(c.id))}
            for c in pk.allow_credentials
        ]
    return {
        "challenge": b64url_encode(bytes(pk.challenge)),
        "rpId": pk.rp_id,
        "allowCredentials": allow_creds,
        "userVerification": (
            pk.user_verification.value if pk.user_verification else "preferred"
        ),
        "timeout": pk.timeout,
    }
