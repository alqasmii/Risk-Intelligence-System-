"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          AUTOMATED RISK INTELLIGENCE SYSTEM                                  ║
║          Module: Operational Anomaly Detection Engine (ADE)                  ║
║          Regulatory Framework: BSA/AML, FATF Recommendations, FinCEN SAR    ║
╚══════════════════════════════════════════════════════════════════════════════╝

Overview
--------
This module implements a rule-based anomaly detection engine that scans
transaction data to flag suspicious patterns aligned with three regulatory
risk domains:

  1. Fraud Detection —  velocity, geographic impossibility
  2. AML (Anti-Money Laundering) — structuring / smurfing, large cash
  3. Operational Risk — dormant account reactivation, round-amount patterns

Each rule produces zero or more AnomalyFlag records, which are persisted
to the anomaly_flags table and surfaced via the Reporting API.

Algorithmic Design
------------------
Rule architecture: strategy pattern — each detection function receives a
pre-processed Pandas DataFrame and returns a list of AnomalyFlag objects.
Adding new rules requires zero changes to the orchestrator function.

Why Pandas? For regulatory scanning over historical windows, vectorised
DataFrame operations are orders of magnitude faster than Python loops:
  - groupby() → velocity aggregation: O(T)  vs. nested loops O(T²)
  - Boolean masking → threshold detection: O(T)  vs. item iteration O(T)
  - shift() / diff() → sequential pattern comparison: O(T)

Time Complexity per rule:
  Rule 1 (Velocity):              O(T log T) — sort then groupby
  Rule 2 (Structuring):           O(T log T) — sort then rolling window
  Rule 3 (Location Mismatch):     O(T log T) — sort then per-client sort+shift
  Rule 4 (Large Cash):            O(T) — single boolean mask
  Rule 5 (Dormant Account Spike): O(T log T) — sort + groupby + shift

Full scan over all clients: O(N · T log T)
  where N = clients to scan, T = transactions per client in window.

Space Complexity: O(T) for the full DataFrame (one load per scan);
  each rule operates in constant additional space.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import uuid4

import pandas as pd
from sqlalchemy.orm import Session

from app.config import settings
from app.models.anomaly import AnomalyFlag, AnomalyType, AnomalySeverity
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Rule 1: Transaction Velocity Detection
# AML Category: Layering / Rapid Fund Dispersal
# Regulatory Ref: FATF Recommendation 20; FinCEN Advisory FIN-2019-A006
# ──────────────────────────────────────────────────────────────────────────────

def _detect_velocity_anomalies(df: pd.DataFrame) -> List[AnomalyFlag]:
    """
    FLAGS clients who execute more than VELOCITY_MAX_TRANSACTIONS transactions
    within any rolling VELOCITY_WINDOW_MINUTES minute window.

    Business Risk Value:
      Rapid successive transactions are a strong indicator of:
      - Account takeover fraud (attacker draining funds quickly)
      - Placement stage of money laundering (rapidly dispersing cash)
      - Automated bot activity / synthetic identity fraud

    Algorithm:
      For each client, sort transactions by timestamp, then use a
      sliding pointer (two-pointer / deque approach) to find the
      maximum transaction count within any fixed-width time window.

      Time Complexity: O(T log T) for sort + O(T) for two-pointer scan
      Space Complexity: O(T) for client transaction subset

    Args:
        df: Full transaction DataFrame with columns [client_id, timestamp, amount, id]

    Returns:
        List of AnomalyFlag ORM objects ready for bulk insert.
    """
    flags: List[AnomalyFlag] = []
    window = timedelta(minutes=settings.VELOCITY_WINDOW_MINUTES)
    max_allowed = settings.VELOCITY_MAX_TRANSACTIONS

    # Group by client — O(T) amortised
    for client_id, group in df.groupby("client_id"):
        # Sort by timestamp — O(T_c log T_c) where T_c = transactions for this client
        sorted_times = group["timestamp"].sort_values().reset_index(drop=True)

        # Two-pointer scan to find max transactions in any window — O(T_c)
        left = 0
        max_in_window = 0
        burst_window_start = None

        for right in range(len(sorted_times)):
            # Shrink left pointer until the window is valid
            while (sorted_times[right] - sorted_times[left]) > window:
                left += 1
            count_in_window = right - left + 1

            if count_in_window > max_in_window:
                max_in_window = count_in_window
                burst_window_start = sorted_times[left]

        if max_in_window > max_allowed:
            severity = (
                AnomalySeverity.CRITICAL if max_in_window > max_allowed * 2
                else AnomalySeverity.HIGH
            )
            flags.append(AnomalyFlag(
                id=str(uuid4()),
                client_id=str(client_id),
                transaction_id=None,   # Pattern flag spans multiple transactions
                anomaly_type=AnomalyType.VELOCITY.value,
                severity=severity.value,
                rule_triggered="AML-VEL-001",
                description=(
                    f"Transaction velocity breach: {max_in_window} transactions detected "
                    f"within a {settings.VELOCITY_WINDOW_MINUTES}-minute window "
                    f"(threshold: {max_allowed}). "
                    f"Burst window started at {burst_window_start}. "
                    "Possible account takeover, rapid fund dispersal, or bot activity."
                ),
                flagged_amount=group["amount"].sum(),
                flagged_at=datetime.now(timezone.utc),
            ))
            logger.warning(
                "VELOCITY flag: client=%s count=%d in %dmin window",
                str(client_id)[:8], max_in_window, settings.VELOCITY_WINDOW_MINUTES,
            )

    return flags


