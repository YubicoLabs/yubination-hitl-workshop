const checkbox = document.getElementById("captureAll");
const workshop = typeof WORKSHOP_MODE !== "undefined" && WORKSHOP_MODE;
if (workshop) {
  checkbox.disabled = true;
  checkbox.checked = false;
  document.querySelector(".desc").textContent = "Workshop mode only handles previewSign requests from configured top-level origins.";
}

chrome.storage.local.get("captureAll", (result) => {
  checkbox.checked = !workshop && !!result.captureAll;
});

checkbox.addEventListener("change", () => {
  if (workshop) return;
  chrome.storage.local.set({ captureAll: checkbox.checked });
});
