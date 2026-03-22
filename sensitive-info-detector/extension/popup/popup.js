async function sendMessage(message) {
  return await chrome.runtime.sendMessage(message);
}

async function refreshPopup() {
  const settingsResponse = await sendMessage({ type: "getSettings" });
  const settings = settingsResponse?.data || { enabled: true };
  document.getElementById("enabled-toggle").checked = Boolean(settings.enabled);

  const healthResponse = await sendMessage({ type: "checkBackendStatus" });
  const backendStatus = document.getElementById("backend-status");
  backendStatus.textContent = healthResponse?.ok ? "Online" : "Offline";
  backendStatus.style.color = healthResponse?.ok ? "#166534" : "#991b1b";

  const lastDecisionResponse = await sendMessage({ type: "getLastDecision" });
  const lastDecision = lastDecisionResponse?.data;
  if (lastDecision) {
    document.getElementById("last-route").textContent =
      `${lastDecision.platform || "site"} -> ${lastDecision.route} (${lastDecision.risk_level})`;
    document.getElementById("last-reason").textContent = lastDecision.reason || "No reason recorded.";
  }
}

document.getElementById("enabled-toggle").addEventListener("change", async (event) => {
  await sendMessage({ type: "setEnabled", enabled: event.target.checked });
  await refreshPopup();
});

refreshPopup().catch(() => {
  document.getElementById("backend-status").textContent = "Unavailable";
  document.getElementById("backend-status").style.color = "#991b1b";
});