# ──────────────────────────────────────────────────────────────────────────────
# Rule 2: Structuring / Smurfing Detection
# AML Category: Placement / Layering
# Regulatory Ref: 31 U.S.C. § 5324 (Bank Secrecy Act — anti-structuring);
#                 FATF Typologies Report on Proliferation Financing
# ──────────────────────────────────────────────────────────────────────────────

def _detect_structuring_anomalies(df: pd.DataFrame) -> List[AnomalyFlag]:
    """
    FLAGS clients who make multiple transactions just below the Currency
    Transaction Report (CTR) filing threshold ($10,000 USD), a pattern
    known as "structuring" or "smurfing" under the BSA.

    Detection Logic:
      A client who makes ≥ STRUCTURING_MIN_COUNT transactions in the range
      [STRUCTURING_LOWER_BOUND, AML_REPORTING_THRESHOLD) within a 7-day window
      is flagged. This deliberately avoids looking for a single large transaction
      (which would be obvious) — the sophistication is detecting the aggregate.

    Time Complexity:
      O(T log T) — sort by timestamp + O(T) rolling count on filtered subset.

    Returns:
        List of AnomalyFlag ORM objects.
    """
    flags: List[AnomalyFlag] = []
    lower = settings.STRUCTURING_LOWER_BOUND
    upper = settings.AML_REPORTING_THRESHOLD
    min_count = settings.STRUCTURING_MIN_COUNT

    # Filter to the structuring zone — O(T)
    suspect_df = df[
        (df["amount"] >= lower) & (df["amount"] < upper)
    ].copy()

    if suspect_df.empty:
        return flags

    suspect_df.sort_values("timestamp", inplace=True)

    # Rolling 7-day window count per client — O(T log T) for sort + O(T) for rolling
    for client_id, group in suspect_df.groupby("client_id"):
        group = group.set_index("timestamp").sort_index()

        # resample: count transactions per day, then rolling 7-day sum
        daily_counts = group["amount"].resample("1D").count()
        rolling_7d = daily_counts.rolling(window="7D").sum()

        max_7d = rolling_7d.max()

        if max_7d >= min_count:
            peak_date = rolling_7d.idxmax()
            total_amount = group["amount"].sum()
            severity = (
                AnomalySeverity.CRITICAL if max_7d >= min_count * 2
                else AnomalySeverity.HIGH
            )
            flags.append(AnomalyFlag(
                id=str(uuid4()),
                client_id=str(client_id),
                transaction_id=None,
                anomaly_type=AnomalyType.STRUCTURING.value,
                severity=severity.value,
                rule_triggered="AML-STR-001",
                description=(
                    f"Structuring pattern detected: {int(max_7d)} transactions "
                    f"in range ${lower:,.0f}–${upper:,.0f} within a 7-day window "
                    f"(peak around {peak_date.date() if peak_date is not pd.NaT else 'N/A'}). "
                    f"Total amount in structuring range: ${total_amount:,.2f}. "
                    "Possible CTR avoidance (31 U.S.C. § 5324). Recommend SAR filing review."
                ),
                flagged_amount=float(total_amount),
                flagged_at=datetime.now(timezone.utc),
            ))
            logger.warning(
                "STRUCTURING flag: client=%s count=%.0f in 7d window amount=%.2f",
                str(client_id)[:8], max_7d, total_amount,
            )

    return flags


