const OVERLAY_ID = "sentinel-sovereign-overlay";
const BUSY_CLASS = "sentinel-sovereign-busy";
const LOCKED_BUTTON_ATTRIBUTE = "data-sentinel-locked";
const ORIGINAL_DISABLED_ATTRIBUTE = "data-sentinel-original-disabled";

const SITE_NAMES = {
  "chatgpt.com": "ChatGPT",
  "chat.openai.com": "ChatGPT",
  "gemini.google.com": "Gemini"
};

const interceptionState = {
  status: "idle",
  blockedRecord: null,
  approvedSubmission: null,
  overlayMode: null
};

const observer = new MutationObserver(() => {
  refreshSubmitButtonLock();
});

document.addEventListener("keydown", handleKeydownCapture, true);
document.addEventListener("click", handleClickCapture, true);
document.addEventListener("submit", handleSubmitCapture, true);
document.addEventListener("input", handleInputCapture, true);
observer.observe(document.documentElement, { childList: true, subtree: true });

async function handleKeydownCapture(event) {
  if (event.defaultPrevented || event.isComposing || event.key !== "Enter" || event.shiftKey) {
    return;
  }
  const composer = getActiveComposer();
  if (!composer || !composer.contains(event.target)) {
    return;
  }
  await routeSubmissionAttempt(event, composer, "enter");
}

async function handleClickCapture(event) {
  const submitButton = event.target instanceof Element ? event.target.closest("button") : null;
  if (!submitButton || !looksLikeSubmitButton(submitButton)) {
    return;
  }
  const composer = getActiveComposer();
  if (!composer) {
    return;
  }
  await routeSubmissionAttempt(event, composer, "click");
}

async function handleSubmitCapture(event) {
  if (interceptionState.status === "approved_for_single_submit") {
    interceptionState.status = "idle";
    interceptionState.approvedSubmission = null;
    releaseSubmitButtonLock();
    return;
  }

  if (interceptionState.status === "auditing" || interceptionState.status === "blocked" || interceptionState.status === "local_model_running") {
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
  }
}

function handleInputCapture(event) {
  const composer = event.target instanceof HTMLElement ? findComposerFromNode(event.target) : null;
  if (!composer || !interceptionState.blockedRecord) {
    return;
  }

  const composerSignature = getComposerSignature(composer);
  if (composerSignature !== interceptionState.blockedRecord.composerSignature) {
    return;
  }

  const nextNormalized = normalizeText(readComposerText(composer));
  if (nextNormalized === interceptionState.blockedRecord.normalizedText) {
    refreshSubmitButtonLock();
    return;
  }

  clearBlockedState();
}

async function routeSubmissionAttempt(event, composer, trigger) {
  const originalText = readComposerText(composer).trim();
  if (!originalText) {
    return;
  }

  const normalizedText = normalizeText(originalText);
  const promptHash = await hashText(normalizedText);
  const composerSignature = getComposerSignature(composer);

  if (consumeApprovedSubmitIfMatch(composerSignature, promptHash)) {
    return;
  }

  if (interceptionState.status === "blocked" && matchesBlockedPrompt(composerSignature, promptHash)) {
    blockBrowserEvent(event);
    refreshSubmitButtonLock();
    renderBlockedOverlay(interceptionState.blockedRecord, { returnFromCancel: interceptionState.overlayMode === "hidden" });
    return;
  }

  if (interceptionState.status === "auditing" || interceptionState.status === "local_model_running") {
    blockBrowserEvent(event);
    refreshSubmitButtonLock();
    return;
  }

  blockBrowserEvent(event);
  await interceptSubmission({
    composer,
    composerSignature,
    originalText,
    normalizedText,
    promptHash,
    trigger
  });
}

