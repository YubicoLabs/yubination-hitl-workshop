// background.js — Service worker: native messaging bridge.
// Uses sender.origin (unforgeable, set by browser process) for origin verification.
// Connects to native messaging host for FIDO operations.
//
// UI is shown via modal overlays injected by the content script (not popup windows).
// PIN protocol: When the host needs a PIN, we tell the content script to show PIN overlay.
// pin.html sends the PIN back via chrome.runtime.sendMessage.

const NATIVE_HOST = typeof WORKSHOP_NATIVE_HOST !== "undefined"
  ? WORKSHOP_NATIVE_HOST : "com.example.sign_extension";
const workshop = typeof WORKSHOP_MODE !== "undefined" && WORKSHOP_MODE;
const workshopOrigins = workshop
  ? fetch(chrome.runtime.getURL("workshop-origins.json"))
    .then((response) => {
      if (!response.ok) throw new Error("Missing workshop scope");
      return response.json();
    })
    .then((config) => {
      if (!config || !Array.isArray(config.origins) || !config.origins.length ||
          !config.origins.every((origin) => {
            if (typeof origin !== "string") return false;
            const parsed = new URL(origin);
            const validHost = parsed.hostname.startsWith("[") ||
              (parsed.hostname.length <= 253 && parsed.hostname.split(".").every((label) =>
                /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label)));
            return ["http:", "https:"].includes(parsed.protocol) && parsed.origin === origin && validHost;
          })) {
        throw new Error("Invalid workshop scope");
      }
      return new Set(config.origins);
    })
    .catch(() => new Set())
  : null;

let nativePort = null;
const pendingRequests = new Map(); // requestId -> { respond, contentPort }
let pendingPinResolve = null;
let pendingSelectResolve = null;
let pendingSelectUsers = null;
let pendingPinSetupResolve = null;
let pendingPinSetupMessage = null;
let pendingPinChangeResolve = null;
let pendingPinChangeMessage = null;
let activeContentPort = null; // content port for the active request (for UI commands)
let statusDelayTimer = null;

console.log("[sign-ext] Service worker started");

function connectNative() {
  if (nativePort) return nativePort;

  nativePort = chrome.runtime.connectNative(NATIVE_HOST);

  nativePort.onMessage.addListener((msg) => {
    console.log("[sign-ext] Native message received:", JSON.stringify(msg).substring(0, 200));

    // Status updates — show modal overlay in content script
    if (msg.type === "status") {
      console.log(`[sign-ext] Status: ${msg.status}`);
      if (msg.status === "native_prompt") {
        cancelStatusDelay();
        sendUICommand({ action: "showBackdrop" });
      } else if (msg.status === "insert") {
        showStatusDelayed(msg.status, 800);
      } else if (msg.status === "touch" || msg.status === "select" || msg.status === "biometric"
                 || msg.status.startsWith("biometric_retry:") || msg.status === "uv_blocked"
                 || msg.status === "pin_blocked" || msg.status === "pin_auth_blocked"
                 || msg.status === "pin_not_set" || msg.status === "bio_not_enrolled") {
        showStatus(msg.status);
      } else if (msg.status === "done") {
        hideUI();
      }
      return;
    }

    // PIN required — host sends { requestId, needsPin: true, message: "..." }
    if (msg.needsPin) {
      console.log("[sign-ext] PIN required:", msg.message);
      handlePinRequest(msg.requestId, msg.message || "Enter your security key PIN:");
      return;
    }

    // PIN setup — host sends { requestId, needsPinSetup: true, message: "...", minLength: N }
    if (msg.needsPinSetup) {
      console.log("[sign-ext] PIN setup required:", msg.message, "minLength:", msg.minLength);
      handlePinSetupRequest(msg.requestId, msg.message || "Create a PIN for your security key.", msg.minLength || 4);
      return;
    }

    // PIN change — host sends { requestId, needsPinChange: true, message: "...", minLength: N }
    if (msg.needsPinChange) {
      console.log("[sign-ext] PIN change required:", msg.message, "minLength:", msg.minLength);
      handlePinChangeRequest(msg.requestId, msg.message || "Your security key requires a PIN change.", msg.minLength || 4);
      return;
    }

    // Credential selection — host sends { requestId, needsSelect: true, users: [...] }
    if (msg.needsSelect) {
      console.log("[sign-ext] Credential selection required:", msg.users?.length, "users");
      handleSelectRequest(msg.requestId, msg.users || []);
      return;
    }

    const { requestId } = msg;
    hideUI();

    const pending = pendingRequests.get(requestId);
    if (!pending) {
      console.warn(`[sign-ext] No pending request for id: ${requestId}`);
      return;
    }
    pendingRequests.delete(requestId);
    activeContentPort = null;

    if (msg.error) {
      pending.respond({ error: { name: "NotAllowedError", message: msg.error } });
    } else {
      pending.respond({ result: msg.result });
    }
  });

  nativePort.onDisconnect.addListener(() => {
    const lastError = chrome.runtime.lastError;
    console.warn(
      "[sign-ext] Native host disconnected:",
      lastError ? lastError.message : "unknown reason"
    );

    hideUI();
    for (const [requestId, pending] of pendingRequests) {
      pending.respond({
        error: {
          name: "NotAllowedError",
          message: "Native messaging host disconnected",
        },
      });
    }
    pendingRequests.clear();
    activeContentPort = null;
    nativePort = null;
  });

  return nativePort;
}

