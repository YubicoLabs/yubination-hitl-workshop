// pin.js — PIN entry page script.
// Reads the prompt message from URL params, sends PIN back via chrome.runtime.sendMessage.

const params = new URLSearchParams(window.location.search);
const message = params.get("message");
if (message) {
  document.getElementById("message").textContent = message;
}

const pinInput = document.getElementById("pin");
const okBtn = document.getElementById("okBtn");
const cancelBtn = document.getElementById("cancelBtn");

let submitted = false;

function submit(pin) {
  if (submitted) return;
  submitted = true;
  pinInput.value = "";
  chrome.runtime.sendMessage({ type: "__sign_ext_pin_response__", pin });
}

okBtn.addEventListener("click", () => submit(pinInput.value || null));
cancelBtn.addEventListener("click", () => submit(null));
pinInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") submit(pinInput.value || null);
  if (e.key === "Escape") submit(null);
});

// Focus input
pinInput.focus();
