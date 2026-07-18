#!/usr/bin/env python3
"""
Seed Script — Risk Intelligence System
=========================================
Populates the Neon PostgreSQL database with realistic demo data suitable
for a professional portfolio demonstration.

Data generated:
  • 60 clients  (mix of retail individuals + international corporates)
  • 1–3 loans per client  (various types and statuses)
  • 8–20 transactions per client  (spanning last 90 days)
  • 1 risk score per client  (deliberately spread across all tiers)
  • 12 anomaly flags  (HIGH/CRITICAL severity for visual impact)
  • 6 AI alert records  (adverse media, scores 6–9)

Usage:
  python seed_db.py                     # reads DATABASE_URL from .env
  DATABASE_URL=postgresql://... python seed_db.py

Safety:
  The script is idempotent — if clients already exist it will skip seeding
  and exit cleanly. Run with --force to wipe and re-seed.
"""

import argparse
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

# ── Load .env before anything else ───────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

import re as _re
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ── Resolve DATABASE_URL ─────────────────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set.")
    print("  Set it in .env or pass as an env var before running this script.")
    sys.exit(1)

# Normalise to pg8000 dialect (same logic as app/database.py)
_need_ssl = False
if "postgresql" in DATABASE_URL and "pg8000" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql+psycopg2://", "postgresql+pg8000://", 1)
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+pg8000://", 1)
    # pg8000 doesn't understand sslmode or channel_binding query params — strip them
    # and instead pass ssl=True via connect_args
    if "sslmode=require" in DATABASE_URL:
        _need_ssl = True
    DATABASE_URL = _re.sub(r"[&?]channel_binding=[^&]*", "", DATABASE_URL)
    DATABASE_URL = _re.sub(r"[&?]sslmode=[^&]*", "", DATABASE_URL)
    DATABASE_URL = _re.sub(r"\?&", "?", DATABASE_URL)
    DATABASE_URL = DATABASE_URL.rstrip("?")

import ssl as _ssl
_connect_args: dict = {}
if _need_ssl:
    _ssl_ctx = _ssl.create_default_context()
    _ssl_ctx.check_hostname = False
    _ssl_ctx.verify_mode = _ssl.CERT_NONE
    _connect_args["ssl_context"] = _ssl_ctx

engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=_connect_args)
Session = sessionmaker(bind=engine)

# ── Import ORM models (creates tables if missing) ─────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.database import Base
from app.models.client import Client, ClientType
from app.models.loan import Loan, LoanType, LoanStatus
from app.models.transaction import Transaction, TransactionType
from app.models.risk_score import RiskScore, RiskTier
from app.models.anomaly import AnomalyFlag, AnomalyType, AnomalySeverity
from app.models.ai_alert import AIAlert

Base.metadata.create_all(engine)

# ─────────────────────────────────────────────────────────────────────────────
# Master data tables
# ─────────────────────────────────────────────────────────────────────────────

# Fictional retail individuals. Any resemblance to real persons is coincidental.
RETAIL_NAMES = [
    "James Carter", "Sofia Rossi", "Liam O'Brien",
    "Amara Okafor", "Noah Bergström", "Priya Nair",
    "Diego Fernández", "Hana Suzuki", "Omar Haddad",
    "Elena Petrova", "Marcus Cole", "Yuki Tanaka",
    "Aisha Khan", "Lucas Almeida", "Freya Andersen",
    "Rahul Mehta", "Chloe Dubois", "Tomas Novak",
    "Ingrid Larsen", "Samuel Adeyemi", "Wei Chen",
    "Isabella Conti", "Daniel Kowalski", "Layla Hassan",
    "Ethan Brooks", "Mei Lin", "Andrei Popescu",
    "Grace Mwangi", "Viktor Ivanov", "Nadia Rahman",
]

# Fictional corporate entities. Any resemblance to real companies is coincidental.
CORPORATE_NAMES = [
    "Harbor Logistics & Shipping LLC",      "Verdant Renewable Energy PLC",
    "Continental Infrastructure Holdings",  "Loomis Textile Manufacturing Co.",
    "Northgate Port Development Corp.",      "Ferrum Steel Industries Ltd.",
    "Keystone Real Estate LLC",             "Greenfield Agricultural Cooperative",
    "Freeport Trade Investments Ltd.",      "Meridian Financial Services PLC",
    "Transit Integrated Mobility Co.",      "Catalyst Petrochemical Solutions",
    "Summit Capital Group",                 "Continental Trade Finance SARL",
    "Apex Pharmaceutical Distributors",     "Indus Valley Technology Partners",
    "Pacific Rim Commodities Ltd.",         "Nordic Shipping & Logistics AB",
    "Horizon Fintech Ventures LLC",         "Atlas Construction & Engineering",
    "BlueWave Marine Services",             "Pinnacle Healthcare Holdings",
    "Crescent Private Equity Fund",         "Silvergate Asset Management",
    "Triton Energy & Resources Corp.",      "Cardinal Agribusiness International",
    "Vanguard Telecom Solutions",           "Cobalt Mining & Minerals Ltd.",
    "Fortis Insurance Brokers",             "Summit Infrastructure REIT",
]