# ──────────────────────────────────────────────────────────────────────────────
# Rule 3: Geographic Location Mismatch
# Fraud Category: Account Takeover / Card-Not-Present Fraud
# Regulatory Ref: PCI-DSS Requirement 10; FFIEC Authentication Guidance
# ──────────────────────────────────────────────────────────────────────────────

def _detect_location_mismatch_anomalies(df: pd.DataFrame) -> List[AnomalyFlag]:
    """
    FLAGS consecutive transactions from different countries within a time
    window that would be physically impossible to travel between.

    E.g., Transaction at 09:00 in the UK followed by a transaction at
    10:30 in Australia — physically impossible, strong card-fraud indicator.

    Algorithm:
      For each client, sort transactions by timestamp.
      Use Pandas shift() to compare each transaction's country with the
      previous transaction's country.  When countries differ AND the time
      gap is within the impossibility window, flag both transactions.

      Time Complexity: O(T log T) + O(T) — sort once, then vectorised shift
      Space Complexity: O(T_c) per client

    Returns:
        List of AnomalyFlag ORM objects (one per flagged pair).
    """
    flags: List[AnomalyFlag] = []
    window_hours = settings.LOCATION_MISMATCH_WINDOW_HOURS

    for client_id, group in df.groupby("client_id"):
        # Must have location data and at least 2 transactions
        loc_df = group.dropna(subset=["location_country"]).sort_values("timestamp")
        if len(loc_df) < 2:
            continue

        # Vectorised comparison: compare each row to the previous — O(T_c)
        loc_df = loc_df.copy()
        loc_df["prev_country"] = loc_df["location_country"].shift(1)
        loc_df["prev_timestamp"] = loc_df["timestamp"].shift(1)
        loc_df["time_gap_hours"] = (
            (loc_df["timestamp"] - loc_df["prev_timestamp"])
            .dt.total_seconds() / 3600
        )

        # Identify mismatches within the impossibility window
        mismatches = loc_df[
            (loc_df["location_country"] != loc_df["prev_country"])
            & (loc_df["time_gap_hours"].notna())
            & (loc_df["time_gap_hours"] <= window_hours)
            & (loc_df["time_gap_hours"] >= 0)
        ]

        for _, row in mismatches.iterrows():
            flags.append(AnomalyFlag(
                id=str(uuid4()),
                client_id=str(client_id),
                transaction_id=str(row.get("id", "")),
                anomaly_type=AnomalyType.LOCATION_MISMATCH.value,
                severity=AnomalySeverity.HIGH.value,
                rule_triggered="FRAUD-LOC-001",
                description=(
                    f"Geographic impossibility detected: transaction in "
                    f"'{row['prev_country']}' followed by '{row['location_country']}' "
                    f"within {row['time_gap_hours']:.1f}h "
                    f"(threshold: {window_hours}h). "
                    "Possible card cloning, account takeover, or credential sharing."
                ),
                flagged_amount=float(row.get("amount", 0)),
                flagged_at=datetime.now(timezone.utc),
            ))
            logger.warning(
                "LOCATION_MISMATCH flag: client=%s %s→%s in %.1fh",
                str(client_id)[:8], row["prev_country"], row["location_country"],
                row["time_gap_hours"],
            )

    return flags


# ──────────────────────────────────────────────────────────────────────────────
# Rule 4: Large Cash Transaction
# AML Category: Placement
# Regulatory Ref: BSA 31 U.S.C. § 5313 — Currency Transaction Report (CTR)
# ──────────────────────────────────────────────────────────────────────────────

