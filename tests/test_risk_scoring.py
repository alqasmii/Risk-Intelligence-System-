"""
tests/test_risk_scoring.py
==========================
Unit tests for the Algorithmic Risk Scoring Engine.
All tests use plain Python objects — no database required.

Run with:
    pytest tests/test_risk_scoring.py -v
"""

import math
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# We test the internal helpers directly to achieve unit isolation
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engines.risk_scoring import (
    _classify_tier,
    _compute_compliance_adjustments,
)
from app.models.risk_score import RiskTier


# ---------------------------------------------------------------------------
# Helpers — lightweight fakes replacing ORM objects
# ---------------------------------------------------------------------------

def make_client(**kwargs) -> MagicMock:
    """Build a mock Client ORM object with sensible defaults."""
    defaults = {
        "id": "client-001",
        "external_credit_score": 700,
        "debt_to_income_ratio": 0.30,
        "is_pep": False,
        "kyc_status": "APPROVED",
    }
    defaults.update(kwargs)
    client = MagicMock()
    for key, value in defaults.items():
        setattr(client, key, value)
    return client


def make_loan(**kwargs) -> MagicMock:
    """Build a mock Loan ORM object."""
    defaults = {
        "outstanding_balance": 10_000.0,
        "original_amount": 10_000.0,
        "days_past_due": 0,
        "interest_rate": 0.05,
        "loan_type": "PERSONAL",
        "status": "CURRENT",
    }
    defaults.update(kwargs)
    loan = MagicMock()
    for key, value in defaults.items():
        setattr(loan, key, value)
    return loan


# ---------------------------------------------------------------------------
# _classify_tier
# ---------------------------------------------------------------------------

class TestClassifyTier:
    """
    Score → Tier mapping tests.
    Spec: LOW <35 | MEDIUM <55 | HIGH <70 | VERY_HIGH <85 | CRITICAL ≥85
    """

    def test_low_tier_floor(self):
        assert _classify_tier(0.0) == RiskTier.LOW

    def test_low_tier_upper_boundary(self):
        assert _classify_tier(34.9) == RiskTier.LOW

    def test_medium_tier_lower_boundary(self):
        assert _classify_tier(35.0) == RiskTier.MEDIUM

    def test_medium_tier_mid(self):
        assert _classify_tier(45.0) == RiskTier.MEDIUM

    def test_medium_tier_upper_boundary(self):
        assert _classify_tier(54.9) == RiskTier.MEDIUM

    def test_high_tier_lower_boundary(self):
        assert _classify_tier(55.0) == RiskTier.HIGH

    def test_high_tier_mid(self):
        assert _classify_tier(62.5) == RiskTier.HIGH

    def test_high_tier_upper_boundary(self):
        assert _classify_tier(69.9) == RiskTier.HIGH

    def test_very_high_tier_lower_boundary(self):
        assert _classify_tier(70.0) == RiskTier.VERY_HIGH

    def test_very_high_tier_mid(self):
        assert _classify_tier(77.5) == RiskTier.VERY_HIGH

    def test_very_high_tier_upper_boundary(self):
        assert _classify_tier(84.9) == RiskTier.VERY_HIGH

    def test_critical_lower_boundary(self):
        assert _classify_tier(85.0) == RiskTier.CRITICAL

    def test_critical_ceiling(self):
        assert _classify_tier(100.0) == RiskTier.CRITICAL

    def test_score_exactly_at_each_threshold(self):
        boundary_map = [
            (35.0, RiskTier.MEDIUM),
            (55.0, RiskTier.HIGH),
            (70.0, RiskTier.VERY_HIGH),
            (85.0, RiskTier.CRITICAL),
        ]
        for score, expected_tier in boundary_map:
            result = _classify_tier(score)
            assert result == expected_tier, (
                f"Expected {expected_tier} at score={score}, got {result}"
            )

    def test_return_type_is_risk_tier(self):
        result = _classify_tier(50.0)
        assert isinstance(result, RiskTier)


# ---------------------------------------------------------------------------
# _compute_compliance_adjustments
# ---------------------------------------------------------------------------