SECTORS = [
    "Logistics & Supply Chain", "Renewable Energy", "Infrastructure & Construction",
    "Textiles & Manufacturing", "Port & Maritime", "Steel & Metals",
    "Real Estate & Property", "Agriculture & Food", "Free Zone & Trade",
    "Financial Services", "Transport & Aviation", "Petrochemicals",
    "Capital Markets", "Trade Finance", "Pharmaceuticals & Healthcare",
    "Technology & Fintech", "Commodities Trading", "Shipping",
    "Fintech & Payments", "Engineering & Construction",
]

COUNTRIES = ["US", "GB", "DE", "FR", "SG", "IN", "AE", "BR", "JP", "ZA", "AU", "CA"]
# Base reporting currency is Omani Rial (OMR). A minority of transactions are
# booked in foreign currencies (still reported in OMR-equivalent on the dashboard).
CURRENCIES = ["OMR", "OMR", "OMR", "OMR", "USD", "GBP", "EUR", "AED"]
CITIES = {
    "US": ["New York", "Miami", "Houston"],
    "GB": ["London", "Manchester"],
    "DE": ["Frankfurt", "Hamburg"],
    "FR": ["Paris", "Lyon"],
    "SG": ["Singapore"],
    "IN": ["Mumbai", "New Delhi"],
    "AE": ["Dubai", "Abu Dhabi"],
    "BR": ["São Paulo", "Rio de Janeiro"],
    "JP": ["Tokyo", "Osaka"],
    "ZA": ["Johannesburg", "Cape Town"],
    "AU": ["Sydney", "Melbourne"],
    "CA": ["Toronto", "Vancouver"],
}

MERCHANT_CATEGORIES = [
    "Wire Transfer", "Trade Finance", "FX Exchange", "ATM Withdrawal",
    "Payroll Credit", "Utilities", "Insurance Premium", "Real Estate",
    "Healthcare", "Retail Purchase", "Fuel & Transport", "Government Fees",
]

ANOMALY_TEMPLATES = [
    (AnomalyType.STRUCTURING, AnomalySeverity.CRITICAL,
     "Detected 4 cash deposits of OMR 9,100–9,800 within 48 hours — classic smurfing pattern below CTR threshold.",
     "AML-STR-001"),
    (AnomalyType.VELOCITY, AnomalySeverity.HIGH,
     "11 wire transfers executed within 55-minute window — velocity limit of 8/hr exceeded.",
     "AML-VEL-002"),
    (AnomalyType.LARGE_CASH, AnomalySeverity.HIGH,
     "Single cash deposit of OMR 47,500 — exceeds BSA Currency Transaction Report (CTR) threshold.",
     "AML-CASH-003"),
    (AnomalyType.LOCATION_MISMATCH, AnomalySeverity.HIGH,
     "Card transaction in Singapore at 14:22 UTC followed by ATM withdrawal in London at 14:51 UTC — geographically impossible.",
     "AML-GEO-004"),
    (AnomalyType.HIGH_RISK_COUNTERPARTY, AnomalySeverity.CRITICAL,
     "Outbound wire to entity on OFAC SDN List. Transaction flagged for mandatory SAR filing within 30 days.",
     "AML-OFC-005"),
    (AnomalyType.ROUND_AMOUNT_PATTERN, AnomalySeverity.MEDIUM,
     "Eight consecutive transactions in exact multiples of OMR 5,000 — indicative of artificial structuring.",
     "AML-RND-006"),
    (AnomalyType.DORMANT_ACCOUNT_SPIKE, AnomalySeverity.HIGH,
     "Account dormant for 127 days. Sudden inflow of OMR 215,000 from three unrelated counterparties.",
     "AML-DRM-007"),
    (AnomalyType.STRUCTURING, AnomalySeverity.HIGH,
     "Seven transactions ranging OMR 9,200–9,750 across 5 business days — structured to avoid FinCEN reporting.",
     "AML-STR-008"),
    (AnomalyType.VELOCITY, AnomalySeverity.CRITICAL,
     "19 outbound transfers totalling OMR 380,000 executed in 2 hours — automated layering pattern detected.",
     "AML-VEL-009"),
    (AnomalyType.LARGE_CASH, AnomalySeverity.CRITICAL,
     "Cash deposit of OMR 125,000 — no documented business purpose. Enhanced due diligence required.",
     "AML-CASH-010"),
    (AnomalyType.HIGH_RISK_COUNTERPARTY, AnomalySeverity.HIGH,
     "Payments routed through correspondent bank in jurisdiction with FATF deficiency notice.",
     "AML-OFC-011"),
    (AnomalyType.LOCATION_MISMATCH, AnomalySeverity.HIGH,
     "POS transaction in Frankfurt and ATM withdrawal in Toronto within 35 minutes — potential card cloning.",
     "AML-GEO-012"),
]

