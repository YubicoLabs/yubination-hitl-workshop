# Audit an approval

Distinguish an approved action, its verification evidence and actual execution. This challenge reuses Preloop’s existing verifiers; it does not introduce another cryptographic implementation.

## Browser challenge

Before you begin, complete J1 with your own approved request and stored step-up evidence. Use the same signed-in account. No checkout or new signature is needed.

You will identify the approved action, explain its action class, read three server checks and find separate evidence of execution.

1. Open **Audit an approval**, select **Load my approvals**, choose your request and select **Verify my approval**.
2. Read the selected request, tool and arguments. The display omits credential-bearing fields; it is not the canonical original. Open the approval for its receipt and recorded policy context. An action class describes an effect: `read` looks up data; `write` changes it. This approval path defaults to `write`; that label is not a separately enforced policy. The tool’s current approval policy is available under **Tools**.
3. Read each server result: the stored action matches its intent hash; the challenge binds that intent; the stored assertion signature matches the credential public key. Missing, malformed or failed evidence is not a pass. Preserve the original receipt if verification fails.
4. Optionally expand the recorded software comparison. Changing an argument breaks the action binding even if the old signature still validates the old bytes. This is a recorded fixture result, not live browser cryptography, a participant approval or hardware evidence.
5. Return to **J1 step 5**. Run `get_customer_status` through your agent or use the browser alternative there. Compare this independent readback with the original tool result. Explain what changed, what is signed and what proves execution. A green check does not complete the learning outcome.

Expand signed inputs when needed. A Role Delegation Token (RDT) conceptually describes scoped delegation: who may do what, under which constraints. This implementation provides partial intent binding, not a fully signed delegation token. The intent contains `v`, `account_id`, `approval_request_id`, `tool_name`, `tool_args` and `requested_at`; version 2 adds `intent_risk_tier` and `intent_flags`. The whole RDT display, server identity/policy context and supplied purpose are not all signed by this binding.

The browser uses server re-verification. Its three checks do not establish trusted key ownership, origin/RP policy, user-verification (UV) policy, freshness, full delegation authority, PreviewSign’s additional signature or execution. Loaded evidence stays in memory. Keep private receipts out of feedback and source control.

## Optional independent offline verification

The browser challenge needs no source checkout. The steps below require the workshop's published source repository; if no public source is configured, continue the browser challenge and defer these steps. No internal repository access is assumed.

## Before you begin

Use a finalized repository checkout and Python 3.13. This procedure was exercised on macOS with Python 3.13.3, Python-FIDO2 2.2.1, cryptography 49.0.0 and jcs 0.2.1. Windows installation has not been validated. No YubiKey, Preloop account or API key is needed for the software fixtures.

Dependency installation requires network access. Verification after installation is offline. In your terminal, from the repository root, create an isolated environment:

```sh
python3.13 -m venv .venv-receipt
.venv-receipt/bin/python -m pip install --only-binary=:all: --no-deps -r scripts/workshop/requirements-receipt.txt
.venv-receipt/bin/python -m pip check
```

All runtime dependencies are pinned. A fresh isolated installation with these commands, dependency checks and both software fixture commands passed on macOS arm64 with CPython 3.13.3. This does not validate Windows installation or real hardware. If a wheel is unavailable for your platform, stop and ask the facilitator rather than substituting untested versions.

## Inspect a software receipt

1. In your terminal, verify the included ML-DSA-44 receipt:

   ```sh
   .venv-receipt/bin/python scripts/workshop/verify_receipt.py scripts/workshop/fixtures/mldsa44-software-receipt.json --explain
   ```

   Expected first line:

   ```text
   checks_passed: MLDSA44 (COSE -48)
   ```

2. Read the seven checks and limitations. The checks cover canonical action hashing, challenge binding, the signed user-presence flag, and the COSE signature. The receipt's included public key verifies that signature; this does not establish that the key belongs to an authorized person or protected hardware.
3. Verify the classical example:

   ```sh
   .venv-receipt/bin/python scripts/workshop/verify_receipt.py scripts/workshop/fixtures/es256-software-receipt.json --explain
   ```

   Expect `checks_passed: ES256 (COSE -7)`. Compare its algorithm and signature
   with the post-quantum example. Neither result proves the action executed.
4. Add `--json` for stable machine-readable statuses and individual checks. The CLI also accepts `-` for JSON on standard input.

The included receipts were generated with the existing offline verifier test fixtures. Their private keys are software test keys. They are not real approvals, hardware evidence or proof of workshop completion. The fixed example origin is `https://fixture.invalid`.

## Independently inspect your own receipt

Download the receipt from your own approval page to Downloads, outside your repository. It may contain action arguments or identifying information. Replace the filename below with your downloaded filename; keep the path quoted:

```sh
.venv-receipt/bin/python scripts/workshop/verify_receipt.py "$HOME/Downloads/workshop-receipt.json" --explain
```

The verifier reads the local file and makes no network request. Do not paste receipts or keys into feedback. Compare the displayed algorithm with the approval page. Keep database execution evidence separate.

## Interpret the result

| Status | Exit code | Meaning |
|---|---|---|
| `checks_passed` | 0 | Existing verifier checks passed using the supplied public key. |
| `checks_failed` | 1 | At least one check failed; do not rely on the receipt. |
| `malformed_input` | 2 | Input could not be read or parsed as a supported receipt. Dependency/argument errors also exit 2. |
| `unsupported_algorithm` | 3 | The installed verifier cannot verify this algorithm. |

Origin and relying-party ID expectations, ceremony type and user-verification policy are **not checked** by this verifier. A cryptographically signed origin is not an origin allowlist check. Trusted enrollment, hardware protection, authorization, freshness, replay prevention and actual execution are not established by a passing result. Inspecting the `UV` flag is not a substitute for enforcing a user-verification policy.

If an algorithm is unsupported, compare installed versions with the pinned requirements. Do not change a receipt's algorithm label to obtain a passing result. Missing public keys, incomplete receipts and corrupted signatures fail verification. Use the existing offline regression tests to explore corrupt-signature rejection; do not send altered approvals to the running application.

## Check your understanding

Explain what an ML-DSA signature verifies, why a receipt-supplied public key does not establish identity, and which independent evidence would demonstrate database execution.

## Finish the challenge

Return to your original workshop tab. The verifier does not change the server or authenticator. Remove only the `.venv-receipt` environment you created when you no longer need it; retain private receipts according to your organization's policy.

## Canonical stored approval verification API

`GET /api/v1/audit/decisions/{request_id}/verify` is the supported server recheck.
It returns `signature_valid`, `challenge_bound` and `intent_intact`: the stored
assertion signature, SHA256(intent_hash_bytes || nonce) challenge binding, and
canonical v1/v2 intent integrity. Missing approval and incomplete ceremony evidence
retain the existing 404/422 responses. The duplicate `verify-rdt` endpoint is
removed from routing and OpenAPI; RDT construction, storage and retrieval remain.

The server resolves a full credential ID within your account, including retired
keys for historical verification. Old records without full IDs require one unique
account-scoped tail match. Missing/deleted keys, mismatched IDs and ambiguous tails
fail; retirement does not grant current authentication authority. These checks do
not authenticate the whole RDT or unsigned reasoning, policy/identity/context
labels, current authority, origin/RP/UV policy, freshness, hardware provenance,
PreviewSign's extra proof or execution. Inspect those separately; a matching
signature alone is not a whole-token or delegated-authority claim.
