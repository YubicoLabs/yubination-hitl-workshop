# Build and install PreviewSign on Windows (optional)

This local distribution includes source only. Build the extension and matching
helper from the same checkout. Start the local workshop using the
[README](../../../README.md). Helper connectivity does not establish key
compatibility, successful approval or execution. Preserve existing credentials.

## 1. Clone and build

Prerequisites: Windows, Git, Python3.11+, Rust/Cargo/rustup with x86_64-pc-windows-msvc installed, Visual Studio C++ Build Tools and Windows SDK. Use the corresponding Visual Studio developer PowerShell with link.exe and rc.exe on PATH. Chrome must be installed under Program Files for the existing native caller check. Use a YubiKey 5.8 with PreviewSign support only later. The scripts install no tools, relax no policies and do not use the old broad installer.

```powershell
git clone https://github.com/YubicoLabs/yubination-hitl-workshop.git C:\Work\previewsign-source
Set-Location C:\Work\previewsign-source
git rev-parse HEAD
py -3 integrations/previewsign/scripts/build_windows.py --output C:\Temp\previewsign-build --target x86_64-pc-windows-msvc
```

If already using this checkout, skip cloning and run from its root. Repository access is required while it is internal. Use new build/install/profile paths. The source and output must not overlap or contain symlink/reparse components. The locked build downloads pinned dependencies into its own cache and records versions, source revision, lock hash and both executable hashes in report.json. If any command fails, stop; do not continue with missing executables. For ARM64, use the matching installed aarch64-pc-windows-msvc toolchain/target throughout.

Stop if any command fails. Build both components from the same checkout and keep
Cargo.lock unchanged. If matching a separately supplied package, first check out
its manifest's full sourceRevision; a current main link does not identify a package.

## 2. Install this source build

```powershell
py -3 integrations/previewsign/scripts/install_windows.py install --build-report C:\Temp\previewsign-build\report.json --destination C:\Temp\previewsign-install --chrome-user-data-dir C:\Temp\previewsign-chrome --workshop-origin http://localhost:8080
py -3 integrations/previewsign/scripts/install_windows.py preflight --destination C:\Temp\previewsign-install --chrome-user-data-dir C:\Temp\previewsign-chrome
```

Replace the origin with the exact scheme/host/port of the workshop, with no path. The installer derives the extension ID from its existing manifest key and permits only that extension to call the native host. Exact-origin, top-frame capture is configured automatically; do not enable Capture all.

Registration uses only HKCU\Software\Google\Chrome\NativeMessagingHosts\com.yubico.previewsign_workshop. **This registration is user-wide, not profile-specific.** Both registry views and HKLM are inspected first. An existing workshop registration is preserved and blocks installation. The original `com.example.sign_extension` installation can remain: the workshop uses its own native-host name, named pipe and process mutex. The destination/profile must be new. No administrator service, Run startup entry, Edge/Firefox registration or machine policy is created. Preflight verifies owned files/registration only; it does not contact a device or prove Chrome recognition. Keep bundled licenses and notices with any redistributed artifacts.

No administrator privileges are required for the owned HKCU registration. Do not
elevate or change policy to work around a failure.

## 3. Open dedicated Chrome and check real helper health

```powershell
& 'C:\Program Files\Google\Chrome\Application\chrome.exe' --user-data-dir=C:\Temp\previewsign-chrome
```

In this browser open chrome://extensions and record whether Developer mode was
on or off before changing it. Load the built extension:

1. **Developer mode**: enable it if it was off.
2. **Load unpacked**: select this Chrome button.
3. **Select extension folder**: choose `C:\Temp\previewsign-install\extension`.

Confirm extension ID lcknfcjhoadggemnifljpplfjnppofdk. If enterprise policy blocks loading, stop and report it; do not bypass policy. Open the extension's service-worker inspector and run:

```javascript
chrome.runtime.sendNativeMessage('com.yubico.previewsign_workshop', {type:'health', protocolVersion:1, requestId:'windows-health'}, response => console.log(chrome.runtime.lastError?.message ?? response))
```