async function interceptSubmission({ composer, composerSignature, originalText, normalizedText, promptHash }) {
  setState("auditing");
  refreshSubmitButtonLock();

  try {
    const payload = await sendAuditRequest({
      text: originalText,
      page_url: window.location.href,
      page_title: document.title,
      site_name: SITE_NAMES[window.location.hostname] || window.location.hostname,
      attachments: []
    });

    const audit = payload.audit;
    if (payload.approved_automatically) {
      await approveAndSubmit({
        composer,
        composerSignature,
        submitText: payload.submit_text
      });
      return;
    }

    interceptionState.blockedRecord = {
      composerSignature,
      normalizedText,
      promptHash,
      originalText,
      audit,
      localModel: payload.local_model || null
    };
    setState("blocked");
    renderBlockedOverlay(interceptionState.blockedRecord, { returnFromCancel: false });
  } catch (error) {
    interceptionState.blockedRecord = {
      composerSignature,
      normalizedText,
      promptHash,
      originalText,
      audit: null,
      localModel: null,
      error: error instanceof Error ? error.message : "Audit failed"
    };
    setState("blocked");
    renderBlockedOverlay(interceptionState.blockedRecord, { returnFromCancel: false });
  }
}

async function approveAndSubmit({ composer, composerSignature, submitText }) {
  replaceComposerText(composer, submitText);
  const normalized = normalizeText(submitText);
  interceptionState.approvedSubmission = {
    composerSignature,
    promptHash: await hashText(normalized)
  };
  removeOverlay();
  clearBlockedState({ preserveApprovedSubmission: true });
  setState("approved_for_single_submit");
  triggerApprovedSubmission(composer);
}

async function runLocalModel(record) {
  setState("local_model_running");
  renderLocalModelProgress(record);

  try {
    const payload = await sendLocalModelRequest({
      auditId: record.audit.audit_id,
      originalText: record.originalText,
      decisionReason: record.audit.decision.reason,
      siteName: SITE_NAMES[window.location.hostname] || window.location.hostname,
      pageUrl: window.location.href
    });
    clearComposerTextBySignature(record.composerSignature);
    clearBlockedState();
    renderLocalModelSuccess(payload);
  } catch (error) {
    setState("blocked");
    renderBlockedOverlay(
      {
        ...record,
        error: error instanceof Error ? error.message : "Local model execution failed"
      },
      { returnFromCancel: false }
    );
  }
}

