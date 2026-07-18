"""
Portfolio Analytics Routes
==========================
Aggregate, portfolio-level analytics for the "Portfolio Analytics" dashboard.
Answers the questions a Chief Risk Officer asks: where is exposure
concentrated, how is the book aging, and what is our expected credit loss?

All figures are in OMR. Expected Loss follows the Basel formula
EL = PD × LGD × EAD, with PD proxied from the risk tier and LGD from the
loan's collateral type.

Endpoint:
  GET /analytics/portfolio   — sector / country / loan-type / aging / EL / trend
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.client import Client
from app.models.loan import Loan, LoanStatus
from app.models.risk_score import RiskScore, RiskTier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["Portfolio Analytics"])

# PD proxy per risk tier and LGD per collateral type — same assumptions the
# stress-test engine uses, kept consistent so numbers reconcile across screens.
_PD_BY_TIER = {"LOW": 0.01, "MEDIUM": 0.04, "HIGH": 0.12, "VERY_HIGH": 0.28, "CRITICAL": 0.55}
_LGD_BY_COLLATERAL = {
    "PROPERTY": 0.25, "SECURITIES": 0.30, "VEHICLE": 0.45,
    "NONE": 0.75, None: 0.75, "": 0.75,
}


def _latest_score_map(db: Session) -> Dict[str, RiskScore]:
    rows = (
        db.query(RiskScore)
        .order_by(RiskScore.client_id, desc(RiskScore.scored_at))
        .all()
    )
    out: Dict[str, RiskScore] = {}
    for s in rows:
        if s.client_id not in out:
            out[s.client_id] = s
    return out


@router.get(
    "/portfolio",
    summary="Portfolio Analytics Dashboard Data",
    description=(
        "Returns concentration, quality, and expected-loss analytics for the whole "
        "book: exposure by industry sector, exposure by country, loan-type mix, "
        "delinquency aging buckets, expected credit loss (PD×LGD×EAD), and a "
        "risk-score trend series."
    ),
)
def portfolio_analytics(db: Session = Depends(get_db)) -> dict:
    clients = {c.id: c for c in db.query(Client).all()}
    loans = db.query(Loan).all()
    scores = _latest_score_map(db)

    # ── Exposure by sector & country (from client latest scores) ──────────────
    by_sector: Dict[str, float] = defaultdict(float)
    by_country: Dict[str, float] = defaultdict(float)
    for cid, s in scores.items():
        c = clients.get(cid)
        if not c:
            continue
        debt = s.total_outstanding_debt or 0.0
        sector = c.industry_sector or ("Retail Banking"
                 if (getattr(c.client_type, "value", c.client_type) == "RETAIL") else "Unclassified")
        by_sector[sector] += debt
        by_country[c.country_of_residence or "??"] += debt

    # ── Loan-type mix & delinquency aging ─────────────────────────────────────
    by_loan_type: Dict[str, dict] = defaultdict(lambda: {"count": 0, "balance": 0.0})
    aging = {"CURRENT": 0.0, "1-29": 0.0, "30-89": 0.0, "90+": 0.0}
    status_counts: Dict[str, int] = defaultdict(int)
    total_ead = 0.0
    for l in loans:
        bal = l.outstanding_balance or 0.0
        by_loan_type[l.loan_type]["count"] += 1
        by_loan_type[l.loan_type]["balance"] += bal
        status_counts[l.status] += 1
        if l.status == LoanStatus.PAID_OFF.value:
            continue
        total_ead += bal
        dpd = l.days_past_due or 0
        if dpd == 0:
            aging["CURRENT"] += bal
        elif dpd < 30:
            aging["1-29"] += bal
        elif dpd < 90:
            aging["30-89"] += bal
        else:
            aging["90+"] += bal

    # ── Expected Loss: EL = PD × LGD × EAD ────────────────────────────────────
    # PD from the owning client's tier; LGD from the loan's collateral.
    expected_loss = 0.0
    el_by_tier: Dict[str, float] = defaultdict(float)
    for l in loans:
        if l.status == LoanStatus.PAID_OFF.value:
            continue
        s = scores.get(l.client_id)
        tier = s.risk_tier if s else "MEDIUM"
        pd = _PD_BY_TIER.get(tier, 0.04)
        lgd = _LGD_BY_COLLATERAL.get(l.collateral_type, 0.75)
        el = pd * lgd * (l.outstanding_balance or 0.0)
        expected_loss += el
        el_by_tier[tier] += el

    # ── Risk-score trend (portfolio average by day) ───────────────────────────
    trend_rows = (
        db.query(
            func.date(RiskScore.scored_at).label("day"),
            func.avg(RiskScore.composite_score).label("avg_score"),
            func.count(RiskScore.id).label("n"),
        )
        .group_by(func.date(RiskScore.scored_at))
        .order_by(func.date(RiskScore.scored_at))
        .all()
    )
    trend = [
        {"date": str(r.day), "avg_score": round(r.avg_score or 0, 2), "scored": r.n}
        for r in trend_rows
    ]

    def top_sorted(d: Dict[str, float], n: int = 10) -> List[dict]:
        items = sorted(d.items(), key=lambda kv: kv[1], reverse=True)[:n]
        return [{"label": k, "value": round(v, 2)} for k, v in items]

    return {
        "generated_at": datetime.now(timezone.utc),
        "reporting_currency": "OMR",
        "total_clients": len(clients),
        "total_loans": len(loans),
        "total_ead_omr": round(total_ead, 2),
        "expected_loss_omr": round(expected_loss, 2),
        "expected_loss_ratio_pct": round((expected_loss / total_ead * 100) if total_ead else 0.0, 2),
        "exposure_by_sector": top_sorted(by_sector),
        "exposure_by_country": top_sorted(by_country),
        "loan_type_mix": [
            {"label": k, "count": v["count"], "balance": round(v["balance"], 2)}
            for k, v in sorted(by_loan_type.items(), key=lambda kv: kv[1]["balance"], reverse=True)
        ],
        "delinquency_aging": [{"bucket": k, "balance": round(v, 2)} for k, v in aging.items()],
        "loan_status_counts": dict(status_counts),
        "expected_loss_by_tier": [
            {"tier": t, "expected_loss": round(el_by_tier.get(t, 0.0), 2)}
            for t in [x.value for x in RiskTier]
        ],
        "score_trend": trend,
    }
