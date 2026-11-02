# Requirements

Dependencies are split into tiers so bootstrap Phase A only installs what the PyQt6 menu needs. `requirements.txt` is an aggregate that pulls in the full runtime.

| File | Contents | Installed by |
|------|----------|--------------|
| `requirements-ui.txt` | PyQt6, requests, psutil, huggingface_hub | Phase A (Bringup step 1) |
| `requirements-full.txt` | The UI tier plus extractors, ingest, WebEngine, and the MCP tier | Phase B (Bringup step 2) |
| `requirements-mcp.txt` | fastmcp, authlib, starlette | Phase B, via the full tier |
| `requirements-ocr.txt` | pytesseract | Opt-in |
| `requirements-dev.txt` | pytest | Opt-in |
| `requirements-docs.txt` | mkdocs toolchain, openai | Opt-in, system Python 3.12 |
| `requirements.txt` | `-r requirements-full.txt` | Manual full install |

## UI tier

| Package | Version | Purpose |
|---------|---------|---------|
| PyQt6 | >=6.6,<6.12 | GUI framework (capped until PyQt6-WebEngine ships a matching 6.12+) |
| requests | >=2.31 | HTTP client |
| psutil | >=5.9 | System monitoring |
| huggingface_hub | >=0.23 | Model downloads |

## Full tier

| Package | Purpose |
|---------|---------|
| PyQt6-WebEngine | >=6.6,<6.12 | HTML rendering in Ask AI, Google Search, model cards, DB browser (plain-text fallback if missing; must match PyQt6 minor) |
| markdown | Markdown to HTML for model cards |
| PyMuPDF | PDF text extraction and previews |
| Pillow | Image handling |
| beautifulsoup4, lxml | HTML parsing and the `lxml` parser backend |
| python-docx, openpyxl, pandas | Word, Excel/CSV extraction |
| watchdog | Filesystem watching for continuous Wiki Scan |
| keyring | Credential storage |
| reportlab | PDF export from the model selector |
| google-auth | Application Default Credentials for Gemini |
| nvidia-ml-py | NVML GPU telemetry (`pynvml`) |
| fastmcp, authlib, starlette | MCP server (`scripts/mcp_spock_server.py`) |

GPU detection uses `nvidia-smi` and NVML; `torch` and `GPUtil` were removed.

## Opt-in tiers

### OCR

Text inside images is only extracted when both halves are installed:

```powershell
winget install UB-Mannheim.TesseractOCR
.venv\Scripts\python.exe -m pip install -r requirements-ocr.txt
```

The extractor looks for `C:\Program Files\Tesseract-OCR\tesseract.exe`; `TESSERACT_CMD` overrides the path. Without it, scans still succeed and log the reason once.

### Dev and docs

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest tests -q
```

The docs toolchain targets the system Python 3.12 used by `spock-onboarding-mkdocs.ps1`, not `.venv`.

## Install everything

```bat
.venv\Scripts\pip install -r requirements.txt
```