function renderBlockedOverlay(record, { returnFromCancel }) {
  removeOverlay();
  const overlay = document.createElement("div");
  overlay.id = OVERLAY_ID;

  if (record.error && !record.audit) {
    overlay.innerHTML = `
      <div class="sentinel-panel">
        <div class="sentinel-header">
          <div>
            <p class="sentinel-eyebrow">SentinelSovereign</p>
            <h2>Outbound prompt remains blocked</h2>
          </div>
          <button class="sentinel-close">Hide Review</button>
        </div>
        <p class="sentinel-error">${escapeHtml(record.error)}</p>
        <p class="sentinel-note">
          Sending is locked until the prompt changes or the local audit becomes available again.
        </p>
      </div>
    `;
    overlay.querySelector(".sentinel-close")?.addEventListener("click", hideBlockedOverlay);
    document.body.appendChild(overlay);
    return;
  }

  const audit = record.audit;
  const findings = audit.findings
    .map(
      (finding) => `
        <li>
          <strong>${escapeHtml(finding.category)}</strong>
          <span>${escapeHtml(finding.label)}</span>
          <small>score ${Number(finding.risk_score).toFixed(2)} via ${escapeHtml(finding.source)}</small>
        </li>
      `
    )
    .join("");

  const trace = audit.trace
    .map(
      (step) => `
        <li>
          <strong>${escapeHtml(step.stage)}</strong>
          <span>${escapeHtml(step.summary)}</span>
          <pre>${escapeHtml(JSON.stringify(step.details, null, 2))}</pre>
        </li>
      `
    )
    .join("");

  const candidateOptions = (audit.contextual_candidates || [])
    .map(
      (candidate) => `<option value="${escapeHtml(candidate.term)}">${escapeHtml(candidate.term)} (${candidate.occurrences}x)</option>`
    )
    .join("");

  const localModelAvailable = Boolean(record.localModel?.available);
  const localModelStatus = record.localModel?.status_message || "Local model status unavailable.";

  overlay.innerHTML = `
    <div class="sentinel-panel">
      <div class="sentinel-header">
        <div>
          <p class="sentinel-eyebrow">SentinelSovereign</p>
          <h2>Outbound prompt intercepted</h2>
        </div>
        <button class="sentinel-close">Cancel</button>
      </div>

      <p class="sentinel-note">
        ${
          returnFromCancel
            ? "This prompt is still locked. Cancel only hides the review; it does not allow the same content to be sent."
            : "This prompt is locked until you approve the redacted version, run it on the local model, or change the prompt."
        }
      </p>

      <div class="sentinel-summary">
        <div>
          <span>Client</span>
          <strong>${escapeHtml(audit.client_id)}</strong>
        </div>
        <div>
          <span>Decision</span>
          <strong>${escapeHtml(audit.decision.action)}</strong>
        </div>
        <div>
          <span>Reason</span>
          <strong>${escapeHtml(audit.decision.reason)}</strong>
        </div>
        <div>
          <span>Audit ID</span>
          <strong>${escapeHtml(audit.audit_id)}</strong>
        </div>
      </div>

      <div class="sentinel-columns">
        <section>
          <h3>Original</h3>
          <pre>${escapeHtml(audit.original_text)}</pre>
        </section>
        <section>
          <h3>Sanitized</h3>
          <pre>${escapeHtml(audit.sanitized_text)}</pre>
        </section>
      </div>

      <div class="sentinel-columns">
        <section>
          <h3>Findings</h3>
          <ul class="sentinel-list">${findings || "<li><span>No findings</span></li>"}</ul>
        </section>
        <section>
          <h3>Trace</h3>
          <ul class="sentinel-list sentinel-trace">${trace}</ul>
        </section>
      </div>

      <section class="sentinel-feedback">
        <h3>Missed Sensitive Term?</h3>
        <p>Select a contextual candidate to raise its local sensitivity weight for this active profile.</p>
        ${
          candidateOptions
            ? `
          <div class="sentinel-feedback-row">
            <select class="sentinel-feedback-select">${candidateOptions}</select>
            <button class="sentinel-secondary sentinel-feedback-button">Flag Missed Term</button>
          </div>
          <p class="sentinel-feedback-status"></p>
        `
            : `<p class="sentinel-feedback-status">No candidate terms extracted from this prompt.</p>`
        }
      </section>

      <section class="sentinel-local-model">
        <h3>Local Model</h3>
        <p>${
          localModelAvailable
            ? "Run this sensitive prompt entirely on the active employee machine instead of the public site."
            : "Local model execution is unavailable for this profile right now."
        }</p>
        <p class="sentinel-feedback-status">${escapeHtml(localModelStatus)}</p>
      </section>

      <div class="sentinel-actions sentinel-actions-wide">
        <button class="sentinel-secondary sentinel-cancel">Cancel</button>
        <button class="sentinel-secondary sentinel-local" ${localModelAvailable ? "" : "disabled"}>
          Run On Local Model Instead
        </button>
        <button class="sentinel-primary sentinel-approve">Approve Redacted Prompt</button>
      </div>
    </div>
  `;

  overlay.querySelector(".sentinel-close")?.addEventListener("click", hideBlockedOverlay);
  overlay.querySelector(".sentinel-cancel")?.addEventListener("click", hideBlockedOverlay);
  overlay.querySelector(".sentinel-approve")?.addEventListener("click", () => {
    const composer = getComposerBySignature(record.composerSignature);
    if (!composer) {
      return;
    }
    void approveAndSubmit({
      composer,
      composerSignature: record.composerSignature,
      submitText: audit.sanitized_text
    });
  });
  overlay.querySelector(".sentinel-local")?.addEventListener("click", () => {
    if (!localModelAvailable) {
      return;
    }
    void runLocalModel(record);
  });

  const feedbackButton = overlay.querySelector(".sentinel-feedback-button");
  if (feedbackButton) {
    feedbackButton.addEventListener("click", async () => {
      const select = overlay.querySelector(".sentinel-feedback-select");
      const status = overlay.querySelector(".sentinel-feedback-status");
      const term = select?.value;
      if (!term) {
        return;
      }
      status.textContent = `Flagging ${term}...`;
      try {
        const payload = await sendFeedbackRequest(term);
        status.textContent = `${payload.term} raised to local ${Number(payload.local_weight).toFixed(2)} and exported ${Number(payload.noisy_weight).toFixed(2)}.`;
      } catch (feedbackError) {
        status.textContent = feedbackError instanceof Error ? feedbackError.message : "Feedback failed";
      }
    });
  }

  document.body.appendChild(overlay);
}

