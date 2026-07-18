"""
Settings Routes — Model Governance & Threshold Tuning
=====================================================
Exposes the tunable risk parameters so a Risk Officer can adjust tier
boundaries and exposure thresholds without a redeploy — the config layer was
built for exactly this (see app/config.py).

Changes apply to the running process only (in-memory). They are intentionally
NOT written to .env or the database: threshold changes are a governed action
that in production would flow through a change-approval workflow. The endpoint
also reports how many clients would migrate tier under the proposed boundaries,
so the officer sees the impact before committing.

Endpoints:
  GET   /settings/thresholds          — Current thresholds + model metadata
  PATCH /settings/thresholds          — Update thresholds (in-memory, session)
  GET   /settings/threshold-preview   — Client tier counts under given thresholds

NOTE: These endpoints are unauthenticated, consistent with the rest of this
proof-of-concept. In production they would require an authenticated Risk
Officer role with change-management approval.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.risk_score import RiskScore, RiskTier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings", tags=["Settings"])


class ThresholdUpdate(BaseModel):
    medium_risk_threshold: Optional[float] = Field(None, ge=1, le=99)
    high_risk_threshold: Optional[float] = Field(None, ge=1, le=99)
    very_high_risk_threshold: Optional[float] = Field(None, ge=1, le=99)
    critical_risk_threshold: Optional[float] = Field(None, ge=1, le=99)
    high_dti_threshold: Optional[float] = Field(None, ge=0.05, le=1.0)
    critical_dti_threshold: Optional[float] = Field(None, ge=0.05, le=1.5)


def _snapshot() -> dict:
    return {
        "model_version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "reporting_currency": "OMR",
        "thresholds": {
            "medium_risk_threshold": settings.MEDIUM_RISK_THRESHOLD,
            "high_risk_threshold": settings.HIGH_RISK_THRESHOLD,
            "very_high_risk_threshold": settings.VERY_HIGH_RISK_THRESHOLD,
            "critical_risk_threshold": settings.CRITICAL_RISK_THRESHOLD,
            "high_dti_threshold": settings.HIGH_DTI_THRESHOLD,
            "critical_dti_threshold": settings.CRITICAL_DTI_THRESHOLD,
        },
        "component_weights": {
            "credit_history": settings.CREDIT_HISTORY_WEIGHT,
            "behavioral": settings.BEHAVIORAL_WEIGHT,
            "exposure": settings.EXPOSURE_WEIGHT,
        },
        "anomaly_parameters": {
            "velocity_window_minutes": settings.VELOCITY_WINDOW_MINUTES,
            "velocity_max_transactions": settings.VELOCITY_MAX_TRANSACTIONS,
            "structuring_lower_bound": settings.STRUCTURING_LOWER_BOUND,
            "structuring_min_count": settings.STRUCTURING_MIN_COUNT,
        },
    }


def _classify(score: float, med: float, high: float, vhigh: float, crit: float) -> str:
    if score >= crit:
        return RiskTier.CRITICAL.value
    if score >= vhigh:
        return RiskTier.VERY_HIGH.value
    if score >= high:
        return RiskTier.HIGH.value
    if score >= med:
        return RiskTier.MEDIUM.value
    return RiskTier.LOW.value


@router.get("/thresholds", summary="Current risk thresholds & model metadata")
def get_thresholds() -> dict:
    return _snapshot()


@router.get(
    "/threshold-preview",
    summary="Preview tier distribution under proposed thresholds",
    description=(
        "Re-buckets the latest score of every client using the supplied tier "
        "boundaries WITHOUT changing anything. Lets the officer see how many "
        "clients would move before committing a threshold change."
    ),
)
def threshold_preview(
    medium: float = settings.MEDIUM_RISK_THRESHOLD,
    high: float = settings.HIGH_RISK_THRESHOLD,
    very_high: float = settings.VERY_HIGH_RISK_THRESHOLD,
    critical: float = settings.CRITICAL_RISK_THRESHOLD,
    db: Session = Depends(get_db),
) -> dict:
    # Latest score per client
    subq = (
        db.query(RiskScore.client_id, RiskScore.composite_score, RiskScore.risk_tier,
                 RiskScore.scored_at)
        .order_by(RiskScore.client_id, desc(RiskScore.scored_at))
        .all()
    )
    seen = set()
    current = {t.value: 0 for t in RiskTier}
    proposed = {t.value: 0 for t in RiskTier}
    changed = 0
    for row in subq:
        if row.client_id in seen:
            continue
        seen.add(row.client_id)
        current[row.risk_tier] = current.get(row.risk_tier, 0) + 1
        new_tier = _classify(row.composite_score, medium, high, very_high, critical)
        proposed[new_tier] += 1
        if new_tier != row.risk_tier:
            changed += 1
    return {
        "clients": len(seen),
        "clients_changing_tier": changed,
        "current_distribution": current,
        "proposed_distribution": proposed,
        "proposed_thresholds": {
            "medium": medium, "high": high, "very_high": very_high, "critical": critical,
        },
    }


@router.patch(
    "/thresholds",
    summary="Update risk thresholds (in-memory, session-scoped)",
    description=(
        "Applies new thresholds to the running process. Not persisted to disk — "
        "in production this would route through a change-approval workflow. "
        "Thresholds must be strictly increasing: medium < high < very_high < critical."
    ),
)
def update_thresholds(update: ThresholdUpdate) -> dict:
    # Resolve final values (fall back to current where not supplied)
    med = update.medium_risk_threshold if update.medium_risk_threshold is not None else settings.MEDIUM_RISK_THRESHOLD
    high = update.high_risk_threshold if update.high_risk_threshold is not None else settings.HIGH_RISK_THRESHOLD
    vhigh = update.very_high_risk_threshold if update.very_high_risk_threshold is not None else settings.VERY_HIGH_RISK_THRESHOLD
    crit = update.critical_risk_threshold if update.critical_risk_threshold is not None else settings.CRITICAL_RISK_THRESHOLD

    if not (med < high < vhigh < crit):
        return {
            "status": "rejected",
            "reason": "Thresholds must be strictly increasing: medium < high < very_high < critical.",
            "attempted": {"medium": med, "high": high, "very_high": vhigh, "critical": crit},
        }

    settings.MEDIUM_RISK_THRESHOLD = med
    settings.HIGH_RISK_THRESHOLD = high
    settings.VERY_HIGH_RISK_THRESHOLD = vhigh
    settings.CRITICAL_RISK_THRESHOLD = crit
    if update.high_dti_threshold is not None:
        settings.HIGH_DTI_THRESHOLD = update.high_dti_threshold
    if update.critical_dti_threshold is not None:
        settings.CRITICAL_DTI_THRESHOLD = update.critical_dti_threshold

    logger.info("Risk thresholds updated in-memory: %s", _snapshot()["thresholds"])
    return {"status": "updated", **_snapshot()}
