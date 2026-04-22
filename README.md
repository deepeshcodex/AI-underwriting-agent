# SA Bank — Structured Annuity Underwriting Agent

Generic, dynamic, no-hardcode underwriting pipeline built with **LangGraph**, **LangChain**, **Pandas**, and **Streamlit**.

```
PDF upload → OCR → Delinquency ML → DSCR/DTI → Credit → Decision → Policy PDF
```

---

## Quick start

```bash
# 1. Clone / open workspace
cd "loan underwriting AI"

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) Full OCR support
pip install -r requirements-ocr.txt

# 5. Set your API key
cp .env.example env.local
# edit env.local → set OPENAI_API_KEY=sk-...

# 6. Train the demo ML model
python scripts/train_dummy_model.py

# 7. Launch dashboard
python -m streamlit run ui/dashboard.py
# → open http://localhost:8501
```

---

## Pipeline (per END-TO-END.md)

| Step | Node | What it does |
|------|------|--------------|
| Pre-screen | `nodes/pre_screen.py` | Age (40-85) + minimum premium (R50 000) from `config/underwriting.yaml` |
| Doc ingest | `nodes/doc_ingest.py` | Upload validation, OCR via Unstructured |
| LLM extract | `nodes/extract_data.py` | GPT-4o-mini + config prompts → Pydantic models |
| Delinquency ML | `nodes/delinquency_ml.py` | Parses bank statement DF, detects keywords, NumPy credit score (300-850) |
| Risk ratios | `nodes/risk_calc.py` | DSCR = NOI / debt_service, DTI = debt / income |
| Credit check | `nodes/credit_check.py` | Mock TransUnion / Experian + ML score → combined score |
| Decision | `nodes/decision.py` | STP or MANUAL_REVIEW based on all checks |
| Policy gen | `nodes/policy_gen.py` | ReportLab PDF: applicant, terms, premium schedule |

Routing: delinq OR score < 650 OR DSCR fail OR DTI fail → **MANUAL_REVIEW**, else → **STP**.

---

## Config files (edit YAML — no code changes needed)

| File | Controls |
|------|----------|
| `config/underwriting.yaml` | Age, premium, DSCR/DTI min, credit score min, delinquency keywords |
| `config/validation.yaml` | PDF column aliases, ML features, heuristic weights |
| `config/prompts.yaml` | All LLM prompts including `extract_income` |
| `config/docs.yaml` | Mandatory SA document categories |
| `config/credit.yaml` | Bureau endpoints, mock toggle |
| `config/ml.yaml` | Risk model path, fallback heuristic weights |

---

## UI flow

```
/ui  →  upload PDF  →  Run pipeline  →  see decision
                                           ├── STP → Auto-approve + download policy PDF
                                           └── MANUAL_REVIEW → Risk flags + Approve / Reject buttons
```

---

## Run tests

```bash
pytest -q tests/
```

Scenarios covered: `test_low_risk_stp`, `test_delinq_reject`, `test_high_dti`, `test_pre_screen_decline`, delinquency unit tests.

---

## Docker

```bash
# Build and start UI + Redis
docker-compose up --build

# Also start API (FastAPI) service
docker-compose --profile api up --build
```

Services:
- **Streamlit UI**: http://localhost:8501
- **FastAPI** (profile `api`): http://localhost:8000
- **Redis**: localhost:6379

---

## Azure deployment

See `deploy_azure.yaml` (Azure Pipelines). Requires:
- Azure Container Registry (`saunderwriting.azurecr.io`)
- Azure service connection `saAzureConnection`
- Secrets `openai-api-key` in Container Apps environment

---

## NO HARDCODING RULE

Every threshold, prompt, endpoint, and API key comes from `config/*.yaml` or `env.local` / `.env`.  
Edit a YAML → instant behaviour change, zero code redeploy.
