"""
Pipeline Routes
===============
Endpoints for triggering data ingestion and batch scoring runs.
These are designed to be called by a scheduler (cron / Celery beat) or
manually by a Risk Operations team member for an ad-hoc portfolio refresh.

Endpoints:
  POST /pipeline/ingest              — Run data ingestion pipeline
  POST /pipeline/score-portfolio     — Run batch risk scoring
  POST /pipeline/scan-anomalies      — Run anomaly detection scan
  GET  /pipeline/status              — Health check for pipeline readiness
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    AnomalyScanResultSchema,
    BatchScoringResultSchema,
    PipelineRunResultSchema,
)

# Heavy dependencies (pandas, numpy, Faker) are imported lazily inside each
# route function so they are NOT loaded on cold start.  The pipeline endpoints
# are admin-only operations, never called on dashboard page load.

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pipeline", tags=["Pipeline"])


@router.post(
    "/ingest",
    response_model=PipelineRunResultSchema,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run Data Ingestion Pipeline",
    description=(
        "Executes the three-stage data ingestion pipeline: "
        "client master → transaction log → loan portfolio. "
        "Returns a summary of records loaded and any data quality errors. "
        "**Production note**: this endpoint is idempotent — safe to call multiple times."
    ),
)
def trigger_ingestion(
    n_retail: int = Query(default=80, ge=1, le=5000, description="Number of retail client records to generate"),
    n_corporate: int = Query(default=20, ge=1, le=1000, description="Number of corporate client records to generate"),
    avg_tx_per_client: int = Query(default=50, ge=1, le=500, description="Average transactions per client"),
    db: Session = Depends(get_db),
) -> PipelineRunResultSchema:
    """
    Triggers the automated data ingestion pipeline.

    In a production environment, this would be called by:
    - A nightly Celery scheduled task at 01:00 UTC
    - A CI/CD workflow after a database migration
    - A Risk Operations team member for manual data refresh

    The pipeline uses bulk inserts — loading 1,000 clients + 50,000
    transactions takes under 10 seconds, vs. ~45 seconds with ORM row-by-row.
    """
    try:
        from app.pipeline.ingestion import run_ingestion_pipeline  # lazy — pulls numpy+Faker
        result = run_ingestion_pipeline(db, n_retail, n_corporate, avg_tx_per_client)
        return PipelineRunResultSchema(**result)
    except Exception as exc:
        logger.error("Ingestion pipeline failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline failed: {exc}",
        )


@router.post(
    "/score-portfolio",
    response_model=BatchScoringResultSchema,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run Batch Risk Scoring",
    description=(
        "Scores all clients (or a specified subset) using the "
        "Algorithmic Risk Scoring Engine. Persists results to the "
        "risk_scores table. Algorithm complexity: O(N·T log T)."
    ),
)
def trigger_batch_scoring(
    db: Session = Depends(get_db),
) -> BatchScoringResultSchema:
    """
    Triggers a full portfolio risk scoring run.
    Scores are persisted as immutable records — each run creates new
    score rows rather than updating existing ones, preserving the full
    audit history required for regulatory review.
    """
    try:
        from app.engines.risk_scoring import score_portfolio  # lazy — pulls numpy+pandas
        result = score_portfolio(db)
        return BatchScoringResultSchema(**result)
    except Exception as exc:
        logger.error("Batch scoring failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scoring run failed: {exc}",
        )


@router.post(
    "/scan-anomalies",
    response_model=AnomalyScanResultSchema,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run Anomaly Detection Scan",
    description=(
        "Scans transaction data using all 5 detection rules: velocity, structuring, "
        "geographic impossibility, large cash, and dormant account reactivation."
    ),
)
def trigger_anomaly_scan(
    lookback_days: int = Query(default=90, ge=1, le=365, description="Transaction lookback window in days"),
    db: Session = Depends(get_db),
) -> AnomalyScanResultSchema:
    """
    Triggers the full AML/Fraud anomaly detection scan.
    Uses a single-load, multi-pass architecture: one DB query loads all
    transactions, then each rule operates on the in-memory DataFrame.
    """
    try:
        from app.engines.anomaly_detection import run_anomaly_scan  # lazy — pulls pandas
        result = run_anomaly_scan(db, lookback_days=lookback_days)
        return AnomalyScanResultSchema(**result)
    except Exception as exc:
        logger.error("Anomaly scan failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Anomaly scan failed: {exc}",
        )


@router.get(
    "/status",
    summary="Pipeline Readiness Check",
    description="Returns database record counts — useful for verifying pipeline has run successfully.",
)
def pipeline_status(db: Session = Depends(get_db)) -> dict:
    """Lightweight status check — useful for monitoring dashboards / healthchecks."""
    from app.models.client import Client
    from app.models.transaction import Transaction
    from app.models.loan import Loan
    from app.models.risk_score import RiskScore
    from app.models.anomaly import AnomalyFlag

    return {
        "clients": db.query(Client).count(),
        "transactions": db.query(Transaction).count(),
        "loans": db.query(Loan).count(),
        "risk_scores": db.query(RiskScore).count(),
        "anomaly_flags": db.query(AnomalyFlag).count(),
        "status": "ready",
    }
