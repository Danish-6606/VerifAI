# VerifAI · Smart Legal Auditor

> **Privacy-first AI contract analysis — everything runs locally on your machine.**

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Flet](https://img.shields.io/badge/Flet-0.24-blueviolet)
![Ollama](https://img.shields.io/badge/Ollama-local%20LLM-green)
![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)

---

## What is VerifAI?

VerifAI is a cross-platform desktop application that uses a **locally-running LLM** (via Ollama) to audit legal contracts. No data ever leaves your machine.

**What it detects:**
- Hidden liability & indemnification clauses
- One-sided termination conditions
- Ambiguous or missing standard protections
- High-risk keywords (non-compete, arbitration, unlimited liability, etc.)
- Overall risk score: LOW / MEDIUM / HIGH / CRITICAL

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | [python.org](https://python.org) |
| Ollama | latest | [ollama.com](https://ollama.com) |

---
[VerifAi Final documentation.pdf](https://github.com/user-attachments/files/28755078/VerifAi.Final.documentation.pdf)

---
## Quick Start

### 1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/verifai.git
cd verifai
```

### 2. Create & activate a virtual environment
```bash
# macOS / Linux
python3.11 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### 3. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 4. Pull the Ollama model
```bash
# Make sure Ollama is running first
ollama serve          # (in a separate terminal, or as a background service)

ollama pull llama3.2:3b
```
> You can swap the model. Edit `MODEL = "llama3.2:3b"` in `engine.py` to use
> `mistral`, `gemma3`, `llama3`, etc.

### 5. Run VerifAI
```bash
python main.py
```

---

## Project Structure

```
verifai/
├── main.py          # Flet UI – all interface code
├── engine.py        # PDF extraction + Ollama audit logic
├── requirements.txt # Python dependencies
├── README.md
└── assets/          # (optional) icons, splash screens
    └── icon.png
```

---

## Packaging as a Standalone App

VerifAI uses `flet pack` to create a single `.app` (macOS) or `.exe` (Windows)
that users can run without installing Python.

### macOS
```bash
# Install flet CLI packaging tools
pip install flet[cli]

# Package (creates dist/main.app)
flet pack main.py \
  --name "VerifAI" \
  --product-name "VerifAI Smart Legal Auditor" \
  --icon assets/icon.png

# The .app will appear in dist/
open dist/
```

### Windows
```powershell
pip install flet[cli]

flet pack main.py `
  --name "VerifAI" `
  --product-name "VerifAI Smart Legal Auditor" `
  --icon assets/icon.ico

# The .exe will appear in dist\
```

> **Note:** Ollama must still be installed separately on the end-user's machine.
> The packaged app bundles Python + your code, but not Ollama itself.

---

## Changing the LLM Model

Open `engine.py` and edit line 14:
```python
MODEL = "llama3.2:3b"   # ← change this
```

Recommended models (pull with `ollama pull <name>`):
| Model | Size | Speed | Quality |
|-------|------|-------|---------|
| `llama3.2:3b` | 2 GB | Fast | Good |
| `mistral` | 4 GB | Medium | Very good |
| `llama3` | 4.7 GB | Medium | Excellent |
| `gemma3` | 5 GB | Medium | Excellent |

---

## FilePicker Fix (macOS M1)

The standard Flet `FilePicker` has a known bug on macOS Apple Silicon that
renders it as a red "Unknown control" error. VerifAI fixes this by using
**Python's built-in `tkinter.filedialog`** instead — it's native, fast, and
works perfectly on M1/M2/M3 Macs, Intel Macs, and Windows.

No action needed on your part — the fix is already in `main.py`.

---

## Privacy & Security

- ✅ 100% local inference — no API calls to OpenAI / Anthropic / Google
- ✅ No telemetry, no analytics
- ✅ PDFs are read from disk and never uploaded anywhere
- ✅ Ollama runs as a local server (127.0.0.1:11434)

---

## License

MIT — free for personal and commercial use.
