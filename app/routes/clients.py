"""
Client Routes — Client Explorer API
====================================
Backs the "Client Explorer" screen: a searchable, filterable directory of the
whole book with a 360° drill-down per client (profile, latest score with
component breakdown, loan facilities, recent transactions, open anomalies).

The list endpoint joins each client to their latest risk score so the grid can
sort by risk without an N+1 query. The detail endpoint composes a single
client's full risk picture in one round-trip.

Endpoints:
  GET /clients/            — Searchable / filterable client directory
  GET /clients/{id}/360    — Full drill-down for one client
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.anomaly import AnomalyFlag
from app.models.client import Client, ClientType
from app.models.loan import Loan, LoanStatus
from app.models.risk_score import RiskScore
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clients", tags=["Client Explorer"])


def _latest_scores(db: Session, client_ids: Optional[List[str]] = None) -> dict:
    """Return {client_id: RiskScore} for the most recent score of each client."""
    q = db.query(RiskScore)
    if client_ids is not None:
        q = q.filter(RiskScore.client_id.in_(client_ids))
    q = q.order_by(RiskScore.client_id, desc(RiskScore.scored_at)).all()
    out: dict = {}
    for s in q:
        if s.client_id not in out:
            out[s.client_id] = s
    return out


@router.get(
    "/",
    summary="Client Directory",
    description=(
        "Searchable, filterable, paginated client directory. Each row carries the "
        "client's latest composite score and tier for risk-first sorting."
    ),
)
def list_clients(
    q: Optional[str] = Query(None, description="Search by client name or ID"),
    client_type: Optional[str] = Query(None, description="RETAIL | CORPORATE"),
    tier: Optional[str] = Query(None, description="Filter by latest risk tier"),
    is_pep: Optional[bool] = Query(None, description="Politically Exposed Persons only"),
    kyc_status: Optional[str] = Query(None, description="VERIFIED | PENDING | EXPIRED | REJECTED"),
    sort: str = Query("score_desc", description="score_desc|score_asc|name|debt_desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    query = db.query(Client)

    if q:
        like = f"%{q}%"
        query = query.filter(or_(Client.name.ilike(like), Client.id.ilike(like)))
    if client_type:
        query = query.filter(Client.client_type == client_type.upper())
    if is_pep is not None:
        query = query.filter(Client.is_pep == is_pep)
    if kyc_status:
        query = query.filter(Client.kyc_status == kyc_status.upper())

    all_matching = query.all()
    scores = _latest_scores(db, [c.id for c in all_matching])

    rows = []
    for c in all_matching:
        s = scores.get(c.id)
        row_tier = s.risk_tier if s else None
        if tier and row_tier != tier.upper():
            continue
        ctype = c.client_type.value if hasattr(c.client_type, "value") else c.client_type
        rows.append({
            "client_id": c.id,
            "client_name": c.name,
            "client_type": ctype,
            "country_of_residence": c.country_of_residence,
            "industry_sector": c.industry_sector,
            "is_pep": bool(c.is_pep),
            "kyc_status": c.kyc_status,
            "external_credit_score": c.external_credit_score,
            "composite_score": s.composite_score if s else None,
            "risk_tier": row_tier,
            "total_outstanding_debt": (s.total_outstanding_debt if s else None),
            "last_scored_at": s.scored_at if s else None,
        })

    # ── Sort ──────────────────────────────────────────────────────────────────
    if sort == "score_asc":
        rows.sort(key=lambda r: (r["composite_score"] is None, r["composite_score"] or 0))
    elif sort == "name":
        rows.sort(key=lambda r: r["client_name"].lower())
    elif sort == "debt_desc":
        rows.sort(key=lambda r: r["total_outstanding_debt"] or 0, reverse=True)
    else:  # score_desc default
        rows.sort(key=lambda r: r["composite_score"] or 0, reverse=True)

    total = len(rows)
    page = rows[skip: skip + limit]
    return {"total": total, "skip": skip, "limit": limit, "items": page}


@router.get(
    "/{client_id}/360",
    summary="Client 360° Drill-Down",
    description=(
        "Full risk picture for one client: profile, latest score with component "
        "breakdown, loan facilities, recent transactions, and open anomaly flags."
    ),
)
def client_360(
    client_id: str,
    tx_limit: int = Query(15, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client {client_id} not found.")

    score = (
        db.query(RiskScore)
        .filter(RiskScore.client_id == client_id)
        .order_by(desc(RiskScore.scored_at))
        .first()
    )

    # Score history (trend sparkline) — last 12 scores oldest→newest
    history = (
        db.query(RiskScore)
        .filter(RiskScore.client_id == client_id)
        .order_by(desc(RiskScore.scored_at))
        .limit(12)
        .all()
    )
    history = list(reversed(history))

    loans = db.query(Loan).filter(Loan.client_id == client_id).all()
    txns = (
        db.query(Transaction)
        .filter(Transaction.client_id == client_id)
        .order_by(desc(Transaction.timestamp))
        .limit(tx_limit)
        .all()
    )
    anomalies = (
        db.query(AnomalyFlag)
        .filter(AnomalyFlag.client_id == client_id)
        .order_by(desc(AnomalyFlag.flagged_at))
        .all()
    )

    ctype = client.client_type.value if hasattr(client.client_type, "value") else client.client_type

    return {
        "client": {
            "client_id": client.id,
            "client_name": client.name,
            "client_type": ctype,
            "external_credit_score": client.external_credit_score,
            "annual_income": client.annual_income,
            "debt_to_income_ratio": client.debt_to_income_ratio,
            "country_of_residence": client.country_of_residence,
            "industry_sector": client.industry_sector,
            "years_in_operation": client.years_in_operation,
            "is_pep": bool(client.is_pep),
            "kyc_status": client.kyc_status,
        },
        "latest_score": None if not score else {
            "composite_score": score.composite_score,
            "risk_tier": score.risk_tier,
            "credit_history_score": score.credit_history_score,
            "behavioral_score": score.behavioral_score,
            "exposure_score": score.exposure_score,
            "pep_adjustment": score.pep_adjustment,
            "kyc_adjustment": score.kyc_adjustment,
            "total_outstanding_debt": score.total_outstanding_debt,
            "active_loans_count": score.active_loans_count,
            "transactions_analyzed": score.transactions_analyzed,
            "scored_at": score.scored_at,
        },
        "score_history": [
            {"scored_at": h.scored_at, "composite_score": h.composite_score, "risk_tier": h.risk_tier}
            for h in history
        ],
        "loans": [
            {
                "id": l.id,
                "loan_type": l.loan_type,
                "loan_amount": l.loan_amount,
                "outstanding_balance": l.outstanding_balance,
                "interest_rate": l.interest_rate,
                "status": l.status,
                "days_past_due": l.days_past_due,
                "collateral_type": l.collateral_type,
                "collateral_value": l.collateral_value,
            }
            for l in loans
        ],
        "recent_transactions": [
            {
                "id": t.id,
                "amount": t.amount,
                "currency": t.currency,
                "transaction_type": t.transaction_type,
                "timestamp": t.timestamp,
                "location_country": t.location_country,
                "merchant_category": t.merchant_category,
            }
            for t in txns
        ],
        "anomalies": [
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
    }
