# Codex Build Prompt: Sentinel-Style Federated Privacy Gateway

Use this prompt with another Codex-enabled programmer to recreate a system similar to SentinelSovereign.

---

You are building a production-style federated-learning privacy gateway for public LLM use. The system should simulate three users and demonstrate how a keyword can be marked sensitive on two users, then be recognized by the third user through federated learning even though that third user never marked it locally.

## Product Goal

Build a browser-extension-first privacy gateway for ChatGPT and Gemini with these behaviors:

- three simulated users: `user-a`, `user-b`, `user-c`
- each user has a local backend client
- one central federated aggregator combines keyword risk weights
- the extension popup lets the operator:
  - switch active user
  - add a sensitive keyword for the active user
  - remove a locally learned keyword with an `X`
  - see per-user local keyword weights
  - see simple local-model readiness
- the content script intercepts outbound prompts on ChatGPT/Gemini
- if a prompt includes risky content or a globally learned keyword, the extension blocks the public send path and shows a review overlay
- blocked prompts can optionally be handled on a local model on that user’s own machine

## Architecture

Implement these subsystems:

### 1. Local client daemon

Each user runs a local backend service.

Responsibilities:

- deterministic audit of outgoing prompts
- contextual keyword scoring using local and global weights
- local keyword feedback and local keyword removal
- sync to federated aggregator
- local-model execution path
- status endpoints for the extension popup

Suggested stack:

- Python
- FastAPI

Required client endpoints:

- `GET /health`
- `GET /api/client/status`
- `POST /api/browser/intercept`
- `POST /api/context/feedback`
- `DELETE /api/context/keywords/{term}`
- `GET /api/context/secrets`
- `GET /api/local-model/status`
- `POST /api/local-model/execute`

`/api/client/status` should return:

- client id
- daemon URL
- local keyword weights
- known global secrets
- local model readiness
- simple connection-ready metadata for the popup

### 2. Federated aggregator

Build one central service that receives keyword weights from all clients and performs federated averaging.

Responsibilities:

- receive local keyword risk weights
- average weights across expected clients
- promote keywords to global secrets when the threshold is crossed
- expose summary endpoints for debugging or demo visibility

Suggested endpoints:

- `GET /health`
- `POST /api/federated/submit`
- `GET /api/federated/global-secrets`
- `GET /api/federated/summary`

Default behavior:

- expected clients: `user-a`, `user-b`, `user-c`
- apply Gaussian noise before weights leave each client
- if the same keyword is marked sensitive on `user-a` and `user-b`, the averaged global weight should become high enough for `user-c` to recognize it as sensitive

### 3. Browser extension

Target:

- Chrome or Edge

Supported sites:

- `chatgpt.com`
- `chat.openai.com`
- `gemini.google.com`

The extension should have three parts:

#### Popup

The popup is the demo console, not a debugging dashboard.

It must support:

- active user switcher
- add sensitive keyword text box and button
- remove local keyword with `X`
- per-user local keyword weights
- simple local-model readiness
- minimal connection status

Do not clutter it with audit history, transparency logs, traces, or technical debugging details.

#### Service worker

The service worker should:

- persist profiles in storage
- route extension actions to the active user’s backend daemon
- support adding a keyword
- support removing a local keyword
- support running the local model
- keep cached profile status and local-model result data

Default profile map:

- `user-a` -> `http://127.0.0.1:8101`
- `user-b` -> `http://127.0.0.1:8102`
- `user-c` -> `http://127.0.0.1:8103`

#### Content script

The content script must be enforcement-first.

Requirements:

- intercept send button clicks and `Enter`
- audit the prompt before it leaves the page
- if blocked, keep the prompt locked until resolved
- `Cancel` should not allow the same unchanged prompt to be sent
- if the same blocked prompt is retried, show the overlay again immediately
- if the prompt is edited materially, trigger a fresh audit on the next attempt
- if approved, submit the redacted version exactly once
- if sent to the local model, never forward it to ChatGPT/Gemini

Overlay actions:

- `Approve Redacted Prompt`
- `Cancel`
- `Run On Local Model Instead`
- optional missed-keyword feedback control

### 4. Local model path

Use Ollama first.

Per-client configuration:

- enable flag
- base URL
- model name
- timeout

Default assumptions:

- Ollama on `http://127.0.0.1:11434`
- model like `llama3.2:3b`

Behavior:

- local-model execution receives the **original blocked prompt**
- it runs entirely on that user’s machine
- blocked content must never be forwarded to the public site
- successful local execution should open an extension-hosted results tab showing:
  - user/profile
  - reason the public send was blocked
  - original blocked prompt
  - note that it stayed local
  - local model response

## Data and Learning Model

Store these local artifacts per user:

- local keyword risks
- global secrets synced from aggregator
- recent keyword feedback history

Local removal behavior:

- clicking `X` removes the keyword only from that user’s local keyword store
- it does not send a negative vote
- it does not remove the keyword globally

Contextual learning demo flow:

1. operator selects `user-a` in the popup
2. operator adds a keyword like `ORION_TEST_7`
3. operator selects `user-b`
4. operator adds the same keyword
5. aggregator averages the two users’ local noised weights
6. operator selects `user-c`
7. `user-c` has no local keyword row for `ORION_TEST_7`
8. when `user-c` uses ChatGPT/Gemini with that keyword, the extension blocks it because the keyword was learned globally

## UI Requirements

Keep the demo UI clean and understandable:

- proper capitalization
- plain language
- no transparency or audit-history UI
- no technical jargon unless required
- keep the keyword weights visible because they explain the federated learning story

Suggested popup wording:

- `Active User`
- `Add Sensitive Keyword`
- `This Computer's Local Model`
- `User Keyword Weights`
- `No Local Keywords`

## Testing and Acceptance

The implementation is complete only if these pass:

### Keyword demo

- add a keyword on `user-a`
- confirm it appears only on `user-a`
- add the same keyword on `user-b`
- confirm it appears on `user-b`
- confirm `user-c` does not show it locally
- use ChatGPT/Gemini as `user-c` with that keyword
- confirm it is recognized and blocked through federated learning

### Local removal

- remove the keyword from `user-a` with `X`
- confirm it disappears only from `user-a`
- confirm it remains on `user-b`

### Interception

- blocked prompts cannot be resent unchanged by clicking send or pressing `Enter`
- cancel hides the overlay but does not unlock the same prompt
- editing the prompt triggers a new audit path

### Local model

- blocked prompt can be sent to Ollama on-device
- public site does not receive the blocked prompt
- extension opens a local results tab

## Output Expectation

Implement the full stack with:

- modular backend services
- extension popup, service worker, content script, and local results tab
- three-user local simulation
- federated aggregation
- local keyword add and remove controls
- Ollama fallback path
- simple run instructions for demo use

Do not stop at planning. Make the code changes, wire the endpoints, verify the flow, and leave the system runnable end to end.