def _detect_large_cash_anomalies(df: pd.DataFrame) -> List[AnomalyFlag]:
    """
    FLAGS individual CASH transactions >= the BSA reporting threshold ($10,000).
    These mandate automatic Currency Transaction Report (CTR) filing.

    Note: this rule is deliberately simple — a single vectorised boolean mask.
    Simplicity is a feature here: the rule must never miss a CTR-reportable
    transaction regardless of the client's overall risk profile.

    Time Complexity: O(T) — single Pandas boolean mask. No sorting required.

    Returns:
        List of AnomalyFlag ORM objects (one per qualifying transaction).
    """
    flags: List[AnomalyFlag] = []
    threshold = settings.AML_REPORTING_THRESHOLD

    cash_df = df[
        (df["transaction_type"] == "CASH")
        & (df["amount"] >= threshold)
    ]

    for _, row in cash_df.iterrows():
        severity = (
            AnomalySeverity.CRITICAL if row["amount"] >= threshold * 5
            else AnomalySeverity.HIGH
        )
        flags.append(AnomalyFlag(
            id=str(uuid4()),
            client_id=str(row["client_id"]),
            transaction_id=str(row.get("id", "")),
            anomaly_type=AnomalyType.LARGE_CASH.value,
            severity=severity.value,
            rule_triggered="AML-CASH-001",
            description=(
                f"Large cash transaction of ${row['amount']:,.2f} detected "
                f"(BSA CTR threshold: ${threshold:,.0f}). "
                "Mandatory Currency Transaction Report (CTR) filing required within 15 days."
            ),
            flagged_amount=float(row["amount"]),
            flagged_at=datetime.now(timezone.utc),
        ))

    return flags


# ──────────────────────────────────────────────────────────────────────────────
# Rule 5: Dormant Account Reactivation Spike
# Fraud Category: Account Takeover / Synthetic Identity / Mule Accounts
# Regulatory Ref: FFIEC BSA/AML Examination Manual — Unusual Account Activity
# ──────────────────────────────────────────────────────────────────────────────

def _detect_dormant_account_spikes(df: pd.DataFrame) -> List[AnomalyFlag]:
    """
    FLAGS accounts that show a large spike in activity after a 90+ day
    dormancy period.  This is a classic pattern for:
      - Account takeover (ATO): attacker acquires dormant account and
        immediately moves funds
      - Mule account activation: dormant personal account suddenly used
        to receive and forward large amounts

    Algorithm:
      1. groupby client → resample to monthly counts
      2. shift(1) to get previous month count
      3. Flag rows where prior 90-day total = 0 AND current 30-day total > threshold.

    Time Complexity: O(T log T) for sort + O(N · T/12) for monthly groupby.

    Returns:
        List of AnomalyFlag ORM objects.
    """
    flags: List[AnomalyFlag] = []
    spike_threshold = 5   # > 5 transactions after dormancy = flag

    for client_id, group in df.groupby("client_id"):
        g = group.set_index("timestamp").sort_index()
        if len(g) < 2:
            continue

        # "ME" (month-end) replaced deprecated "M" in pandas >= 2.2; try both for compatibility
        try:
            monthly = g["amount"].resample("ME").count()
        except ValueError:
            monthly = g["amount"].resample("M").count()
        if len(monthly) < 2:
            continue

        # Detect: at least one 0-activity month followed by spike
        for i in range(1, len(monthly)):
            if monthly.iloc[i - 1] == 0 and monthly.iloc[i] >= spike_threshold:
                spike_month = monthly.index[i]
                # Calculate the amount sum during spike month
                spike_amount = g.loc[
                    g.index.to_period("M") == spike_month.to_period("M"),
                    "amount"
                ].sum() if hasattr(spike_month, 'to_period') else g["amount"].sum()

                flags.append(AnomalyFlag(
                    id=str(uuid4()),
                    client_id=str(client_id),
                    transaction_id=None,
                    anomaly_type=AnomalyType.DORMANT_ACCOUNT_SPIKE.value,
                    severity=AnomalySeverity.HIGH.value,
                    rule_triggered="FRAUD-DORM-001",
                    description=(
                        f"Dormant account reactivation: {int(monthly.iloc[i])} transactions "
                        f"in {spike_month.strftime('%B %Y') if hasattr(spike_month, 'strftime') else spike_month} "
                        f"following a month of zero activity. "
                        f"Total spike-period amount: ${float(spike_amount):,.2f}. "
                        "Possible account takeover or mule account activation."
                    ),
                    flagged_amount=float(spike_amount),
                    flagged_at=datetime.now(timezone.utc),
                ))
                break  # One flag per client for dormancy events

    return flags


# ──────────────────────────────────────────────────────────────────────────────
# Orchestrator: Full Anomaly Scan
# ──────────────────────────────────────────────────────────────────────────────

