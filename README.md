# Automated Risk Intelligence System

A full-stack banking risk platform that replaces ad-hoc Excel risk packs with automated data ingestion, algorithmic risk scoring, AML/Fraud anomaly detection, AI-powered adverse media monitoring, portfolio analytics, and Basel-style model stress testing — all surfaced through a real-time React dashboard.

Built as a portfolio piece to demonstrate production-grade engineering patterns aligned with the standards of regulated financial institutions. All data is synthetic and generated for demonstration only. Base reporting currency is Omani Rial (**OMR**).

---

## Dashboard Gallery

> Live screenshots captured from the running application (synthetic data).

### Executive Dashboard
Portfolio KPIs, risk-tier distribution, and the live AI adverse-media feed at a glance.

<img width="1916" height="915" alt="image" src="https://github.com/user-attachments/assets/5eb450fa-684e-4bbb-9a4e-5e174ac6acad" />
<img width="1639" height="809" alt="image" src="https://github.com/user-attachments/assets/fa716e32-5912-4529-8082-c32d4e9e1adf" />


### Portfolio Analytics
Sector and country concentration, loan-book aging, and Expected Loss (PD × LGD × EAD) with score-trend history.
<img width="1639" height="826" alt="image" src="https://github.com/user-attachments/assets/36f1da89-b2af-4831-94e7-aedff95392de" />
<img width="1651" height="905" alt="image" src="https://github.com/user-attachments/assets/21b3bf45-2768-4f53-a6d8-d8dd7a1d028e" />



### Model Stress Testing
Re-scores the entire book through the production scoring engine under a macro shock. Shown running the *2008-Style Credit Crisis* preset — Expected Loss before/after, tier-migration table, and EL waterfall.

<img width="1646" height="829" alt="image" src="https://github.com/user-attachments/assets/5bb81225-5918-44c4-bc8f-43815088aa9a" />

### Client Explorer & Client 360°
Searchable client directory with a full dossier drawer: score breakdown, exposures, transactions, and open flags.

<img width="1651" height="817" alt="image" src="https://github.com/user-attachments/assets/a7ad5f52-3ba7-46d6-8358-ec0f83cf914d" />
<img width="568" height="887" alt="image" src="https://github.com/user-attachments/assets/ed13b636-1858-463f-ba6e-33f96554753d" />


### Live Transactions
Paginated transaction feed with client attribution and a rolling-window statistics strip.
<img width="1647" height="817" alt="image" src="https://github.com/user-attachments/assets/fd0c4dcd-6687-4d6c-b699-ccbfc715d7e5" />

### Fraud & AML Alerts
The anomaly queue produced by the 7-rule detection engine, with severity and investigator workflow.

<img width="1643" height="825" alt="image" src="https://github.com/user-attachments/assets/20982386-73b5-4c84-a36b-099d29cc4769" />


### Risk Governance Settings
Live tier-boundary tuning with a migration preview showing how many clients move tier before you commit.

<img width="1655" height="822" alt="image" src="https://github.com/user-attachments/assets/00c03427-dae5-4c19-b9f5-437f96e1cc50" />


---

## Executive Summary

Modern credit risk and compliance officers face a fundamental tension: regulatory pressure demands comprehensive client due-diligence at scale, yet many mid-sized institutions still rely on manually maintained spreadsheets for risk monitoring. This system eliminates that bottleneck.

**What it delivers:**

| Capability | Business Value |
|---|---|
| Algorithmic risk-scoring engine | Consistent, auditable, regulatory-aligned scores — removes human subjectivity |
| Real-time AML/fraud detection | 7 rules covering FATF, BSA/FinCEN, and FFIEC typologies — flags in milliseconds, not days |
| Model stress testing | Re-scores the whole book under macro shocks through the *same* production engine |
| Portfolio analytics | Concentration, aging, and Expected Loss (PD × LGD × EAD) surfaced live |
| n8n + AI adverse media pipeline | Automated external intelligence feeds — no manual news monitoring |
| Live React dashboard | Compliance officer self-service — reduces analyst queue load |
| Full REST API | Integrable into core banking, CRM, or RegTech stacks with zero rework |

