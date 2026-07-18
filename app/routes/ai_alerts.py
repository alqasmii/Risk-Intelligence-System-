"""
AI Adverse Media Alerts Routes
================================
Receives structured risk intelligence from the n8n Adverse Media Early
Warning Radar workflow and serves the alerts to the React dashboard's
Live AI Risk Feed panel.

Endpoints:
  POST  /ai-alerts                      — Ingest alert from n8n (OpenAI output)
  GET   /ai-alerts                      — Retrieve latest alerts for dashboard
  PATCH /ai-alerts/{id}/acknowledge     — Mark an alert as reviewed by analyst
"""

import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.ai_alert import AIAlert
from app.schemas import AIAlertPayload, AIAlertSchema

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai-alerts", tags=["AI Adverse Media Alerts"])


# ──────────────────────────────────────────────────────────────────────────────
# POST /ai-alerts — Ingest from n8n
# ──────────────────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=AIAlertSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest AI-generated Adverse Media Alert",
    description=(
        "Receives a structured risk signal from the n8n Adverse Media Early Warning Radar. "
        "The payload is produced by an OpenAI LLM acting as a Senior Credit Risk Analyst, "
        "having read and assessed a financial news article for counterparty risk signals. "
        "The alert is persisted and immediately surfaced on the dashboard Live Feed."
    ),
)
def create_ai_alert(
    payload: AIAlertPayload,
    db: Session = Depends(get_db),
) -> AIAlertSchema:
    """
    Validates incoming n8n payload and persists to the ai_alerts table.

    Security note: Input is validated by Pydantic before reaching this handler.
    The source_article field is stored as plain text — never executed or echoed
    back as HTML to prevent stored XSS. The API is not publicly exposed.
    """
    alert = AIAlert(
        company_name=payload.company_name.strip(),
        risk_score=payload.risk_score,
        risk_summary=payload.risk_summary.strip(),
        source_article=payload.source_article,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    logger.info(
        "AI alert stored | company=%s | risk_score=%d | id=%s",
        alert.company_name,
        alert.risk_score,
        alert.id,
    )
    return AIAlertSchema.model_validate(alert)


# ──────────────────────────────────────────────────────────────────────────────
# GET /ai-alerts — Serve to dashboard
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=List[AIAlertSchema],
    summary="List AI Adverse Media Alerts",
    description=(
        "Returns AI-generated adverse media alerts ordered newest-first. "
        "Consumed by the Live AI Risk Feed panel in the React dashboard. "
        "Use `unacknowledged_only=true` to show only open items requiring analyst action."
    ),
)
def get_ai_alerts(
    limit: int = Query(default=50, ge=1, le=500, description="Maximum alerts to return"),
    unacknowledged_only: bool = Query(
        default=False,
        description="If true, return only open (unacknowledged) alerts",
    ),
    min_risk_score: int = Query(
        default=1,
        ge=1,
        le=10,
        description="Filter to alerts at or above this severity (e.g. 8 for critical only)",
    ),
    db: Session = Depends(get_db),
) -> List[AIAlertSchema]:
    query = db.query(AIAlert)

    if unacknowledged_only:
        query = query.filter(AIAlert.is_acknowledged == 0)

    if min_risk_score > 1:
        query = query.filter(AIAlert.risk_score >= min_risk_score)

    alerts = (
        query
        .order_by(desc(AIAlert.risk_score), desc(AIAlert.created_at))
        .limit(limit)
        .all()
    )
    return [AIAlertSchema.model_validate(a) for a in alerts]


# ──────────────────────────────────────────────────────────────────────────────
# PATCH /ai-alerts/{id}/acknowledge — Analyst action
# ──────────────────────────────────────────────────────────────────────────────

@router.patch(
    "/{alert_id}/acknowledge",
    response_model=AIAlertSchema,
    summary="Acknowledge AI Adverse Media Alert",
    description=(
        "Marks an alert as reviewed. Required for audit trail — regulators expect "
        "evidence that every AI-generated risk signal has been reviewed by a qualified analyst."
    ),
)
def acknowledge_alert(
    alert_id: str,
    analyst_name: str = Query(..., min_length=1, max_length=100, description="Acknowledging analyst's name/ID"),
    db: Session = Depends(get_db),
) -> AIAlertSchema:
    alert = db.query(AIAlert).filter(AIAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AI alert '{alert_id}' not found.",
        )
    if alert.is_acknowledged:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Alert already acknowledged by {alert.acknowledged_by}.",
        )

    alert.is_acknowledged = 1
    alert.acknowledged_at = datetime.now(timezone.utc)
    alert.acknowledged_by = analyst_name.strip()
    db.commit()
    db.refresh(alert)

    logger.info(
        "AI alert acknowledged | id=%s | analyst=%s", alert.id, analyst_name
    )
    return AIAlertSchema.model_validate(alert)
