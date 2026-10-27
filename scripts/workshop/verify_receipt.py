#!/usr/bin/env python3
"""Summarize existing offline WebAuthn verifier checks; never assert execution."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_webauthn_proof import _algorithm_name, _verify  # noqa: E402

LIMITS = (
    "Checks use the public key supplied in the receipt. Its trusted enrollment, "
    "hardware protection and attestation provenance are not established. "
    "Expected origin, relying-party ID, ceremony type and user-verification policy "
    "are not validated by this verifier. A signed origin is not an origin allowlist check. "
    "Passing checks does not prove authorization, freshness, non-replay or execution."
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", help="Receipt JSON path, or - for stdin")
    parser.add_argument(
        "--json", action="store_true", help="Print machine-readable checks"
    )
    parser.add_argument(
        "--explain", action="store_true", help="Show each verifier check"
    )
    args = parser.parse_args()
    try:
        if args.receipt == "-":
            raw = sys.stdin.read(2_000_001)
        else:
            with Path(args.receipt).open() as source:
                raw = source.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Input too large")
        receipt = json.loads(raw)
        if not isinstance(receipt, dict) or type(receipt.get("alg")) is not int:
            raise ValueError("Expected a receipt object and integer algorithm")
        checks, passed = _verify(receipt)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        error = {
            "status": "malformed_input",
            "message": "Cannot read a supported receipt JSON object (maximum 2 MB).",
        }
        print(json.dumps(error) if args.json else error["message"])
        return 2
    report = {
        "status": "unsupported_algorithm"
        if _algorithm_name(receipt.get("alg")) == "unsupported"
        else ("checks_passed" if passed else "checks_failed"),
        "algorithm": {
            "cose_id": receipt.get("alg"),
            "name": _algorithm_name(receipt.get("alg")),
        },
        "checks": checks,
        "execution": "not_checked",
        "key_provenance": "not_established",
        "relying_party_policy": "not_checked",
        "limits": LIMITS,
    }
    if args.json:
        print(json.dumps(report))
    else:
        print(
            f"{report['status']}: {report['algorithm']['name']} (COSE {receipt.get('alg')})"
        )
        if args.explain:
            for check in checks:
                print(f"{'PASS' if check['ok'] else 'FAIL'}: {check['step']}")
        print(LIMITS)
    return 3 if report["status"] == "unsupported_algorithm" else (0 if passed else 1)


if __name__ == "__main__":
    sys.exit(main())