**Technology stack:** Python / FastAPI / PostgreSQL / React — a widely adopted stack for modern digital banking and RegTech platforms.

---

## Architecture

```mermaid
graph TD
    U[Browser / Compliance Officer]

    subgraph "Vercel Edge"
        FE[React 18 SPA<br/>Vite + Tailwind + Recharts]
    end

    subgraph "Vercel Serverless Functions"
        API[FastAPI · Python 3.12]
        SCORE[Risk Scoring Engine]
        ANOM[Anomaly Detection Engine]
        STRESS[Stress-Test Runner]
    end

    subgraph "Neon PostgreSQL"
        DB[(PostgreSQL 15<br/>Serverless)]
    end

    subgraph "n8n Workflow Engine<br/>DigitalOcean Droplet"
        WF[Adverse Media Workflow]
        OAI[OpenAI GPT-4o-mini<br/>Risk Summaries]
        SRCH[Perplexity / Tavily<br/>News Search]
    end

    U -->|HTTPS| FE
    FE -->|REST API calls| API
    API --> SCORE
    API --> ANOM
    API --> STRESS
    STRESS -->|re-scores book| SCORE
    API -->|SQLAlchemy| DB
    SCORE -->|SELECT / bulk INSERT| DB
    FE -->|POST /webhook| WF
    WF --> SRCH
    WF --> OAI
    WF -->|INSERT ai_alerts| DB
```

**Data flow:**
1. The dashboard calls FastAPI endpoints for risk scores, client data, transactions, analytics, and anomaly flags.
2. **Stress tests** re-score the entire book through the production scoring engine under a chosen macro shock, then diff the result against baseline.
3. When the user runs the pipeline, a webhook fires to the n8n instance; GPT-4o-mini generates a concise adverse-media summary that is persisted directly to the database.
4. The dashboard auto-refreshes and surfaces new alerts within seconds.

---

## Project Structure

```
risk_intelligence_system/
├── app/
│   ├── main.py                   # FastAPI app factory · CORS · lifespan · router registration
│   ├── config.py                 # Pydantic Settings — all thresholds via .env
│   ├── database.py               # SQLAlchemy engine, dialect handling (SQLite ↔ Postgres)
│   ├── schemas.py                # Pydantic v2 DTOs (API response contracts)
│   ├── models/                   # Client · Transaction · Loan · RiskScore · AnomalyFlag · AIAlert
│   ├── engines/
│   │   ├── risk_scoring.py       # Composite scoring formula (Basel III IRB / IFRS 9)
│   │   └── anomaly_detection.py  # 7-rule AML/Fraud detection engine
│   ├── pipeline/
│   │   └── ingestion.py          # Synthetic data ingestion pipeline
│   └── routes/
│       ├── pipeline.py           # POST /pipeline/*     trigger endpoints
│       ├── reports.py            # GET  /reports/*      reporting API
│       ├── anomalies.py          # GET/PATCH /anomalies/*  flag management
│       ├── ai_alerts.py          # GET/PATCH /ai-alerts/*  adverse media feed
│       ├── transactions.py       # GET  /transactions/*   live feed + stats
│       ├── stress_tests.py       # GET/POST /stress-tests/* macro-shock re-scoring
│       ├── settings.py           # GET/PATCH /settings/*   tier-boundary governance
│       ├── analytics.py          # GET  /analytics/*      concentration · aging · EL
│       └── clients.py            # GET  /clients/*        directory + Client 360°
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── Sidebar.jsx              # Primary navigation
│       │   ├── KPICards.jsx             # Summary metric cards
│       │   ├── RiskDistributionChart.jsx# Tier distribution
│       │   ├── ClientTable.jsx          # Sortable / filterable client grid
│       │   ├── ClientExplorerView.jsx   # Directory + Client 360° drawer
│       │   ├── LiveTransactionsView.jsx # Paginated feed + stats strip
│       │   ├── FraudAlertsView.jsx      # AML/Fraud alert queue
│       │   ├── PortfolioAnalyticsView.jsx# Concentration · aging · Expected Loss
│       │   ├── StressTestView.jsx       # Macro-shock scenario runner
│       │   ├── SettingsView.jsx         # Tier-threshold governance
│       │   └── LiveAIRiskFeed.jsx       # Adverse media news feed
│       ├── utils/risk.js                # Shared tier colours / formatting
│       └── App.jsx
├── docs/screenshots/             # Gallery images (this README)
├── scripts/capture-screenshots.mjs  # Playwright gallery capture
├── seed_db.py                    # One-command demo data seeder (60 clients)
├── requirements.txt
├── vercel.json
└── .env.example
```

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| API Framework | FastAPI | Async, Pydantic v2, auto OpenAPI — modern fintech standard |
| ORM | SQLAlchemy 2.0 | Type-safe queries; dialect-swap for local SQLite → prod Postgres |
| Database | PostgreSQL (Neon) / SQLite | Serverless Postgres in prod; zero-config SQLite for local dev |
| Data Processing | Pandas + NumPy | Vectorised scoring and detection — avoids Python loops |
| Config | Pydantic-Settings | All risk thresholds in `.env` — zero code changes for threshold tuning |
| Frontend | React 18 + Vite | Fast dev server, code-splitting, tree-shaking |
| Charts | Recharts | Declarative SVG charts for analytics and stress-test visuals |
| Styling | Tailwind CSS | Utility-first; consistent with modern bank-portal aesthetics |
| Workflow Automation | n8n (self-hosted) | No-code canvas + code nodes — extensible without redeployment |
| AI Summaries | OpenAI GPT-4o-mini | Low-cost, high-quality adverse-media summarisation |
| Hosting | Vercel (API + SPA) | Edge CDN + zero-config CI/CD from GitHub push |
| Testing | pytest | Fixtures isolate DB from unit tests |