function renderLocalModelProgress(record) {
  removeOverlay();
  const overlay = document.createElement("div");
  overlay.id = OVERLAY_ID;
  overlay.innerHTML = `
    <div class="sentinel-panel">
      <div class="sentinel-header">
        <div>
          <p class="sentinel-eyebrow">SentinelSovereign</p>
          <h2>Running locally on this employee machine</h2>
        </div>
      </div>
      <p class="sentinel-note">
        The blocked prompt is being executed on the local model for ${escapeHtml(record.audit.client_id)}. Nothing is
        being sent to ChatGPT or Gemini.
      </p>
      <pre>${escapeHtml(record.originalText)}</pre>
    </div>
  `;
  document.body.appendChild(overlay);
}

function renderLocalModelSuccess(payload) {
  removeOverlay();
  const overlay = document.createElement("div");
  overlay.id = OVERLAY_ID;
  overlay.innerHTML = `
    <div class="sentinel-panel">
      <div class="sentinel-header">
        <div>
          <p class="sentinel-eyebrow">SentinelSovereign</p>
          <h2>Prompt kept local</h2>
        </div>
        <button class="sentinel-close">Close</button>
      </div>
      <p class="sentinel-note">
        ${escapeHtml(payload.statusMessage)} A local results tab was opened for ${escapeHtml(payload.profileLabel)}.
      </p>
    </div>
  `;
  overlay.querySelector(".sentinel-close")?.addEventListener("click", () => {
    removeOverlay();
  });
  document.body.appendChild(overlay);
}

function hideBlockedOverlay() {
  interceptionState.overlayMode = "hidden";
  removeOverlay();
}

function clearBlockedState(options = {}) {
  interceptionState.blockedRecord = null;
  interceptionState.overlayMode = null;
  if (!options.preserveApprovedSubmission) {
    interceptionState.approvedSubmission = null;
    interceptionState.status = "idle";
  }
  releaseSubmitButtonLock();
  removeOverlay();
}

function setState(nextStatus) {
  interceptionState.status = nextStatus;
  document.body.classList.toggle(BUSY_CLASS, nextStatus === "auditing" || nextStatus === "local_model_running");
  refreshSubmitButtonLock();
}

function matchesBlockedPrompt(composerSignature, promptHash) {
  return (
    interceptionState.blockedRecord &&
    interceptionState.blockedRecord.composerSignature === composerSignature &&
    interceptionState.blockedRecord.promptHash === promptHash
  );
}

function consumeApprovedSubmitIfMatch(composerSignature, promptHash) {
  if (
    interceptionState.status === "approved_for_single_submit" &&
    interceptionState.approvedSubmission &&
    interceptionState.approvedSubmission.composerSignature === composerSignature &&
    interceptionState.approvedSubmission.promptHash === promptHash
  ) {
    interceptionState.approvedSubmission = null;
    interceptionState.status = "idle";
    releaseSubmitButtonLock();
    return true;
  }
  return false;
}

function triggerApprovedSubmission(composer) {
  const submitButton = Array.from(document.querySelectorAll("button")).find((button) => looksLikeSubmitButton(button));
  if (submitButton) {
    submitButton.click();
    return;
  }

  composer.dispatchEvent(
    new KeyboardEvent("keydown", {
      key: "Enter",
      code: "Enter",
      bubbles: true
    })
  );
}

function refreshSubmitButtonLock() {
  const shouldLock =
    interceptionState.status === "auditing" ||
    interceptionState.status === "blocked" ||
    interceptionState.status === "local_model_running";
  const submitButtons = Array.from(document.querySelectorAll("button")).filter((button) => looksLikeSubmitButton(button));

  submitButtons.forEach((button) => {
    if (shouldLock) {
      if (!button.hasAttribute(LOCKED_BUTTON_ATTRIBUTE)) {
        button.setAttribute(ORIGINAL_DISABLED_ATTRIBUTE, button.disabled ? "true" : "false");
      }
      button.setAttribute(LOCKED_BUTTON_ATTRIBUTE, "true");
      button.disabled = true;
      button.setAttribute("aria-disabled", "true");
      button.title = "SentinelSovereign has locked sending until this prompt is resolved.";
      button.classList.add("sentinel-button-locked");
      return;
    }

    if (!button.hasAttribute(LOCKED_BUTTON_ATTRIBUTE)) {
      return;
    }
    const originallyDisabled = button.getAttribute(ORIGINAL_DISABLED_ATTRIBUTE) === "true";
    button.disabled = originallyDisabled;
    if (!originallyDisabled) {
      button.removeAttribute("aria-disabled");
    }
    button.removeAttribute(LOCKED_BUTTON_ATTRIBUTE);
    button.removeAttribute(ORIGINAL_DISABLED_ATTRIBUTE);
    button.removeAttribute("title");
    button.classList.remove("sentinel-button-locked");
  });
}

