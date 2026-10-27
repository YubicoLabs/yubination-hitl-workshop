# Build the Chrome extension and PreviewSign helper (optional)

On an Apple-silicon Mac, build the native helper and assemble an unpacked Chrome extension from the same checkout. You will load that extension in a dedicated Chrome profile and check its connection to the helper. This does not require a YubiKey until you return to the workshop approval exercise.

Chrome does not natively support the proposed PreviewSign WebAuthn extension. The JavaScript extension bridges the page to the Rust native helper; the helper communicates with the YubiKey. Cargo builds the helper. The packaging command assembles the extension's JavaScript, manifest and exact workshop-origin configuration into the folder Chrome can load.

## Before you start

This optional developer path needs tools beyond the participant download:

- Git and [Xcode Command Line Tools](https://developer.apple.com/xcode/resources/).
- Native Apple-silicon [Rust and Cargo](https://rust-lang.org/tools/install/).
- [Python 3](https://www.python.org/downloads/macos/) for assembly and installation.
- [Google Chrome](https://www.google.com/chrome/).
- Network access to crates.io and the pinned public Yubico Git dependency.

Verify the installed tools before building:

```sh
uname -m
git --version
xcode-select -p
rustc --version
cargo --version
python3 --version
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version
```

The architecture must be `arm64`. Stop if a required command is missing; install it through the official link above. Do not change global Cargo settings or bypass browser/operating-system policy. The helper is a development build, not signed or notarized.

Use the source repository linked in **Build from source (optional)** on the workshop page. If that link is unavailable, this source path is not available from the deployment yet. The participant download remains a separate path. Do not substitute an unrelated repository.

## Obtain the matching source

Use the repository URL configured on the workshop page and its published
source ref (full commit, published tag or branch). For a hosted package,
its manifest's full `sourceRevision` identifies the matching source, not a current
main link. In a terminal, choose a new checkout path:

```sh
printf 'Configured workshop repository URL: '
IFS= read -r SOURCE_URL
printf 'Published source ref: '
IFS= read -r SOURCE_REF
SOURCE_CHECKOUT="$HOME/PreviewSign-source"
git clone "$SOURCE_URL" "$SOURCE_CHECKOUT"
cd "$SOURCE_CHECKOUT"
git checkout --detach "$SOURCE_REF"
git rev-parse HEAD
```

Stop on any failure. Compare HEAD with the selected published revision before building.
The extension and native host must come from that same checkout. From that
repository root, choose a new scratch directory outside Git:

```sh
BUILD_ROOT="$(mktemp -d "${TMPDIR:-/private/tmp}/previewsign-build.XXXXXX")"
BUILD_ROOT="$(cd "$BUILD_ROOT" && pwd -P)"
export CARGO_HOME="$BUILD_ROOT/cargo-home"
export CARGO_TARGET_DIR="$BUILD_ROOT/target"
export CARGO_PROFILE_DEV_DEBUG=0
export CARGO_INCREMENTAL=0
cargo build --locked \
  --manifest-path integrations/previewsign/native/Cargo.toml \
  -p sign-extension-host
file "$CARGO_TARGET_DIR/debug/sign-extension-host"
shasum -a 256 "$CARGO_TARGET_DIR/debug/sign-extension-host"
```

This produces `target/debug/sign-extension-host` under BUILD_ROOT, a development
binary, not an optimized/signed release or proof of key compatibility. Keep Cargo.lock unchanged;
do not substitute a newer Git dependency when a pinned fetch fails.

From the same repository root, enter the exact workshop origin shown in your browser (scheme, host and optional port; no path). Then assemble and install both components:

```sh
printf 'Workshop origin (for example http://localhost:8080): '
IFS= read -r WORKSHOP_ORIGIN
python3 -I -S integrations/previewsign/scripts/package_macos_chrome.py assemble \
  --extension-dir "$PWD/integrations/previewsign/extension" \
  --host-binary "$CARGO_TARGET_DIR/debug/sign-extension-host" \
  --output "$BUILD_ROOT/package" \
  --workshop-origin "$WORKSHOP_ORIGIN"
python3 -I -S integrations/previewsign/scripts/package_macos_chrome.py install \
  --package "$BUILD_ROOT/package" \
  --destination "$BUILD_ROOT/installed" \
  --chrome-user-data-dir "$BUILD_ROOT/temporary-chrome"

```

Expected output: `$BUILD_ROOT/installed/extension/manifest.json` and `$BUILD_ROOT/installed/bin/sign-extension-host`. The former is the unpacked Chrome extension; the latter is its native helper. Never add a wildcard or broad capture setting.
Keep bundled licenses and notices with redistributed artifacts. See
`package_macos_chrome.py --help` for provenance.
Do not include credentials, key
handles, runtime logs or private build evidence in a distributed package.

The source is in this checkout's `integrations/previewsign` directory. Its README,
LICENSE and LICENSE-SCOPE.md describe the licensing scope. Use the
repository configured on the workshop page; an internal development checkout is
not an external participant download.

## Open the dedicated Chrome profile and load the extension

Keep the installation in place until the exercise is finished. The native manifest
is registered under `$BUILD_ROOT/temporary-chrome/NativeMessagingHosts`; Chrome
must use that exact user-data directory. Do not register into your personal profile.
The manual steps below are **not yet participant-rehearsed**. Prior engineering
checks used automated unpacked-extension flags, not this manual UI sequence.

Use the installed Google Chrome application with this dedicated profile:

```sh
CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
"$CHROME_BIN" --user-data-dir="$BUILD_ROOT/temporary-chrome" --no-first-run 'chrome://extensions'
```

If Google Chrome is absent, obtain the supported browser through the normal
facilitator setup;
do not substitute a personal profile or bypass browser policy.
In that window, record whether Developer mode was on or off before changing it.
Follow the same setup sequence shown in participant step 3 ([Chrome’s Load unpacked instructions](https://developer.chrome.com/docs/extensions/get-started/tutorial/hello-world#load-unpacked)):

1. **Developer mode**: enable it if it was off.
2. **Load unpacked**: select this Chrome button.
3. **Select extension folder**: run the following command, copy its absolute output, then use **Go to Folder** (Command-Shift-G) in Chrome’s file picker. Shell variables are not expanded by the file picker.

```sh
printf '%s\n' "$BUILD_ROOT/installed/extension"
```

4. **Confirm installation**: the extension card and its service worker link must be present before running the connection check below. Keep broad “Capture all” disabled: packaged exact-origin
capture is the intended workshop mode.

## Check the installed connection without a key

On that extension card, open its **service worker** inspector. In its DevTools
console (not the web page console), run this synthetic, device-free health request:

```js
chrome.runtime.sendNativeMessage('com.example.sign_extension',
  {type: 'health', requestId: 'manual-health-1', protocolVersion: 1},
  result => console.log(chrome.runtime.lastError?.message ?? result));
```

Expect this response shape (the request ID must match):

```json
{"requestId":"manual-health-1","result":{"version":"0.1.0","protocolVersion":1,"deviceAccess":false}}
```

This tests transport/version only;
it does not register a key, sign, or establish readiness for a transaction. A
missing host or error is a stop condition: check the exact profile, installed
manifest path and matching helper; never fall back to an unverified signing result.
This manual inspector sequence remains untested; the automated installed-browser
health/removal seam has separate recorded evidence.

## Handoff to the workshop

Open the workshop address in this dedicated window and sign in to
the same J1 account. Check readiness **before asking for a key touch**:

- Ready existing credential: check **Account security** for its **PreviewSign ready**
  badge (distinct from **Supports PreviewSign** model capability). Use it directly; no new registration is needed. The badge is a saved
  metadata hint, not a device test. The badge does not establish valid signatures; check both verification results after approval.
- Missing saved metadata: ordinary WebAuthn may still succeed, but it cannot count
  as PreviewSign. There is no in-place metadata enrichment. Installing the helper
  alone does not change the credential.
- Supported preparation: on the same account, normal **Account security → Add
  passkey** with PreviewSign-enabled registration and the extension/helper active
  can prepare an **unregistered compatible key**. The same already-registered
  physical key may be blocked by `excludeCredentials`. Do not delete/replace a
  credential or bypass exclusion. If that is your only compatible key, this application currently has no supported preparation path for it. Preserve the account and credential.

The browser extension supports one YubiKey at a time. Unplug other YubiKeys. Once ready, reload the workshop page. The workshop extension automatically captures explicit PreviewSign requests from its configured origin; keep **Capture all WebAuthn calls** disabled. Then perform **one step-up assertion with both proofs** for the governed action. No
extra enrollment or second approval is needed for a ready credential. PreviewSign
adds a P-256 signature; it does not turn the WebAuthn credential post-quantum.

Helper connectivity alone does not show that enrollment is complete. If the customer is VIP, use
**Reset customer to standard** on the main workshop when available, approve that
separate request and confirm the actual Standard result before requesting VIP.
A reset does not repair enrollment metadata.

After approval, expand **Receipt verification details**, select **Verify stored
evidence** for server WebAuthn verification and inspect the additional server
PreviewSign report separately. The independent offline check below is optional for developers; server results are not independent verification.
Compare **Actual MCP tool result** with **Check current status** on the main workshop
(or a separate `get_customer_status` read) for the same account-owned email.
A valid signature alone is not execution evidence.

## Optional advanced developer proof validation

This advanced check requires a separately prepared proof capture and compatible Python dependencies; building the extension does not prepare them. Use an existing Python with deployment-compatible `fido2`, `cryptography` and
`jcs`, and the matching source checkout. From its repository root:

```sh
/path/to/existing/python -I -B integrations/previewsign/scripts/verify_participant_receipt.py < /private/capture.json
```

The JSON capture contains the unchanged `receipt` from the existing receipt
endpoint, `begin` from the matching step-up begin response, and externally supplied
`expected` with `origin`, `rp_id`, `account_id`, `request_id`, `action`, exact
`tool_args`. Obtain expected values from the intended run, not from the receipt.
Keep captures private. The required reused source is
`scripts/verify_webauthn_proof.py`; no new COSE implementation is needed.

Success is exit 0 with `independent_webauthn_valid: true`,
`independent_previewsign_valid: true`, and `errors: []`. Exit 1 or either false
means incomplete proof: stop, preserve the matching receipt and inspect the
reported category; do not repeat the action to hide the failure. Missing
interpreter/source/dependencies is also a stop condition. The helper checks
expected origin/RP hash, UP+UV, canonical intent/challenge and both signatures,
including begin TBS agreement. This is mathematical validity under included keys,
not a server report, hardware provenance, enrollment attestation or execution.

Use the [offline receipt guide](../../../docs/receipt-lab.md) to prepare pinned
Python dependencies. These checks do not establish hardware or execution.

## Final step 7: remove only this installation when finished

First remove only the workshop extension card at chrome://extensions and confirm it disappears. Restore Developer mode to its prior setting; turn it off only if you enabled it for this exercise. Then close the dedicated Chrome window. In the same terminal with BUILD_ROOT still
set, return to the matching source checkout root, then run:

```sh
cd "$SOURCE_CHECKOUT"
python3 -I -S integrations/previewsign/scripts/package_macos_chrome.py remove \
  --destination "$BUILD_ROOT/installed" \
  --chrome-user-data-dir "$BUILD_ROOT/temporary-chrome"
```

Preserve the dedicated profile and unrelated files. Preserve preexisting extensions, profiles, accounts,
passkeys and approval history. Confirm
ordinary WebAuthn works after removal as a separate manual acceptance check; this
has not yet been qualified by the source-build smoke. Revoke any exercise-created
API key through API Keys; do not remove other keys. No blanket profile deletion.

## This repository's RP source map

Paths are relative to this checkout; a separate public .NET example is not this
browser/helper build. Use these entry points when adapting an RP:

| Stage | Local source / fields |
| --- | --- |
| Registration options/completion | `backend/preloop/api/endpoints/webauthn_registration.py`: `register_begin`, `register_complete`; `options.extensions.previewSign.generateKey`, returned generated-key metadata. |
| Browser registration | `frontend/src/components/security-keys-manager.ts`: normal Add passkey captures generated-key output. |
| Assertion input/output | `frontend/src/views/authed/approval-view.ts`: `previewSign.signByCredential`, `keyHandle`, `tbs`, `additionalArgs`; returned signature/public key. |
| Browser-to-helper bridge | `integrations/previewsign/extension/page.js`, `background.js`; exact-origin scope and native messaging. |
| Standard and additional verification / receipt | `backend/preloop/api/endpoints/webauthn_stepup.py`; `backend/preloop/services/arkg_p256.py`; receipt `arkg_step_up_verified` is separate from WebAuthn verification. |
| Intent encoding | `backend/preloop/services/rdt_intent.py`: canonical intent binding. |

Illustrative field names only, never live key material:
`{previewSign: {generateKey: {algorithms: [/* pinned signing algorithm */]}}}`
and `{previewSign: {signByCredential: {"<credential-id>": {keyHandle: "<opaque>", tbs: "<intent-digest>", additionalArgs: "<encoded-context>"}}}}`.
Actual browser inputs use binary buffers, not these display placeholders. Preserve
protocol revision/algorithm distinctions; this P-256 additional proof is not ML-DSA.

## Windows diagnostic build (runtime qualification pending)

Windows runtime installation remains unqualified. The following diagnostic builds source only; consult `install_windows.py --help` for the explicit-path installation interface.

Use Python 3.11 or newer, Rust with Cargo/rustup and the chosen MSVC target
already installed, and a Visual Studio developer terminal with the corresponding
MSVC linker and Windows SDK resource compiler on PATH. This driver installs no
prerequisites. From the cloned repository root in that terminal:

```powershell
py -3 integrations/previewsign/scripts/build_windows.py --output C:\Temp\previewsign-build --target x86_64-pc-windows-msvc
```

The output must be a new directory outside this repository, with no symlink or
reparse-point ancestors. Use an explicit aarch64-pc-windows-msvc target instead
only when that is the intended machine/toolchain. Remove inherited Cargo/Rust
build overrides named by preflight; values are not printed. The command uses
fresh output/cargo-home and output/target directories, downloads locked public
dependencies as needed, and builds only sign-extension-host and
sign-extension-service. It never runs those executables.

On success, report.json records the target, tool versions, unchanged lock and
both executable hashes. Executables are under target/<target>/debug in the
chosen output. build.log retains compiler output locally; inspect before sharing.
Failed builds retain their owned output for diagnosis and return a nonzero
status. Choose a new output for another run; there is no automatic cleanup.

The subprocess tests cover simulated dispatch and real non-Windows refusal.
Actual Windows compilation, Chrome registration, installation, helper health,
manual PIN/touch and end-to-end proof/result verification remain unqualified.
This is a developer build diagnostic, not Windows workshop automation.

