# SentinelSovereign Browser Extension

This extension is the real-site interception layer for SentinelSovereign.

## What it does

- intercepts outbound prompts on ChatGPT and Gemini before they leave the page
- sends them to the currently selected local profile
- blocks or rewrites the prompt based on the daemon decision
- lets the user submit contextual feedback for missed sensitive terms
- persists profile selection and health state across popup closes and browser restarts
- can route blocked prompts to a local Ollama model on the active employee machine

## Supported sites

- `chatgpt.com`
- `chat.openai.com`
- `gemini.google.com`

## Persistent profiles

The popup now stores these profiles in `chrome.storage.local`:

- `desktop-local` -> `http://127.0.0.1:8777`
- `user-a` -> `http://127.0.0.1:8101`
- `user-b` -> `http://127.0.0.1:8102`
- `user-c` -> `http://127.0.0.1:8103`

That means one browser session can simulate three separate federated clients just by switching the popup profile.

## What is persisted

- active profile id
- daemon URL per profile
- last successful health check per profile
- last audit summary per profile
- last feedback summary per profile

## Load locally

1. Open `chrome://extensions`
2. Enable developer mode
3. Click `Load unpacked`
4. Select the [extension](/Users/amanm/Documents/this better work/extension) folder
5. Open the popup
6. Pick a profile
7. Click `Test Connection`
8. Confirm the popup shows `Connected`

## Overlay behavior

If the local daemon requires review, the extension shows an in-page overlay with:

- original prompt
- sanitized prompt
- findings
- audit trace
- contextual candidate terms
- a local-model option when the active profile reports Ollama availability

The "Missed Sensitive Term?" action uses the same `/api/context/feedback` backend path that the corpus trainer uses.

The overlay now enforces a persistent lock:

- `Enter` and send buttons stay blocked while the prompt is unresolved
- `Cancel` only hides the review and does not unlock the same prompt
- the user must approve the redacted version, run the prompt locally, or edit the prompt enough to trigger a fresh audit

## Local model results

If the active profile reports Ollama as available, the overlay exposes `Run On Local Model Instead`.

That path:

- keeps the original blocked prompt local
- sends it to the active client's local Ollama daemon
- opens `local-result.html` inside the extension
- never forwards that blocked prompt to ChatGPT or Gemini

## Troubleshooting

If the popup shows `Disconnected`:

1. Confirm the local client for that profile is actually running
2. Re-run `curl <profile-url>/api/client/status`
3. Open `chrome://extensions`
4. Find SentinelSovereign
5. Click `Errors` if that link appears

The manifest now allows local profile routing through `http://127.0.0.1/*` and `http://localhost/*`, so the same extension build can talk to all local demo clients.
