const { ipcRenderer } = require("electron");

const channels = {
  retry: "desktop:retry",
  openInBrowser: "desktop:open-in-browser",
  openCloud: "desktop:open-cloud",
  openDownload: "desktop:open-download",
  openDocs: "desktop:open-docs",
  copyInstall: "desktop:copy-install",
  copyOnboard: "desktop:copy-onboard",
  copyApiKey: "desktop:copy-api-key",
};

window.addEventListener("DOMContentLoaded", () => {
  if (window.location.protocol !== "data:") return;
  document.addEventListener("click", (event) => {
    const button = event.target?.closest?.("[data-desktop-action]");
    if (!button) return;
    const channel = channels[button.getAttribute("data-desktop-action")];
    if (!channel) return;
    event.preventDefault();
    ipcRenderer.send(channel);
  });
});
