# SA Bank — AI Underwriting Agent

A fully config-driven loan underwriting pipeline built with **LangGraph**, **LangChain (GPT-4o-mini)**, **Pandas**, and **Streamlit**.  
Upload a bank statement or financial statement → extract fields → compute ratios → get a credit decision — all in one browser UI.

```
Upload docs → OCR/LLM extract → DSCR · DTI · EBITDA → ML credit score → Decision → Policy PDF
```

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Clone the repo](#2-clone-the-repo)
3. [Create a virtual environment](#3-create-a-virtual-environment)
4. [Install dependencies](#4-install-dependencies)
5. [Configure API keys](#5-configure-api-keys)
6. [Train the ML model (first run only)](#6-train-the-ml-model-first-run-only)
7. [Launch the app](#7-launch-the-app)
8. [Using the UI](#8-using-the-ui)
9. [Project structure](#9-project-structure)
10. [Config reference](#10-config-reference)
11. [Run tests](#11-run-tests)
12. [Docker (optional)](#12-docker-optional)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Prerequisites

| Tool | Minimum version | Check |
|---|---|---|
| Python | **3.12+** | `python3 --version` |
| pip | latest | `pip --version` |
| Git | any | `git --version` |
| OpenAI API key | — | [platform.openai.com](https://platform.openai.com/api-keys) |

> **No other services required for local dev.** Credit bureau calls (TransUnion / Experian) are mocked by default.

---

## 2. Clone the repo

```bash
git clone https://github.com/deepeshcodex/AI-underwriting-agent.git
cd AI-underwriting-agent
```

---

## 3. Create a virtual environment

```bash
python3 -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

You should see `(.venv)` prefix in your terminal after activation.

---

## 4. Install dependencies

```bash
pip install -r requirements.txt
```

**Optional — heavier PDF OCR stack** (needed only if pure-Python `pypdf` can't extract text from a scanned/image PDF):

```bash
pip install -r requirements-ocr.txt
```

> `requirements-ocr.txt` installs `unstructured[pdf]` which requires `poppler` and `tesseract` on the system.  
> Install them with: `brew install poppler tesseract` (macOS) or `apt install poppler-utils tesseract-ocr` (Ubuntu).

---

## 5. Configure API keys

Copy the example file and fill in your OpenAI key:

```bash
cp .env.example env.local
```

Open `env.local` and set:

```env
# Required — your OpenAI API key
OPEN_API=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxx

# Keep as true for local dev (mocks TransUnion/Experian)
CREDIT_USE_MOCK=true

# Optional — LangSmith tracing (set to false to disable)
LANGCHAIN_TRACING_V2=false
LANGCHAIN_API_KEY=
```

> **Never commit `env.local`** — it is listed in `.gitignore` and will not be pushed to GitHub.

---

## 6. Train the ML model (first run only)

The app uses a lightweight NumPy-based credit scoring model stored in `artifacts/`.  
Generate it once before first launch:

```bash
python scripts/train_dummy_model.py
```

Expected output:
```
✅  Dummy risk model saved → artifacts/risk_model.joblib
✅  Dummy delinquency model saved → artifacts/delinq_model.joblib
```

> You only need to run this once. The files persist across app restarts.

---

## 7. Launch the app

```bash
streamlit run ui/dashboard.py
```

Streamlit will print:

```
  Local URL: http://localhost:8501
  Network URL: http://192.168.x.x:8501
```

Open **http://localhost:8501** in your browser.

---

## 8. Using the UI

The app is a **5-step wizard** accessible from the dashboard:

| Step | What you do |
|---|---|
| **1 — Upload** | Drag & drop one or more documents (PDF, PNG, JPG, TXT, CSV). Tag each file as *Bank Statement* or *Annual Financial Statement*. |
| **2 — Extract** | Click **Extract Fields**. The LLM reads each document, extracts financials, and merges them. Review the extracted data. |
| **3 — Apply** | Enter loan details: amount, tenure, interest rate. Click **Run Underwriting**. |
| **4 — Decision** | View the automated decision (Approved / Conditionally Approved / Manual Review / Declined) with DSCR, DTI, EBITDA, credit score gauges. |
| **5 — Schedule** | View the full amortization table and download the policy PDF. |

**Dashboard** shows all submitted applications with status badges and **View / Edit** buttons.

### Supported document types

| Document | What gets extracted |
|---|---|
| Bank Statement (PDF) | Revenue, OPEX, delinquency events, monthly transactions |
| Annual Financial Statement (PDF) | EBITDA, revenue, net profit margin, current ratio, debt-to-equity, years in business |
| Both together | Merged — financial statement ratios take priority; bank statement fills transaction gaps |

---

## 9. Project structure

```
AI-underwriting-agent/
├── app.py                        # LangGraph workflow entry point
├── env.local                     # Your secrets (not committed)
├── .env.example                  # Template for env.local
│
├── config/                       # All thresholds, prompts, rules — edit YAML, no code changes needed
│   ├── underwriting.yaml         # DSCR min, DTI max, credit score min, age limits
│   ├── rules.yaml                # Policy rule definitions
│   ├── prompts.yaml              # LLM extraction prompts
│   ├── validation.yaml           # Delinquency keywords, ML features
│   ├── docs.yaml                 # Mandatory document categories
│   ├── credit.yaml               # Bureau endpoints + mock toggle
│   └── ml.yaml                   # Model paths and fallback weights
│
├── nodes/                        # LangGraph pipeline nodes
│   ├── pre_screen.py             # Age + minimum premium eligibility
│   ├── doc_ingest.py             # PDF upload validation and OCR
│   ├── extract_data.py           # GPT-4o-mini LLM extraction
│   ├── risk_calc.py              # DSCR, DTI, EBITDA, ratios
│   ├── delinquency_ml.py         # Keyword scan + ML credit score
│   ├── credit_check.py           # Mock bureau + combined score
│   ├── decision.py               # STP / Conditional / Review routing
│   └── policy_gen.py             # ReportLab policy PDF generation
│
├── services/                     # Shared utilities
│   ├── document_parser.py        # Generic LLM document parser + merge logic
│   ├── application_store.py      # JSON persistence (data/applications.json)
│   ├── config_loader.py          # YAML loader
│   ├── ocr_service.py            # Unstructured / pypdf text extraction
│   ├── ml_risk.py                # ML model inference
│   ├── credit_client.py          # Bureau API client (mock)
│   └── settings.py               # Environment variable loader
│
├── models/
│   ├── graph_state.py            # Pydantic UnderwritingState
│   └── extraction.py             # Pydantic extraction models
│
├── ui/
│   ├── dashboard.py              # Main Streamlit app (run this)
│   ├── streamlit_app.py          # Legacy entry point
│   └── pages/
│       └── policy_rules.py       # Policy rules viewer page
│
├── scripts/
│   └── train_dummy_model.py      # Generates artifacts/*.joblib
│
├── tests/
│   ├── test_flows.py             # End-to-end pipeline scenarios
│   └── test_risk_scenarios.py    # DSCR / DTI edge cases
│
├── artifacts/                    # ML model files (generated, not committed)
├── data/                         # Application store JSON (not committed)
├── requirements.txt
├── requirements-ocr.txt
├── Dockerfile
├── docker-compose.yaml
└── deploy_azure.yaml
```

---

## 10. Config reference

All behaviour is controlled by YAML files — **no code changes needed** to adjust thresholds.

### `config/underwriting.yaml` — Core policy thresholds

```yaml
ratios:
  dscr_min: 1.25        # Debt Service Coverage Ratio minimum
  dti_max: 0.43         # Debt-to-Income maximum
credit:
  score_min: 650        # Minimum credit score for auto-approval
```

### `config/prompts.yaml` — LLM extraction prompts

Edit the `document_parser_user` key to change what fields the LLM extracts from uploaded documents.

### `config/credit.yaml` — Bureau mock toggle

```yaml
use_mock: true          # Set false to hit real TransUnion/Experian endpoints
```

---

## 11. Run tests

```bash
pytest -q tests/
```

Scenarios covered:

| Test | What it checks |
|---|---|
| `test_low_risk_stp` | All ratios pass → Straight-Through approval |
| `test_delinq_reject` | Delinquency flag → Manual Review |
| `test_high_dti` | DTI > 43% → Review |
| `test_pre_screen_decline` | Age or premium out of range → Declined |

---

## 12. Docker (optional)

No Python installation required — Docker handles everything.

```bash
# Build and start
docker-compose up --build

# App is available at http://localhost:8501
```

Make sure to set `OPEN_API` in `env.local` before running Docker — the compose file mounts it automatically.

---

## 13. Troubleshooting

### `ModuleNotFoundError: No module named 'langgraph'`
Your virtual environment is not activated.
```bash
source .venv/bin/activate   # macOS/Linux
```

### `AuthenticationError: No API key provided`
`env.local` is missing or the key is empty.
```bash
cat env.local               # check the file exists and has OPEN_API=sk-...
```

### `FileNotFoundError: artifacts/risk_model.joblib`
ML model hasn't been generated yet.
```bash
python scripts/train_dummy_model.py
```

### DSCR / EBITDA shows `—` after upload
The document may be a scanned image PDF that `pypdf` cannot read.  
Install the full OCR stack:
```bash
brew install poppler tesseract   # macOS
pip install -r requirements-ocr.txt
```

### Streamlit shows a blank page or import error
Check the terminal for a Python traceback. Most common fix:
```bash
pip install -r requirements.txt --upgrade
```

---

## No-hardcoding rule

Every threshold, prompt, endpoint, and API key is sourced from `config/*.yaml` or `env.local`.  
Edit a YAML → instant behaviour change, zero code redeploy.
