# 🚀 END-TO-END SA BANK UNDERWRITING AGENT BUILDER

## Dynamic, Generic, No-Hardcode Implementation for Structured Annuity (SA)

**GOAL:** Complete agent: Pre-screen → Docs → OCR/LLM → DSCR/DTI/ML + Credit → Policy → Underwriter Pane. Low-risk STP.

**NEW:** PDF Bank Stmt → Delinquency Check → ML Credit Score → Loan Decision.

---

## 🎯 EXECUTE IN THIS EXACT ORDER (Cursor Agent Commands)

### PHASE 1: PROJECT SCAFFOLD (5 mins)

@agent Create repo structure exactly:

```
sa-underwriting-agent/
├── app.py                          # Main LangGraph workflow
├── config/
│   ├── underwriting.yaml           # Rules/thresholds
│   ├── docs.yaml                   # SA mandatory docs
│   ├── prompts.yaml                # LLM prompts
│   ├── validation.yaml             # Delinq/ML config
│   └── ml.yaml                     # Model paths
├── nodes/                          # LangGraph nodes
│   ├── pre_screen.py
│   ├── doc_ingest.py
│   ├── extract_data.py
│   ├── risk_calc.py
│   ├── credit_check.py
│   ├── delinquency_ml.py           # NEW: PDF validation
│   ├── decision.py
│   └── policy_gen.py
├── ui/                             # Streamlit dashboard
│   └── dashboard.py
├── tests/
│   └── test_flows.py
├── requirements.txt
├── config.yaml                     # LangGraph config
├── docker-compose.yaml
├── .env.example
└── README.md
```

### PHASE 2: CONFIG FILES (GENERATE ALL - NO HARDCODING)

@agent Generate ALL config YAMLs.

**config/underwriting.yaml:**

```yaml
rules:
  age_min: 40
  age_max: 85
  min_premium: 50000  # ZAR
ratios:
  dscr_min: 1.25
  dti_max: 0.4
credit:
  score_min: 650
delinquency_keywords: ["overdue", "late", "failed", "nsf", "dishonored"]
```

**config/docs.yaml:**

```yaml
mandatory_sa:
  - id_document
  - proof_income
  - bank_statement_3m
  - life_expectancy_form
optional:
  - medical_history
```

**config/validation.yaml:** # NEW for PDF delinq/ML

```yaml
delinq_keywords: ["failed", "dishonored", "overdue", "late fee", "nsf"]
ml_features:
  - avg_monthly_balance
  - delinquency_count
  - repayment_consistency
  - cashflow_ratio
thresholds:
  credit_score_min: 650
  delinq_max: 0
  cashflow_min: 1.2
```

**config/prompts.yaml:**

```yaml
extract_income: |
  From bank statement, extract:
  1. Monthly avg income (credits)
  2. Monthly expenses (debits)
  3. Debt obligations
  Output JSON only.
```

### PHASE 3: CORE NODES (LangGraph - BUILD EACH)

@agent Build `nodes/` directory with Pydantic state.

**nodes/pre_screen.py**  
Prompt: "Basic eligibility: age, premium from config. Return eligible:bool"

**nodes/doc_ingest.py**  
Prompt: "Handle PDF upload (like ABC-Manufacturing-Pty-Ltd.pdf). Unstructured/PyMuPDF → Pandas DF (date,desc,debit,credit,balance). OCR tables."

**nodes/extract_data.py**  
Prompt: "LLM (GPT-4o-mini) + config prompts → Pydantic models: Income, Debts, Assets from DF/text."

**nodes/delinquency_ml.py** # NEW - KEY FOR PDF  
Prompt:

```
CRITICAL: PDF Bank Statement Validator

Scan DF desc for config delinq_keywords → delinq_count

Check "FAILED"/negative balances → is_delinq

ML Features: avg_balance, inflow/outflow ratio, repay % on-time

XGBoost credit_score (300-850) - train on synthetic if no model

Return: {'is_delinquent': bool, 'credit_score': float, 'risk_flags': list}
TEST: ABC-Manufacturing-Pty-Ltd.pdf → June "FAILED" → delinq=True, score drops
```