# NOTE: All entries below are entirely fictional and generated for demonstration
# only. Company names, allegations, and URLs are synthetic — any resemblance to
# real organisations, individuals, or events is coincidental. Source URLs point
# to example.com placeholders on purpose so nothing links to real reporting.
AI_ALERT_DATA = [
    (9, "Northgate Port Development Corp.",
     "Regulator reportedly investigating alleged facilitation of transactions for sanctioned entities. Potential enforcement penalties under review. Regulatory enforcement risk is critical.",
     "https://example.com/news/northgate-sanctions-probe"),
    (8, "Verdant Renewable Energy PLC",
     "Energy firm under regulatory inquiry following whistleblower allegations of inflated EPC contract valuations. CEO placed on administrative leave pending investigation.",
     "https://example.com/business/verdant-inquiry"),
    (7, "Harbor Logistics & Shipping LLC",
     "Customs authority has initiated an audit of shipment manifests. Potential AML exposure related to underdeclared cargo valuations across 18 consignments.",
     "https://example.com/article/logistics-audit"),
    (8, "Summit Capital Group",
     "Securities regulator issued a cease-and-desist for unlicensed fund management activities. Asset freeze order pending court hearing.",
     "https://example.com/markets/summit-capital-action"),
    (6, "Triton Energy & Resources Corp.",
     "Named in an investigative report alleging a shell-company network used to obscure beneficial ownership of resource-extraction revenues.",
     "https://example.com/investigations/triton-energy"),
    (9, "Crescent Private Equity Fund",
     "International red notice reportedly issued for a fund manager in connection with an alleged EUR 340M investment fraud scheme targeting institutional investors.",
     "https://example.com/notices/crescent-fund"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
rng = random.Random(42)  # fixed seed for reproducibility

def _uid() -> str:
    return str(uuid4())

def _ago(days: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)

def _date_ago(days: int) -> date:
    return (datetime.now(timezone.utc) - timedelta(days=days)).date()


def _score_to_tier(score: float) -> str:
    if score < 35:  return RiskTier.LOW.value
    if score < 55:  return RiskTier.MEDIUM.value
    if score < 70:  return RiskTier.HIGH.value
    if score < 85:  return RiskTier.VERY_HIGH.value
    return RiskTier.CRITICAL.value


# ─────────────────────────────────────────────────────────────────────────────
# Seeding functions
# ─────────────────────────────────────────────────────────────────────────────
def seed_clients(session) -> list[Client]:
    clients = []

    # --- 30 Retail (individuals) ---
    retail_scores = (
        [rng.uniform(10, 34) for _ in range(9)]   # LOW
        + [rng.uniform(35, 54) for _ in range(8)]  # MEDIUM
        + [rng.uniform(55, 69) for _ in range(7)]  # HIGH
        + [rng.uniform(70, 84) for _ in range(4)]  # VERY_HIGH
        + [rng.uniform(85, 99) for _ in range(2)]  # CRITICAL
    )
    rng.shuffle(retail_scores)

    for i, name in enumerate(RETAIL_NAMES):
        is_pep = (i % 15 == 0)
        kyc = "VERIFIED" if i % 7 != 0 else ("PENDING" if i % 3 == 0 else "EXPIRED")
        c = Client(
            id=_uid(), client_type=ClientType.RETAIL, name=name,
            external_credit_score=rng.randint(400, 820),
            annual_income=rng.uniform(8_000, 85_000),
            debt_to_income_ratio=rng.uniform(0.08, 0.62),
            country_of_residence=rng.choice(COUNTRIES),
            is_pep=is_pep, kyc_status=kyc,
            created_at=_ago(rng.uniform(60, 730)),
        )
        c._target_score = retail_scores[i]
        clients.append(c)
        session.add(c)

    # --- 30 Corporate (international) ---
    corp_scores = (
        [rng.uniform(10, 34) for _ in range(8)]   # LOW
        + [rng.uniform(35, 54) for _ in range(8)]  # MEDIUM
        + [rng.uniform(55, 69) for _ in range(7)]  # HIGH
        + [rng.uniform(70, 84) for _ in range(4)]  # VERY_HIGH
        + [rng.uniform(85, 99) for _ in range(3)]  # CRITICAL
    )
    rng.shuffle(corp_scores)

    for i, corp in enumerate(CORPORATE_NAMES):
        country = rng.choice(COUNTRIES)
        is_pep = (i % 20 == 0)
        kyc = "VERIFIED" if i % 5 != 0 else "PENDING"
        c = Client(
            id=_uid(), client_type=ClientType.CORPORATE, name=corp,
            external_credit_score=rng.randint(500, 830),
            annual_income=rng.uniform(500_000, 50_000_000),
            debt_to_income_ratio=rng.uniform(0.10, 0.75),
            country_of_residence=country,
            industry_sector=SECTORS[i % len(SECTORS)],
            years_in_operation=rng.randint(2, 45),
            is_pep=is_pep, kyc_status=kyc,
            created_at=_ago(rng.uniform(90, 1825)),
        )
        c._target_score = corp_scores[i]
        clients.append(c)
        session.add(c)

    session.flush()
    return clients


def seed_loans(session, clients: list[Client]):
    loan_types = [lt.value for lt in LoanType]
    statuses_weighted = (
        ["CURRENT"] * 6 + ["DELINQUENT"] * 2 + ["DEFAULT"] * 1 + ["PAID_OFF"] * 1
    )
    collateral_types = ["NONE", "PROPERTY", "VEHICLE", "SECURITIES", "NONE"]

    for client in clients:
        n_loans = rng.randint(1, 3)
        for _ in range(n_loans):
            principal = rng.uniform(5_000, 800_000)
            origination_days_ago = rng.randint(180, 2190)
            maturity_in = rng.randint(365, 3650)
            status = rng.choice(statuses_weighted)
            dpd = 0
            if status == "DELINQUENT": dpd = rng.randint(30, 89)
            elif status == "DEFAULT":  dpd = rng.randint(90, 400)

            session.add(Loan(
                id=_uid(), client_id=client.id,
                loan_type=rng.choice(loan_types),
                loan_amount=principal,
                outstanding_balance=principal * rng.uniform(0.1, 0.98),
                interest_rate=rng.uniform(3.5, 18.5),
                status=status,
                origination_date=_date_ago(origination_days_ago),
                maturity_date=_date_ago(origination_days_ago - maturity_in),
                days_past_due=dpd,
                collateral_type=rng.choice(collateral_types),
                collateral_value=principal * rng.uniform(0.5, 1.6) if status != "NONE" else None,
            ))


def seed_transactions(session, clients: list[Client]):
    tx_types = [t.value for t in TransactionType]
    for client in clients:
        n_tx = rng.randint(8, 20)
        country = client.country_of_residence or "US"
        for _ in range(n_tx):
            tx_country = rng.choice([country, rng.choice(COUNTRIES)])
            days_ago = rng.uniform(0.1, 90)
            session.add(Transaction(
                id=_uid(), client_id=client.id,
                amount=rng.uniform(50, 75_000),
                currency=rng.choice(CURRENCIES),
                transaction_type=rng.choice(tx_types),
                timestamp=_ago(days_ago),
                location_country=tx_country,
                location_city=rng.choice(CITIES.get(tx_country, ["Unknown"])),
                merchant_category=rng.choice(MERCHANT_CATEGORIES),
                counterparty_id=f"CPT-{rng.randint(10000,99999)}",
                status="COMPLETED",
            ))


def seed_risk_scores(session, clients: list[Client]):
    for client in clients:
        target = getattr(client, "_target_score", rng.uniform(10, 90))
        # Back-calculate components that produce this composite score
        # composite = 0.4*credit + 0.3*behavioural + 0.3*exposure + adjustments
        pep_adj = 10.0 if client.is_pep else 0.0
        kyc_adj = 15.0 if client.kyc_status != "VERIFIED" else 0.0
        base = max(0.0, target - pep_adj - kyc_adj)
        credit_h = min(100, max(0, base * rng.uniform(0.8, 1.15)))
        behavioural = min(100, max(0, base * rng.uniform(0.75, 1.20)))
        exposure = min(100, max(0, base * rng.uniform(0.80, 1.10)))
        composite = min(99.9, 0.4 * credit_h + 0.3 * behavioural + 0.3 * exposure + pep_adj + kyc_adj)

        session.add(RiskScore(
            id=_uid(), client_id=client.id,
            composite_score=round(composite, 2),
            risk_tier=_score_to_tier(composite),
            credit_history_score=round(credit_h, 2),
            behavioral_score=round(behavioural, 2),
            exposure_score=round(exposure, 2),
            pep_adjustment=pep_adj,
            kyc_adjustment=kyc_adj,
            scored_at=_ago(rng.uniform(0, 3)),
            model_version="2.1.0",
            active_loans_count=rng.randint(0, 4),
            total_outstanding_debt=rng.uniform(0, 900_000),
            transactions_analyzed=rng.randint(5, 90),
        ))


def seed_anomaly_flags(session, clients: list[Client]):
    # Use the highest-risk clients for anomaly flags
    sorted_clients = sorted(clients, key=lambda c: getattr(c, "_target_score", 0), reverse=True)
    target_clients = sorted_clients[:12]

    for i, (atype, severity, desc, rule) in enumerate(ANOMALY_TEMPLATES):
        client = target_clients[i]
        amount = rng.uniform(8_000, 250_000)
        session.add(AnomalyFlag(
            id=_uid(), client_id=client.id,
            anomaly_type=atype.value,
            severity=severity.value,
            description=desc,
            rule_triggered=rule,
            flagged_amount=round(amount, 2),
            flagged_at=_ago(rng.uniform(0.1, 30)),
            status=rng.choice(["OPEN", "OPEN", "UNDER_REVIEW", "OPEN"]),
        ))


def seed_ai_alerts(session):
    for score, company, summary, source in AI_ALERT_DATA:
        days_ago = random.uniform(0.5, 14)
        session.add(AIAlert(
            id=_uid(),
            company_name=company,
            risk_score=score,
            risk_summary=summary,
            source_article=source,
            source="N8N_WORKFLOW",
            is_acknowledged=0,
            created_at=_ago(days_ago),
        ))


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Seed the Risk Intelligence demo database.")
    parser.add_argument("--force", action="store_true", help="Drop all data and re-seed")
    args = parser.parse_args()

    with Session() as session:
        existing = session.execute(text("SELECT COUNT(*) FROM clients")).scalar_one()
        if existing > 0 and not args.force:
            print(f"Database already contains {existing} clients. Skipping seed.")
            print("Run with --force to wipe and re-seed.")
            return

        if args.force and existing > 0:
            print("--force flag set. Wiping existing data…")
            for table in ["anomaly_flags", "risk_scores", "transactions", "loans", "ai_alerts", "clients"]:
                session.execute(text(f"DELETE FROM {table}"))
            session.commit()
            print("  ✓ Tables cleared.")

        print("Seeding clients…")
        clients = seed_clients(session)
        print(f"  ✓ {len(clients)} clients created")

        print("Seeding loans…")
        seed_loans(session, clients)
        print("  ✓ Loans created")

        print("Seeding transactions…")
        seed_transactions(session, clients)
        print("  ✓ Transactions created")

        print("Seeding risk scores…")
        seed_risk_scores(session, clients)
        print("  ✓ Risk scores created")

        print("Seeding anomaly flags…")
        seed_anomaly_flags(session, clients)
        print("  ✓ 12 anomaly flags created")

        print("Seeding AI alerts…")
        seed_ai_alerts(session)
        print("  ✓ 6 AI adverse media alerts created")

        session.commit()

    print("\n✅ Database seeded successfully.")
    print("   Breakdown:")
    print(f"   • {len(RETAIL_NAMES)} retail clients (individuals)")
    print(f"   • {len(CORPORATE_NAMES)} corporate clients (international)")
    print(f"   • Risk tiers: LOW / MEDIUM / HIGH / VERY HIGH / CRITICAL distributed")
    print(f"   • 12 AML anomaly flags (HIGH + CRITICAL)")
    print(f"   • 6 AI adverse media alerts (risk scores 6–9)")


if __name__ == "__main__":
    main()