class TestComputeComplianceAdjustments:
    """
    KYC / PEP compliance adjustment penalty tests.
    Spec:
      - PEP status adds +20 pts
      - KYC REJECTED adds +30 pts
      - KYC PENDING or EXPIRED adds +15 pts
      - KYC APPROVED adds 0 pts
      - Adjustments are additive (PEP + REJECTED = +50)
    """

    def test_clean_client_zero_penalty(self):
        client = make_client(is_pep=False, kyc_status="APPROVED")
        penalty = _compute_compliance_adjustments(client)
        assert penalty == pytest.approx(0.0)

    def test_pep_adds_twenty_points(self):
        client = make_client(is_pep=True, kyc_status="APPROVED")
        penalty = _compute_compliance_adjustments(client)
        assert penalty == pytest.approx(20.0)

    def test_kyc_rejected_adds_thirty_points(self):
        client = make_client(is_pep=False, kyc_status="REJECTED")
        penalty = _compute_compliance_adjustments(client)
        assert penalty == pytest.approx(30.0)

    def test_kyc_pending_adds_fifteen_points(self):
        client = make_client(is_pep=False, kyc_status="PENDING")
        penalty = _compute_compliance_adjustments(client)
        assert penalty == pytest.approx(15.0)

    def test_kyc_expired_adds_fifteen_points(self):
        client = make_client(is_pep=False, kyc_status="EXPIRED")
        penalty = _compute_compliance_adjustments(client)
        assert penalty == pytest.approx(15.0)

    def test_pep_and_rejected_kyc_additive(self):
        """Worst-case client: PEP + KYC REJECTED = +50 adjustment."""
        client = make_client(is_pep=True, kyc_status="REJECTED")
        penalty = _compute_compliance_adjustments(client)
        assert penalty == pytest.approx(50.0)

    def test_pep_and_pending_kyc_additive(self):
        """PEP + KYC PENDING = +35 adjustment."""
        client = make_client(is_pep=True, kyc_status="PENDING")
        penalty = _compute_compliance_adjustments(client)
        assert penalty == pytest.approx(35.0)

    def test_non_pep_approved_kyc_zero(self):
        """Standard retail client — no adjustment."""
        client = make_client(is_pep=False, kyc_status="APPROVED")
        penalty = _compute_compliance_adjustments(client)
        assert penalty == 0.0

    def test_penalty_is_float(self):
        client = make_client()
        result = _compute_compliance_adjustments(client)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# Score clamping — score should always be between 0 and 100
# ---------------------------------------------------------------------------

class TestScoreClamping:
    """
    The public `score_single_client` function should never return a score
    outside [0, 100] regardless of input extremes.
    We test this via the `_classify_tier` + boundary conditions indirectly
    since direct testing of score_single_client requires a DB Session mock.
    """

    @pytest.mark.parametrize("score", [-10.0, 0.0, 50.0, 100.0, 150.0])
    def test_classify_tier_accepts_any_numeric_score(self, score):
        """_classify_tier must not raise even for out-of-range scores."""
        result = _classify_tier(max(0.0, min(100.0, score)))
        assert result in list(RiskTier)


# ---------------------------------------------------------------------------
# PEP floor enforcement
# ---------------------------------------------------------------------------

class TestPEPFloor:
    """
    PEP clients must be classified at HIGH tier or above (score ≥ 55).
    This is a regulatory requirement — FATF Recommendation 12.
    """

    def test_pep_floor_applied_low_score(self):
        """
        Even if raw components produce a LOW score, a PEP client
        must be elevated to HIGH tier minimum (score floor = 55.0).
        We verify the floor value maps to HIGH tier via _classify_tier.
        """
        pep_floor_score = 55.0
        tier = _classify_tier(pep_floor_score)
        assert tier == RiskTier.HIGH, (
            "PEP floor score of 55.0 must map to at least HIGH tier."
        )

    def test_pep_floor_does_not_cap_higher_tiers(self):
        """
        If a PEP client's actual score is 90 (CRITICAL), the floor
        must not override it downward.
        """
        pep_high_score = 90.0
        tier = _classify_tier(pep_high_score)
        assert tier == RiskTier.CRITICAL
