// content.js — Content script relay between page world (page.js) and background SW.
// Injects page.js into the main world, forwards messages bidirectionally,
// and displays modal overlays for PIN entry and touch/insert prompts.

(function () {
  "use strict";

  const MSG_REQUEST = "__sign_ext_request__";
  const MSG_RESPONSE = "__sign_ext_response__";
  const workshop = typeof WORKSHOP_MODE !== "undefined" && WORKSHOP_MODE;

  // Inject page.js into the main world
  const script = document.createElement("script");
  script.src = chrome.runtime.getURL("page.js");
  script.onload = () => script.remove();
  (document.head || document.documentElement).appendChild(script);

  // Read captureAll setting and push it into the page world via a data attribute.
  // Data attributes are shared between content script and page worlds (no CSP issues).
  chrome.storage.local.get("captureAll", (result) => {
    if (workshop) return;
    if (result.captureAll) {
      document.documentElement.dataset.signExtCaptureAll = "true";
    }
  });

  // Update the flag live when the setting changes (e.g. user toggles in popup)
  chrome.storage.onChanged.addListener((changes, area) => {
    if (workshop) return;
    if (area !== "local" || !("captureAll" in changes)) return;
    if (changes.captureAll.newValue) {
      document.documentElement.dataset.signExtCaptureAll = "true";
    } else {
      delete document.documentElement.dataset.signExtCaptureAll;
    }
  });

  // --- Modal overlay management ---
  //
  // We use a <dialog> shown with showModal() so our overlay is promoted to the
  // browser's top layer — the same layer page <dialog> elements occupy — rather
  // than relying on z-index, which cannot beat top-layer elements.
  // The shadow host is a <div> inside the dialog (<dialog> itself cannot host
  // a shadow root per spec). The dialog's ::backdrop is suppressed via injected
  // CSS; we render our own semi-transparent backdrop inside the shadow DOM.

  let overlayDialog = null; // <dialog> element shown with showModal()
  let overlayShadow = null; // Closed shadow root inside overlayDialog
  let overlayBackdrop = null;
  let overlayIframe = null;

  function ensureOverlayDialog() {
    if (overlayDialog) return;

    overlayDialog = document.createElement("dialog");
    overlayDialog.id = "__sign_ext_dialog__";
    // Make the dialog cover the full viewport transparently — all visual
    // content is rendered inside the shadow DOM.
    overlayDialog.style.cssText = [
      "position: fixed",
      "inset: 0",
      "width: 100%", "height: 100%",
      "max-width: 100%", "max-height: 100%",
      "padding: 0", "margin: 0",
      "border: none",
      "background: transparent",
      "overflow: hidden",
    ].join(";");
    // Prevent the dialog from closing itself on Escape (we handle it).
    overlayDialog.addEventListener("cancel", (e) => e.preventDefault());

    const shadowHost = document.createElement("div");
    overlayShadow = shadowHost.attachShadow({ mode: "closed" });
    overlayDialog.appendChild(shadowHost);

    // Suppress the dialog's ::backdrop — we draw our own inside the shadow DOM.
    if (!document.getElementById("__sign_ext_style__")) {
      const style = document.createElement("style");
      style.id = "__sign_ext_style__";
      style.textContent = "#__sign_ext_dialog__::backdrop{background:transparent!important}";
      (document.head || document.documentElement).appendChild(style);
    }

    document.documentElement.appendChild(overlayDialog);
    overlayDialog.showModal();
  }

  function showOverlay(url, height) {
    ensureOverlayDialog();

    if (!overlayBackdrop) {
      overlayBackdrop = document.createElement("div");
      overlayBackdrop.style.cssText = [
        "position: fixed",
        "top: 0", "left: 0", "right: 0", "bottom: 0",
        "background: rgba(0, 0, 0, 0.5)",
        "display: flex",
        "align-items: center",
        "justify-content: center",
      ].join(";");
      overlayShadow.appendChild(overlayBackdrop);
    }

    if (!overlayIframe) {
      overlayIframe = document.createElement("iframe");
      overlayIframe.style.cssText = [
        "border: none",
        "border-radius: 12px",
        "box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3)",
        "width: 420px",
        "background: #f5f5f5",
      ].join(";");
      overlayBackdrop.appendChild(overlayIframe);
    }

    overlayIframe.style.height = height + "px";
    overlayIframe.src = url;
    document.addEventListener("keydown", overlayEscapeHandler, true);
  }

  function hideOverlay() {
    if (overlayDialog) {
      overlayDialog.close();
      overlayDialog.remove();
      overlayDialog = null;
      overlayShadow = null;
      overlayBackdrop = null;
      overlayIframe = null;
    }
    document.removeEventListener("keydown", overlayEscapeHandler, true);
  }

  function overlayEscapeHandler(e) {
    if (e.key === "Escape" && overlayDialog) {
      e.preventDefault();
      e.stopPropagation();
      chrome.runtime.sendMessage({ type: "__sign_ext_cancel__" });
    }
  }

  // --- Background port ---

  let bgPort = null;

  function getBackgroundPort() {
    if (bgPort) return bgPort;
    bgPort = chrome.runtime.connect({ name: "content" });
    bgPort.onMessage.addListener((msg) => {
      // UI commands from background
      if (msg.type === "__sign_ext_ui__") {
        handleUICommand(msg);
        return;
      }
      // FIDO responses → page
      window.postMessage(
        {
          type: MSG_RESPONSE,
          requestId: msg.requestId,
          error: msg.error || null,
          result: msg.result || null,
        },
        "*"
      );
    });
    bgPort.onDisconnect.addListener(() => {
      bgPort = null;
      hideOverlay();
    });
    return bgPort;
  }

  function showBackdrop() {
    ensureOverlayDialog();

    // Remove iframe if present from a previous showOverlay
    if (overlayIframe) {
      overlayIframe.remove();
      overlayIframe = null;
    }

    if (!overlayBackdrop) {
      overlayBackdrop = document.createElement("div");
      overlayBackdrop.style.cssText = [
        "position: fixed",
        "top: 0", "left: 0", "right: 0", "bottom: 0",
        "background: rgba(0, 0, 0, 0.5)",
      ].join(";");
      overlayShadow.appendChild(overlayBackdrop);
    }
    // No Escape handler — cancel is via the native dialog
  }

  function handleUICommand(msg) {
    switch (msg.action) {
      case "showStatus": {
        const url = chrome.runtime.getURL("touch.html?status=" + msg.status);
        showOverlay(url, 180);
        break;
      }
      case "showPin": {
        const encoded = encodeURIComponent(msg.message || "");
        const url = chrome.runtime.getURL("pin.html?message=" + encoded);
        showOverlay(url, 230);
        break;
      }
      case "showSelect": {
        const url = chrome.runtime.getURL("select.html");
        showOverlay(url, 300);
        break;
      }
      case "showPinSetup": {
        const url = chrome.runtime.getURL("pin-setup.html");
        showOverlay(url, 320);
        break;
      }
      case "showPinChange": {
        const url = chrome.runtime.getURL("pin-change.html");
        showOverlay(url, 400);
        break;
      }
      case "showBackdrop":
        showBackdrop();
        break;
      case "hide":
        hideOverlay();
        break;
    }
  }

  // --- page.js -> background SW ---

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    if (!event.data || event.data.type !== MSG_REQUEST) return;

    const { requestId, action, options } = event.data;

    try {
      const port = getBackgroundPort();
      port.postMessage({ action, options, requestId });
    } catch (err) {
      window.postMessage(
        {
          type: MSG_RESPONSE,
          requestId,
          error: {
            name: "NotAllowedError",
            message: err.message || "Extension communication error",
          },
        },
        "*"
      );
    }
  });
})();