// --- UI commands sent to content script ---

function sendUICommand(cmd) {
  if (activeContentPort) {
    try {
      activeContentPort.postMessage({ type: "__sign_ext_ui__", ...cmd });
    } catch (e) {
      console.warn("[sign-ext] Failed to send UI command:", e);
    }
  }
}

function showStatus(status) {
  cancelStatusDelay();
  sendUICommand({ action: "showStatus", status });
}

function showStatusDelayed(status, delayMs) {
  if (statusDelayTimer) return;
  statusDelayTimer = setTimeout(() => {
    statusDelayTimer = null;
    showStatus(status);
  }, delayMs);
}

function cancelStatusDelay() {
  if (statusDelayTimer) {
    clearTimeout(statusDelayTimer);
    statusDelayTimer = null;
  }
}

function hideUI() {
  cancelStatusDelay();
  sendUICommand({ action: "hide" });
}

// --- PIN handling ---

async function handlePinRequest(requestId, message) {
  try {
    hideUI();
    const pin = await new Promise((resolve) => {
      pendingPinResolve = resolve;
      sendUICommand({ action: "showPin", message });
    });

    console.log("[sign-ext] Sending pinResponse, has PIN:", pin !== null);
    nativePort.postMessage({ type: "pinResponse", pin: pin });
  } catch (err) {
    console.error("[sign-ext] PIN request error:", err);
    if (nativePort) {
      nativePort.postMessage({ type: "pinResponse", pin: null });
    }
  }
}

// --- Credential selection handling ---

async function handleSelectRequest(requestId, users) {
  try {
    hideUI();
    pendingSelectUsers = users;
    const index = await new Promise((resolve) => {
      pendingSelectResolve = resolve;
      sendUICommand({ action: "showSelect" });
    });
    pendingSelectUsers = null;

    console.log("[sign-ext] Sending selectResponse, index:", index);
    nativePort.postMessage({ type: "selectResponse", index: index });
  } catch (err) {
    console.error("[sign-ext] Select request error:", err);
    if (nativePort) {
      nativePort.postMessage({ type: "selectResponse", index: null });
    }
  }
}

// --- PIN setup handling ---

async function handlePinSetupRequest(requestId, message, minLength) {
  try {
    hideUI();
    pendingPinSetupMessage = { message, minLength };
    const pin = await new Promise((resolve) => {
      pendingPinSetupResolve = resolve;
      sendUICommand({ action: "showPinSetup" });
    });
    pendingPinSetupMessage = null;

    console.log("[sign-ext] Sending pinSetupResponse, has PIN:", pin !== null);
    nativePort.postMessage({ type: "pinSetupResponse", pin: pin });
  } catch (err) {
    console.error("[sign-ext] PIN setup request error:", err);
    if (nativePort) {
      nativePort.postMessage({ type: "pinSetupResponse", pin: null });
    }
  }
}

// --- PIN change handling ---

