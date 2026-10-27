// page.js — Main world script injected into the page's JS context.
// Intercepts navigator.credentials.create/get when previewSign extension is present.
// Non-previewSign calls fall through to the original implementation (zero overhead).

(function () {
  "use strict";

  // Avoid double-injection
  if (window.__signExtInstalled) return;
  window.__signExtInstalled = true;

  const MSG_REQUEST = "__sign_ext_request__";
  const MSG_RESPONSE = "__sign_ext_response__";
  const workshop = typeof WORKSHOP_MODE !== "undefined" && WORKSHOP_MODE;

  // Save originals before any other code can tamper
  const origCreate = navigator.credentials.create.bind(navigator.credentials);
  const origGet = navigator.credentials.get.bind(navigator.credentials);

  // Pending requests awaiting response from the content script
  const pending = new Map(); // requestId -> { resolve, reject }
  let nextId = 0;

  // --- Base64url helpers ---

  function toBase64url(buffer) {
    const bytes = buffer instanceof ArrayBuffer
      ? new Uint8Array(buffer)
      : new Uint8Array(buffer.buffer, buffer.byteOffset, buffer.byteLength);
    let binary = "";
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function fromBase64url(str) {
    str = str.replace(/-/g, "+").replace(/_/g, "/");
    while (str.length % 4) str += "=";
    const binary = atob(str);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
  }

  // --- Serialization: convert WebAuthn options to JSON-safe form ---

  function bufferToB64(val) {
    if (val instanceof ArrayBuffer || ArrayBuffer.isView(val)) {
      return toBase64url(val);
    }
    return val;
  }

  function serializeCreateOptions(options) {
    const pk = options.publicKey;
    const out = {
      rp: pk.rp,
      user: {
        id: bufferToB64(pk.user.id),
        name: pk.user.name,
        displayName: pk.user.displayName,
      },
      challenge: bufferToB64(pk.challenge),
      pubKeyCredParams: pk.pubKeyCredParams,
    };
    if (pk.timeout) out.timeout = pk.timeout;
    if (pk.excludeCredentials) {
      out.excludeCredentials = pk.excludeCredentials.map((c) => ({
        type: c.type,
        id: bufferToB64(c.id),
        transports: c.transports,
      }));
    }
    if (pk.authenticatorSelection) {
      out.authenticatorSelection = pk.authenticatorSelection;
    }
    if (pk.attestation) out.attestation = pk.attestation;
    if (pk.extensions) {
      out.extensions = serializeExtensions(pk.extensions);
    }
    return out;
  }

  function serializeGetOptions(options) {
    const pk = options.publicKey;
    const out = {
      rpId: pk.rpId,
      challenge: bufferToB64(pk.challenge),
    };
    if (pk.timeout) out.timeout = pk.timeout;
    if (pk.allowCredentials) {
      out.allowCredentials = pk.allowCredentials.map((c) => ({
        type: c.type,
        id: bufferToB64(c.id),
        transports: c.transports,
      }));
    }
    if (pk.userVerification) out.userVerification = pk.userVerification;
    if (pk.extensions) {
      out.extensions = serializeExtensions(pk.extensions);
    }
    return out;
  }

  function serializeExtensions(ext) {
    const out = {};
    for (const [key, value] of Object.entries(ext)) {
      out[key] = serializeValue(value);
    }
    return out;
  }

  function serializeValue(val) {
    if (val instanceof ArrayBuffer || ArrayBuffer.isView(val)) {
      return { __b64: toBase64url(val) };
    }
    if (Array.isArray(val)) {
      return val.map(serializeValue);
    }
    if (val !== null && typeof val === "object") {
      const out = {};
      for (const [k, v] of Object.entries(val)) {
        out[k] = serializeValue(v);
      }
      return out;
    }
    return val;
  }

  // --- Deserialization: convert response back to PublicKeyCredential-like ---

  function deserializeCreateResponse(resp) {
    const response = {
      attestationObject: fromBase64url(resp.attestationObject),
      clientDataJSON: fromBase64url(resp.clientDataJSON),
      getTransports: () => resp.transports || [],
    };
    if (resp.authenticatorData) {
      response.getAuthenticatorData = () =>
        fromBase64url(resp.authenticatorData);
    }
    if (resp.publicKey) {
      response.getPublicKey = () => fromBase64url(resp.publicKey);
    }
    if (resp.publicKeyAlgorithm !== undefined) {
      response.getPublicKeyAlgorithm = () => resp.publicKeyAlgorithm;
    }

    return {
      id: resp.id,
      rawId: fromBase64url(resp.rawId),
      type: "public-key",
      response,
      authenticatorAttachment: resp.authenticatorAttachment || "cross-platform",
      getClientExtensionResults: () =>
        deserializeExtensionResults(resp.clientExtensionResults || {}),
    };
  }

  function deserializeGetResponse(resp) {
    const response = {
      authenticatorData: fromBase64url(resp.authenticatorData),
      clientDataJSON: fromBase64url(resp.clientDataJSON),
      signature: fromBase64url(resp.signature),
    };
    if (resp.userHandle) {
      response.userHandle = fromBase64url(resp.userHandle);
    }

    return {
      id: resp.id,
      rawId: fromBase64url(resp.rawId),
      type: "public-key",
      response,
      authenticatorAttachment: resp.authenticatorAttachment || "cross-platform",
      getClientExtensionResults: () =>
        deserializeExtensionResults(resp.clientExtensionResults || {}),
    };
  }

  function deserializeExtensionResults(ext) {
    const out = {};
    for (const [key, value] of Object.entries(ext)) {
      out[key] = deserializeResultValue(value);
    }
    return out;
  }

  function deserializeResultValue(val) {
    if (val !== null && typeof val === "object" && "__b64" in val) {
      return fromBase64url(val.__b64);
    }
    if (Array.isArray(val)) {
      return val.map(deserializeResultValue);
    }
    if (val !== null && typeof val === "object") {
      const out = {};
      for (const [k, v] of Object.entries(val)) {
        out[k] = deserializeResultValue(v);
      }
      return out;
    }
    return val;
  }

  // --- Listen for responses from content script ---

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    if (!event.data || event.data.type !== MSG_RESPONSE) return;

    const { requestId, error, result } = event.data;
    const p = pending.get(requestId);
    if (!p) return;
    pending.delete(requestId);

    if (error) {
      p.reject(new DOMException(error.message, error.name || "NotAllowedError"));
    } else {
      p.resolve(result);
    }
  });

  // --- Intercept navigator.credentials.create ---

  navigator.credentials.create = function (options) {
    // Intercept if captureAll is enabled, or if previewSign extension is present
    if (!options || !options.publicKey) return origCreate(options);
    if (
      (workshop || document.documentElement.dataset.signExtCaptureAll !== "true") &&
      !(options.publicKey.extensions && options.publicKey.extensions.previewSign)
    ) {
      return origCreate(options);
    }

    const requestId = String(nextId++);

    return new Promise((resolve, reject) => {
      pending.set(requestId, {
        resolve: (result) => resolve(deserializeCreateResponse(result)),
        reject,
      });

      window.postMessage(
        {
          type: MSG_REQUEST,
          requestId,
          action: "create",
          options: serializeCreateOptions(options),
        },
        "*"
      );
    });
  };

  // --- Intercept navigator.credentials.get ---

  navigator.credentials.get = function (options) {
    // Intercept if captureAll is enabled, or if previewSign extension is present
    if (!options || !options.publicKey) return origGet(options);
    if (
      (workshop || document.documentElement.dataset.signExtCaptureAll !== "true") &&
      !(options.publicKey.extensions && options.publicKey.extensions.previewSign)
    ) {
      return origGet(options);
    }

    const requestId = String(nextId++);

    return new Promise((resolve, reject) => {
      pending.set(requestId, {
        resolve: (result) => resolve(deserializeGetResponse(result)),
        reject,
      });

      window.postMessage(
        {
          type: MSG_REQUEST,
          requestId,
          action: "get",
          options: serializeGetOptions(options),
        },
        "*"
      );
    });
  };
})();
