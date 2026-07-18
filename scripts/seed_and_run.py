#!/usr/bin/env python3
"""
scripts/seed_and_run.py
=======================
Convenience CLI runner that executes the full end-to-end pipeline in a single
command — ideal for demos.  No API server needed.

Pipeline stages:
  1. Ingest — generate synthetic clients, transactions, and loans
  2. Score  — run the algorithmic risk scoring engine across all clients
  3. Scan   — run all 5 AML/Fraud anomaly detection rules
  4. Report — print a portfolio summary to the console

Usage:
    # From the project root (with venv activated):
    python scripts/seed_and_run.py

    # Custom sizes:
    python scripts/seed_and_run.py --retail 300 --corporate 50 --tx 40
"""

import argparse
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Make sure the project root is on sys.path so `app.*` imports resolve whether
# this script is run from the project root or from the scripts/ subdirectory.
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import SessionLocal, create_tables
from app.pipeline.ingestion import run_ingestion_pipeline
from app.engines.risk_scoring import score_portfolio
from app.engines.anomaly_detection import run_anomaly_scan
from app.models.risk_score import RiskScore, RiskTier
from app.models.anomaly import AnomalyFlag, AnomalySeverity
from sqlalchemy import func


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BAR = "=" * 64


def _header(text: str) -> None:
    print(f"\n{BAR}")
    print(f"  {text}")
    print(BAR)


def _print_summary(db) -> None:
    """Print a KPI summary table to stdout after the pipeline completes."""
    _header("PORTFOLIO RISK SUMMARY")

    # --- Tier distribution ---
    tier_counts = (
        db.query(RiskScore.risk_tier, func.count(RiskScore.id))
        .group_by(RiskScore.risk_tier)
        .all()
    )
    tier_order = [t.value for t in RiskTier]
    tier_map = {tier: count for tier, count in tier_counts}

    print("\n  Risk Tier Distribution:")
    print(f"  {'Tier':<15} {'Clients':>8}")
    print(f"  {'-'*23}")
    for tier in tier_order:
        count = tier_map.get(tier, 0)
        bar = "█" * min(count, 40)
        print(f"  {tier:<15} {count:>8}  {bar}")

    total_scored = sum(tier_map.values())
    print(f"\n  Total scored: {total_scored}")

    # --- Anomaly distribution ---
    _header("ANOMALY FLAG SUMMARY")

    sev_counts = (
        db.query(AnomalyFlag.severity, func.count(AnomalyFlag.id))
        .filter(AnomalyFlag.status == "OPEN")
        .group_by(AnomalyFlag.severity)
        .all()
    )
    sev_order = [s.value for s in AnomalySeverity]
    sev_map = {sev: count for sev, count in sev_counts}

    print("\n  Open Flags by Severity:")
    print(f"  {'Severity':<12} {'Count':>8}")
    print(f"  {'-'*20}")
    for sev in sev_order:
        count = sev_map.get(sev, 0)
        print(f"  {sev:<12} {count:>8}")

    total_flags = sum(sev_map.values())
    print(f"\n  Total open flags: {total_flags}")

    # --- Rule breakdown ---
    rule_counts = (
        db.query(AnomalyFlag.rule_triggered, func.count(AnomalyFlag.id))
        .filter(AnomalyFlag.status == "OPEN")
        .group_by(AnomalyFlag.rule_triggered)
        .all()
    )
    if rule_counts:
        print("\n  Open Flags by Detection Rule:")
        print(f"  {'Rule':<25} {'Count':>8}")
        print(f"  {'-'*33}")
        for rule, count in sorted(rule_counts, key=lambda x: -x[1]):
            print(f"  {rule:<25} {count:>8}")

    print(f"\n{BAR}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the full Risk Intelligence pipeline end-to-end."
    )
    parser.add_argument("--retail", type=int, default=200, help="Number of retail clients to generate (default: 200)")
    parser.add_argument("--corporate", type=int, default=40, help="Number of corporate clients to generate (default: 40)")
    parser.add_argument("--tx", type=int, default=30, help="Average transactions per client (default: 30)")
    parser.add_argument("--lookback", type=int, default=90, help="Anomaly scan lookback window in days (default: 90)")
    args = parser.parse_args()

    print(f"\n{'*' * 64}")
    print("  AUTOMATED RISK INTELLIGENCE SYSTEM — POC PIPELINE RUNNER")
    print(f"{'*' * 64}")
    print(f"  Retail clients   : {args.retail}")
    print(f"  Corporate clients: {args.corporate}")
    print(f"  Avg tx/client    : {args.tx}")
    print(f"  Anomaly lookback : {args.lookback} days")
    print(f"{'*' * 64}\n")

    # --- Initialise database ---
    _header("STAGE 0: Database Initialisation")
    create_tables()
    print("  Tables created / verified.")

    db = SessionLocal()

    try:
        # --- Stage 1: Ingest ---
        _header("STAGE 1: Data Ingestion Pipeline")
        t0 = time.perf_counter()
        ingest_result = run_ingestion_pipeline(
            db=db,
            n_retail=args.retail,
            n_corporate=args.corporate,
            avg_tx_per_client=args.tx,
        )
        t1 = time.perf_counter()
        print(f"  Clients     : {ingest_result['clients_loaded']}")
        print(f"  Transactions: {ingest_result['transactions_loaded']}")
        print(f"  Loans       : {ingest_result['loans_loaded']}")
        print(f"  Duration    : {t1 - t0:.2f}s")

        # --- Stage 2: Score ---
        _header("STAGE 2: Risk Scoring Engine")
        t0 = time.perf_counter()
        score_result = score_portfolio(db=db)
        t1 = time.perf_counter()
        print(f"  Scored    : {score_result.get('clients_scored', '?')} clients")
        print(f"  Errors    : {len(score_result.get('errors', []))}")
        print(f"  Duration  : {t1 - t0:.2f}s")

        # --- Stage 3: Anomaly Scan ---
        _header("STAGE 3: Anomaly Detection Scan")
        t0 = time.perf_counter()
        scan_result = run_anomaly_scan(db=db, lookback_days=args.lookback)
        t1 = time.perf_counter()
        breakdown = scan_result.get('breakdown_by_severity', {})
        print(f"  Tx scanned   : {scan_result.get('transactions_scanned', '?')}")
        print(f"  Flags raised : {scan_result.get('anomalies_detected', '?')}")
        print(f"  Critical     : {breakdown.get('CRITICAL', 0)}")
        print(f"  Duration     : {t1 - t0:.2f}s")

        # --- Summary ---
        _print_summary(db)

    finally:
        db.close()

    print("  Pipeline complete. Run the API server to explore the data:")
    print("  uvicorn app.main:app --reload --port 8000\n")
    print("  Then open: http://127.0.0.1:8000/docs\n")


if __name__ == "__main__":
    main()
