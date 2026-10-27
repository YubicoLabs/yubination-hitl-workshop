const params = new URLSearchParams(window.location.search);
const status = params.get("status");
const icon = document.getElementById("icon");

if (status === "insert") {
  // Security key with downward arrow
  icon.innerHTML = '<svg viewBox="0 0 48 48" fill="none" stroke="#0066cc" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="15" y="2" width="18" height="30" rx="3"/><rect x="20" y="5" width="3" height="7" rx="0.5" fill="#0066cc" opacity="0.3" stroke="none"/><rect x="25" y="5" width="3" height="7" rx="0.5" fill="#0066cc" opacity="0.3" stroke="none"/><line x1="15" y1="14" x2="33" y2="14"/><circle cx="24" cy="24" r="4" fill="#0066cc" opacity="0.1"/><path d="M24 36v8M20 40l4 4 4-4" stroke-width="2.5"/></svg>';
  document.getElementById("title").textContent = "Insert Your Security Key";
  document.getElementById("message").textContent = "Plug in your security key to continue.";
} else if (status === "select") {
  // Two overlapping security keys
  icon.innerHTML = '<svg viewBox="0 0 48 48" fill="none" stroke="#0066cc" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="6" width="16" height="32" rx="3" opacity="0.4"/><rect x="13" y="9" width="2.5" height="6" rx="0.5" fill="#0066cc" opacity="0.15" stroke="none"/><rect x="17" y="9" width="2.5" height="6" rx="0.5" fill="#0066cc" opacity="0.15" stroke="none"/><line x1="8" y1="17" x2="24" y2="17" opacity="0.4"/><circle cx="16" cy="25" r="3.5" opacity="0.4"/><rect x="24" y="4" width="16" height="32" rx="3"/><rect x="29" y="7" width="2.5" height="6" rx="0.5" fill="#0066cc" opacity="0.3" stroke="none"/><rect x="33" y="7" width="2.5" height="6" rx="0.5" fill="#0066cc" opacity="0.3" stroke="none"/><line x1="24" y1="15" x2="40" y2="15"/><circle cx="32" cy="23" r="3.5" fill="#0066cc" opacity="0.1"/></svg>';
  document.getElementById("title").textContent = "Multiple Keys Detected";
  document.getElementById("message").textContent = "Touch the security key you want to use.";
} else if (status === "biometric") {
  // Fingerprint
  icon.innerHTML = '<svg viewBox="0 0 48 48" fill="none" stroke="#0066cc" stroke-width="2" stroke-linecap="round"><path d="M16 34c-2-3-3-6-3-10a11 11 0 0 1 22 0"/><path d="M19 36c-1-2-1.5-4-1.5-7a6.5 6.5 0 0 1 13 0c0 2-.5 5-2 7"/><path d="M22 37c-.3-1-.5-2.5-.5-4.5a2.5 2.5 0 0 1 5 0c0 3-1 5.5-2 7"/><path d="M38 28c0-3-.8-5.5-2-7.5"/><path d="M10 24c0-2 .5-3.8 1.2-5.5"/><path d="M34 14c-2.5-3-6-5-10-5s-7.5 2-10 5"/></svg>';
  document.getElementById("title").textContent = "Scan Your Fingerprint";
  document.getElementById("message").textContent = "Touch the fingerprint sensor on your security key.";
} else if (status.startsWith("biometric_retry:")) {
  const retries = status.split(":")[1];
  // Fingerprint in orange with exclamation
  icon.innerHTML = '<svg viewBox="0 0 48 48" fill="none" stroke="#cc6600" stroke-width="2" stroke-linecap="round"><path d="M16 34c-2-3-3-6-3-10a11 11 0 0 1 22 0"/><path d="M19 36c-1-2-1.5-4-1.5-7a6.5 6.5 0 0 1 13 0c0 2-.5 5-2 7"/><path d="M22 37c-.3-1-.5-2.5-.5-4.5a2.5 2.5 0 0 1 5 0c0 3-1 5.5-2 7"/><path d="M38 28c0-3-.8-5.5-2-7.5"/><path d="M10 24c0-2 .5-3.8 1.2-5.5"/><path d="M34 14c-2.5-3-6-5-10-5s-7.5 2-10 5"/><circle cx="40" cy="40" r="6" fill="#cc6600" stroke="none"/><line x1="40" y1="36.5" x2="40" y2="40" stroke="white" stroke-width="2.5"/><circle cx="40" cy="42.5" r="0.5" fill="white" stroke="none"/></svg>';
  document.getElementById("title").textContent = "Fingerprint Not Recognized";
  const msg = retries ? `Try again. ${retries} ${retries === "1" ? "attempt" : "attempts"} remaining.` : "Try again.";
  document.getElementById("message").textContent = msg;
} else if (status === "uv_blocked") {
  // Circle with X
  icon.innerHTML = '<svg viewBox="0 0 48 48" fill="none" stroke="#cc0000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="24" cy="24" r="16"/><line x1="30" y1="18" x2="18" y2="30"/><line x1="18" y1="18" x2="30" y2="30"/></svg>';
  document.getElementById("title").textContent = "Fingerprint Blocked";
  document.getElementById("message").textContent = "Too many failed attempts. Falling back to PIN.";
} else if (status === "pin_blocked") {
  icon.innerHTML = '<svg viewBox="0 0 48 48" fill="none" stroke="#cc0000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="10" y="20" width="28" height="22" rx="3"/><path d="M16 20v-6a8 8 0 0 1 16 0v6"/><line x1="18" y1="28" x2="30" y2="38"/><line x1="30" y1="28" x2="18" y2="38"/></svg>';
  document.getElementById("title").textContent = "PIN Permanently Locked";
  document.getElementById("message").textContent = "Your security key PIN is permanently locked. The key must be factory reset before it can be used again.";
} else if (status === "pin_auth_blocked") {
  icon.innerHTML = '<svg viewBox="0 0 48 48" fill="none" stroke="#cc6600" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="10" y="20" width="28" height="22" rx="3"/><path d="M16 20v-6a8 8 0 0 1 16 0v6"/><circle cx="24" cy="30" r="1.5" fill="#cc6600"/><line x1="24" y1="33" x2="24" y2="37"/></svg>';
  document.getElementById("title").textContent = "Too Many PIN Attempts";
  document.getElementById("message").textContent = "Remove and re-insert your security key to try again.";
} else if (status === "pin_not_set") {
  icon.innerHTML = '<svg viewBox="0 0 48 48" fill="none" stroke="#cc6600" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="10" y="20" width="28" height="22" rx="3"/><path d="M16 20v-6a8 8 0 0 1 16 0v6" stroke-dasharray="4 3"/><circle cx="24" cy="31" r="1.5" fill="#cc6600"/><line x1="24" y1="34" x2="24" y2="38"/></svg>';
  document.getElementById("title").textContent = "PIN Not Set";
  document.getElementById("message").textContent = "Your security key requires a PIN, but none is set. Use your key manufacturer\u2019s app to set a PIN.";
} else if (status === "bio_not_enrolled") {
  icon.innerHTML = '<svg viewBox="0 0 48 48" fill="none" stroke="#0066cc" stroke-width="2" stroke-linecap="round"><path d="M16 34c-2-3-3-6-3-10a11 11 0 0 1 22 0"/><path d="M19 36c-1-2-1.5-4-1.5-7a6.5 6.5 0 0 1 13 0c0 2-.5 5-2 7"/><path d="M22 37c-.3-1-.5-2.5-.5-4.5a2.5 2.5 0 0 1 5 0c0 3-1 5.5-2 7"/><path d="M38 28c0-3-.8-5.5-2-7.5"/><path d="M10 24c0-2 .5-3.8 1.2-5.5"/><path d="M34 14c-2.5-3-6-5-10-5s-7.5 2-10 5"/><circle cx="40" cy="40" r="6" fill="#0066cc" stroke="none"/><line x1="37" y1="40" x2="43" y2="40" stroke="white" stroke-width="2"/><line x1="40" y1="37" x2="40" y2="43" stroke="white" stroke-width="2"/></svg>';
  document.getElementById("title").textContent = "Set Up Fingerprint";
  document.getElementById("message").textContent = "Your key supports fingerprint login. Use your key manufacturer\u2019s app to enroll fingerprints for faster, more secure sign-in.";
}

document.getElementById("cancelBtn").addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "__sign_ext_cancel__" });
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    chrome.runtime.sendMessage({ type: "__sign_ext_cancel__" });
  }
});
