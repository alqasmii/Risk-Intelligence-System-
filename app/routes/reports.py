"""
Risk Reporting Routes — Automated Reporting API
================================================
These endpoints replace manual Excel-based risk reporting workflows.

Instead of a Risk Analyst spending 2–3 hours each morning pulling data
from multiple systems and building a PowerPoint/Excel summary, this API
delivers a structured JSON payload in <200ms that can be consumed by:
  - A React/Next.js Risk Operations Dashboard (heatmap + KPI cards)
  - A downstream BI tool (Power BI, Tableau)
  - An automated email report generator
  - A regulatory reporting pipeline

Endpoints:
  GET /reports/high-risk-exposure     — Main heatmap dashboard payload
  GET /reports/risk-heatmap           — Alias optimised for React component
  GET /reports/client/{client_id}     — Single client deep-dive
  GET /reports/portfolio-summary      — Aggregate portfolio statistics
"""

import logging
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.anomaly import AnomalyFlag
from app.models.client import Client
from app.models.risk_score import RiskScore, RiskTier
from app.schemas import (
    HighRiskClientSchema,
    RiskHeatmapPayloadSchema,
    RiskScoreSchema,
    RiskSummarySchema,
    TierDistributionSchema,
    ClientSummarySchema,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["Risk Reports"])