async function handlePinChangeRequest(requestId, message, minLength) {
  try {
    hideUI();
    pendingPinChangeMessage = { message, minLength };
    const result = await new Promise((resolve) => {
      pendingPinChangeResolve = resolve;
      sendUICommand({ action: "showPinChange" });
    });
    pendingPinChangeMessage = null;

    console.log("[sign-ext] Sending pinChangeResponse, has PINs:", result !== null);
    nativePort.postMessage({
      type: "pinChangeResponse",
      currentPin: result?.currentPin || null,
      newPin: result?.newPin || null,
    });
  } catch (err) {
    console.error("[sign-ext] PIN change request error:", err);
    if (nativePort) {
      nativePort.postMessage({ type: "pinChangeResponse", currentPin: null, newPin: null });
    }
  }
}

// Handle one-shot messages (PIN responses from pin.html iframe, cancel from touch overlay)
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "__sign_ext_pin_response__") {
    if (pendingPinResolve) {
      pendingPinResolve(message.pin || null);
      pendingPinResolve = null;
    }
    return false;
  }
  if (message.type === "__sign_ext_pin_setup_ready__") {
    sendResponse({
      message: pendingPinSetupMessage?.message || "",
      minLength: pendingPinSetupMessage?.minLength || 4,
    });
    return false;
  }
  if (message.type === "__sign_ext_pin_setup_response__") {
    if (pendingPinSetupResolve) {
      pendingPinSetupResolve(message.pin || null);
      pendingPinSetupResolve = null;
    }
    return false;
  }
  if (message.type === "__sign_ext_pin_change_ready__") {
    sendResponse({
      message: pendingPinChangeMessage?.message || "",
      minLength: pendingPinChangeMessage?.minLength || 4,
    });
    return false;
  }
  if (message.type === "__sign_ext_pin_change_response__") {
    if (pendingPinChangeResolve) {
      if (message.currentPin && message.newPin) {
        pendingPinChangeResolve({ currentPin: message.currentPin, newPin: message.newPin });
      } else {
        pendingPinChangeResolve(null);
      }
      pendingPinChangeResolve = null;
    }
    return false;
  }
  if (message.type === "__sign_ext_select_ready__") {
    sendResponse({ users: pendingSelectUsers || [] });
    return false;
  }
  if (message.type === "__sign_ext_select_response__") {
    if (pendingSelectResolve) {
      pendingSelectResolve(message.index ?? null);
      pendingSelectResolve = null;
    }
    return false;
  }
  if (message.type === "__sign_ext_cancel__") {
    console.log("[sign-ext] User cancelled from overlay");
    hideUI();
    // Send cancel to the native host so it can cleanly abort the YubiKey transaction.
    // The host will respond with an error for each pending request.
    if (nativePort) {
      nativePort.postMessage({ type: "cancel" });
    }
    return false;
  }
});

// Handle port-based connections from content scripts
chrome.runtime.onConnect.addListener((contentPort) => {
  if (contentPort.name !== "content") return;

  // sender.origin is set by the browser process and is unforgeable
  const origin = contentPort.sender?.origin;

  contentPort.onMessage.addListener(async (message) => {
    if (!origin || (workshop &&
        (contentPort.sender?.frameId !== 0 || !(await workshopOrigins).has(origin)))) {
      contentPort.postMessage({
        requestId: message.requestId,
        error: { name: "SecurityError", message: "Sender is outside the permitted origin scope" },
      });
      return;
    }

    const { action, options, requestId } = message;

    if (action !== "create" && action !== "get") {
      contentPort.postMessage({
        requestId,
        error: { name: "NotSupportedError", message: `Unknown action: ${action}` },
      });
      return;
    }

    try {
      const nPort = connectNative();

      // Track this content port for sending UI commands
      activeContentPort = contentPort;

      pendingRequests.set(requestId, {
        respond: (response) => {
          contentPort.postMessage({ requestId, ...response });
        },
        contentPort,
      });

      nPort.postMessage({
        type: action,
        requestId,
        origin,
        options,
      });
    } catch (err) {
      contentPort.postMessage({
        requestId,
        error: { name: "NotAllowedError", message: err.message || String(err) },
      });
    }
  });

  contentPort.onDisconnect.addListener(() => {
    if (activeContentPort === contentPort) {
      activeContentPort = null;
    }
  });
});