function releaseSubmitButtonLock() {
  refreshSubmitButtonLock();
}

function getActiveComposer() {
  const active = document.activeElement;
  if (active instanceof HTMLElement && isComposer(active)) {
    return active;
  }
  const composers = Array.from(document.querySelectorAll('textarea, div[contenteditable="true"][role="textbox"], div[contenteditable="true"]'));
  return composers.find((node) => isComposer(node));
}

function findComposerFromNode(node) {
  if (isComposer(node)) {
    return node;
  }
  return node.closest?.('textarea, div[contenteditable="true"][role="textbox"], div[contenteditable="true"]') || null;
}

function getComposerSignature(node) {
  if (!node.dataset.sentinelComposerId) {
    node.dataset.sentinelComposerId = `sentinel-composer-${Math.random().toString(36).slice(2, 10)}`;
  }
  return node.dataset.sentinelComposerId;
}

function getComposerBySignature(signature) {
  return document.querySelector(`[data-sentinel-composer-id="${CSS.escape(signature)}"]`);
}

function isComposer(node) {
  if (!(node instanceof HTMLElement)) {
    return false;
  }
  if (node instanceof HTMLTextAreaElement) {
    return true;
  }
  return node.getAttribute("contenteditable") === "true";
}

function looksLikeSubmitButton(button) {
  const label = [button.getAttribute("aria-label"), button.textContent, button.getAttribute("data-testid")]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return /send|submit|arrow up|run|ask|spark|message/.test(label);
}

function readComposerText(node) {
  if (node instanceof HTMLTextAreaElement || node instanceof HTMLInputElement) {
    return node.value;
  }
  return node.innerText || node.textContent || "";
}

function replaceComposerText(node, nextText) {
  if (node instanceof HTMLTextAreaElement || node instanceof HTMLInputElement) {
    node.focus();
    const setter =
      Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set ||
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
    if (setter) {
      setter.call(node, nextText);
    } else {
      node.value = nextText;
    }
    node.dispatchEvent(new Event("input", { bubbles: true }));
    return;
  }

  node.focus();
  node.textContent = nextText;
  node.dispatchEvent(new InputEvent("input", { bubbles: true, data: nextText, inputType: "insertText" }));
}

function clearComposerTextBySignature(signature) {
  const composer = getComposerBySignature(signature);
  if (composer) {
    replaceComposerText(composer, "");
  }
}

function blockBrowserEvent(event) {
  event.preventDefault();
  event.stopPropagation();
  event.stopImmediatePropagation();
}

function removeOverlay() {
  document.getElementById(OVERLAY_ID)?.remove();
}

function normalizeText(value) {
  return String(value || "").trim();
}

async function hashText(text) {
  const payload = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", payload);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function sendAuditRequest(payload) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type: "sentinel.audit", payload }, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      if (!response?.ok) {
        reject(new Error(response?.error || "Unknown audit failure"));
        return;
      }
      resolve(response.payload);
    });
  });
}

function sendFeedbackRequest(term) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type: "sentinel.feedback-term", payload: { term, source: "extension_manual_feedback" } }, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      if (!response?.ok) {
        reject(new Error(response?.error || "Unknown feedback failure"));
        return;
      }
      resolve(response.payload);
    });
  });
}

function sendLocalModelRequest(payload) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type: "sentinel.run-local-model", payload }, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      if (!response?.ok) {
        reject(new Error(response?.error || "Unknown local model failure"));
        return;
      }
      resolve(response.payload);
    });
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
