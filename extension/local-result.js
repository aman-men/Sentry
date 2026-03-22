const content = document.getElementById("result-content");
const executionId = new URLSearchParams(window.location.search).get("execution_id");

if (!executionId) {
  renderError("Missing local execution id.");
} else {
  void loadResult(executionId);
}

async function loadResult(id) {
  try {
    const result = await sendMessage("sentinel.get-local-model-result", { executionId: id });
    renderResult(result);
  } catch (error) {
    renderError(error instanceof Error ? error.message : "Could not load local result.");
  }
}

function renderResult(result) {
  content.innerHTML = `
    <article class="card">
      <h2>Execution Summary</h2>
      <p class="muted">${escapeHtml(result.status_message)}</p>
      <dl class="meta-grid">
        <div>
          <dt>Profile</dt>
          <dd>${escapeHtml(result.profileLabel || result.client_id)}</dd>
        </div>
        <div>
          <dt>Client</dt>
          <dd>${escapeHtml(result.client_id)}</dd>
        </div>
        <div>
          <dt>Model</dt>
          <dd>${escapeHtml(result.model_name)}</dd>
        </div>
        <div>
          <dt>Site</dt>
          <dd>${escapeHtml(result.site_name || "Local execution")}</dd>
        </div>
      </dl>
    </article>

    <div class="result-columns">
      <article class="card">
        <h2>Blocked Prompt Kept Local</h2>
        <p class="muted">This prompt never went to ChatGPT or Gemini.</p>
        <pre>${escapeHtml(result.original_text)}</pre>
      </article>

      <article class="card">
        <h2>Ollama Response</h2>
        <p class="muted">${escapeHtml(result.decision_reason)}</p>
        <pre>${escapeHtml(result.response_text)}</pre>
      </article>
    </div>
  `;
}

function renderError(message) {
  content.innerHTML = `
    <article class="card">
      <h2>Local result unavailable</h2>
      <p class="muted">${escapeHtml(message)}</p>
    </article>
  `;
}

function sendMessage(type, payload = {}) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type, payload }, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      if (!response?.ok) {
        reject(new Error(response?.error || "Unknown extension error"));
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