---

## Risk Scoring Formula

$$S(c) = 0.40 \cdot H(c) + 0.30 \cdot B(c) + 0.30 \cdot E(c) + P(c) + K(c)$$

| Component | Symbol | Weight | Description |
|---|---|---|---|
| Credit History | $H(c)$ | 40 % | FICO normalisation + IFRS 9 DPD stage penalties |
| Behavioural | $B(c)$ | 30 % | Monthly transaction CV, 30/60-day acceleration, wire ratio |
| Exposure | $E(c)$ | 30 % | DTI buckets, loan concentration, unsecured-to-collateralised ratio |
| PEP Adjustment | $P(c)$ | +10 pts | Politically Exposed Person flag (FATF Rec. 12) |
| KYC Adjustment | $K(c)$ | 0/+15 | VERIFIED = 0, PENDING / EXPIRED = +15 |

**PEP Floor Rule**: PEP clients are hard-floored at score = 55 (minimum HIGH tier), regardless of component computation.

### Risk Tier Thresholds

| Score Range | Tier | Compliance Action |
|---|---|---|
| 0 – 34 | LOW | Standard periodic monitoring |
| 35 – 54 | MEDIUM | Enhanced monitoring, annual review |
| 55 – 69 | HIGH | Relationship manager review required |
| 70 – 84 | VERY HIGH | Senior credit approval + EDD |
| 85 – 100 | CRITICAL | Account hold consideration + mandatory Compliance escalation |

Thresholds are configurable at runtime via the **Settings** page, which previews client tier-migration before committing a change.

---

## Model Stress Testing

The stress-test runner re-scores the **entire portfolio through the same production scoring engine** under a chosen macro scenario, then diffs the shocked state against baseline. Both states are computed by identical methodology, so results are directly comparable (a no-op scenario yields zero migrations by construction).

| Preset | Shock |
|---|---|
| `baseline` | No shock — sanity check |
| `rate_300` | Policy rate +300 bps |
| `downturn` | Regional economic downturn |
| `credit_crisis` | 2008-style credit crisis |