**nodes/risk_calc.py**  
Prompt: "DSCR = NOI/debt_service, DTI=debt/income from extracted data + config thresholds"

**nodes/credit_check.py**  
Prompt: "Mock TransUnion/Experian API (config endpoints). Combine with ML score."

**nodes/decision.py**  
Prompt:

```
Routing Logic:

delinq=True OR score<650 → UNDERWRITER REVIEW

DSCR<1.25 OR DTI>40% → REVIEW

ALL PASS → STRAIGHT-THROUGH BOOKING
```

**nodes/policy_gen.py**  
Prompt: "Generate SA policy PDF (ReportLab): Customer data, terms, premium schedule."

### PHASE 4: MAIN WORKFLOW

@agent Create `app.py`:

```python
from langgraph.graph import StateGraph, END
from pydantic import BaseModel
class AgentState(BaseModel):
    customer_data: dict
    documents: dict  
    risk_scores: dict
    decision: str
    policy: str = None

# Wire ALL nodes with conditional edges
workflow = StateGraph(AgentState)
workflow.add_node("pre_screen", pre_screen)
workflow.add_node("doc_ingest", doc_ingest)
# ... ALL nodes
workflow.add_conditional_edges("decision", route_decision) 
# Run: app.run()
```

### PHASE 5: UNDERWRITER UI (Single Pane)

@agent Create `ui/dashboard.py`:

Streamlit app:

- File uploader (PDF/docs)
- Run workflow → Live results table
- Low-risk: AUTO APPROVE + Policy download
- Review: Risk flags, ML score, Edit & Approve/Reject
- Charts: Cashflow trends, DSCR timeline

**Test:** Upload ABC-Manufacturing-Pty-Ltd.pdf → Show delinq flag

### PHASE 6: TESTING HARNESS

@agent `tests/test_flows.py`:

- pytest scenarios:
  - `test_low_risk_stp()` — All pass → booking
  - `test_delinq_reject()` — PDF June failed → review
  - `test_high_dti()` — DTI>40 → review

### PHASE 7: PRODUCTION READY

@agent Generate:

1. `requirements.txt` (langgraph, unstructured, streamlit, xgboost, pydantic, fastapi, reportlab)
2. `docker-compose.yaml` (FastAPI + Streamlit + Redis)
3. `.env.example` (OPENAI_API_KEY, credit_api_key=mock)
4. `deploy_azure.yaml` (your DevOps pref)
5. `README.md` with /run → /ui → /approve flow

---

## 🎪 CURSOR EXECUTION COMMANDS (Copy-Paste Each)

- @agent Follow END-TO-END.md Phase 1-2: Scaffold + configs
- @agent Phase 3: Build ALL nodes with PDF delinq/ML focus
- @agent Phase 4: app.py LangGraph workflow
- @agent Phase 5: Streamlit UI single pane
- @agent Phase 6-7: Tests + Production
- @test Upload ABC-Manufacturing-Pty-Ltd.pdf → expect delinq=True June, score<650 → REVIEW
- @deploy Dockerize + run locally

---

## ✅ SUCCESS CRITERIA

- PDF upload → OCR → Delinq flag + ML score 5s
- Low-risk → Policy PDF auto-download
- High-risk → Underwriter dashboard w/ edit
- 100% config-driven (edit YAML → instant change)
- Docker runs: `docker-compose up`

---

## NO HARDCODING RULE

**EVERY** threshold/prompt/endpoint/API from YAML/env. Cursor will enforce.

---

## EXECUTE NOW

Copy this file as END-TO-END.md → Cmd+K Composer → **"Implement entire agent per END-TO-END.md"**
