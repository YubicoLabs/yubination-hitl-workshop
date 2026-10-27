"""Verify captured participant proofs offline against caller-supplied run inputs."""

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils
import jcs


VERIFIER_PATH = Path(__file__).resolve().parents[3] / "scripts/verify_webauthn_proof.py"
SPEC = importlib.util.spec_from_file_location(
    "previewsign_webauthn_verifier", VERIFIER_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Required WebAuthn verifier unavailable: {VERIFIER_PATH}")
WEBAUTHN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WEBAUTHN)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def decode_b64(value: str) -> bytes:
    return base64.b64decode(
        value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
    )


def verify_participant_receipt(
    receipt: dict[str, Any], begin: dict[str, Any], expected: dict[str, Any]
) -> dict[str, Any]:
    """Verify each signature independently, bound to the expected run's intent."""
    result: dict[str, Any] = {
        "independent_webauthn_valid": False,
        "independent_previewsign_valid": False,
        "errors": [],
    }
    try:
        require(
            all(isinstance(value, dict) for value in (receipt, begin, expected)),
            "receipt, begin and expected objects required",
        )
        for field in ("origin", "rp_id", "account_id", "request_id", "action"):
            require(
                isinstance(expected.get(field), str) and bool(expected[field]),
                "external expected run inputs required",
            )
        require(
            isinstance(expected.get("tool_args"), dict) and bool(expected["tool_args"]),
            "external expected tool arguments required",
        )
        intent = receipt["intent_envelope"]
        for field, anchor in (
            ("account_id", "account_id"),
            ("approval_request_id", "request_id"),
            ("tool_name", "action"),
            ("tool_args", "tool_args"),
        ):
            require(
                intent[field] == expected[anchor], "intent differs from expected run"
            )
        digest = hashlib.sha256(jcs.canonicalize(intent)).digest()
        require(
            bytes.fromhex(receipt["intent_hash_hex"]) == digest,
            "stored intent digest differs from recomputed intent",
        )
    except Exception:
        result["errors"].append(
            "context: invalid intent or external expected run inputs"
        )
        return result

    try:
        standard_ok = WEBAUTHN._verify(receipt)[1]
        require(standard_ok, "stored WebAuthn proof or challenge binding invalid")
        client = json.loads(bytes.fromhex(receipt["client_data_json_hex"]))
        require(
            client["type"] == "webauthn.get", "clientData type must be webauthn.get"
        )
        require(client["origin"] == expected["origin"], "unexpected clientData origin")
        auth = bytes.fromhex(receipt["authenticator_data_hex"])
        require(len(auth) >= 37, "authenticatorData truncated")
        require(
            auth[:32] == hashlib.sha256(expected["rp_id"].encode()).digest(),
            "unexpected RP ID hash",
        )
        require(auth[32] & 0x05 == 0x05, "both UP and UV required")
        nonce = bytes.fromhex(receipt["challenge_nonce_hex"])
        require(len(nonce) == 32, "32-byte challenge nonce required")
        challenge = hashlib.sha256(digest + nonce).digest()
        require(
            decode_b64(begin["options"]["challenge"]) == challenge,
            "begin challenge differs from recomputed intent challenge",
        )
        result["independent_webauthn_valid"] = True
    except Exception:
        result["errors"].append(
            "webauthn: invalid proof/challenge, type, expected origin/RP ID or UP+UV"
        )

    try:
        require(
            decode_b64(begin["preview_sign_tbs_b64"]) == digest,
            "begin TBS differs from recomputed intent digest",
        )
        public_point = bytes.fromhex(receipt["arkg_derived_pk_hex"])
        require(
            len(public_point) == 65 and public_point[0] == 0x04,
            "65-byte uncompressed P-256 point required",
        )
        public_key = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), public_point
        )
        public_key.verify(
            bytes.fromhex(receipt["arkg_signature_hex"]),
            digest,
            ec.ECDSA(utils.Prehashed(hashes.SHA256())),
        )
        result["independent_previewsign_valid"] = True
    except Exception:
        result["errors"].append(
            "previewsign: invalid P-256 point, DER signature or begin TBS"
        )
    return result


def main() -> None:
    """Read a receipt/begin/expected capture on stdin; emit JSON and fail closed."""
    try:
        capture = json.load(sys.stdin)
        result = verify_participant_receipt(
            capture["receipt"], capture["begin"], capture["expected"]
        )
    except Exception:
        result = {
            "independent_webauthn_valid": False,
            "independent_previewsign_valid": False,
            "errors": [
                "input: JSON receipt, begin and external expected objects required"
            ],
        }
    print(json.dumps(result))
    sys.exit(
        0
        if result["independent_webauthn_valid"]
        and result["independent_previewsign_valid"]
        else 1
    )


if __name__ == "__main__":
    main()