Output includes portfolio Expected Loss before/after (PD × LGD × EAD), the count of tier downgrades, a full tier-migration matrix, and an EL waterfall.

---

## Anomaly Detection Rules

| Rule ID | Category | Trigger Condition | Regulatory Reference |
|---|---|---|---|
| AML-VEL-001 | Velocity | >8 transactions in any 60-minute window | FATF Rec. 20 |
| AML-STR-001 | Structuring | ≥3 transactions just below the CTR threshold within 7 days | BSA / FinCEN |
| FRAUD-LOC-001 | Location Mismatch | Same card used in two countries within 2 hours | Card fraud typology |
| AML-CASH-001 | Large Cash | Single CASH transaction ≥ CTR threshold | FinCEN CTR requirement |
| FRAUD-DORM-001 | Dormant Spike | Zero-activity period followed by high-volume inflow | Account takeover indicator |
| AML-RND-001 | Round Amount | ≥5 consecutive round-figure transactions | ML placement typology |
| AML-CTPY-001 | High-Risk Counterparty | Transfer to entity on OFAC SDN / FATF grey list | OFAC compliance |

---

## API Reference

Full interactive docs when running locally: `http://localhost:8000/docs`

### Pipeline `/api/v1/pipeline/`
| Method | Path | Description |
|---|---|---|
| `POST` | `/pipeline/ingest` | Generate and persist synthetic clients, transactions, loans |
| `POST` | `/pipeline/score-portfolio` | Score all (or specific) clients |
| `POST` | `/pipeline/scan-anomalies` | Execute all 7 AML/Fraud detection rules |
| `GET` | `/pipeline/status` | Count of clients, scores, open flags |

### Reports `/api/v1/reports/`
| Method | Path | Description |
|---|---|---|
| `GET` | `/reports/high-risk-exposure` | All HIGH+ clients with latest score + open flags |
| `GET` | `/reports/risk-heatmap` | Full Risk Heatmap JSON payload |
| `GET` | `/reports/portfolio-summary` | KPI card aggregates |

### Transactions `/api/v1/transactions/`
| Method | Path | Description |
|---|---|---|
| `GET` | `/transactions/` | Paginated feed with client attribution |
| `GET` | `/transactions/stats` | Rolling-window volume/value summary |

### Stress Tests `/api/v1/stress-tests/`
| Method | Path | Description |
|---|---|---|
| `GET` | `/stress-tests/presets` | List built-in macro scenarios |
| `POST` | `/stress-tests/run` | Re-score the book under a shock; return EL + migration diff |

### Settings `/api/v1/settings/`
| Method | Path | Description |
|---|---|---|
| `GET` | `/settings/thresholds` | Current tier boundaries + model metadata |
| `GET` | `/settings/threshold-preview` | Preview client migration for candidate boundaries |
| `PATCH`| `/settings/thresholds` | Commit new tier boundaries |

### Analytics `/api/v1/analytics/`
| Method | Path | Description |
|---|---|---|
| `GET` | `/analytics/portfolio` | Sector/country concentration, aging, Expected Loss, score trend |

### Clients `/api/v1/clients/`
| Method | Path | Description |
|---|---|---|
| `GET` | `/clients/` | Searchable client directory (paginated) |
| `GET` | `/clients/{client_id}/360` | Full client dossier (score, exposures, transactions, flags) |

### Anomalies `/api/v1/anomalies/` · AI Alerts `/api/v1/ai-alerts/`
| Method | Path | Description |
|---|---|---|
| `GET` | `/anomalies/` | List open flags (filterable by severity and type) |
| `PATCH` | `/anomalies/{id}/resolve` | Close a flag with investigator note |
| `GET` | `/ai-alerts/` | List adverse-media alerts |
| `PATCH` | `/ai-alerts/{id}/acknowledge` | Acknowledge an alert |

---

## Algorithmic Complexity

