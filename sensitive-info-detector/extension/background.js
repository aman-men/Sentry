const DEFAULT_SETTINGS = {
  enabled: true,
  backendUrl: "http://127.0.0.1:8000",
  timeoutMs: 8000
};
const LOCAL_WORKSPACE_PATH = "local/local_chat.html";
const workspaceWindows = new Map();

function getTabStateKey(tabId) {
  return `tabState:${tabId}`;
}

async function getSessionStorageArea() {
  if (chrome.storage.session) {
    return chrome.storage.session;
  }
  return chrome.storage.local;
}

async function getSettings() {
  const stored = await chrome.storage.local.get(DEFAULT_SETTINGS);
  return { ...DEFAULT_SETTINGS, ...stored };
}

async function setBadgeState(kind) {
  const states = {
    on: { text: "ON", color: "#1d7a34" },
    off: { text: "OFF", color: "#6b7280" },
    low: { text: "LOW", color: "#0f9d58" },
    local: { text: "LOC", color: "#d97706" },
    block: { text: "BLK", color: "#dc2626" },
    error: { text: "ERR", color: "#7c3aed" }
  };
  const state = states[kind] || states.on;
  await chrome.action.setBadgeText({ text: state.text });
  await chrome.action.setBadgeBackgroundColor({ color: state.color });
}

async function withTimeout(promise, timeoutMs) {
  let timerId;
  const timeout = new Promise((_, reject) => {
    timerId = setTimeout(() => reject(new Error("Request to local backend timed out.")), timeoutMs);
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    clearTimeout(timerId);
  }
}

function validateDecision(payload) {
  if (!payload || typeof payload !== "object") {
    throw new Error("Local backend returned an invalid response.");
  }
  if (!["chatgpt", "local", "block"].includes(payload.route)) {
    throw new Error("Local backend returned an unknown route.");
  }
  return payload;
}

function validateLocalChat(payload) {
  if (!payload || typeof payload !== "object") {
    throw new Error("Local backend returned an invalid local chat response.");
  }
  if (typeof payload.session_id !== "string" || !payload.session_id) {
    throw new Error("Local backend returned a missing local session id.");
  }
  if (typeof payload.response !== "string") {
    throw new Error("Local backend returned an invalid local response.");
  }
  return payload;
}

async function processPrompt(message) {
  const settings = await getSettings();
  const endpoint = `${settings.backendUrl.replace(/\/$/, "")}/process_prompt`;
  const response = await withTimeout(
    fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: message.text,
        platform: message.platform
      })
    }),
    settings.timeoutMs
  );

  if (!response.ok) {
    throw new Error(`Local backend returned HTTP ${response.status}.`);
  }

  const decision = validateDecision(await response.json());
  await chrome.storage.local.set({
    lastDecision: {
      ...decision,
      platform: message.platform,
      textPreview: String(message.text || "").slice(0, 120),
      timestamp: Date.now()
    }
  });

  const badgeKind = decision.route === "chatgpt" ? "low" : decision.route === "local" ? "local" : "block";
  await setBadgeState(badgeKind);
  return decision;
}

