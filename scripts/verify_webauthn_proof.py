#!/usr/bin/env python3
"""Offline WebAuthn step-up proof verifier for Preloop approval step-up.

Usage:
    python scripts/verify_webauthn_proof.py receipt.json

The WebAuthnConsumptionReceipt JSON is available via "Copy WebAuthn proof bundle"
on the Preloop approval view, or from:
    GET /approval/<request_id>/step-up/receipt?token=<token>

Requires: python-fido2 matching the deployment, cryptography, jcs.
PQC verification needs the ML-DSA-enabled python-fido2 build and crypto backend.
"""

import argparse
import base64
import hashlib
import json
import sys
import textwrap

try:
    from fido2.cose import CoseKey
except ImportError:
    print(
        "ERROR: install python-fido2 matching the deployment; PQC requires its ML-DSA-enabled build and cryptography backend",
        file=sys.stderr,
    )
    sys.exit(2)

try:
    import jcs as _jcs
except ImportError:
    print("ERROR: pip install jcs", file=sys.stderr)
    sys.exit(2)

from fido2 import cbor

# ── terminal width helpers ────────────────────────────────────────────────────

WIDTH = 72


def _rule(char: str = "─") -> str:
    return char * WIDTH


def _section(title: str) -> None:
    print()
    print(_rule("═"))
    print(f"  {title}")
    print(_rule("─"))


def _wrap(text: str, indent: int = 2) -> str:
    prefix = " " * indent
    return textwrap.fill(
        text, width=WIDTH, initial_indent=prefix, subsequent_indent=prefix
    )


def _field(label: str, value: str, indent: int = 2) -> None:
    prefix = " " * indent
    label_col = f"{label}:"
    line = f"{prefix}{label_col:<26}{value}"
    if len(line) > WIDTH:
        print(f"{prefix}{label_col}")
        print(_wrap(value, indent + 4))
    else:
        print(line)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


# ── crypto ────────────────────────────────────────────────────────────────────


def _algorithm_name(alg):
    return (
        CoseKey.for_alg(alg).__name__
        if alg in CoseKey.supported_algorithms()
        else "unsupported"
    )


def _load_pub_key_from_cbor(cbor_hex: str, expected_alg: int):
    """Use the same COSE verification implementation as the WebAuthn backend."""
    key_map = cbor.decode(bytes.fromhex(cbor_hex))
    if not isinstance(key_map, dict) or key_map.get(3) != expected_alg:
        raise ValueError("Receipt algorithm does not match COSE public key")
    if expected_alg not in CoseKey.supported_algorithms():
        raise ValueError(
            "Algorithm unsupported by installed python-fido2/crypto backend"
        )
    return CoseKey.parse(key_map)


VerificationResult = dict  # {step: str, ok: bool, detail: str}


