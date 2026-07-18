"""
tests/test_anomaly_detection.py
================================
Unit tests for the 5 AML/Fraud anomaly detection rules.
All tests use in-memory Pandas DataFrames — no database required.

Detection rules tested:
  AML-VEL-001   — Transaction velocity burst
  AML-STR-001   — Currency structuring (smurfing)
  FRAUD-LOC-001 — Geographic location mismatch
  AML-CASH-001  — Large cash transaction
  FRAUD-DORM-001 — Dormant account activity spike

Run with:
    pytest tests/test_anomaly_detection.py -v
"""

import sys
from pathlib import Path

import pandas as pd
import pytest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engines.anomaly_detection import (
    _detect_velocity_anomalies,
    _detect_structuring_anomalies,
    _detect_location_mismatch_anomalies,
    _detect_large_cash_anomalies,
    _detect_dormant_account_spikes,
)


# ---------------------------------------------------------------------------
# DataFrame builder helpers
# ---------------------------------------------------------------------------

BASE_TIME = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_tx_df(records: list[dict]) -> pd.DataFrame:
    """
    Build a minimal transactions DataFrame matching the columns expected
    by the detection engine.
    """
    df = pd.DataFrame(records)
    if "timestamp" not in df.columns:
        df["timestamp"] = BASE_TIME
    if "transaction_type" not in df.columns:
        df["transaction_type"] = "DEBIT"
    if "location_country" not in df.columns:
        df["location_country"] = "US"
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def _make_simple_tx(
    client_id: str,
    n: int,
    amount: float = 500.0,
    tx_type: str = "DEBIT",
    spacing_seconds: int = 300,
    base_time: datetime | None = None,
    country: str = "US",
) -> pd.DataFrame:
    """Create `n` evenly-spaced transactions for one client."""
    t0 = base_time or BASE_TIME
    records = [
        {
            "id": f"tx-{client_id}-{i}",
            "client_id": client_id,
            "amount": amount,
            "transaction_type": tx_type,
            "timestamp": t0 + timedelta(seconds=i * spacing_seconds),
            "location_country": country,
        }
        for i in range(n)
    ]
    return _make_tx_df(records)


# ---------------------------------------------------------------------------
# AML-VEL-001: Transaction Velocity
# ---------------------------------------------------------------------------