Require response.requestId matching windows-health, response.result.version equal to 0.1.0, protocolVersion equal to 1 and deviceAccess false. This runs before backend/device initialization. A missing callback, error or different response is a stop condition. Do not invoke the host directly or enable a caller-validation bypass. Close the inspector afterward; never log ceremony payloads, PINs, seeds or key handles.

## 4. Human-only key and approval stage

Only after health and explicit participant readiness, launch the existing interactive backend in a separate terminal from the source checkout:

```powershell
py -3 integrations/previewsign/scripts/install_windows.py run-human-service --destination C:\Temp\previewsign-install --chrome-user-data-dir C:\Temp\previewsign-chrome
```

Keep Chrome and this terminal unelevated. The dedicated launcher verifies and
locks the installed binaries, then requests explicit UAC consent for only the
temporary signing helper. Same-user consent is required; alternate administrator
credentials are unsupported. The helper is tied to its short-lived controller
and has a ten-minute maximum lifetime. Ctrl+C ends the controller; the helper
self-terminates. No startup entry, scheduled task or SCM service is created.
If UAC is declined, policy blocks launch, or the helper exits, stop without retry
or disabling trust checks. This unsigned local evaluation is not a signed release.

Before touching a key, check Account security on the same account. A ready existing credential needs no registration: use one step-up assertion carrying both proofs. The badge is a metadata hint; the begin response must also supply seed/key handle/credential ID for that intended credential. If metadata is missing, ordinary WebAuthn can still work but cannot count as PreviewSign; there is no in-place metadata enrichment. Normal Add passkey with PreviewSign-enabled registration and the extension active can prepare an unregistered compatible key on the same account. The same physical key may be blocked by excludeCredentials. Do not delete/replace credentials or bypass exclusion. If no unregistered compatible key is available, ask the facilitator for a supported starting state and stop this exercise. Only then connect the single intended compatible key and return to the exact workshop origin in the dedicated profile.

For a Standard customer, request Standard→VIP once through the existing governed client. If already VIP, use and verify the separate governed reset first. The human reviews the actual approval and supplies PIN/touch; these scripts do not approve. Expand Receipt verification details and choose Verify stored evidence for the three stored WebAuthn checks (intent, challenge and signature). That auditor action does not verify the additional PreviewSign proof. Separately inspect the receipt’s recorded PreviewSign server-verification result and additional proof; require the original Actual MCP tool result and independent customer readback. A recorded PreviewSign flag is not an independent offline re-verification. Ordinary WebAuthn fallback is not a PreviewSign pass. Preserve the exact request/receipt correlation without sharing secrets.

For independent mathematical verification, follow the offline CLI and external
expected-input instructions in the [developer quickstart](DEVELOPER-QUICKSTART.md). Require both independent
booleans; neither server reports nor mathematical validity proves hardware
provenance. Use the main workshop's **Check current status** for customer readback.

## 5. Stop and remove only owned installation

Stop the owned service with Ctrl+C in its launching terminal; close the dedicated browser. From the matching source checkout:

```powershell
# Run from the same source checkout root.
py -3 integrations/previewsign/scripts/install_windows.py remove --destination C:\Temp\previewsign-install --chrome-user-data-dir C:\Temp\previewsign-chrome
```

Removal validates the ownership inventory and unchanged files/default registration. Changed or ambiguous state fails closed for inspection. It preserves unrelated files and the Chrome profile/account/history. If registry publication failed after assembly, the retained inventory permits this same remove command. A failure before the inventory exists requires inspection of that new destination; never sweep directories or registry names.

Reopen the dedicated browser if needed: a fresh health connection must report
native host unavailable. Remove only the workshop extension card. Restore
Developer mode to its previous setting: turn it off only if this exercise enabled
it. Preserve preexisting extensions, profiles, accounts and credentials, then
verify ordinary WebAuthn in the account. Do not infer successful approval or hardware behavior from a build or health check.

Registry behavior follows [Chrome native messaging documentation](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging); current source caller and service policies remain unchanged.