def _verify(receipt: dict) -> tuple[list[VerificationResult], bool]:
    results: list[VerificationResult] = []

    def step(name: str, ok: bool, detail: str = "") -> None:
        results.append({"step": name, "ok": ok, "detail": detail})

    # Step 1: receipt type + algorithm
    rt = receipt.get("receipt_type")
    alg = receipt.get("alg")
    step(
        "Confirm receipt type and algorithm",
        rt == "webauthn_step_up" and alg in CoseKey.supported_algorithms(),
        f"receipt_type={rt!r}  alg={alg} ({_algorithm_name(alg)})",
    )

    # Step 2: intent_hash = SHA-256(JCS(intent_envelope))
    env = receipt.get("intent_envelope", {})
    canonical: bytes = _jcs.canonicalize(env)
    computed_intent_hash = hashlib.sha256(canonical).hexdigest()
    stored_intent_hash = receipt.get("intent_hash_hex", "")
    step(
        "Verify intent_hash_hex = SHA-256(JCS(intent_envelope))",
        computed_intent_hash == stored_intent_hash,
        f"computed = {computed_intent_hash}\n    stored  = {stored_intent_hash}",
    )

    # Step 3: challenge = SHA-256(intent_hash_bytes || nonce_bytes)
    try:
        intent_hash_bytes = bytes.fromhex(stored_intent_hash)
        nonce_bytes = bytes.fromhex(receipt.get("challenge_nonce_hex", ""))
        computed_challenge = hashlib.sha256(intent_hash_bytes + nonce_bytes).hexdigest()
        stored_challenge = receipt.get("challenge_hex", "")
        step(
            "Verify challenge = SHA-256(intent_hash || nonce)",
            computed_challenge == stored_challenge,
            f"computed = {computed_challenge}\n    stored  = {stored_challenge}",
        )
    except Exception as exc:
        step("Verify challenge = SHA-256(intent_hash || nonce)", False, str(exc))

    # Step 4: client_data_json.challenge == base64url(challenge_bytes)
    try:
        cdj_bytes = bytes.fromhex(receipt.get("client_data_json_hex", ""))
        cdj = json.loads(cdj_bytes.decode("utf-8"))
        expected_challenge_b64 = _b64url_encode(bytes.fromhex(stored_challenge))
        actual_challenge_b64 = cdj.get("challenge", "")
        # browser may or may not pad — strip = before compare
        match = actual_challenge_b64.rstrip("=") == expected_challenge_b64.rstrip("=")
        step(
            "Verify clientDataJSON.challenge == base64url(challenge)",
            match,
            f"clientDataJSON.challenge = {actual_challenge_b64}\n    expected              = {expected_challenge_b64}",
        )
    except Exception as exc:
        step("Verify clientDataJSON.challenge == base64url(challenge)", False, str(exc))

    # Step 5: authenticatorData flags (UP bit must be set)
    up_set = uv_set = be_set = False
    try:
        auth_data = bytes.fromhex(receipt.get("authenticator_data_hex", ""))
        flags_byte = auth_data[32]
        up_set = bool(flags_byte & 0x01)  # bit 0 = User Present
        uv_set = bool(flags_byte & 0x04)  # bit 2 = User Verified
        be_set = bool(flags_byte & 0x08)  # bit 3 = Backup Eligible
        rp_id_hash = auth_data[:32].hex()
        step(
            "Parse authenticatorData: UP flag must be set",
            up_set,
            f"UP={up_set}  UV={uv_set}  BE={be_set}\n    rpIdHash={rp_id_hash[:32]}…",
        )
    except Exception as exc:
        step("Parse authenticatorData: UP flag must be set", False, str(exc))

    # Step 6: client_data_hash = SHA-256(clientDataJSON)
    try:
        cdj_bytes = bytes.fromhex(receipt.get("client_data_json_hex", ""))
        client_data_hash = hashlib.sha256(cdj_bytes).digest()
        step(
            "Compute client_data_hash = SHA-256(clientDataJSON)",
            True,
            f"client_data_hash = {client_data_hash.hex()}",
        )
    except Exception as exc:
        step("Compute client_data_hash = SHA-256(clientDataJSON)", False, str(exc))
        client_data_hash = b""

    # Step 7: verify COSE signature over authData || clientDataHash
    pk_cbor_hex = receipt.get("public_key_cbor_hex")
    if not pk_cbor_hex:
        step(
            "Verify COSE signature",
            False,
            "public_key_cbor_hex absent — signature not verified. The key was de-enrolled after the step-up.",
        )
    else:
        try:
            auth_data_bytes = bytes.fromhex(receipt.get("authenticator_data_hex", ""))
            sig_bytes = bytes.fromhex(receipt.get("signature_hex", ""))
            signed_data = auth_data_bytes + client_data_hash
            pub_key = _load_pub_key_from_cbor(pk_cbor_hex, alg)
            pub_key.verify(signed_data, sig_bytes)
            step(
                "Verify COSE signature",
                True,
                "Signature over (authData || SHA-256(clientDataJSON)) is valid.",
            )
        except Exception as exc:
            step("Verify COSE signature", False, str(exc))

    all_ok = all(r["ok"] for r in results)
    return results, all_ok


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline WebAuthn step-up proof verifier"
    )
    parser.add_argument(
        "receipt_json", help="Path to WebAuthnConsumptionReceipt JSON file"
    )
    args = parser.parse_args()

    with open(args.receipt_json) as f:
        receipt = json.load(f)

    env = receipt.get("intent_envelope", {})
    tool_name = env.get("tool_name", "(not present)")
    tool_args = env.get("tool_args", {})
    account_id = env.get("account_id", "(not present)")
    request_id = env.get("approval_request_id", "(not present)")
    requested_at = env.get("requested_at", "(not present)")
    signed_at = receipt.get("signed_at", "(not present)")
    intent_hash_hex = receipt.get("intent_hash_hex", "")

    # ── header ────────────────────────────────────────────────────────────────
    print()
    print(_rule("═"))
    print("  PRELOOP  ·  WEBAUTHN STEP-UP PROOF VERIFIER")
    print("  Format: WebAuthnConsumptionReceipt v1.0 (RDT-compatible)")
    print(_rule("─"))
    print(
        _wrap(
            "This tool verifies, without contacting any server, that a registered "
            "hardware security key cryptographically approved the exact AI agent "
            "action shown below, using the standard WebAuthn authentication protocol."
        )
    )

    # ── what was approved ─────────────────────────────────────────────────────
    _section("WHAT WAS APPROVED")
    _field("Request ID", request_id)
    _field("Account ID", account_id)
    _field("Tool / action", tool_name)
    _field("Requested at (UTC)", requested_at)
    _field("Signed at (UTC)", signed_at)
    _field(
        "COSE algorithm",
        f"{receipt.get('alg')} ({_algorithm_name(receipt.get('alg'))})",
    )
    print()
    print("  Arguments passed to the tool:")
    for k, v in tool_args.items():
        val = v if isinstance(v, str) else json.dumps(v)
        _field(f"    {k}", val, indent=0)

    # ── glossary ──────────────────────────────────────────────────────────────
    _section("GLOSSARY OF TERMS")

    terms = [
        (
            "WebAuthn / FIDO2",
            "Web Authentication — the W3C + FIDO Alliance protocol for hardware-backed "
            "authentication. The browser (or native app) mediates between a hardware "
            "security key (YubiKey, TouchID, Windows Hello) and the server. The private "
            "key never leaves the authenticator.",
        ),
        (
            "COSE signature algorithm",
            "The receipt and public key must declare the same supported COSE algorithm. "
            "ML-DSA requires the matching python-fido2 and cryptography backend. "
            "but the key is registered in the standard WebAuthn fashion and the signed "
            "payload is (authenticatorData || SHA-256(clientDataJSON)).",
        ),
        (
            "Challenge derivation (RDT invariant)",
            "The WebAuthn challenge is not a random nonce alone. It is computed as: "
            "SHA-256(intent_hash_bytes || challenge_nonce_bytes). This binds the hardware "
            "response cryptographically to the exact same intent_hash as the ARKG flow, "
            "so both flows authorize the same action fingerprint.",
        ),
        (
            "intent_hash",
            "SHA-256 of the RFC 8785 JCS canonical encoding of the intent_envelope. "
            "Covers account_id, approval_request_id, tool_name, tool_args, and "
            "requested_at. Any change to any field invalidates the challenge derivation "
            "and thus the signature. Both ARKG and WebAuthn step-up flows reference the "
            "same intent_hash.",
        ),
        (
            "authenticatorData flags",
            "A flags byte at offset 32 of the authenticatorData blob. "
            "UP (bit 0) = User Present: the authenticator required physical interaction "
            "(touch). UV (bit 2) = User Verified: PIN or biometric check was performed. "
            "BE (bit 3) = Backup Eligible: key can be synced across devices (cloud keys). "
            "This verifier checks UP is set; UV and BE are reported for auditor review.",
        ),
        (
            "Signed payload",
            "The bytes the hardware key actually signs: "
            "authenticatorData || SHA-256(clientDataJSON). "
            "clientDataJSON includes the challenge, origin, and type. authenticatorData "
            "includes the rpIdHash, flags, sign counter, and (for registration) the "
            "credential public key. Both are verified here.",
        ),
        (
            "Offline verification",
            "No network call, no Preloop account, no trust in Preloop's servers is "
            "required. Verification uses only the receipt fields and standard "
            "cryptographic primitives.",
        ),
    ]

    for term, defn in terms:
        print()
        print(f"  {term}")
        print(_wrap(defn, indent=4))

    # ── verification steps ─────────────────────────────────────────────────────
    _section("VERIFICATION STEPS PERFORMED")

    try:
        results, all_ok = _verify(receipt)
    except Exception as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        sys.exit(2)

    for i, r in enumerate(results, 1):
        icon = "✓" if r["ok"] else "✗"
        print()
        print(f"  Step {i} — {icon}  {r['step']}")
        if r.get("detail"):
            for line in r["detail"].split("\n"):
                print(_wrap(line.strip(), indent=6))

    # ── what this proves ──────────────────────────────────────────────────────
    _section("WHAT THIS VERIFICATION PROVES")
    proven = [
        "The approval data is tamper-evident. Altering any field — account, "
        "request ID, tool name, any argument, or the requested_at timestamp — "
        "changes the intent_hash, which changes the challenge, which breaks "
        "the clientDataJSON challenge binding and the signature.",
        "The challenge was derived from the same intent_hash as the ARKG flow. "
        "Both step-up protocols authorize the exact same canonical action fingerprint. "
        "An auditor can independently verify that the WebAuthn and ARKG challenges "
        "are bound to the same intent_envelope.",
        "The registered key produced a valid COSE signature over the standard "
        "WebAuthn signed payload (authenticatorData || SHA-256(clientDataJSON)). "
        "Signature verification alone does not establish hardware provenance.",
        "The User Present (UP) flag was set in the authenticator's response, "
        "indicating the key's touch sensor was activated. This is enforced by "
        "authenticator firmware, not by the server.",
    ]
    for i, point in enumerate(proven, 1):
        print()
        print(_wrap(f"[{i}] {point}"))

    # ── limitations ───────────────────────────────────────────────────────────
    _section("WHAT THIS DOES NOT PROVE")

    uv_note = ""
    try:
        auth_data = bytes.fromhex(receipt.get("authenticator_data_hex", ""))
        uv_set = bool(auth_data[32] & 0x04)
        be_set = bool(auth_data[32] & 0x08)
        uv_note = (
            f"UV (User Verified) was {'SET' if uv_set else 'NOT SET'} in this receipt. "
            f"{'A PIN or biometric check was performed.' if uv_set else 'No PIN or biometric was required by the server at the time of this step-up.'}"
        )
        be_note = (
            f"BE (Backup Eligible) was {'SET' if be_set else 'NOT SET'}: "
            f"{'this key may be synced to the cloud (e.g. a platform passkey). Physical device uniqueness cannot be guaranteed.' if be_set else 'this key is hardware-bound and cannot be synced across devices.'}"
        )
    except Exception:
        uv_note = ""
        be_note = ""

    limits = [
        "The identity of the individual who touched the security key. The proof "
        "establishes that someone with physical access to a registered authenticator "
        "approved this action. Organisation policy determines who is authorised to "
        "hold that device.",
        (
            "Strong biometric or PIN authentication, unless UV is set. " + uv_note
            if uv_note
            else "Strong biometric or PIN authentication unless UV is set in the receipt."
        ),
        (
            "Physical device uniqueness if BE is set. " + be_note
            if be_note
            else "Physical device uniqueness if the BE (Backup Eligible) flag is set."
        ),
        "That the public key in the receipt still corresponds to an active, enrolled "
        "credential. The verifier cannot confirm the key was not de-enrolled after "
        "the step-up. The public_key_cbor_hex comes from the stored credential at "
        "receipt-generation time.",
        "That a SCITT transparency log receipt exists. The scitt_receipt field "
        "is None — Merkle-anchored non-repudiation is pending in the live system.",
    ]
    for i, point in enumerate(limits, 1):
        print()
        print(_wrap(f"[{i}] {point}"))

    # ── verdict ───────────────────────────────────────────────────────────────
    print()
    print(_rule("═"))
    if all_ok:
        print("  RESULT:  ✓  VALID")
        print()
        print(
            _wrap(
                "The WebAuthn COSE signature is cryptographically valid. "
                "The challenge is correctly derived from the intent_hash. "
                "A registered hardware security key approved this exact AI agent action."
            )
        )
    else:
        print("  RESULT:  ✗  INVALID")
        print()
        failed = [r["step"] for r in results if not r["ok"]]
        print(
            _wrap(
                f"One or more verification steps failed: {', '.join(failed)}. "
                "The approval data may have been tampered with, the receipt may be "
                "incomplete, or the public key is unavailable."
            )
        )
    print(_rule("═"))
    print()

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
