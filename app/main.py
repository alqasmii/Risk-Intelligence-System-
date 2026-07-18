"""
Automated Risk Intelligence System — FastAPI Application Factory
================================================================
Entry point for the API server. Handles:
  - Application lifecycle (table creation on startup)
  - Router registration with versioned prefix /api/v1
  - CORS middleware (origins configured via FRONTEND_URL)
  - Health & readiness probe endpoints
  - OpenAPI metadata for Swagger UI documentation

Usage:
    pip install -r requirements.txt
    uvicorn app.main:app --reload --port 8000

Then open: http://127.0.0.1:8000/docs
"""

from contextlib import asynccontextmanager
import logging
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import create_tables
from app.routes import (
    ai_alerts,
    analytics,
    anomalies,
    clients,
    pipeline,
    reports,
    settings as settings_routes,
    stress_tests,
    transactions,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — replaces deprecated @app.on_event("startup")
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(application: FastAPI):
    """
    Creates database tables (or validates they exist) at startup.
    Wrapped in try/except so a transient DB error on cold-start does not
    crash the entire serverless function — individual requests will surface
    DB errors through their own exception handlers instead.
    """
    logger.info("Initialising database schema...")
    try:
        create_tables()
        logger.info("Database ready.")
    except Exception as exc:  # pragma: no cover
        logger.error("Database initialisation failed: %s", exc)
    yield  # Application runs here
    logger.info("Application shutdown.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Automated Risk Intelligence System",
    description=(
        "A proof-of-concept banking risk platform exposing four automated modules: "
        "**Data Ingestion Pipeline**, **Algorithmic Risk Scoring Engine** (Basel III IRB / IFRS 9), "
        "**Operational Anomaly Detection** (AML/Fraud — FATF-aligned), and "
        "**Automated Reporting API** (replaces manual Excel risk packs).\n\n"
        "All risk scores are computed using the formula:\n\n"
        "**S(c) = 0.40·H(c) + 0.30·B(c) + 0.30·E(c) + P(c) + K(c)**\n\n"
        "where H = Credit History, B = Behavioural, E = Exposure, P = PEP adjustment, K = KYC adjustment."
    ),
    version="1.0.0",
    contact={"name": "Risk Technology Team"},
    license_info={"name": "MIT"},
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — origins are resolved from settings.cors_origins (driven by the
# FRONTEND_URL env var, comma-separated for multiple domains). Localhost dev
# servers are auto-included only in development. We never use a "*" wildcard
# here because credentialed requests (allow_credentials=True) are incompatible
# with a wildcard origin under the CORS spec.
# ---------------------------------------------------------------------------

_cors_origins = settings.cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Router registration
# ---------------------------------------------------------------------------

API_PREFIX = "/api/v1"

app.include_router(pipeline.router,       prefix=API_PREFIX)
app.include_router(reports.router,        prefix=API_PREFIX)
app.include_router(anomalies.router,      prefix=API_PREFIX)
app.include_router(ai_alerts.router,      prefix=API_PREFIX)
app.include_router(transactions.router,   prefix=API_PREFIX)
app.include_router(stress_tests.router,   prefix=API_PREFIX)
app.include_router(settings_routes.router, prefix=API_PREFIX)
app.include_router(analytics.router,      prefix=API_PREFIX)
app.include_router(clients.router,        prefix=API_PREFIX)


# ---------------------------------------------------------------------------
# Root endpoints
# ---------------------------------------------------------------------------

@app.get("/", tags=["Health"], summary="Root / Health Probe")
@app.get("/api", tags=["Health"], summary="API / Health Probe")
def root() -> Dict[str, Any]:
    """
    Liveness probe.  Return 200 OK so load-balancers and Docker HEALTHCHECK
    confirm the process is running.
    """
    return {
        "service": "Automated Risk Intelligence System",
        "version": "1.0.0",
        "status": "healthy",
        "docs": "/docs",
        "openapi": "/openapi.json",
    }


@app.get("/health", tags=["Health"], summary="Readiness / Health Check")
def health(db_ok: bool = True) -> Dict[str, str]:
    """
    Readiness probe — checks DB connectivity.
    Kubernetes readiness probes should target this endpoint.
    """
    from sqlalchemy import text
    from app.database import SessionLocal

    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_status = "ok"
    except Exception as exc:  # pragma: no cover
        logger.error("Health check DB query failed: %s", exc)
        db_status = "error"

    return {"api": "ok", "database": db_status}
