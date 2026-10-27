// pin-setup.js — PIN setup page script.
// Two-field (new + confirm) PIN entry. Validates length and match before sending.

const MAX_PIN_BYTES = 63; // CTAP2 spec maximum
let minPinLength = 4; // Default, updated from background
let submitted = false;

function submit(pin) {
  if (submitted) return;
  submitted = true;
  chrome.runtime.sendMessage({ type: "__sign_ext_pin_setup_response__", pin });
}

// Load message and minLength from background
chrome.runtime.sendMessage({ type: "__sign_ext_pin_setup_ready__" }, (response) => {
  if (response && response.message) {
    document.getElementById("message").textContent = response.message;
  }
  if (response && response.minLength) {
    minPinLength = response.minLength;
  }
});

const pin1 = document.getElementById("pin1");
const pin2 = document.getElementById("pin2");
const okBtn = document.getElementById("okBtn");
const cancelBtn = document.getElementById("cancelBtn");
const errorEl = document.getElementById("error");

function showError(msg) {
  errorEl.textContent = msg;
  errorEl.style.display = "block";
}

function trySubmit() {
  errorEl.style.display = "none";
  const p1 = pin1.value;
  const p2 = pin2.value;

  if (!p1) {
    showError("Please enter a PIN.");
    pin1.focus();
    return;
  }
  if (p1.length < minPinLength) {
    showError(`PIN must be at least ${minPinLength} characters.`);
    pin1.focus();
    return;
  }
  if (new TextEncoder().encode(p1).length > MAX_PIN_BYTES) {
    showError("PIN is too long (maximum 63 bytes).");
    pin1.focus();
    return;
  }
  if (p1 !== p2) {
    showError("PINs don't match. Please try again.");
    pin2.value = "";
    pin2.focus();
    return;
  }
  submit(p1);
}

okBtn.addEventListener("click", trySubmit);
cancelBtn.addEventListener("click", () => submit(null));

pin1.addEventListener("keydown", (e) => {
  if (e.key === "Enter") pin2.focus();
  if (e.key === "Escape") submit(null);
});
pin2.addEventListener("keydown", (e) => {
  if (e.key === "Enter") trySubmit();
  if (e.key === "Escape") submit(null);
});

pin1.focus();
