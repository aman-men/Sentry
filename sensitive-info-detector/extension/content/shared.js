(function () {
  const ROOT_ID = "ai-security-extension-root";
  const BADGE_ID = "ai-security-mini-badge";
  const PANEL_HTML_URL = chrome.runtime.getURL("ui/panel.html");

  const state = {
    settings: null,
    panelReady: null,
    allowNextSubmit: false,
    processing: false,
    platform: "unknown",
    composeReady: null,
    localChat: {
      sessionId: null,
      transcript: [],
      platform: "unknown",
      backend: "unknown",
      fallbackUsed: false
    },
    localChatBusy: false
  };

  function sendMessage(message) {
    return new Promise((resolve) => chrome.runtime.sendMessage(message, resolve));
  }

  async function getSettings() {
    if (state.settings) {
      return state.settings;
    }
    const response = await sendMessage({ type: "getSettings" });
    state.settings = response?.data || { enabled: true };
    return state.settings;
  }

  async function getTabState() {
    const response = await sendMessage({ type: "getTabState" });
    return response?.data || null;
  }

  async function setTabState(patch) {
    const response = await sendMessage({ type: "setTabState", state: patch });
    return response?.data || null;
  }

  async function clearTabState() {
    await sendMessage({ type: "clearTabState" });
  }

  async function ensurePanel(platform) {
    if (state.panelReady) {
      return state.panelReady;
    }

    state.platform = platform;
    state.panelReady = (async () => {
      let root = document.getElementById(ROOT_ID);
      if (root) {
        return root;
      }

      root = document.createElement("div");
      root.id = ROOT_ID;
      root.className = "ai-security-root";
      const response = await fetch(PANEL_HTML_URL);
      root.innerHTML = await response.text();
      document.documentElement.appendChild(root);

      const badge = document.createElement("div");
      badge.id = BADGE_ID;
      badge.className = "ai-security-mini-badge";
      badge.hidden = true;
      document.documentElement.appendChild(badge);

      root.querySelector("[data-platform]").textContent = platform.toUpperCase();
      const closeButton = root.querySelector("[data-close-local-modal]");
      const copyButton = root.querySelector("[data-copy-local-response]");
      const clearButton = root.querySelector("[data-clear-local-chat]");
      const sendButton = root.querySelector("[data-send-local-chat]");
      const textarea = root.querySelector("[data-local-chat-input]");
      const modal = root.querySelector("[data-local-modal]");

      closeButton?.addEventListener("click", () => {
        modal.hidden = true;
      });

      copyButton?.addEventListener("click", async () => {
        const assistantMessages = state.localChat.transcript.filter((entry) => entry.role === "assistant");
        const text = assistantMessages.length
          ? assistantMessages[assistantMessages.length - 1].content
          : "";
        if (!text) {
          return;
        }
        try {
          await navigator.clipboard.writeText(text);
          showBadge("Local response copied", "local");
        } catch (_error) {
          showBadge("Unable to copy response", "block");
        }
      });

      clearButton?.addEventListener("click", async () => {
        state.localChat = {
          sessionId: null,
          transcript: [],
          platform: state.platform,
          backend: "unknown",
          fallbackUsed: false
        };
        textarea.value = "";
        await clearTabState();
        renderLocalTranscript(root, []);
        updateLocalComposer(root);
        modal.hidden = true;
        showBadge("Local chat cleared", "low");
      });

      sendButton?.addEventListener("click", async () => {
        await sendLocalChatTurn();
      });

      textarea?.addEventListener("keydown", async (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          await sendLocalChatTurn();
        }
      });

      return root;
    })();

    return state.panelReady;
  }

  function isVisible(element) {
    if (!element) {
      return false;
    }
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function firstVisible(selectors) {
    for (const selector of selectors) {
      const element = document.querySelector(selector);
      if (isVisible(element)) {
        return element;
      }
    }
    return null;
  }

  function closestMatchingButton(target, selectors) {
    const button = target instanceof Element ? target.closest("button") : null;
    if (!button || !isVisible(button)) {
      return null;
    }
    return selectors.some((selector) => button.matches(selector)) ? button : null;
  }

  function extractText(element) {
    if (!element) {
      return "";
    }
    if ("value" in element && typeof element.value === "string") {
      return element.value.trim();
    }
    return (element.innerText || element.textContent || "").trim();
  }

  function showBadge(text, tone) {
    const badge = document.getElementById(BADGE_ID);
    if (!badge) {
      return;
    }
    badge.textContent = text;
    badge.hidden = false;
    badge.style.background =
      tone === "low" ? "#dcfce7" : tone === "local" ? "#ffedd5" : "#fee2e2";
    badge.style.color =
      tone === "low" ? "#166534" : tone === "local" ? "#9a3412" : "#991b1b";
    window.clearTimeout(showBadge.timerId);
    showBadge.timerId = window.setTimeout(() => {
      badge.hidden = true;
    }, 3200);
  }

  function renderCategories(container, categories) {
    container.innerHTML = "";
    if (!categories.length) {
      const empty = document.createElement("span");
      empty.className = "ai-security-value";
      empty.textContent = "No categories reported.";
      container.appendChild(empty);
      return;
    }
    for (const category of categories) {
      const tag = document.createElement("span");
      tag.className = "ai-security-tag";
      tag.textContent = category;
      container.appendChild(tag);
    }
  }

  function renderLocalTranscript(root, transcript) {
    const transcriptNode = root.querySelector("[data-local-transcript]");
    transcriptNode.innerHTML = "";

    if (!transcript.length) {
      const empty = document.createElement("div");
      empty.className = "ai-security-empty-thread";
      empty.textContent = "No local messages yet.";
      transcriptNode.appendChild(empty);
      return;
    }

    for (const entry of transcript) {
      const message = document.createElement("div");
      const role = entry.role === "assistant" ? "assistant" : entry.role === "system" ? "system" : "user";
      message.className = `ai-security-chat-message ${role}`;

      const meta = document.createElement("div");
      meta.className = "ai-security-chat-meta";
      meta.textContent =
        role === "assistant" ? "Local assistant" : role === "system" ? "System" : "You";

      const body = document.createElement("div");
      body.className = "ai-security-chat-body";
      body.textContent = entry.content || "";

      message.appendChild(meta);
      message.appendChild(body);
      transcriptNode.appendChild(message);
    }

    transcriptNode.scrollTop = transcriptNode.scrollHeight;
  }

  function updateLocalComposer(root) {
    const textarea = root.querySelector("[data-local-chat-input]");
    const sendButton = root.querySelector("[data-send-local-chat]");
    const status = root.querySelector("[data-local-chat-status]");
    const canSend = Boolean(state.localChat.sessionId) && !state.localChatBusy;
    textarea.disabled = !canSend;
    sendButton.disabled = !canSend;
    status.textContent = state.localChatBusy
      ? "Waiting for the local model..."
      : state.localChat.sessionId
        ? "Continue the conversation locally. Press Enter to send."
        : "Start a new local prompt from the page to open a local-only thread.";
  }

  async function persistLocalState() {
    await setTabState({
      localChat: state.localChat
    });
  }

  async function restoreLocalState(platform) {
    const stored = await getTabState();
    const localChat = stored?.localChat;
    if (!localChat?.sessionId || !Array.isArray(localChat.transcript) || !localChat.transcript.length) {
      return;
    }

    state.localChat = {
      sessionId: localChat.sessionId,
      transcript: localChat.transcript,
      platform: localChat.platform || platform,
      backend: localChat.backend || "unknown",
      fallbackUsed: Boolean(localChat.fallbackUsed)
    };

    const root = await ensurePanel(platform);
    renderLocalModal(platform, {
      route: "local",
      risk_level: stored?.lastDecision?.risk_level || "high",
      label: stored?.lastDecision?.label || "unknown",
      categories: stored?.lastDecision?.categories || [],
      local_backend: state.localChat.backend,
      local_fallback_used: state.localChat.fallbackUsed,
      local_backend_error: stored?.lastDecision?.local_backend_error || "",
      local_response: ""
    });
    renderLocalTranscript(root, state.localChat.transcript);
    updateLocalComposer(root);
  }

  async function renderDecision(platform, decision) {
    const root = await ensurePanel(platform);
    const panel = root.querySelector(".ai-security-panel");
    panel.hidden = false;

    const routeTone =
      decision.route === "chatgpt"
        ? "low"
        : decision.route === "local"
          ? "local"
          : decision.requires_review
            ? "review"
            : "block";
    const routeLabel =
      decision.route === "chatgpt"
        ? "Low Risk"
        : decision.route === "local"
          ? "High Risk / Local"
          : "Blocked";

    const pill = root.querySelector("[data-route-pill]");
    pill.textContent = routeLabel;
    pill.className = `ai-security-pill ${routeTone}`;

    root.querySelector("[data-route]").textContent = decision.route;
    root.querySelector("[data-risk-level]").textContent = decision.risk_level || "unknown";
    root.querySelector("[data-label]").textContent = decision.label || "unknown";
    root.querySelector("[data-confidence]").textContent =
      typeof decision.confidence === "number"
        ? `${Math.round(decision.confidence * 100)}%`
        : "n/a";
    root.querySelector("[data-review]").textContent = decision.requires_review ? "Yes" : "No";
    root.querySelector("[data-reason]").textContent = decision.reason || "No reason provided.";
    root.querySelector("[data-local-response]").textContent =
      decision.local_response || "No local response was returned.";
    renderCategories(root.querySelector("[data-categories]"), decision.categories || []);
    await setTabState({ lastDecision: decision, platform });
  }

  async function renderLocalModal(platform, decision) {
    const root = await ensurePanel(platform);
    const modal = root.querySelector("[data-local-modal]");
    const warningRow = root.querySelector("[data-local-warning-row]");
    const warningBody = root.querySelector("[data-local-warning]");

    root.querySelector("[data-local-platform]").textContent = `${platform.toUpperCase()} LOCAL WORKSPACE`;
    root.querySelector("[data-local-backend]").textContent =
      decision.local_backend || decision.local_mode || "unknown";
    root.querySelector("[data-local-risk]").textContent = decision.risk_level || "unknown";
    root.querySelector("[data-local-label]").textContent = decision.label || "unknown";
    renderCategories(root.querySelector("[data-local-categories]"), decision.categories || []);
    root.querySelector("[data-local-backend-state]").textContent =
      decision.local_backend_available === false ? "Unavailable" : "Ready";

    if (decision.local_fallback_used) {
      warningRow.hidden = false;
      warningBody.textContent =
        decision.local_backend_error ||
        "Ollama was unavailable, so the mock local responder handled this prompt.";
    } else {
      warningRow.hidden = true;
      warningBody.textContent = "";
    }

    renderLocalTranscript(root, state.localChat.transcript);
    updateLocalComposer(root);
    modal.hidden = false;
  }

  async function renderPending(platform, text) {
    await renderDecision(platform, {
      route: "local",
      risk_level: "pending",
      label: "screening",
      confidence: 0,
      categories: [],
      requires_review: false,
      reason: text,
      local_response: ""
    });
  }

  async function callBackend(platform, text) {
    const response = await sendMessage({
      type: "processPrompt",
      platform,
      text
    });
    if (response?.ok) {
      return response.data;
    }
    return {
      route: "block",
      risk_level: "high",
      label: "backend_unavailable",
      confidence: 0,
      categories: [],
      requires_review: true,
      reason:
        response?.error ||
        "Local backend unavailable. Safe failure mode blocked the prompt from leaving the page."
    };
  }

  async function callLocalChat(sessionId, platform, text) {
    const response = await sendMessage({
      type: "chatLocal",
      sessionId,
      platform,
      text
    });
    if (response?.ok) {
      return response.data;
    }
    throw new Error(
      response?.error ||
        "Local chat could not reach the backend. The sensitive conversation remains blocked from leaving the page."
    );
  }

  async function sendLocalChatTurn() {
    if (state.localChatBusy || !state.localChat.sessionId) {
      return;
    }

    const root = await ensurePanel(state.platform);
    const textarea = root.querySelector("[data-local-chat-input]");
    const draft = (textarea.value || "").trim();
    if (!draft) {
      showBadge("Local message is empty", "block");
      return;
    }

    state.localChatBusy = true;
    state.localChat.transcript.push({ role: "user", content: draft });
    textarea.value = "";
    renderLocalTranscript(root, state.localChat.transcript);
    updateLocalComposer(root);

    try {
      const result = await callLocalChat(state.localChat.sessionId, state.platform, draft);
      state.localChat.backend = result.backend_name || state.localChat.backend;
      state.localChat.fallbackUsed = Boolean(result.fallback_used);
      state.localChat.transcript.push({ role: "assistant", content: result.response || "" });
      await persistLocalState();

      await renderLocalModal(state.platform, {
        route: "local",
        risk_level: root.querySelector("[data-local-risk]").textContent || "high",
        label: root.querySelector("[data-local-label]").textContent || "unknown",
        categories: Array.from(root.querySelectorAll("[data-local-categories] .ai-security-tag")).map(
          (tag) => tag.textContent || ""
        ),
        local_backend: result.backend_name,
        local_backend_available: result.backend_available,
        local_fallback_used: result.fallback_used,
        local_backend_error: result.backend_error,
        local_response: result.response
      });
    } catch (error) {
      const errorMessage =
        error instanceof Error
          ? error.message.replace(/^"|"$/g, "")
          : "The local session expired. Start a new local prompt.";
      state.localChat.sessionId = null;
      state.localChat.transcript.push({ role: "system", content: errorMessage });
      await persistLocalState();
      showBadge("Local session needs restart", "block");
      renderLocalTranscript(root, state.localChat.transcript);
    } finally {
      state.localChatBusy = false;
      updateLocalComposer(root);
    }
  }

  async function triggerNativeSubmit(config, composeElement, submitSource) {
    const sendButton = firstVisible(config.sendButtonSelectors);
    state.allowNextSubmit = true;

    if (sendButton) {
      sendButton.click();
      return;
    }

    const keyboardEvent = new KeyboardEvent("keydown", {
      key: "Enter",
      code: "Enter",
      bubbles: true,
      cancelable: true
    });
    (composeElement || submitSource?.target || document.activeElement)?.dispatchEvent(keyboardEvent);
  }

  function isComposeTarget(target, selectors) {
    if (!(target instanceof Element)) {
      return false;
    }
    return selectors.some((selector) => target.matches(selector) || target.closest(selector));
  }

  async function handleSubmission(config, submitSource) {
    const settings = await getSettings();
    if (!settings.enabled) {
      return;
    }

    const composeElement = firstVisible(config.composeSelectors);
    const text = extractText(composeElement);
    if (!text) {
      showBadge("Prompt is empty", "block");
      return;
    }

    if (state.processing) {
      return;
    }

    state.processing = true;
    await renderPending(config.platform, "Checking prompt with the local security backend...");
    const decision = await callBackend(config.platform, text);
    await renderDecision(config.platform, decision);

    if (decision.route === "chatgpt") {
      showBadge("Low risk: allowed", "low");
      state.processing = false;
      await triggerNativeSubmit(config, composeElement, submitSource);
      return;
    }

    if (decision.route === "local") {
      state.localChat = {
        sessionId: decision.local_session_id || null,
        transcript: [
          { role: "user", content: text },
          { role: "assistant", content: decision.local_response || "No local response was returned." }
        ],
        platform: config.platform,
        backend: decision.local_backend || decision.local_mode || "unknown",
        fallbackUsed: Boolean(decision.local_fallback_used)
      };
      await persistLocalState();
      showBadge("Handled locally", "local");
      await renderLocalModal(config.platform, decision);
    } else {
      state.localChat = {
        sessionId: null,
        transcript: [],
        platform: config.platform,
        backend: "unknown",
        fallbackUsed: false
      };
      await clearTabState();
      showBadge("Prompt blocked", "block");
    }
    state.processing = false;
  }

  function installInterception(config) {
    state.platform = config.platform;
    ensurePanel(config.platform)
      .then(() => restoreLocalState(config.platform))
      .catch(() => {});

    document.addEventListener(
      "keydown",
      async (event) => {
        if (state.allowNextSubmit) {
          state.allowNextSubmit = false;
          return;
        }

        const isSendKey = event.key === "Enter" && !event.shiftKey;
        if (!isSendKey || !isComposeTarget(event.target, config.composeSelectors)) {
          return;
        }

        event.preventDefault();
        event.stopPropagation();
        await handleSubmission(config, event);
      },
      true
    );

    document.addEventListener(
      "click",
      async (event) => {
        const matchedButton = closestMatchingButton(event.target, config.sendButtonSelectors);
        if (!matchedButton) {
          return;
        }

        if (state.allowNextSubmit) {
          state.allowNextSubmit = false;
          return;
        }

        event.preventDefault();
        event.stopPropagation();
        await handleSubmission(config, event);
      },
      true
    );

    const observer = new MutationObserver(() => {
      const composeElement = firstVisible(config.composeSelectors);
      const composeReady = Boolean(composeElement);
      if (composeReady === state.composeReady) {
        return;
      }
      state.composeReady = composeReady;
      const badgeText = composeReady ? `AI Security Active: ${config.platform}` : "Waiting for composer";
      showBadge(badgeText, composeReady ? "low" : "block");
    });

    observer.observe(document.documentElement, {
      childList: true,
      subtree: true
    });
  }

  window.AISecurityExtension = {
    installInterception,
    firstVisible
  };
})();
