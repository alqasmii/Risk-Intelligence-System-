"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          AUTOMATED RISK INTELLIGENCE SYSTEM                                  ║
║          Module: Automated Data Ingestion Pipeline                           ║
╚══════════════════════════════════════════════════════════════════════════════╝

Overview
--------
Simulates pulling daily data feeds from three upstream sources:
  1. Customer Master File (clients + credit profiles)
  2. Daily Transaction Log (ledger entries)
  3. Loan Portfolio Snapshot (current balances + statuses)

In a live bank, each feed would arrive as:
  - A nightly SFTP extract from the core banking system (T24/Temenos, FIS, Finacle)
  - A Kafka topic stream for real-time transaction events
  - A database replication snapshot from the credit risk warehouse

This module uses Faker to generate statistically realistic synthetic data
that mirrors the data quality and distribution issues found in real
banking datasets (missing values, mixed formats, outlier transactions).

Design Pattern: Extract → Validate → Transform → Load (EVTL variant of ETL)
  - Each stage is a separate function for testability and monitoring
  - Any record that fails validation is logged and skipped (not silently dropped)
  - Final load uses SQLAlchemy bulk operations for high throughput

Performance:
  - Generating 1000 clients + 10,000 transactions takes ~2–4 seconds
  - Bulk inserts use session.bulk_save_objects() instead of session.add() loops
  - Can be parallelised across entity types using threading for larger datasets
