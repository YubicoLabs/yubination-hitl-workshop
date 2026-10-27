// select.js — Credential picker page script.
// Requests credential list from background via messaging, sends selected index back.

const list = document.getElementById("accounts");
let submitted = false;

function submit(index) {
  if (submitted) return;
  submitted = true;
  chrome.runtime.sendMessage({ type: "__sign_ext_select_response__", index });
}

function renderUsers(users) {
  list.innerHTML = "";
  users.forEach((user, i) => {
    const li = document.createElement("li");
    li.textContent = user.displayName || user.name || "Unknown account";
    li.addEventListener("click", () => submit(i));
    list.appendChild(li);
  });
}

// Ask background for the pending user list
chrome.runtime.sendMessage({ type: "__sign_ext_select_ready__" }, (response) => {
  if (response && response.users) {
    renderUsers(response.users);
  }
});

document.getElementById("cancelBtn").addEventListener("click", () => submit(null));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") submit(null);
});
