# sensitive-info-detector

## Fastest Way To Run It

For normal use, you only need:

1. train the detector once
2. run the gateway on `127.0.0.1:8000`
3. load the Chrome extension

You do **not** need to run the detector, router, and local-response services separately.

## First-Time Setup

Open one PowerShell terminal and run:

```powershell
cd c:\Users\rprat\OneDrive\Documents\Hoohacks\sensitive-info-detector
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\.venv\Scripts\python.exe detector\train.py
```

That creates:

- `detector/artifacts/vectorizer.pkl`
- `detector/artifacts/risk_model.pkl`
- `detector/artifacts/label_model.pkl`

## Normal Startup

After the detector has been trained once, run:

```powershell
cd c:\Users\rprat\OneDrive\Documents\Hoohacks\sensitive-info-detector
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m uvicorn gateway.service:app --host 127.0.0.1 --port 8000 --reload
```

That starts the single backend the extension uses.

By default, the Local Response Agent now uses Ollama.

## Mock Startup

If you want to force the Local Response Agent to use the mock responder instead of Ollama:

```powershell
cd c:\Users\rprat\OneDrive\Documents\Hoohacks\sensitive-info-detector
.\.venv\Scripts\Activate.ps1
$env:LOCAL_RESPONSE_BACKEND="mock"
.\.venv\Scripts\python.exe -m uvicorn gateway.service:app --host 127.0.0.1 --port 8000 --reload
```

## Ollama Details

Default local-model settings:

```powershell
$env:OLLAMA_MODEL="llama3"
```

Start Ollama first if it is not already running:

```powershell
ollama serve
```

Ollama is expected at `http://localhost:11434`.

If Ollama is not running or returns an error, the Local Response Agent falls back to mock-local behavior.

## How To Verify Ollama Is Actually Active

Check Ollama directly:

```powershell
Invoke-RestMethod -Method Get -Uri http://localhost:11434/api/tags
```

When a prompt is routed locally:

- if Ollama is active, the local modal shows backend `ollama`
- if Ollama fails, the modal shows a warning that fallback-to-mock was used
- if you still see mock mode, Ollama was unreachable or returned an invalid response

## Load The Chrome Extension

1. Open `chrome://extensions`
2. Turn on `Developer mode`
3. Click `Load unpacked`
4. Select:

```text
c:\Users\rprat\OneDrive\Documents\Hoohacks\sensitive-info-detector\extension
```

The extension will call:

- `POST http://127.0.0.1:8000/process_prompt`

## Quick Verification

Check that the backend is running:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/health
```

Test a high-risk prompt:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/process_prompt -ContentType 'application/json' -Body '{"text":"Review payroll report for employee E48291 tied to Project Falcon.","platform":"chatgpt"}'
```

Test a blocked prompt:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/process_prompt -ContentType 'application/json' -Body '{"text":"Please review this config with API key sk-live-ALPHA7demo9TOKEN.","platform":"chatgpt"}'
```

## What To Expect

- `route = "chatgpt"`: the prompt is allowed through normally
- `route = "local"`: the prompt is kept local and a dedicated local modal opens
- `route = "block"`: the prompt is blocked from leaving the page

## What The Gateway Does

The gateway combines the pipeline into one local backend:

1. `detector.infer.scan_text(text)`
2. `policy.router.route_from_scan(scan_result)`
3. if route is `local`, `local_response.agent.respond_local(text, router_result)`

## Run Tests

Run everything:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Run gateway-only tests:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_gateway -v
```

## Optional: Federated Learning

Federated learning is separate from normal runtime:

```powershell
.\.venv\Scripts\python.exe federated\run_federated.py
```

## Optional: Debug Mode

These services still exist for debugging only:

- `detector.service:app` on `8001`
- `policy.service:app` on `8002`
- `local_response.service:app` on `8003`
