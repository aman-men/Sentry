(function () {
  const params = new URLSearchParams(window.location.search);
  const sourceTabId = Number(params.get("sourceTabId"));
  const fallbackPlatform = params.get("platform") || "unknown";

  const state = {
    sourceTabId,
    platform: fallbackPlatform,
    sessionId: null,
    transcript: [],
    backend: "local",
    fallbackUsed: false,
    sending: false,
    lastDecision: null
  };

  function el(id) {
    return document.getElementById(id);
  }

  async function sendMessage(message) {
    return await chrome.runtime.sendMessage(message);
  }

  async function getSourceTabState() {
    const response = await sendMessage({ type: "getTabStateForTab", tabId: state.sourceTabId });
    return response?.data || null;
  }

  async function setSourceTabState(patch) {
    const response = await sendMessage({
      type: "setTabStateForTab",
      tabId: state.sourceTabId,
      state: patch
    });
    return response?.data || null;
  }

  async function clearSourceTabState() {
    await sendMessage({ type: "clearTabStateForTab", tabId: state.sourceTabId });
  }

  function renderTags(categories) {
    const container = el("categories-list");
    container.innerHTML = "";
    if (!categories?.length) {
      const empty = document.createElement("span");
      empty.className = "empty-thread";
      empty.textContent = "No categories reported.";
      container.appendChild(empty);
      return;
    }
    for (const category of categories) {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = category;
      container.appendChild(tag);
    }
  }

  function renderThread() {
    const thread = el("thread");
    thread.innerHTML = "";

    if (!state.transcript.length) {
      const empty = document.createElement("div");
      empty.className = "empty-thread";
      empty.textContent = "No local messages yet.";
      thread.appendChild(empty);
      return;
    }

    for (const entry of state.transcript) {
      const message = document.createElement("div");
      const role = entry.role === "assistant" ? "assistant" : entry.role === "system" ? "system" : "user";
      message.className = `message ${role}`;

      const meta = document.createElement("div");
      meta.className = "message-meta";
      meta.textContent =
        role === "assistant" ? "Local assistant" : role === "system" ? "System" : "You";

      const body = document.createElement("div");
      body.className = "message-body";
      body.textContent = entry.content || "";

      message.appendChild(meta);
      message.appendChild(body);
      thread.appendChild(message);
    }

    thread.scrollTop = thread.scrollHeight;
  }

  function renderSummary() {
    const lastDecision = state.lastDecision || {};
    el("platform-value").textContent = String(state.platform || "unknown").toUpperCase();
    el("risk-value").textContent = lastDecision.risk_level || "high";
    el("label-value").textContent = lastDecision.label || "unknown";

    const backendText = state.backend ? String(state.backend).toUpperCase() : "LOCAL";
    el("backend-pill").textContent = state.fallbackUsed ? `${backendText} FALLBACK` : backendText;

    const warning = el("warning-banner");
    if (lastDecision.local_backend_error && state.fallbackUsed) {
      warning.hidden = false;
      warning.textContent = lastDecision.local_backend_error;
    } else {
      warning.hidden = true;
      warning.textContent = "";
    }

    renderTags(lastDecision.categories || []);
  }

  function renderComposer() {
    const input = el("chat-input");
    const send = el("send-button");
    const clear = el("clear-button");
    const status = el("composer-status");
    const enabled = Boolean(state.sessionId) && !state.sending;

    input.disabled = !enabled;
    send.disabled = !enabled;
    clear.disabled = state.sending;
    status.textContent = state.sending
      ? "Waiting for the local model..."
      : state.sessionId
        ? "This conversation is staying on device."
        : "No active local session. Submit a sensitive prompt from ChatGPT or Gemini to start one.";
  }

  function renderAll() {
    renderSummary();
    renderThread();
    renderComposer();
  }

  async function loadState() {
    if (!Number.isFinite(state.sourceTabId)) {
      state.transcript = [{ role: "system", content: "The local workspace is missing its source tab context." }];
      renderAll();
      return;
    }

    const stored = await getSourceTabState();
    state.lastDecision = stored?.lastDecision || null;
    const localChat = stored?.localChat || {};
    state.platform = localChat.platform || stored?.platform || fallbackPlatform;
    state.sessionId = localChat.sessionId || null;
    state.transcript = Array.isArray(localChat.transcript) ? localChat.transcript : [];
    state.backend = localChat.backend || state.lastDecision?.local_backend || "local";
    state.fallbackUsed = Boolean(localChat.fallbackUsed);
    renderAll();
  }

  async function sendLocalTurn() {
    if (state.sending || !state.sessionId) {
      return;
    }

    const input = el("chat-input");
    const draft = input.value.trim();
    if (!draft) {
      return;
    }

    state.sending = true;
    state.transcript.push({ role: "user", content: draft });
    input.value = "";
    renderAll();

    try {
      const response = await sendMessage({
        type: "chatLocal",
        sessionId: state.sessionId,
        text: draft,
        platform: state.platform
      });

      if (!response?.ok) {
        throw new Error(response?.error || "Local chat failed.");
      }

      const payload = response.data;
      state.sessionId = payload.session_id || state.sessionId;
      state.backend = payload.backend_name || state.backend;
      state.fallbackUsed = Boolean(payload.fallback_used);
      state.transcript.push({ role: "assistant", content: payload.response || "" });
      state.lastDecision = {
        ...(state.lastDecision || {}),
        local_backend_error: payload.backend_error || null
      };

      await setSourceTabState({
        localChat: {
          sessionId: state.sessionId,
          transcript: state.transcript,
          platform: state.platform,
          backend: state.backend,
          fallbackUsed: state.fallbackUsed
        },
        lastDecision: state.lastDecision
      });
    } catch (error) {
      state.sessionId = null;
      state.transcript.push({
        role: "system",
        content: error instanceof Error ? error.message : "The local session expired."
      });
    } finally {
      state.sending = false;
      renderAll();
    }
  }

  async function clearThread() {
    state.sessionId = null;
    state.transcript = [];
    state.backend = "local";
    state.fallbackUsed = false;
    await clearSourceTabState();
    renderAll();
  }

  el("send-button").addEventListener("click", async () => {
    await sendLocalTurn();
  });

  el("clear-button").addEventListener("click", async () => {
    await clearThread();
  });

  el("chat-input").addEventListener("keydown", async (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      await sendLocalTurn();
    }
  });

  chrome.storage.onChanged.addListener(async (_changes, areaName) => {
    if (areaName !== "session" && areaName !== "local") {
      return;
    }
    await loadState();
  });

  loadState().catch(() => {
    state.transcript = [{ role: "system", content: "Unable to load the local workspace state." }];
    renderAll();
  });
})();