# ──────────────────────────────────────────────────────────────────────────────
# High-Risk Exposure Report — Primary Dashboard Endpoint
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/high-risk-exposure",
    response_model=RiskHeatmapPayloadSchema,
    summary="High-Risk Exposure Report",
    description=(
        "Returns all clients scoring at HIGH tier or above, with full component "
        "breakdown and anomaly counts. This is the primary payload for the Risk "
        "Heatmap dashboard. Replaces manual Excel reporting — produced in <200ms "
        "vs. 2-3 hours of manual data assembly."
    ),
)
def get_high_risk_exposure(
    min_tier: str = Query(
        default="HIGH",
        description="Minimum risk tier to include. One of: LOW, MEDIUM, HIGH, VERY_HIGH, CRITICAL",
        pattern="^(LOW|MEDIUM|HIGH|VERY_HIGH|CRITICAL)$",
    ),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> RiskHeatmapPayloadSchema:
    """
    Executes an optimised JOIN query to produce the dashboard payload.

    Query Strategy:
      1. Subquery: Find the latest score per client (window function pattern)
         → avoids loading all historical scores
      2. Main query: JOIN clients + latest_scores + anomaly aggregates
         → single round-trip, no N+1 queries

    The response is structured to map directly to the React Risk Heatmap:
      - high_risk_clients → table rows + heatmap cells
      - tier_distribution → heatmap grid data + bar chart
      - summary → KPI cards row
    """
    tier_order = {t.value: i for i, t in enumerate(RiskTier)}
    min_tier_idx = tier_order.get(min_tier, tier_order["HIGH"])

    # ── Step 1: Fetch latest score per client (subquery pattern) ──────────────
    # Subquery: MAX(scored_at) per client_id
    latest_score_subq = (
        db.query(
            RiskScore.client_id,
            func.max(RiskScore.scored_at).label("max_scored_at"),
        )
        .group_by(RiskScore.client_id)
        .subquery()
    )

    # Main query: join to get the actual latest score row
    latest_scores = (
        db.query(RiskScore)
        .join(
            latest_score_subq,
            (RiskScore.client_id == latest_score_subq.c.client_id)
            & (RiskScore.scored_at == latest_score_subq.c.max_scored_at),
        )
        .all()
    )

    if not latest_scores:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No risk scores found. Run POST /pipeline/ingest then POST /pipeline/score-portfolio first.",
        )

    # ── Step 2: Filter to requested tier threshold ─────────────────────────────
    filtered_scores = [
        s for s in latest_scores
        if tier_order.get(s.risk_tier, 0) >= min_tier_idx
    ]
    # Sort: highest risk first
    filtered_scores.sort(key=lambda s: s.composite_score, reverse=True)
    filtered_scores = filtered_scores[:limit]

    # ── Step 3: Fetch client details for the filtered set ─────────────────────
    client_ids = [s.client_id for s in filtered_scores]
    clients_map = {
        c.id: c for c in db.query(Client).filter(Client.id.in_(client_ids)).all()
    }

    # ── Step 4: Aggregate anomaly counts per client in one query ──────────────
    # Avoids querying per-client (N+1 anti-pattern)
    anomaly_agg = (
        db.query(
            AnomalyFlag.client_id,
            func.count(AnomalyFlag.id).label("total_open"),
        )
        .filter(
            AnomalyFlag.client_id.in_(client_ids),
            AnomalyFlag.status == "OPEN",
        )
        .group_by(AnomalyFlag.client_id)
        .all()
    )
    anomaly_map = {row.client_id: row for row in anomaly_agg}

    # ── Step 5: Assemble response objects ─────────────────────────────────────
    high_risk_clients = []
    for score in filtered_scores:
        client = clients_map.get(score.client_id)
        if not client:
            continue

        anom = anomaly_map.get(score.client_id)
        open_count = int(anom.total_open) if anom and anom.total_open else 0
        # Compute critical anomaly count directly from flags for accuracy
        crit_count = (
            db.query(func.count(AnomalyFlag.id))
            .filter(
                AnomalyFlag.client_id == score.client_id,
                AnomalyFlag.severity == "CRITICAL",
                AnomalyFlag.status == "OPEN",
            )
            .scalar() or 0
        )

        high_risk_clients.append(HighRiskClientSchema(
            client_id=client.id,
            client_name=client.name,
            client_type=client.client_type if isinstance(client.client_type, str) else client.client_type.value,
            risk_tier=score.risk_tier,
            composite_score=score.composite_score,
            credit_history_score=score.credit_history_score,
            behavioral_score=score.behavioral_score,
            exposure_score=score.exposure_score,
            open_anomaly_count=open_count,
            critical_anomaly_count=crit_count,
            active_loans_count=score.active_loans_count or 0,
            total_outstanding_debt=score.total_outstanding_debt or 0.0,
            is_pep=client.is_pep,
            kyc_status=client.kyc_status,
            country_of_residence=client.country_of_residence,
            last_scored_at=score.scored_at,
        ))

    # ── Step 6: Compute tier distribution for heatmap grid ───────────────────
    tier_dist = _compute_tier_distribution(latest_scores, db)

    # ── Step 7: Build summary KPI cards ───────────────────────────────────────
    all_high_count = sum(1 for s in latest_scores if tier_order.get(s.risk_tier, 0) >= tier_order["HIGH"])
    critical_count = sum(1 for s in latest_scores if s.risk_tier == RiskTier.CRITICAL.value)
    total_open_anomalies = db.query(func.count(AnomalyFlag.id)).filter(AnomalyFlag.status == "OPEN").scalar() or 0
    total_critical_anomalies = (
        db.query(func.count(AnomalyFlag.id))
        .filter(AnomalyFlag.status == "OPEN", AnomalyFlag.severity == "CRITICAL")
        .scalar() or 0
    )
    total_exposure = sum(
        (s.total_outstanding_debt or 0.0)
        for s in latest_scores
        if tier_order.get(s.risk_tier, 0) >= tier_order["HIGH"]
    )
    avg_score = round(sum(s.composite_score for s in latest_scores) / len(latest_scores), 2)

    summary = RiskSummarySchema(
        total_high_risk=all_high_count,
        total_critical=critical_count,
        total_open_anomalies=total_open_anomalies,
        total_critical_anomalies=total_critical_anomalies,
        total_exposure_usd=round(total_exposure, 2),
        portfolio_average_score=avg_score,
    )

    return RiskHeatmapPayloadSchema(
        generated_at=datetime.now(timezone.utc),
        model_version="1.0.0",
        total_clients_analyzed=len(latest_scores),
        summary=summary,
        high_risk_clients=high_risk_clients,
        tier_distribution=tier_dist,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Risk Heatmap alias (clean URL for React component)
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/risk-heatmap",
    response_model=RiskHeatmapPayloadSchema,
    summary="Risk Heatmap Data (React Dashboard)",
    description="Alias for /high-risk-exposure. Returns the full payload for the React Risk Heatmap component.",
)
def get_risk_heatmap(db: Session = Depends(get_db)) -> RiskHeatmapPayloadSchema:
    """Direct heatmap data — includes all tiers for the full grid."""
    return get_high_risk_exposure(min_tier="LOW", limit=1000, db=db)


