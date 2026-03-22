# Chrome Extension Frontend

## What It Does

This Manifest V3 extension runs on:

- `https://chatgpt.com/*`
- `https://gemini.google.com/*`

It intercepts prompt send attempts, calls the local backend at `http://127.0.0.1:8000/process_prompt`, and enforces the returned route:

- `chatgpt`: allow the site to submit normally
- `local`: prevent submission and open a dedicated local-only modal with the response
- `block`: prevent submission and show a warning

## Start The Local Backend

Start the one-command gateway before testing the extension:

```powershell
cd c:\Users\rprat\OneDrive\Documents\Hoohacks\sensitive-info-detector
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m uvicorn gateway.service:app --host 127.0.0.1 --port 8000 --reload
```

If you want real local-model responses through Ollama, start Ollama first:

```powershell
ollama serve
```

## Load Unpacked In Chrome

1. Open `chrome://extensions`
2. Enable `Developer mode`
3. Click `Load unpacked`
4. Select the `extension/` folder from this repo

## Expected Local Backend Contract

`POST /process_prompt`

```json
{
  "text": "user prompt",
  "platform": "chatgpt"
}
```

Example response:

```json
{
  "route": "local",
  "risk_level": "high",
  "label": "confidential",
  "confidence": 0.94,
  "categories": ["project_codename"],
  "requires_review": false,
  "reason": "Prompt classified as high risk, must remain on device.",
  "local_response": "This prompt was handled locally."
}
```

## Safe Failure Behavior

If the localhost backend is unavailable, times out, or returns malformed data, the extension blocks submission and shows a warning. This is intentional so prompts do not leave the page without local screening.

If a prompt is routed local and Ollama is unavailable, the local modal explicitly shows that fallback-to-mock was used.

## How Site Interception Works

- Content scripts run on ChatGPT and Gemini
- A `MutationObserver` waits for compose boxes and send buttons
- The extension intercepts actual send attempts only
- It avoids keystroke-by-keystroke backend calls
- Low-risk prompts are re-submitted through the site's normal UI flow after approval

## Known Limitations

- ChatGPT and Gemini DOM structures can change at any time
- Selectors are defensive, but browser-extension interception on third-party apps is inherently fragile
- The floating panel is overlay-based and intentionally avoids deep site rewrites