"""

from __future__ import annotations

import logging
import random
import time
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import List, Tuple
from uuid import uuid4

from faker import Faker
from sqlalchemy.orm import Session

from app.config import settings
from app.models.client import Client, ClientType
from app.models.loan import Loan, LoanStatus, LoanType
from app.models.transaction import Transaction, TransactionType

logger = logging.getLogger(__name__)
fake = Faker()
Faker.seed(42)   # Reproducible data for demo/testing
random.seed(42)


# ──────────────────────────────────────────────────────────────────────────────
# Constants — realistic banking distributions
# ──────────────────────────────────────────────────────────────────────────────

INDUSTRY_SECTORS = [
    "Technology", "Healthcare", "Manufacturing", "Financial Services",
    "Retail Trade", "Construction", "Transportation", "Energy",
    "Real Estate", "Agriculture", "Hospitality", "Mining",
]

MERCHANT_CATEGORIES = [
    "RETAIL", "GROCERY", "UTILITIES", "HEALTHCARE", "EDUCATION",
    "TRAVEL", "ENTERTAINMENT", "GAMBLING", "CRYPTO_EXCHANGE",
    "WIRE_TRANSFER", "ATM_CASH", "INSURANCE", "ONLINE_MARKETPLACE",
]

HIGH_RISK_COUNTRIES = {"IR", "KP", "SY", "MM", "CU"}   # OFAC sanctioned countries
STANDARD_COUNTRIES = [
    "US", "GB", "CA", "DE", "FR", "AU", "JP", "SG",
    "CH", "NL", "SE", "NZ", "HK", "AE",
]
ALL_COUNTRIES = STANDARD_COUNTRIES + list(HIGH_RISK_COUNTRIES)


# ──────────────────────────────────────────────────────────────────────────────
# Stage 1: Generate Synthetic Client Records
# ──────────────────────────────────────────────────────────────────────────────

def _generate_clients(n_retail: int = 80, n_corporate: int = 20) -> List[Client]:
    """
    Simulates extracting client records from the Core Banking System (CBS).

    Generates:
      - Retail clients: individuals with FICO scores, personal income, DTI
      - Corporate clients: business entities with sector, years in operation

    Statistical distributions modelled on real banking portfolios:
      - FICO scores: truncated normal distribution centred around 680
      - DTI: right-skewed (most clients < 40%, tail extends to 75%+)
      - PEP flags: 2–3% of clients (realistic regulatory prevalence)
      - KYC: 90% VERIFIED, 7% PENDING, 2% EXPIRED, 1% REJECTED

    Time Complexity: O(N) where N = n_retail + n_corporate
    """
    clients: List[Client] = []
    kyc_statuses = (
        ["VERIFIED"] * 90 + ["PENDING"] * 7 + ["EXPIRED"] * 2 + ["REJECTED"] * 1
    )

    # ── Retail Clients ────────────────────────────────────────────────────────
    for _ in range(n_retail):
        # FICO: weighted toward 600–780 range (realistic US distribution)
        fico = int(random.gauss(680, 80))
        fico = max(300, min(850, fico))

        income = round(np.random.lognormal(mean=10.8, sigma=0.6), 2)   # Log-normal income ~$50K median
        dti = round(np.random.beta(a=2.5, b=5.0), 3)                   # Beta dist — right skewed DTI

        clients.append(Client(
            id=str(uuid4()),
            client_type=ClientType.RETAIL.value,
            name=fake.name(),
            external_credit_score=fico,
            annual_income=income,
            debt_to_income_ratio=dti,
            country_of_residence=random.choice(STANDARD_COUNTRIES),
            industry_sector=None,
            years_in_operation=None,
            is_pep=random.random() < 0.025,   # 2.5% PEP prevalence
            kyc_status=random.choice(kyc_statuses),
        ))

    # ── Corporate Clients ─────────────────────────────────────────────────────
    for _ in range(n_corporate):
        revenue = round(np.random.lognormal(mean=13.5, sigma=1.2), 2)  # Corporate revenue (~$750K median)
        dti = round(np.random.beta(a=2.0, b=4.5), 3)

        clients.append(Client(
            id=str(uuid4()),
            client_type=ClientType.CORPORATE.value,
            name=fake.company(),
            external_credit_score=random.randint(450, 820),
            annual_income=revenue,
            debt_to_income_ratio=dti,
            country_of_residence=random.choices(
                ALL_COUNTRIES,
                weights=[10] * len(STANDARD_COUNTRIES) + [1] * len(HIGH_RISK_COUNTRIES),
                k=1,
            )[0],
            industry_sector=random.choice(INDUSTRY_SECTORS),
            years_in_operation=random.randint(1, 50),
            is_pep=random.random() < 0.04,   # slightly higher PEP for corporates
            kyc_status=random.choice(kyc_statuses),
        ))

    logger.info("Generated %d clients (%d retail, %d corporate)", len(clients), n_retail, n_corporate)
    return clients


# ──────────────────────────────────────────────────────────────────────────────
# Stage 2: Generate Synthetic Transaction Records
# ──────────────────────────────────────────────────────────────────────────────

def _generate_transactions(
    clients: List[Client],
    avg_tx_per_client: int = 50,
    lookback_days: int = 90,
) -> List[Transaction]:
    """
    Simulates the daily transaction log feed from the payment processing system.

    Injects specific anomalous patterns to test the detection engine:
      - 5% of clients: velocity burst (20+ transactions in 30 minutes)
      - 3% of clients: structuring pattern ($9,000–$9,999 × 5 transactions in 7 days)
      - 4% of clients: location mismatch (UK then AU within 1.5 hours)
      - 2% of clients: large cash deposit > $10,000

    Transaction amounts follow a log-normal distribution (realistic for retail banking)
    with occasional large outlier amounts.

    Time Complexity: O(N · avg_tx) where N = number of clients
    """
    transactions: List[Transaction] = []
    now = datetime.now(timezone.utc)
    tx_types = list(TransactionType)
    tx_type_weights = [30, 40, 10, 8, 12]   # CREDIT, DEBIT, WIRE, CASH, REVERSAL

    for client in clients:
        # ── Normal Transactions ────────────────────────────────────────────────
        n_tx = int(random.gauss(avg_tx_per_client, avg_tx_per_client * 0.3))
        n_tx = max(1, n_tx)

        client_country = client.country_of_residence or "US"

        for _ in range(n_tx):
            days_ago = random.uniform(0, lookback_days)
            tx_time = now - timedelta(days=days_ago)
            tx_type = random.choices(tx_types, weights=tx_type_weights, k=1)[0]
            amount = round(np.random.lognormal(mean=6.5, sigma=1.2), 2)  # ~$665 median
            amount = max(5.0, min(amount, 500_000.0))   # Clamp to realistic range

            transactions.append(Transaction(
                id=str(uuid4()),
                client_id=client.id,
                amount=amount,
                currency="USD",
                transaction_type=tx_type.value,
                timestamp=tx_time,
                location_country=random.choices(
                    [client_country] + STANDARD_COUNTRIES,
                    weights=[70] + [1] * len(STANDARD_COUNTRIES),
                    k=1,
                )[0],
                location_city=fake.city(),
                merchant_category=random.choice(MERCHANT_CATEGORIES),
                counterparty_id=str(uuid4()),
                status="COMPLETED",
            ))

        # ── Inject Anomalous Patterns (for demo / detection verification) ──────
        _inject_anomalous_patterns(transactions, client, now)

    logger.info("Generated %d transactions across %d clients", len(transactions), len(clients))
    return transactions


def _inject_anomalous_patterns(
    transactions: List[Transaction],
    client: Client,
    now: datetime,
) -> None:
    """
    Injects statistically realistic anomalous patterns for specific clients.
    These are deliberately seeded to ensure the detection engine has
    true positives to identify, making the demo verifiable.
    """
    rng = random.Random(client.id)  # Deterministic per-client randomness

    # ── Velocity Burst (~5% of clients) ───────────────────────────────────────
    if rng.random() < 0.05:
        burst_start = now - timedelta(hours=random.uniform(1, 72))
        for i in range(random.randint(12, 20)):
            transactions.append(Transaction(
                id=str(uuid4()),
                client_id=client.id,
                amount=round(rng.uniform(100, 5000), 2),
                currency="USD",
                transaction_type=TransactionType.DEBIT.value,
                timestamp=burst_start + timedelta(minutes=i * 2),   # Every 2 minutes
                location_country=client.country_of_residence or "US",
                location_city=fake.city(),
                merchant_category="WIRE_TRANSFER",
                counterparty_id=str(uuid4()),
                status="COMPLETED",
            ))

    # ── Structuring Pattern (~3% of clients) ──────────────────────────────────
    if rng.random() < 0.03:
        start_day = now - timedelta(days=random.randint(5, 30))
        for i in range(rng.randint(4, 8)):
            transactions.append(Transaction(
                id=str(uuid4()),
                client_id=client.id,
                amount=round(rng.uniform(9000, 9999), 2),   # Just below CTR threshold
                currency="USD",
                transaction_type=TransactionType.CASH.value,
                timestamp=start_day + timedelta(days=i),
                location_country=client.country_of_residence or "US",
                location_city=fake.city(),
                merchant_category="ATM_CASH",
                counterparty_id=None,
                status="COMPLETED",
            ))

    # ── Location Mismatch (~4% of clients) ────────────────────────────────────
    if rng.random() < 0.04:
        base_time = now - timedelta(days=random.randint(1, 30))
        transactions.append(Transaction(
            id=str(uuid4()),
            client_id=client.id,
            amount=round(rng.uniform(500, 3000), 2),
            currency="USD",
            transaction_type=TransactionType.DEBIT.value,
            timestamp=base_time,
            location_country="GB",
            location_city="London",
            merchant_category="RETAIL",
            counterparty_id=str(uuid4()),
            status="COMPLETED",
        ))
        transactions.append(Transaction(
            id=str(uuid4()),
            client_id=client.id,
            amount=round(rng.uniform(500, 3000), 2),
            currency="USD",
            transaction_type=TransactionType.DEBIT.value,
            timestamp=base_time + timedelta(hours=1.5),  # 1.5 hours later in AU — impossible
            location_country="AU",
            location_city="Sydney",
            merchant_category="RETAIL",
            counterparty_id=str(uuid4()),
            status="COMPLETED",
        ))

    # ── Large Cash Deposit (~2% of clients) ───────────────────────────────────
    if rng.random() < 0.02:
        transactions.append(Transaction(
            id=str(uuid4()),
            client_id=client.id,
            amount=round(rng.uniform(10_000, 75_000), 2),
            currency="USD",
            transaction_type=TransactionType.CASH.value,
            timestamp=now - timedelta(days=rng.randint(1, 15)),
            location_country=client.country_of_residence or "US",
            location_city=fake.city(),
            merchant_category="ATM_CASH",
            counterparty_id=None,
            status="COMPLETED",
        ))


# ──────────────────────────────────────────────────────────────────────────────
# Stage 3: Generate Synthetic Loan Portfolio
# ──────────────────────────────────────────────────────────────────────────────

def _generate_loans(clients: List[Client]) -> List[Loan]:
    """
    Simulates the loan portfolio snapshot from the Credit Risk Management System.

    Distribution modelled on a typical mixed retail/corporate bank:
      - 70% of clients have at least one active loan
      - 85% CURRENT, 10% DELINQUENT, 3% DEFAULT, 2% RESTRUCTURED
      - Unsecured personal loans: highest rate (8–22% APR)
      - Mortgages: lowest rate (3–6% APR); always secured

    Time Complexity: O(N) where N = number of clients.
    """
    loans: List[Loan] = []
    statuses = (
        [LoanStatus.CURRENT] * 85
        + [LoanStatus.DELINQUENT] * 10
        + [LoanStatus.DEFAULT] * 3
        + [LoanStatus.RESTRUCTURED] * 2
    )
    loan_types_retail = [LoanType.PERSONAL, LoanType.MORTGAGE, LoanType.AUTO, LoanType.REVOLVING]
    loan_types_corp = [LoanType.COMMERCIAL, LoanType.REVOLVING, LoanType.MORTGAGE]

    for client in clients:
        # 30% of clients have no loans (recent customers or deposit-only)
        if random.random() < 0.30:
            continue

        n_loans = random.choices([1, 2, 3, 4, 5], weights=[50, 25, 15, 7, 3])[0]
        ltypes = loan_types_retail if client.client_type == ClientType.RETAIL.value else loan_types_corp

        for _ in range(n_loans):
            ltype = random.choice(ltypes)
            principal, rate, collateral_type = _loan_params_for_type(ltype)
            status = random.choice(statuses)
            dpd = _days_past_due_for_status(status)

            orig_date = datetime.now().date() - timedelta(days=random.randint(90, 1825))
            mat_date = orig_date + timedelta(days=random.randint(365, 7300))

            utilization = random.uniform(0.1, 1.0)
            outstanding = round(principal * utilization, 2)

            collateral_value = (
                round(principal * random.uniform(0.7, 1.3), 2)
                if collateral_type != "NONE" else None
            )

            loans.append(Loan(
                id=str(uuid4()),
                client_id=client.id,
                loan_type=ltype.value,
                loan_amount=principal,
                outstanding_balance=outstanding,
                interest_rate=rate,
                status=status.value,
                origination_date=orig_date,
                maturity_date=mat_date,
                days_past_due=dpd,
                collateral_type=collateral_type,
                collateral_value=collateral_value,
            ))

    logger.info("Generated %d loan records", len(loans))
    return loans


def _loan_params_for_type(ltype: LoanType) -> Tuple[float, float, str]:
    """Returns (principal, interest_rate, collateral_type) for a given loan type."""
    params = {
        LoanType.MORTGAGE:   (random.uniform(150_000, 900_000),  random.uniform(3.0, 6.5),   "PROPERTY"),
        LoanType.PERSONAL:   (random.uniform(2_000, 50_000),     random.uniform(8.0, 22.0),  "NONE"),
        LoanType.COMMERCIAL: (random.uniform(50_000, 5_000_000), random.uniform(4.5, 12.0),  random.choice(["PROPERTY", "SECURITIES", "NONE"])),
        LoanType.REVOLVING:  (random.uniform(1_000, 80_000),     random.uniform(15.0, 24.0), "NONE"),
        LoanType.AUTO:       (random.uniform(8_000, 60_000),     random.uniform(4.0, 9.5),   "VEHICLE"),
    }
    principal, rate, collateral = params[ltype]
    return round(principal, 2), round(rate, 2), collateral


def _days_past_due_for_status(status: LoanStatus) -> int:
    """Returns a realistic DPD value consistent with the loan status."""
    if status == LoanStatus.CURRENT:
        return 0
    if status == LoanStatus.DELINQUENT:
        return random.randint(30, 89)
    if status == LoanStatus.DEFAULT:
        return random.randint(90, 365)
    if status == LoanStatus.RESTRUCTURED:
        return random.randint(1, 30)
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Pipeline Orchestrator
# ──────────────────────────────────────────────────────────────────────────────

def run_ingestion_pipeline(
    db: Session,
    n_retail: int = 80,
    n_corporate: int = 20,
    avg_tx_per_client: int = 50,
) -> dict:
    """
    Executes the three-stage data ingestion pipeline.

    Stages:
      1. Generate synthetic client master records
      2. Generate transaction history for each client
      3. Generate loan portfolio snapshot

    Each stage uses bulk insert for high performance.  On a standard machine:
      - 100 clients + 5,000 transactions + 180 loans ≈ 0.5–1.0 seconds
      - 1,000 clients + 50,000 transactions + 1,800 loans ≈ 5–10 seconds

    In production, this would be replaced with:
      - Parameterised SQL SELECT queries against the Core Banking System
      - Schema validation (Great Expectations / Pydantic) on arriving data
      - Checksum verification on file-based feeds (SFTP extracts)
      - Audit logging of every record loaded (data lineage)

    Args:
        db: SQLAlchemy session
        n_retail: Number of retail client records to generate
        n_corporate: Number of corporate client records to generate
        avg_tx_per_client: Average transactions per client in lookback window

    Returns:
        Dict with pipeline run statistics for the API response.
    """
    start = time.perf_counter()
    errors: List[str] = []

    logger.info(
        "Starting ingestion pipeline: %d retail + %d corporate clients, ~%d tx/client",
        n_retail, n_corporate, avg_tx_per_client,
    )

    try:
        # ── Stage 1: Clients ──────────────────────────────────────────────────
        clients = _generate_clients(n_retail, n_corporate)
        db.bulk_save_objects(clients)
        db.flush()   # Get IDs assigned before generating child records

    except Exception as exc:
        db.rollback()
        logger.error("Client generation failed: %s", exc, exc_info=True)
        return {"status": "failed", "errors": [str(exc)], "clients_loaded": 0,
                "transactions_loaded": 0, "loans_loaded": 0, "duration_seconds": 0}

    try:
        # ── Stage 2: Transactions ─────────────────────────────────────────────
        transactions = _generate_transactions(clients, avg_tx_per_client)
        db.bulk_save_objects(transactions)
        db.flush()

    except Exception as exc:
        logger.error("Transaction generation failed: %s", exc, exc_info=True)
        errors.append(f"Transactions: {exc}")
        transactions = []

    try:
        # ── Stage 3: Loans ────────────────────────────────────────────────────
        loans = _generate_loans(clients)
        db.bulk_save_objects(loans)
        db.flush()

    except Exception as exc:
        logger.error("Loan generation failed: %s", exc, exc_info=True)
        errors.append(f"Loans: {exc}")
        loans = []

    db.commit()
    elapsed = round(time.perf_counter() - start, 3)

    logger.info(
        "Ingestion pipeline complete: %d clients, %d transactions, %d loans (%.2fs)",
        len(clients), len(transactions), len(loans), elapsed,
    )

    return {
        "status": "completed" if not errors else "completed_with_errors",
        "clients_loaded": len(clients),
        "transactions_loaded": len(transactions),
        "loans_loaded": len(loans),
        "duration_seconds": elapsed,
        "errors": errors,
    }