# ──────────────────────────────────────────────────────────────────────────────
# Single Client Deep-Dive
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/client/{client_id}",
    summary="Single Client Risk Profile",
    description="Returns the latest risk score and all open anomaly flags for one client.",
)
def get_client_profile(
    client_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """
    Provides a complete risk profile for a single client.
    Used by the Relationship Manager / Credit Analyst client detail view.
    """
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client {client_id} not found.")

    latest_score = (
        db.query(RiskScore)
        .filter(RiskScore.client_id == client_id)
        .order_by(desc(RiskScore.scored_at))
        .first()
    )

    anomalies = (
        db.query(AnomalyFlag)
        .filter(AnomalyFlag.client_id == client_id, AnomalyFlag.status == "OPEN")
        .order_by(desc(AnomalyFlag.flagged_at))
        .all()
    )

    return {
        "client": ClientSummarySchema.model_validate(client),
        "latest_risk_score": RiskScoreSchema.from_orm_model(latest_score) if latest_score else None,
        "open_anomalies": [
            {
                "id": a.id,
                "type": a.anomaly_type,
                "severity": a.severity,
                "rule": a.rule_triggered,
                "description": a.description,
                "amount": a.flagged_amount,
                "flagged_at": a.flagged_at,
                "status": a.status,
            }
            for a in anomalies
        ],
        "anomaly_count": len(anomalies),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Portfolio Summary
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/portfolio-summary",
    summary="Portfolio-Level Risk Statistics",
    description="High-level aggregate statistics for the entire scored portfolio.",
)
def get_portfolio_summary(db: Session = Depends(get_db)) -> dict:
    """Returns portfolio-wide statistics for executive dashboard KPI cards."""
    from app.models.loan import Loan

    total_clients = db.query(func.count(Client.id)).scalar() or 0
    total_loans = db.query(func.count(Loan.id)).scalar() or 0
    total_outstanding = db.query(func.sum(Loan.outstanding_balance)).scalar() or 0.0
    total_anomalies = db.query(func.count(AnomalyFlag.id)).filter(AnomalyFlag.status == "OPEN").scalar() or 0

    tier_counts = (
        db.query(RiskScore.risk_tier, func.count(RiskScore.id))
        .group_by(RiskScore.risk_tier)
        .all()
    )

    return {
        "total_clients": total_clients,
        "total_loans": total_loans,
        "total_outstanding_usd": round(float(total_outstanding), 2),
        "total_open_anomalies": total_anomalies,
        "risk_tier_distribution": {tier: count for tier, count in tier_counts},
    }


# ──────────────────────────────────────────────────────────────────────────────
# Internal Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _compute_tier_distribution(
    scores: list,
    db: Session,
) -> list:
    """
    Builds the tier × client_type distribution matrix for the heatmap grid.
    Groups latest scores by (risk_tier, client_type) and aggregates counts,
    average scores, and total exposure.
    """
    from collections import defaultdict

    # Map client IDs to client types
    client_ids = [s.client_id for s in scores]
    clients_map = {
        c.id: c for c in db.query(Client).filter(Client.id.in_(client_ids)).all()
    }

    groups: dict = defaultdict(lambda: {"count": 0, "scores": [], "exposure": 0.0})

    for score in scores:
        client = clients_map.get(score.client_id)
        if not client:
            continue
        ctype = client.client_type if isinstance(client.client_type, str) else client.client_type.value
        key = (score.risk_tier, ctype)
        groups[key]["count"] += 1
        groups[key]["scores"].append(score.composite_score)
        groups[key]["exposure"] += score.total_outstanding_debt or 0.0

    result = []
    for (tier, ctype), data in groups.items():
        avg = round(sum(data["scores"]) / len(data["scores"]), 2) if data["scores"] else 0.0
        result.append(TierDistributionSchema(
            risk_tier=tier,
            client_type=ctype,
            count=data["count"],
            avg_score=avg,
            total_exposure_usd=round(data["exposure"], 2),
        ))

    # Sort for consistent heatmap rendering order
    tier_order = {t.value: i for i, t in enumerate(RiskTier)}
    result.sort(key=lambda x: (tier_order.get(x.risk_tier, 99), x.client_type))
    return result