async function chatLocal(message) {
  const settings = await getSettings();
  const endpoint = `${settings.backendUrl.replace(/\/$/, "")}/chat_local`;
  const response = await withTimeout(
    fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: message.sessionId,
        text: message.text,
        platform: message.platform
      })
    }),
    settings.timeoutMs
  );

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Local backend returned HTTP ${response.status}.`);
  }

  const payload = validateLocalChat(await response.json());
  await setBadgeState("local");
  return payload;
}

async function checkBackendStatus() {
  const settings = await getSettings();
  const endpoint = `${settings.backendUrl.replace(/\/$/, "")}/health`;
  const response = await withTimeout(fetch(endpoint), settings.timeoutMs);
  if (!response.ok) {
    throw new Error(`Health check failed with HTTP ${response.status}.`);
  }
  return await response.json();
}

async function getTabState(tabId) {
  const storage = await getSessionStorageArea();
  const stored = await storage.get({ [getTabStateKey(tabId)]: null });
  return stored[getTabStateKey(tabId)];
}

async function setTabState(tabId, statePatch) {
  const storage = await getSessionStorageArea();
  const key = getTabStateKey(tabId);
  const current = await getTabState(tabId);
  await storage.set({
    [key]: { ...(current || {}), ...statePatch, updatedAt: Date.now() }
  });
}

async function clearTabState(tabId) {
  const storage = await getSessionStorageArea();
  await storage.remove(getTabStateKey(tabId));
}

async function openLocalWorkspace(sourceTabId, platform) {
  const existingWindowId = workspaceWindows.get(sourceTabId);
  if (typeof existingWindowId === "number") {
    try {
      await chrome.windows.update(existingWindowId, { focused: true });
      return { windowId: existingWindowId, reused: true };
    } catch (_error) {
      workspaceWindows.delete(sourceTabId);
    }
  }

  const url = chrome.runtime.getURL(
    `${LOCAL_WORKSPACE_PATH}?sourceTabId=${encodeURIComponent(String(sourceTabId))}&platform=${encodeURIComponent(platform || "unknown")}`
  );
  const created = await chrome.windows.create({
    url,
    type: "popup",
    width: 520,
    height: 760,
    focused: true
  });

  if (typeof created.id === "number") {
    workspaceWindows.set(sourceTabId, created.id);
  }
  return { windowId: created.id, reused: false };
}

chrome.windows.onRemoved.addListener((windowId) => {
  for (const [tabId, mappedWindowId] of workspaceWindows.entries()) {
    if (mappedWindowId === windowId) {
      workspaceWindows.delete(tabId);
    }
  }
});

chrome.runtime.onInstalled.addListener(async () => {
  await chrome.storage.local.set(DEFAULT_SETTINGS);
  await setBadgeState("on");
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    try {
      const tabId = sender?.tab?.id;
      if (message?.type === "getSettings") {
        sendResponse({ ok: true, data: await getSettings() });
        return;
      }
      if (message?.type === "setEnabled") {
        await chrome.storage.local.set({ enabled: Boolean(message.enabled) });
        await setBadgeState(message.enabled ? "on" : "off");
        sendResponse({ ok: true, data: await getSettings() });
        return;
      }
      if (message?.type === "getLastDecision") {
        const stored = await chrome.storage.local.get({ lastDecision: null });
        sendResponse({ ok: true, data: stored.lastDecision });
        return;
      }
      if (message?.type === "checkBackendStatus") {
        sendResponse({ ok: true, data: await checkBackendStatus() });
        return;
      }
      if (message?.type === "getTabState") {
        if (typeof tabId !== "number") {
          throw new Error("Tab state is unavailable for this extension context.");
        }
        sendResponse({ ok: true, data: await getTabState(tabId) });
        return;
      }
      if (message?.type === "setTabState") {
        if (typeof tabId !== "number") {
          throw new Error("Tab state is unavailable for this extension context.");
        }
        await setTabState(tabId, message.state || {});
        sendResponse({ ok: true, data: await getTabState(tabId) });
        return;
      }
      if (message?.type === "clearTabState") {
        if (typeof tabId !== "number") {
          throw new Error("Tab state is unavailable for this extension context.");
        }
        await clearTabState(tabId);
        sendResponse({ ok: true });
        return;
      }
      if (message?.type === "getTabStateForTab") {
        if (typeof message.tabId !== "number") {
          throw new Error("A source tab id is required.");
        }
        sendResponse({ ok: true, data: await getTabState(message.tabId) });
        return;
      }
      if (message?.type === "setTabStateForTab") {
        if (typeof message.tabId !== "number") {
          throw new Error("A source tab id is required.");
        }
        await setTabState(message.tabId, message.state || {});
        sendResponse({ ok: true, data: await getTabState(message.tabId) });
        return;
      }
      if (message?.type === "clearTabStateForTab") {
        if (typeof message.tabId !== "number") {
          throw new Error("A source tab id is required.");
        }
        await clearTabState(message.tabId);
        sendResponse({ ok: true });
        return;
      }
      if (message?.type === "processPrompt") {
        const settings = await getSettings();
        if (!settings.enabled) {
          sendResponse({
            ok: true,
            data: {
              route: "chatgpt",
              risk_level: "low",
              label: "extension_disabled",
              confidence: 1,
              categories: [],
              requires_review: false,
              reason: "Extension disabled. Prompt allowed through without local screening."
            }
          });
          return;
        }
        sendResponse({ ok: true, data: await processPrompt(message) });
        return;
      }
      if (message?.type === "chatLocal") {
        sendResponse({ ok: true, data: await chatLocal(message) });
        return;
      }
      if (message?.type === "openLocalWorkspace") {
        const sourceTabId = typeof message.sourceTabId === "number" ? message.sourceTabId : tabId;
        if (typeof sourceTabId !== "number") {
          throw new Error("Local workspace requires a source tab id.");
        }
        sendResponse({ ok: true, data: await openLocalWorkspace(sourceTabId, message.platform) });
        return;
      }
      sendResponse({ ok: false, error: "Unknown message type." });
    } catch (error) {
      await setBadgeState("error");
      sendResponse({
        ok: false,
        error: error instanceof Error ? error.message : "Unknown extension error."
      });
    }
  })();
  return true;
});
