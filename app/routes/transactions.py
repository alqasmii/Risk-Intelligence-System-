"""
Transaction Routes — Live Transaction Monitoring API
====================================================
Powers the real-time "Live Transactions" operations screen. In a production
system these rows would arrive from a streaming source (Kafka / Kinesis); here
they are served from the persisted transaction store with the same query shape
a streaming consumer would use — newest-first, filterable by type / geography /
amount — so the frontend can poll for a live-feed experience.

Endpoints:
  GET /transactions/          — Paginated, filterable transaction feed (newest first)
  GET /transactions/stats     — Rolling KPI strip (volume, wire %, cash %, cross-border)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.client import Client
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/transactions", tags=["Live Transactions"])

# Transaction types that carry elevated AML scrutiny — surfaced to the UI so the
# feed can visually flag them without re-deriving the rule client-side.
_HIGH_RISK_TYPES = {"WIRE", "CASH"}
# Amount (OMR) above which a single transaction is worth a second look.
_LARGE_AMOUNT = 20_000.0


def _risk_flag(tx: Transaction, home_country: Optional[str]) -> Optional[str]:
    """Cheap, explainable risk annotation for a single row."""
    if tx.transaction_type == "WIRE":
        return "WIRE"
    if tx.transaction_type == "CASH" and (tx.amount or 0) >= 10_000:
        return "LARGE_CASH"
    if (tx.amount or 0) >= _LARGE_AMOUNT:
        return "HIGH_VALUE"
    if home_country and tx.location_country and tx.location_country != home_country:
        return "CROSS_BORDER"
    return None


@router.get(
    "/",
    summary="Live Transaction Feed",
    description=(
        "Returns the transaction feed newest-first with optional filters. "
        "The frontend polls this endpoint to render a live-updating monitoring "
        "table. Each row carries a lightweight risk annotation (WIRE, LARGE_CASH, "
        "HIGH_VALUE, CROSS_BORDER) for at-a-glance triage."
    ),
)
def list_transactions(
    tx_type: Optional[str] = Query(None, description="CREDIT|DEBIT|WIRE|CASH|REVERSAL"),
    country: Optional[str] = Query(None, description="ISO alpha-2 location country"),
    min_amount: Optional[float] = Query(None, ge=0, description="Minimum OMR amount"),
    client_id: Optional[str] = Query(None),
    high_risk_only: bool = Query(False, description="Only WIRE / CASH transactions"),
    skip: int = Query(0, ge=0),
    limit: int = Query(40, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    query = db.query(Transaction)

    if tx_type:
        query = query.filter(Transaction.transaction_type == tx_type.upper())
    if country:
        query = query.filter(Transaction.location_country == country.upper())
    if min_amount is not None:
        query = query.filter(Transaction.amount >= min_amount)
    if client_id:
        query = query.filter(Transaction.client_id == client_id)
    if high_risk_only:
        query = query.filter(Transaction.transaction_type.in_(list(_HIGH_RISK_TYPES)))

    total = query.count()
    rows = (
        query.order_by(desc(Transaction.timestamp))
        .offset(skip)
        .limit(limit)
        .all()
    )

    # Resolve client names + home countries in one round-trip (avoid N+1).
    client_ids = {t.client_id for t in rows}
    clients = {
        c.id: c
        for c in db.query(Client).filter(Client.id.in_(client_ids)).all()
    } if client_ids else {}

    items = []
    for t in rows:
        c = clients.get(t.client_id)
        items.append({
            "id": t.id,
            "client_id": t.client_id,
            "client_name": c.name if c else "Unknown",
            "amount": round(t.amount or 0.0, 3),
            "currency": t.currency,
            "transaction_type": t.transaction_type,
            "timestamp": t.timestamp,
            "location_country": t.location_country,
            "location_city": t.location_city,
            "merchant_category": t.merchant_category,
            "status": t.status,
            "risk_flag": _risk_flag(t, c.country_of_residence if c else None),
        })

    return {"total": total, "skip": skip, "limit": limit, "items": items}


@router.get(
    "/stats",
    summary="Live Transaction KPIs",
    description=(
        "Rolling aggregates for the Live Transactions KPI strip: total volume and "
        "value, wire / cash share, and cross-border count. Computed over the most "
        "recent window of transactions to mimic a streaming dashboard."
    ),
)
def transaction_stats(
    window_hours: int = Query(24, ge=1, le=720, description="Look-back window in hours"),
    db: Session = Depends(get_db),
) -> dict:
    # The synthetic dataset is spread around "now"; anchor the window on the most
    # recent transaction so the KPIs are never empty regardless of seed timing.
    latest = db.query(func.max(Transaction.timestamp)).scalar()
    anchor = latest or datetime.now(timezone.utc)
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    since = anchor - timedelta(hours=window_hours)

    window_q = db.query(Transaction).filter(Transaction.timestamp >= since)

    total_count = window_q.count()
    total_value = db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(
        Transaction.timestamp >= since
    ).scalar() or 0.0

    by_type = dict(
        db.query(Transaction.transaction_type, func.count())
        .filter(Transaction.timestamp >= since)
        .group_by(Transaction.transaction_type)
        .all()
    )
    wire_count = by_type.get("WIRE", 0)
    cash_count = by_type.get("CASH", 0)

    # Cross-border = transaction booked in a country other than the client's home.
    cross_border = (
        db.query(func.count(Transaction.id))
        .join(Client, Client.id == Transaction.client_id)
        .filter(
            Transaction.timestamp >= since,
            Transaction.location_country.isnot(None),
            Client.country_of_residence.isnot(None),
            Transaction.location_country != Client.country_of_residence,
        )
        .scalar() or 0
    )

    def pct(n):
        return round((n / total_count * 100), 1) if total_count else 0.0

    return {
        "window_hours": window_hours,
        "as_of": anchor,
        "total_count": total_count,
        "total_value_omr": round(total_value, 3),
        "wire_count": wire_count,
        "wire_pct": pct(wire_count),
        "cash_count": cash_count,
        "cash_pct": pct(cash_count),
        "cross_border_count": cross_border,
        "cross_border_pct": pct(cross_border),
        "by_type": by_type,
    }