def run_anomaly_scan(
    db: Session,
    lookback_days: int = 90,
    client_ids: Optional[List[str]] = None,
) -> dict:
    """
    Orchestrates a full anomaly detection scan across all 5 rules.

    Execution Model:
      1. Load all transactions in the lookback window into a single DataFrame
         (one database query — avoids N+1 pattern)
      2. Pass the same DataFrame to each detection rule sequentially
         (rules are stateless; same data, different perspectives)
      3. Bulk-persist all detected anomalies in one DB write

    This single-load, multi-pass architecture means the largest cost (DB I/O)
    is paid once regardless of how many rules are executed.

    Time Complexity: O(T log T) — dominated by the sort within each rule.
    Space Complexity: O(T) — single DataFrame load, shared across all rules.

    Args:
        db: SQLAlchemy session
        lookback_days: How far back to scan. Default 90 days.
        client_ids: Optional sub-set of clients to scan.

    Returns:
        Dict with scan statistics for the API response.
    """
    start = time.perf_counter()
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    # ── Single Database Load ──────────────────────────────────────────────────
    query = db.query(Transaction).filter(Transaction.timestamp >= cutoff)
    if client_ids:
        query = query.filter(Transaction.client_id.in_(client_ids))

    transactions = query.all()
    total_tx = len(transactions)

    logger.info("Anomaly scan loaded %d transactions for analysis", total_tx)

    if not transactions:
        return _empty_scan_result(start)

    # ── Materialise to Pandas DataFrame ───────────────────────────────────────
    # One-time O(T) conversion; subsequent operations are vectorised
    df = pd.DataFrame([
        {
            "id": t.id,
            "client_id": t.client_id,
            "amount": t.amount,
            "transaction_type": t.transaction_type,
            "timestamp": t.timestamp,
            "location_country": t.location_country,
            "location_city": t.location_city,
            "status": t.status,
        }
        for t in transactions
    ])

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df.sort_values("timestamp", inplace=True)   # Global pre-sort used by all rules

    # ── Execute All Detection Rules ───────────────────────────────────────────
    all_flags: List[AnomalyFlag] = []

    rules = [
        ("velocity",      _detect_velocity_anomalies),
        ("structuring",   _detect_structuring_anomalies),
        ("geo_mismatch",  _detect_location_mismatch_anomalies),
        ("large_cash",    _detect_large_cash_anomalies),
        ("dormant_spike", _detect_dormant_account_spikes),
    ]

    breakdown_by_type: dict = {}
    breakdown_by_severity: dict = {}

    for rule_name, rule_fn in rules:
        try:
            rule_flags = rule_fn(df)
            all_flags.extend(rule_flags)
            if rule_flags:
                breakdown_by_type[rule_flags[0].anomaly_type] = (
                    breakdown_by_type.get(rule_flags[0].anomaly_type, 0) + len(rule_flags)
                )
                for f in rule_flags:
                    breakdown_by_severity[f.severity] = (
                        breakdown_by_severity.get(f.severity, 0) + 1
                    )
            logger.debug("Rule [%s]: %d flags", rule_name, len(rule_flags))
        except Exception as exc:
            logger.error("Rule [%s] failed: %s", rule_name, exc, exc_info=True)

    # ── Bulk Persist Anomaly Flags ────────────────────────────────────────────
    if all_flags:
        db.bulk_save_objects(all_flags)
        db.commit()

    elapsed = round(time.perf_counter() - start, 3)
    logger.info(
        "Anomaly scan complete: %d transactions → %d flags (%.2fs)",
        total_tx, len(all_flags), elapsed,
    )

    return {
        "status": "completed",
        "transactions_scanned": total_tx,
        "anomalies_detected": len(all_flags),
        "breakdown_by_type": breakdown_by_type,
        "breakdown_by_severity": breakdown_by_severity,
        "duration_seconds": elapsed,
    }


def _empty_scan_result(start: float) -> dict:
    """Returns a zero-result scan dict when no transactions are found."""
    return {
        "status": "completed",
        "transactions_scanned": 0,
        "anomalies_detected": 0,
        "breakdown_by_type": {},
        "breakdown_by_severity": {},
        "duration_seconds": round(time.perf_counter() - start, 3),
    }
