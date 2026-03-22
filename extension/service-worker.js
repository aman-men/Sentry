const DEFAULT_SUPPORTED_SITES = ["chatgpt.com", "chat.openai.com", "gemini.google.com"];
const DEFAULT_PROFILES = {
  "desktop-local": { id: "desktop-local", label: "Desktop Local", daemonUrl: "http://127.0.0.1:8777" },
  "user-a": { id: "user-a", label: "User A", daemonUrl: "http://127.0.0.1:8101" },
  "user-b": { id: "user-b", label: "User B", daemonUrl: "http://127.0.0.1:8102" },
  "user-c": { id: "user-c", label: "User C", daemonUrl: "http://127.0.0.1:8103" }
};

chrome.runtime.onInstalled.addListener(async () => {
  await ensureDefaults();
  chrome.alarms.create("sentinel-health-refresh", { periodInMinutes: 1 });
  await refreshAllProfileStatuses();
});

chrome.runtime.onStartup.addListener(async () => {
  await ensureDefaults();
  await refreshAllProfileStatuses();
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === "sentinel-health-refresh") {
    await refreshAllProfileStatuses();
  }
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "sentinel.audit") {
    void handleAudit(message.payload)
      .then((payload) => sendResponse({ ok: true, payload }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "sentinel.status") {
    void handleStatus()
      .then((payload) => sendResponse({ ok: true, payload }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "sentinel.set-active-profile") {
    void setActiveProfile(message.payload?.profileId)
      .then((payload) => sendResponse({ ok: true, payload }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "sentinel.set-profile-daemon-url") {
    void setProfileDaemonUrl(message.payload?.daemonUrl)
      .then((payload) => sendResponse({ ok: true, payload }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "sentinel.feedback-term") {
    void submitFeedback(message.payload)
      .then((payload) => sendResponse({ ok: true, payload }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "sentinel.remove-keyword") {
    void removeKeyword(message.payload)
      .then((payload) => sendResponse({ ok: true, payload }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "sentinel.run-local-model") {
    void runLocalModel(message.payload)
      .then((payload) => sendResponse({ ok: true, payload }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "sentinel.get-local-model-result") {
    void getLocalModelResult(message.payload?.executionId)
      .then((payload) => sendResponse({ ok: true, payload }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "sentinel.open-extensions-page") {
    void chrome.tabs.create({ url: "chrome://extensions" })
      .then(() => sendResponse({ ok: true }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  return false;
});

async function ensureDefaults() {
  const current = await chrome.storage.local.get([
    "profiles",
    "activeProfileId",
    "profileStatusById",
    "profileAuditSummaryById",
    "profileFeedbackSummaryById",
    "localModelResultsById"
  ]);
  const profiles = { ...DEFAULT_PROFILES, ...(current.profiles || {}) };
  const activeProfileId = current.activeProfileId && profiles[current.activeProfileId] ? current.activeProfileId : "desktop-local";
  await chrome.storage.local.set({
    profiles,
    activeProfileId,
    profileStatusById: current.profileStatusById || {},
    profileAuditSummaryById: current.profileAuditSummaryById || {},
    profileFeedbackSummaryById: current.profileFeedbackSummaryById || {},
    localModelResultsById: current.localModelResultsById || {}
  });
  await updateBadge(activeProfileId, null);
}

async function getState() {
  await ensureDefaults();
  const state = await chrome.storage.local.get([
    "profiles",
    "activeProfileId",
    "profileStatusById",
    "profileAuditSummaryById",
    "profileFeedbackSummaryById",
    "localModelResultsById"
  ]);
  return {
    profiles: state.profiles || DEFAULT_PROFILES,
    activeProfileId: state.activeProfileId || "desktop-local",
    profileStatusById: state.profileStatusById || {},
    profileAuditSummaryById: state.profileAuditSummaryById || {},
    profileFeedbackSummaryById: state.profileFeedbackSummaryById || {},
    localModelResultsById: state.localModelResultsById || {}
  };
}

async function getActiveProfile() {
  const state = await getState();
  const profile = state.profiles[state.activeProfileId];
  if (!profile) {
    throw new Error("No active SentinelSovereign profile is configured.");
  }
  return { state, profile };
}

async function handleAudit(payload) {
  const { state, profile } = await getActiveProfile();
  const response = await fetch(`${profile.daemonUrl}/api/browser/intercept`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`Local daemon responded with ${response.status}`);
  }
  const body = await response.json();
  state.profileAuditSummaryById[profile.id] = buildAuditSummary(body.audit, payload?.site_name, profile);
  state.profileStatusById[profile.id] = {
    ...(state.profileStatusById[profile.id] || {}),
    connectionStatus: "connected",
    lastConnectionError: null,
    lastCheckedAt: new Date().toISOString()
  };
  await chrome.storage.local.set({
    profileAuditSummaryById: state.profileAuditSummaryById,
    profileStatusById: state.profileStatusById
  });
  await updateBadge(profile.id, "connected");
  return {
    ...body,
    local_model: state.profileStatusById[profile.id]?.clientStatus?.local_model_status || null,
    active_profile: {
      id: profile.id,
      label: profile.label,
      daemonUrl: profile.daemonUrl
    }
  };
}

async function handleStatus() {
  await refreshAllProfileStatuses();
  const state = await getState();
  const profiles = Object.values(state.profiles).map((profile) => {
    const status = state.profileStatusById[profile.id] || {};
    const clientStatus = status.clientStatus || null;
    const localModelStatus = clientStatus?.local_model_status || null;
    return {
      ...profile,
      connectionStatus: status.connectionStatus || "unknown",
      clientStatus,
      localModelStatus,
      lastConnectionError: status.lastConnectionError || null,
      lastCheckedAt: status.lastCheckedAt || null,
      lastAuditSummary: state.profileAuditSummaryById[profile.id] || null,
      lastFeedbackSummary: state.profileFeedbackSummaryById[profile.id] || null
    };
  });
  return {
    activeProfileId: state.activeProfileId,
    activeProfile: profiles.find((profile) => profile.id === state.activeProfileId) || null,
    profiles,
    supportedSites:
      profiles.find((profile) => profile.id === state.activeProfileId)?.clientStatus?.supported_sites || DEFAULT_SUPPORTED_SITES
  };
}

async function refreshAllProfileStatuses() {
  const state = await getState();
  const updates = {};
  for (const profile of Object.values(state.profiles)) {
    updates[profile.id] = await probeProfile(profile);
  }
  await chrome.storage.local.set({ profileStatusById: updates });
  await updateBadge(state.activeProfileId, updates[state.activeProfileId]?.connectionStatus || null);
}

async function probeProfile(profile) {
  try {
    const response = await fetch(`${profile.daemonUrl}/api/client/status`);
    if (!response.ok) {
      throw new Error(`Local daemon responded with ${response.status}`);
    }
    const clientStatus = await response.json();
    return {
      connectionStatus: "connected",
      clientStatus,
      lastConnectionError: null,
      lastCheckedAt: new Date().toISOString()
    };
  } catch (error) {
    return {
      connectionStatus: "disconnected",
      clientStatus: null,
      lastConnectionError: error instanceof Error ? error.message : "Unknown daemon error",
      lastCheckedAt: new Date().toISOString()
    };
  }
}

async function setActiveProfile(profileId) {
  const state = await getState();
  if (!profileId || !state.profiles[profileId]) {
    throw new Error("A valid SentinelSovereign profile is required.");
  }
  await chrome.storage.local.set({ activeProfileId: profileId });
  await updateBadge(profileId, state.profileStatusById[profileId]?.connectionStatus || null);
  return handleStatus();
}

async function setProfileDaemonUrl(nextDaemonUrl) {
  const normalized = String(nextDaemonUrl || "").trim().replace(/\/+$/, "");
  if (!normalized) {
    throw new Error("A valid daemon URL is required.");
  }
  const state = await getState();
  state.profiles[state.activeProfileId] = {
    ...state.profiles[state.activeProfileId],
    daemonUrl: normalized
  };
  await chrome.storage.local.set({ profiles: state.profiles });
  return handleStatus();
}

async function submitFeedback(payload) {
  const { state, profile } = await getActiveProfile();
  if (!payload?.term) {
    throw new Error("A feedback term is required.");
  }
  const response = await fetch(`${profile.daemonUrl}/api/context/feedback`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      term: payload.term,
      sensitive: true,
      notes: payload.source || "extension_manual_feedback"
    })
  });
  if (!response.ok) {
    throw new Error(`Feedback failed with status ${response.status}`);
  }
  const body = await response.json();
  state.profileFeedbackSummaryById[profile.id] = buildFeedbackSummary(body, profile);
  await chrome.storage.local.set({ profileFeedbackSummaryById: state.profileFeedbackSummaryById });
  await refreshAllProfileStatuses();
  return body;
}

async function removeKeyword(payload) {
  const state = await getState();
  const profileId = payload?.profileId || state.activeProfileId;
  const profile = state.profiles[profileId];
  if (!profile) {
    throw new Error("A valid profile is required.");
  }
  if (!payload?.term) {
    throw new Error("A keyword is required.");
  }

  const encodedTerm = encodeURIComponent(String(payload.term).trim().toLowerCase());
  const response = await fetch(`${profile.daemonUrl}/api/context/keywords/${encodedTerm}`, {
    method: "DELETE"
  });
  if (!response.ok) {
    throw new Error(`Keyword removal failed with status ${response.status}`);
  }
  const body = await response.json();
  await refreshAllProfileStatuses();
  return body;
}

async function runLocalModel(payload) {
  const { state, profile } = await getActiveProfile();
  const response = await fetch(`${profile.daemonUrl}/api/local-model/execute`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      audit_id: payload.auditId,
      original_text: payload.originalText,
      decision_reason: payload.decisionReason,
      site_name: payload.siteName,
      page_url: payload.pageUrl
    })
  });
  if (!response.ok) {
    let detail = `Local model failed with status ${response.status}`;
    try {
      const body = await response.json();
      detail = body?.detail || detail;
    } catch (_error) {
      // Ignore JSON parsing failure.
    }
    throw new Error(detail);
  }
  const body = await response.json();
  const execution = {
    ...body,
    profileId: profile.id,
    profileLabel: profile.label,
    daemonUrl: profile.daemonUrl
  };
  state.localModelResultsById = pruneLocalModelResults({
    ...state.localModelResultsById,
    [execution.execution_id]: execution
  });
  await chrome.storage.local.set({ localModelResultsById: state.localModelResultsById });
  await chrome.tabs.create({ url: chrome.runtime.getURL(`local-result.html?execution_id=${encodeURIComponent(execution.execution_id)}`) });
  return {
    executionId: execution.execution_id,
    statusMessage: execution.status_message,
    profileId: profile.id,
    profileLabel: profile.label
  };
}

async function getLocalModelResult(executionId) {
  if (!executionId) {
    throw new Error("A local execution id is required.");
  }
  const state = await getState();
  const result = state.localModelResultsById[executionId];
  if (!result) {
    throw new Error("Local execution result not found.");
  }
  return result;
}

function buildAuditSummary(audit, siteName, profile) {
  return {
    auditId: audit.audit_id,
    profileId: profile.id,
    profileLabel: profile.label,
    siteName: siteName || "Unknown site",
    decision: audit.decision.action,
    reason: audit.decision.reason,
    findings: audit.findings.length,
    highestRiskScore: audit.highest_risk_score,
    generatedAt: audit.generated_at
  };
}

function buildFeedbackSummary(feedback, profile) {
  return {
    profileId: profile.id,
    profileLabel: profile.label,
    term: feedback.term,
    localWeight: feedback.local_weight,
    noisyWeight: feedback.noisy_weight,
    exported: feedback.exported,
    source: feedback.source,
    createdAt: new Date().toISOString()
  };
}

function pruneLocalModelResults(resultsById) {
  const entries = Object.entries(resultsById).sort((left, right) => {
    const leftTime = Date.parse(left[1]?.created_at || 0);
    const rightTime = Date.parse(right[1]?.created_at || 0);
    return rightTime - leftTime;
  });
  return Object.fromEntries(entries.slice(0, 12));
}

async function updateBadge(profileId, connectionStatus) {
  const textMap = {
    "desktop-local": "D",
    "user-a": "A",
    "user-b": "B",
    "user-c": "C"
  };
  await chrome.action.setBadgeText({ text: textMap[profileId] || "S" });
  const color = connectionStatus === "connected" ? "#0f6c73" : connectionStatus === "disconnected" ? "#8b3117" : "#6b7b88";
  await chrome.action.setBadgeBackgroundColor({ color });
}