| Operation | Time Complexity | Notes |
|---|---|---|
| Single client scoring | $O(T \log T + L)$ | T = transactions, L = loans. Log factor from time-series sort |
| Portfolio batch scoring | $O(N \cdot T \log T)$ | N = clients. `bulk_save_objects()` avoids row-by-row inserts |
| Velocity detection | $O(T \log T)$ | Two-pointer sliding window on sorted timestamps |
| Structuring detection | $O(T \log T)$ | Rolling 7-day count on sorted, resampled index |
| Location mismatch | $O(T \log T)$ | `pd.shift()` on sorted timestamps |
| Large cash detection | $O(T)$ | Single boolean mask — no sort required |
| Dormant spike detection | $O(T \log T)$ | Monthly resample + zero→nonzero transition |

---

## Local Development

### 1 — Clone and install
```bash
git clone https://github.com/alqasmii/risk-intelligence-system.git
cd risk-intelligence-system
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
```

### 2 — Configure environment
```bash
cp .env.example .env
# Pre-configured for local SQLite — no DB changes needed for dev
```

### 3 — Seed demo data
```bash
python seed_db.py            # 60 synthetic clients + transactions + loans
python seed_db.py --force    # re-seed from scratch
```

### 4 — Start the API server
```bash
uvicorn app.main:app --reload --port 8000
# Swagger UI → http://127.0.0.1:8000/docs
```

### 5 — Start the frontend
```bash
cd frontend
npm install
npm run dev
# Dashboard → http://localhost:3000  (proxies /api → :8000)
```

### 6 — Run tests
```bash
pytest tests/ -v
```

### Regenerating the screenshot gallery
With both servers running:
```bash
cd frontend && npm install --no-save playwright && npx playwright install chromium
node ../scripts/capture-screenshots.mjs http://localhost:3000
```

---

## Vercel Deployment

Set these in the Vercel project settings:

| Variable | Example | Required |
|---|---|---|
| `DATABASE_URL` | `postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require` | ✅ |
| `FRONTEND_URL` | `https://your-app.vercel.app` | ✅ |
| `ENVIRONMENT` | `production` | ✅ |
| `DEBUG` | `false` | ✅ |
| `MEDIUM_RISK_THRESHOLD` / `HIGH_RISK_THRESHOLD` / `VERY_HIGH_RISK_THRESHOLD` / `CRITICAL_RISK_THRESHOLD` | `35.0` / `55.0` / `70.0` / `85.0` | Optional |

```bash
npm i -g vercel
vercel               # first deploy — follow prompts
# subsequent deploys auto-trigger on push to main
```

---

## Regulatory References

| Standard | Relevance |
|---|---|
| **Basel III IRB** | Internal Ratings-Based credit risk weights (40/30/30 component split) |
| **IFRS 9** | Stage 1/2/3 classification via Days Past Due (DPD < 30 / 30–89 / ≥ 90) |
| **FATF Rec. 12** | PEP enhanced due diligence — hard score floor implemented |
| **FATF Rec. 20** | Suspicious transaction reporting — velocity and structuring rules |
| **BSA / FinCEN** | Currency Transaction Report threshold (large-cash rule) |
| **OFAC** | SDN-list counterparty matching — high-risk counterparty flag |
| **SR 11-7** | Fed model-risk guidance — score component explainability + stress testing |
| **FFIEC BSA/AML** | Investigation workflow — flag lifecycle (OPEN → UNDER_REVIEW → CLOSED) |

---

## Production Upgrade Path

| Item | Current (Demo) | Production Change |
|---|---|---|
| Database | Neon PostgreSQL (shared) | Dedicated PostgreSQL + PgBouncer pooling |
| Migrations | `create_tables()` | Alembic with version-controlled history |
| Secrets | Vercel env vars | Azure Key Vault / HashiCorp Vault |
| Auth | None | OAuth2 + JWT with RBAC (Compliance / Analyst / Read-only) |
| Scoring | Synchronous | Celery task queue for large portfolio batches |
| AML rules | In-process | Externally configurable rule engine |
| Observability | `logging` | OpenTelemetry → Azure Monitor / Datadog |
| Audit trail | None | Immutable append-only event log |

---

## License
 Open SOurce Free TO USE !! Enjoy
