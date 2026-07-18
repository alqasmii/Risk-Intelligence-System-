"""
Anomaly Routes
==============
Endpoints for querying and managing anomaly flags.

Endpoints:
  GET  /anomalies/                    — List all open anomaly flags (paginated)
  GET  /anomalies/critical            — CRITICAL severity flags only
  GET  /anomalies/by-rule/{rule_id}   — Flags grouped by detection rule
  PATCH /anomalies/{flag_id}/resolve  — Mark a flag as resolved (investigator action)
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.anomaly import AnomalyFlag, AnomalySeverity
from app.schemas import AnomalyFlagSchema

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/anomalies", tags=["Anomaly Detection"])


@router.get(
    "/",
    response_model=List[AnomalyFlagSchema],
    summary="List Open Anomaly Flags",
    description="Returns paginated list of open anomaly flags, newest first. Use severity filter to prioritise review queue.",
)
def list_anomalies(
    severity: Optional[str] = Query(None, description="Filter by severity: LOW, MEDIUM, HIGH, CRITICAL"),
    anomaly_type: Optional[str] = Query(None, description="Filter by type: VELOCITY, STRUCTURING, etc."),
    status_filter: str = Query(default="OPEN", alias="status", description="Flag status: OPEN, UNDER_REVIEW, RESOLVED, FALSE_POSITIVE"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[AnomalyFlagSchema]:
    """
    Lists anomaly flags filtered by severity and type.
    Ordered newest-first — analysts should work from the top of their queue.
    """
    query = db.query(AnomalyFlag).filter(AnomalyFlag.status == status_filter)

    if severity:
        severity_upper = severity.upper()
        if severity_upper not in [s.value for s in AnomalySeverity]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid severity '{severity}'. Must be one of: LOW, MEDIUM, HIGH, CRITICAL",
            )
        query = query.filter(AnomalyFlag.severity == severity_upper)

    if anomaly_type:
        query = query.filter(AnomalyFlag.anomaly_type == anomaly_type.upper())

    flags = (
        query.order_by(desc(AnomalyFlag.flagged_at))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [AnomalyFlagSchema.model_validate(f) for f in flags]


@router.get(
    "/critical",
    response_model=List[AnomalyFlagSchema],
    summary="Critical Anomaly Queue",
    description=(
        "Returns all CRITICAL severity, open anomaly flags. "
        "These require immediate action — account hold consideration + SAR review within 24h."
    ),
)
def get_critical_anomalies(
    db: Session = Depends(get_db),
) -> List[AnomalyFlagSchema]:
    """Priority queue for the AML/Fraud Investigations team."""
    flags = (
        db.query(AnomalyFlag)
        .filter(
            AnomalyFlag.severity == AnomalySeverity.CRITICAL.value,
            AnomalyFlag.status == "OPEN",
        )
        .order_by(desc(AnomalyFlag.flagged_at))
        .all()
    )
    return [AnomalyFlagSchema.model_validate(f) for f in flags]


@router.get(
    "/by-rule/{rule_id}",
    response_model=List[AnomalyFlagSchema],
    summary="Flags by Detection Rule",
    description="Returns all open flags triggered by a specific detection rule (e.g., AML-STR-001).",
)
def get_flags_by_rule(
    rule_id: str,
    db: Session = Depends(get_db),
) -> List[AnomalyFlagSchema]:
    """Useful for rule-level performance monitoring — how many flags does each rule produce?"""
    flags = (
        db.query(AnomalyFlag)
        .filter(
            AnomalyFlag.rule_triggered == rule_id.upper(),
            AnomalyFlag.status == "OPEN",
        )
        .order_by(desc(AnomalyFlag.flagged_at))
        .all()
    )
    return [AnomalyFlagSchema.model_validate(f) for f in flags]


@router.patch(
    "/{flag_id}/resolve",
    response_model=AnomalyFlagSchema,
    summary="Resolve Anomaly Flag",
    description=(
        "Marks a flag as RESOLVED or FALSE_POSITIVE and records the investigator's note. "
        "This is the case closure action — required for AML workflow audit trail."
    ),
)
def resolve_anomaly(
    flag_id: str,
    resolution_status: str = Query(
        description="New status: RESOLVED or FALSE_POSITIVE",
        pattern="^(RESOLVED|FALSE_POSITIVE)$",
    ),
    investigator_note: str = Query(description="Investigator's closure note (required for audit trail)"),
    db: Session = Depends(get_db),
) -> AnomalyFlagSchema:
    """
    Closes an anomaly flag with a documented investigator note.
    The note is mandatory — regulators may request evidence of investigation
    outcome for any flag above LOW severity (FFIEC BSA/AML Examination Manual).
    """
    from datetime import datetime, timezone

    if not investigator_note or len(investigator_note.strip()) < 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="investigator_note must be at least 10 characters (required for audit trail).",
        )

    flag = db.query(AnomalyFlag).filter(AnomalyFlag.id == flag_id).first()
    if not flag:
        raise HTTPException(status_code=404, detail=f"Anomaly flag {flag_id} not found.")

    if flag.status not in ("OPEN", "UNDER_REVIEW"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Flag is already in terminal status: {flag.status}",
        )

    flag.status = resolution_status
    flag.resolved_at = datetime.now(timezone.utc)
    flag.investigator_note = investigator_note.strip()

    db.commit()
    db.refresh(flag)

    logger.info(
        "Anomaly flag %s resolved as %s by system", flag_id[:8], resolution_status
    )

    return AnomalyFlagSchema.model_validate(flag)
