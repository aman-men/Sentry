const connectionBadge = document.getElementById("connection-badge");
const connectionDetail = document.getElementById("connection-detail");
const activeProfileSelect = document.getElementById("active-profile");
const localModelStatus = document.getElementById("local-model-status");
const profileList = document.getElementById("profile-list");
const sensitiveTerm = document.getElementById("sensitive-term");
const feedbackStatus = document.getElementById("feedback-status");

activeProfileSelect?.addEventListener("change", async () => {
  await sendMessage("sentinel.set-active-profile", { profileId: activeProfileSelect.value });
  await refresh();
});

document.getElementById("mark-sensitive")?.addEventListener("click", async () => {
  const term = sensitiveTerm.value.trim();
  if (!term) {
    feedbackStatus.textContent = "Enter a keyword first.";
    return;
  }

  feedbackStatus.textContent = `Adding ${term} for the active user...`;
  try {
    const payload = await sendMessage("sentinel.feedback-term", { term, source: "popup_demo_control" });
    feedbackStatus.textContent = `${capitalizeTerm(payload.term)} added for ${payload.client_id}. Weight ${Number(payload.local_weight).toFixed(2)}.`;
    sensitiveTerm.value = "";
    await refresh();
  } catch (error) {
    feedbackStatus.textContent = error instanceof Error ? error.message : "Could not add the keyword.";
  }
});

void refresh();
setInterval(() => {
  void refresh();
}, 15000);

async function refresh() {
  setPendingState();
  try {
    const payload = await sendMessage("sentinel.status");
    renderStatus(payload);
  } catch (error) {
    renderDisconnected(error instanceof Error ? error.message : "Unknown extension error");
  }
}

function renderStatus(payload) {
  const profiles = payload.profiles || [];
  renderProfileOptions(profiles, payload.activeProfileId);
  renderProfileList(profiles, payload.activeProfileId);

  const active = payload.activeProfile;
  if (active?.connectionStatus === "connected" && active.clientStatus) {
    connectionBadge.textContent = "Connected";
    connectionBadge.className = "badge badge-connected";
    connectionDetail.textContent = `${active.label} is ready on this computer.`;
    localModelStatus.textContent = active.clientStatus.local_model_status?.available
      ? `${active.clientStatus.local_model_status.model_name} Ready`
      : "Unavailable";
    return;
  }

  renderDisconnected(active?.lastConnectionError || "This user is not reachable.");
}

function renderDisconnected(message) {
  connectionBadge.textContent = "Disconnected";
  connectionBadge.className = "badge badge-disconnected";
  connectionDetail.textContent = message;
  localModelStatus.textContent = "Unavailable";
}

function renderProfileOptions(items, activeProfileId) {
  activeProfileSelect.innerHTML = "";
  items.forEach((profile) => {
    const option = document.createElement("option");
    option.value = profile.id;
    option.textContent = profile.label;
    option.selected = profile.id === activeProfileId;
    activeProfileSelect.appendChild(option);
  });
}

function renderProfileList(items, activeProfileId) {
  profileList.innerHTML = "";

  items.forEach((profile) => {
    const localWeights = profile.clientStatus?.local_contextual_weights || {};
    const entries = Object.entries(localWeights).sort((left, right) => right[1] - left[1]);
    const card = document.createElement("article");
    card.className = `profile-card${profile.id === activeProfileId ? " active" : ""}`;

    const header = document.createElement("div");
    header.className = "profile-header";
    header.innerHTML = `
      <strong>${escapeHtml(profile.label)}</strong>
      <span class="profile-meta">${escapeHtml(profile.connectionStatus || "Unknown")}</span>
    `;
    card.appendChild(header);

    const meta = document.createElement("div");
    meta.className = "profile-meta";
    meta.textContent = entries.length ? "Learned on this user" : "No local keywords yet";
    card.appendChild(meta);

    if (!entries.length) {
      const empty = document.createElement("div");
      empty.className = "empty-keywords";
      empty.textContent = "No local keywords";
      card.appendChild(empty);
      profileList.appendChild(card);
      return;
    }

    const weights = document.createElement("div");
    weights.className = "profile-weights";

    entries.forEach(([term, weight]) => {
      const row = document.createElement("div");
      row.className = "keyword-row";
      row.innerHTML = `
        <div class="keyword-info">
          <strong>${escapeHtml(capitalizeTerm(term))}</strong>
          <span class="keyword-weight">Weight ${Number(weight).toFixed(2)}</span>
        </div>
        <button class="remove-button" type="button" data-profile-id="${escapeHtml(profile.id)}" data-term="${escapeHtml(term)}">X</button>
      `;
      const removeButton = row.querySelector(".remove-button");
      removeButton?.addEventListener("click", async () => {
        await removeKeyword(profile.id, term);
      });
      weights.appendChild(row);
    });

    card.appendChild(weights);
    profileList.appendChild(card);
  });
}

async function removeKeyword(profileId, term) {
  feedbackStatus.textContent = `Removing ${term} from ${profileId}...`;
  try {
    await sendMessage("sentinel.remove-keyword", { profileId, term });
    feedbackStatus.textContent = `${capitalizeTerm(term)} removed from ${profileId}.`;
    await refresh();
  } catch (error) {
    feedbackStatus.textContent = error instanceof Error ? error.message : "Could not remove the keyword.";
  }
}

function setPendingState() {
  connectionBadge.textContent = "Checking";
  connectionBadge.className = "badge badge-pending";
  connectionDetail.textContent = "Checking connection...";
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

function capitalizeTerm(value) {
  const text = String(value || "");
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
