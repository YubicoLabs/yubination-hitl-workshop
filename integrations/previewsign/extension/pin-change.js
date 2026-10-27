// pin-change.js — PIN change page script.
// Three-field (current + new + confirm) PIN entry. Validates length and match before sending.

const MAX_PIN_BYTES = 63; // CTAP2 spec maximum
let minPinLength = 4; // Default, updated from background
let submitted = false;

function submit(currentPin, newPin) {
  if (submitted) return;
  submitted = true;
  chrome.runtime.sendMessage({ type: "__sign_ext_pin_change_response__", currentPin, newPin });
}

// Load message and minLength from background
chrome.runtime.sendMessage({ type: "__sign_ext_pin_change_ready__" }, (response) => {
  if (response && response.message) {
    document.getElementById("message").textContent = response.message;
  }
  if (response && response.minLength) {
    minPinLength = response.minLength;
  }
});

const currentField = document.getElementById("current");
const newPinField = document.getElementById("newPin");
const confirmField = document.getElementById("confirm");
const okBtn = document.getElementById("okBtn");
const cancelBtn = document.getElementById("cancelBtn");
const errorEl = document.getElementById("error");

function showError(msg) {
  errorEl.textContent = msg;
  errorEl.style.display = "block";
}

function trySubmit() {
  errorEl.style.display = "none";
  const current = currentField.value;
  const newPin = newPinField.value;
  const confirm = confirmField.value;

  if (!current) {
    showError("Please enter your current PIN.");
    currentField.focus();
    return;
  }
  if (!newPin) {
    showError("Please enter a new PIN.");
    newPinField.focus();
    return;
  }
  if (newPin.length < minPinLength) {
    showError(`New PIN must be at least ${minPinLength} characters.`);
    newPinField.focus();
    return;
  }
  if (new TextEncoder().encode(newPin).length > MAX_PIN_BYTES) {
    showError("New PIN is too long (maximum 63 bytes).");
    newPinField.focus();
    return;
  }
  if (newPin !== confirm) {
    showError("New PINs don't match. Please try again.");
    confirmField.value = "";
    confirmField.focus();
    return;
  }
  submit(current, newPin);
}

okBtn.addEventListener("click", trySubmit);
cancelBtn.addEventListener("click", () => submit(null, null));

currentField.addEventListener("keydown", (e) => {
  if (e.key === "Enter") newPinField.focus();
  if (e.key === "Escape") submit(null, null);
});
newPinField.addEventListener("keydown", (e) => {
  if (e.key === "Enter") confirmField.focus();
  if (e.key === "Escape") submit(null, null);
});
confirmField.addEventListener("keydown", (e) => {
  if (e.key === "Enter") trySubmit();
  if (e.key === "Escape") submit(null, null);
});

currentField.focus();