class TestVelocityDetection:
    """
    Rule triggers when a client executes > MAX_TRANSACTIONS (default=8)
    within any rolling 60-minute window.
    """

    def test_no_flag_below_threshold(self):
        """7 transactions in 60 minutes — no flag expected."""
        df = _make_simple_tx("c1", n=7, spacing_seconds=400)
        flags = _detect_velocity_anomalies(df, "c1")
        assert flags == []

    def test_flag_at_threshold_exceeded(self):
        """10 transactions in 10 minutes — must trigger AML-VEL-001."""
        df = _make_simple_tx("c1", n=10, spacing_seconds=60)
        flags = _detect_velocity_anomalies(df, "c1")
        assert len(flags) > 0

    def test_flag_rule_id_correct(self):
        df = _make_simple_tx("c1", n=12, spacing_seconds=60)
        flags = _detect_velocity_anomalies(df, "c1")
        rule_ids = {f["rule_triggered"] for f in flags}
        assert "AML-VEL-001" in rule_ids

    def test_flag_has_required_keys(self):
        df = _make_simple_tx("c1", n=12, spacing_seconds=60)
        flags = _detect_velocity_anomalies(df, "c1")
        required_keys = {"client_id", "anomaly_type", "severity", "rule_triggered", "description", "flagged_at"}
        for flag in flags:
            assert required_keys.issubset(flag.keys()), f"Missing keys in flag: {flag.keys()}"

    def test_spread_transactions_no_flag(self):
        """8 transactions spread across 3 hours — no 60-minute window violated."""
        df = _make_simple_tx("c1", n=8, spacing_seconds=1350)  # 22.5 min between each
        flags = _detect_velocity_anomalies(df, "c1")
        # With 8 tx across 157.5 minutes, no window of 60 minutes holds >8 tx
        # (each window holds at most 4-5 tx)
        assert flags == []

    def test_empty_dataframe_returns_no_flags(self):
        df = pd.DataFrame(columns=["id", "client_id", "amount", "transaction_type", "timestamp", "location_country"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        flags = _detect_velocity_anomalies(df, "c1")
        assert flags == []


# ---------------------------------------------------------------------------
# AML-STR-001: Structuring / Smurfing
# ---------------------------------------------------------------------------

class TestStructuringDetection:
    """
    Rule triggers when a client has ≥3 transactions between $9,000 and
    $10,000 within any 7-day rolling window (BSA structuring indicator).
    """

    def test_no_flag_below_structuring_threshold(self):
        """2 near-$10K transactions — below the 3-transaction threshold."""
        records = [
            {"id": f"tx-{i}", "client_id": "c2", "amount": 9_500.0,
             "timestamp": BASE_TIME + timedelta(days=i), "transaction_type": "CASH",
             "location_country": "US"}
            for i in range(2)
        ]
        df = _make_tx_df(records)
        flags = _detect_structuring_anomalies(df, "c2")
        assert flags == []

    def test_flag_triggered_three_structuring_tx(self):
        """3 transactions at $9,500 in one week — must flag AML-STR-001."""
        records = [
            {"id": f"tx-{i}", "client_id": "c2", "amount": 9_500.0,
             "timestamp": BASE_TIME + timedelta(days=i), "transaction_type": "CASH",
             "location_country": "US"}
            for i in range(3)
        ]
        df = _make_tx_df(records)
        flags = _detect_structuring_anomalies(df, "c2")
        assert len(flags) > 0

    def test_flag_rule_id(self):
        records = [
            {"id": f"tx-{i}", "client_id": "c2", "amount": 9_200.0,
             "timestamp": BASE_TIME + timedelta(days=i), "transaction_type": "CASH",
             "location_country": "US"}
            for i in range(4)
        ]
        df = _make_tx_df(records)
        flags = _detect_structuring_anomalies(df, "c2")
        rule_ids = {f["rule_triggered"] for f in flags}
        assert "AML-STR-001" in rule_ids

    def test_large_amounts_not_flagged_as_structuring(self):
        """Regular large wire transfers ($50K) are not structuring."""
        records = [
            {"id": f"tx-{i}", "client_id": "c2", "amount": 50_000.0,
             "timestamp": BASE_TIME + timedelta(days=i), "transaction_type": "WIRE",
             "location_country": "US"}
            for i in range(5)
        ]
        df = _make_tx_df(records)
        flags = _detect_structuring_anomalies(df, "c2")
        assert flags == []

    def test_small_amounts_not_flagged(self):
        """Ordinary small transactions should not be caught by the structuring rule."""
        df = _make_simple_tx("c2", n=20, amount=200.0)
        flags = _detect_structuring_anomalies(df, "c2")
        assert flags == []


# ---------------------------------------------------------------------------
# FRAUD-LOC-001: Geographic Location Mismatch
# ---------------------------------------------------------------------------

class TestLocationMismatchDetection:
    """
    Rule triggers when consecutive transactions occur in different countries
    within a 2-hour window — physically impossible travel time indicator.
    """

    def test_same_country_no_flag(self):
        """All transactions in US — no mismatch."""
        df = _make_simple_tx("c3", n=5, country="US", spacing_seconds=600)
        flags = _detect_location_mismatch_anomalies(df, "c3")
        assert flags == []

    def test_different_country_within_window_flags(self):
        """US transaction → GB transaction within 90 minutes — must flag."""
        records = [
            {"id": "tx-1", "client_id": "c3", "amount": 100.0,
             "timestamp": BASE_TIME, "transaction_type": "DEBIT",
             "location_country": "US"},
            {"id": "tx-2", "client_id": "c3", "amount": 150.0,
             "timestamp": BASE_TIME + timedelta(minutes=90), "transaction_type": "DEBIT",
             "location_country": "GB"},
        ]
        df = _make_tx_df(records)
        flags = _detect_location_mismatch_anomalies(df, "c3")
        assert len(flags) > 0

    def test_different_country_outside_window_no_flag(self):
        """US → GB but 5 hours apart — possible, no flag (window is 2 hours)."""
        records = [
            {"id": "tx-1", "client_id": "c3", "amount": 100.0,
             "timestamp": BASE_TIME, "transaction_type": "DEBIT",
             "location_country": "US"},
            {"id": "tx-2", "client_id": "c3", "amount": 150.0,
             "timestamp": BASE_TIME + timedelta(hours=5), "transaction_type": "DEBIT",
             "location_country": "GB"},
        ]
        df = _make_tx_df(records)
        flags = _detect_location_mismatch_anomalies(df, "c3")
        assert flags == []

    def test_flag_rule_id(self):
        records = [
            {"id": "tx-1", "client_id": "c3", "amount": 100.0,
             "timestamp": BASE_TIME, "transaction_type": "DEBIT",
             "location_country": "AU"},
            {"id": "tx-2", "client_id": "c3", "amount": 200.0,
             "timestamp": BASE_TIME + timedelta(minutes=30), "transaction_type": "DEBIT",
             "location_country": "BR"},
        ]
        df = _make_tx_df(records)
        flags = _detect_location_mismatch_anomalies(df, "c3")
        rule_ids = {f["rule_triggered"] for f in flags}
        assert "FRAUD-LOC-001" in rule_ids

    def test_single_transaction_no_flag(self):
        """Only one transaction — no consecutive pair to compare."""
        df = _make_simple_tx("c3", n=1)
        flags = _detect_location_mismatch_anomalies(df, "c3")
        assert flags == []


# ---------------------------------------------------------------------------
# AML-CASH-001: Large Cash Transaction
# ---------------------------------------------------------------------------

class TestLargeCashDetection:
    """
    Rule triggers on any single CASH transaction ≥ $10,000.
    Directly corresponds to FinCEN CTR (Currency Transaction Report) threshold.
    """

    def test_cash_below_threshold_no_flag(self):
        """$9,999 cash — just under the threshold."""
        records = [
            {"id": "tx-1", "client_id": "c4", "amount": 9_999.0,
             "timestamp": BASE_TIME, "transaction_type": "CASH",
             "location_country": "US"}
        ]
        df = _make_tx_df(records)
        flags = _detect_large_cash_anomalies(df, "c4")
        assert flags == []

    def test_cash_at_threshold_flags(self):
        """Exactly $10,000 cash — must flag AML-CASH-001."""
        records = [
            {"id": "tx-1", "client_id": "c4", "amount": 10_000.0,
             "timestamp": BASE_TIME, "transaction_type": "CASH",
             "location_country": "US"}
        ]
        df = _make_tx_df(records)
        flags = _detect_large_cash_anomalies(df, "c4")
        assert len(flags) == 1

    def test_cash_above_threshold_flags(self):
        """$25,000 cash — must flag."""
        records = [
            {"id": "tx-1", "client_id": "c4", "amount": 25_000.0,
             "timestamp": BASE_TIME, "transaction_type": "CASH",
             "location_country": "US"}
        ]
        df = _make_tx_df(records)
        flags = _detect_large_cash_anomalies(df, "c4")
        assert len(flags) == 1

    def test_large_wire_not_flagged_as_cash(self):
        """A large WIRE transfer should NOT trigger AML-CASH-001."""
        records = [
            {"id": "tx-1", "client_id": "c4", "amount": 50_000.0,
             "timestamp": BASE_TIME, "transaction_type": "WIRE",
             "location_country": "US"}
        ]
        df = _make_tx_df(records)
        flags = _detect_large_cash_anomalies(df, "c4")
        assert flags == []

    def test_multiple_large_cash_flagged_individually(self):
        """Each large cash transaction generates its own flag."""
        records = [
            {"id": f"tx-{i}", "client_id": "c4", "amount": 15_000.0,
             "timestamp": BASE_TIME + timedelta(days=i), "transaction_type": "CASH",
             "location_country": "US"}
            for i in range(3)
        ]
        df = _make_tx_df(records)
        flags = _detect_large_cash_anomalies(df, "c4")
        assert len(flags) == 3

    def test_flag_rule_id(self):
        records = [
            {"id": "tx-1", "client_id": "c4", "amount": 12_000.0,
             "timestamp": BASE_TIME, "transaction_type": "CASH",
             "location_country": "US"}
        ]
        df = _make_tx_df(records)
        flags = _detect_large_cash_anomalies(df, "c4")
        assert flags[0]["rule_triggered"] == "AML-CASH-001"

    def test_flag_severity_high(self):
        """Large cash flags should be HIGH or CRITICAL severity."""
        records = [
            {"id": "tx-1", "client_id": "c4", "amount": 10_000.0,
             "timestamp": BASE_TIME, "transaction_type": "CASH",
             "location_country": "US"}
        ]
        df = _make_tx_df(records)
        flags = _detect_large_cash_anomalies(df, "c4")
        assert flags[0]["severity"] in ("HIGH", "CRITICAL")


# ---------------------------------------------------------------------------
# FRAUD-DORM-001: Dormant Account Spike
# ---------------------------------------------------------------------------

class TestDormantAccountSpike:
    """
    Rule triggers when a previously dormant account (zero transactions in a
    prior month) suddenly shows significant activity.
    """

    def test_consistently_active_account_no_flag(self):
        """Account with regular monthly activity — no dormancy spike."""
        records = []
        for month in range(6):
            for day in range(5):  # 5 tx per month
                records.append({
                    "id": f"tx-{month}-{day}",
                    "client_id": "c5",
                    "amount": 500.0,
                    "timestamp": BASE_TIME + timedelta(days=month * 30 + day),
                    "transaction_type": "DEBIT",
                    "location_country": "US",
                })
        df = _make_tx_df(records)
        flags = _detect_dormant_account_spikes(df, "c5")
        assert flags == []

    def test_dormant_then_spike_flags(self):
        """
        Months 1-3: active (5 tx each). Month 4-5: zero. Month 6: 15 tx.
        Should raise FRAUD-DORM-001.
        """
        records = []
        # Active months
        for month in range(3):
            for day in range(5):
                records.append({
                    "id": f"tx-active-{month}-{day}",
                    "client_id": "c5",
                    "amount": 300.0,
                    "timestamp": BASE_TIME + timedelta(days=month * 30 + day),
                    "transaction_type": "DEBIT",
                    "location_country": "US",
                })
        # Skip months 4-5 (dormant)
        # Spike in month 6
        for i in range(15):
            records.append({
                "id": f"tx-spike-{i}",
                "client_id": "c5",
                "amount": 2_000.0,
                "timestamp": BASE_TIME + timedelta(days=5 * 30 + i),
                "transaction_type": "WIRE",
                "location_country": "US",
            })
        df = _make_tx_df(records)
        flags = _detect_dormant_account_spikes(df, "c5")
        assert len(flags) > 0

    def test_flag_rule_id_dormant(self):
        records = []
        for i in range(10):
            records.append({
                "id": f"tx-spike-{i}",
                "client_id": "c5",
                "amount": 1_000.0,
                "timestamp": BASE_TIME + timedelta(days=150 + i),
                "transaction_type": "DEBIT",
                "location_country": "US",
            })
        df = _make_tx_df(records)
        # Only spike data — engine should recognise no prior history
        flags = _detect_dormant_account_spikes(df, "c5")
        # Flags may or may not appear depending on implementation (only 1 month of data)
        # We just check any raised flags have the right rule id
        for flag in flags:
            assert flag["rule_triggered"] == "FRAUD-DORM-001"

    def test_empty_dataframe_no_flags(self):
        df = pd.DataFrame(
            columns=["id", "client_id", "amount", "transaction_type", "timestamp", "location_country"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        flags = _detect_dormant_account_spikes(df, "c5")
        assert flags == []
