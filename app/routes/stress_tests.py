"""
Model Stress Testing Routes — Macro Scenario Engine
===================================================
Runs supervisory-style stress scenarios over the live portfolio and reports the
resulting risk migration. This is the same exercise a bank performs for ICAAP /
CCAR: apply a macroeconomic shock to the risk drivers and measure how capital,
exposure, and tier distribution deteriorate.

The scenarios reuse the PRODUCTION scoring engine (app.engines.risk_scoring) —
we do not fabricate results. Each client's real data is shocked in-memory
(DTI stress, rate shock, collateral haircut, income shock), re-scored through
the exact same weighted formula, then the session is rolled back so nothing is
persisted. What you see is what the model would actually produce under stress.

Endpoint:
  POST /stress-tests/run     — Run a scenario, return before/after migration + EL delta
  GET  /stress-tests/presets — List built-in supervisory scenarios
"""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.engines.risk_scoring import _build_scoring_context, score_single_client
from app.models.client import Client
from app.models.loan import LoanStatus
from app.models.risk_score import RiskTier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stress-tests", tags=["Model Stress Tests"])

_TIER_ORDER = {t.value: i for i, t in enumerate(RiskTier)}

# Loss Given Default assumptions by collateral type (Basel IRB foundation-style).
# Used to translate a tier shift into an Expected-Loss delta.
_LGD = {"PROPERTY": 0.25, "SECURITIES": 0.30, "VEHICLE": 0.45, None: 0.75, "NONE": 0.75, "": 0.75}
# Probability of Default proxy per tier — maps a composite tier to a PD band.
_PD_BY_TIER = {
    "LOW": 0.01, "MEDIUM": 0.04, "HIGH": 0.12, "VERY_HIGH": 0.28, "CRITICAL": 0.55,
}


class Shock(BaseModel):
    """A macro shock vector. All multipliers default to 1.0 (no shock)."""
    dti_multiplier: float = Field(1.0, ge=1.0, le=3.0, description="Debt-to-income stress multiplier")
    rate_shock_bps: float = Field(0.0, ge=0.0, le=1000.0, description="Parallel rate shock (basis points)")
    collateral_haircut: float = Field(0.0, ge=0.0, le=0.9, description="Collateral value haircut (0–0.9)")
    income_shock: float = Field(0.0, ge=0.0, le=0.9, description="Income reduction (0–0.9)")
    default_migration: float = Field(
        0.0, ge=0.0, le=0.5,
        description="Fraction of delinquent loans that roll to DEFAULT",
    )


class StressRequest(BaseModel):
    scenario_name: str = Field("Custom Scenario", max_length=80)
    shock: Shock = Shock()


# ── Built-in supervisory scenarios ──────────────────────────────────────────
PRESETS: Dict[str, dict] = {
    "baseline": {
        "label": "Baseline (no shock)",
        "description": "Control run — confirms the engine reproduces current scores.",
        "shock": Shock().model_dump(),
    },
    "rate_300": {
        "label": "Rate Hike +300bps",
        "description": "Parallel upward shift in interest rates by 300 basis points.",
        "shock": Shock(rate_shock_bps=300, dti_multiplier=1.15).model_dump(),
    },
    "downturn": {
        "label": "Regional Downturn",
        "description": "Income shock 20%, DTI stress, partial delinquency roll to default.",
        "shock": Shock(income_shock=0.20, dti_multiplier=1.35, default_migration=0.15).model_dump(),
    },
    "credit_crisis": {
        "label": "2008-Style Credit Crisis",
        "description": "Severe: 35% collateral crash, 30% income shock, heavy default migration.",
        "shock": Shock(
            dti_multiplier=1.6, rate_shock_bps=200, collateral_haircut=0.35,
            income_shock=0.30, default_migration=0.30,
        ).model_dump(),
    },
}


@router.get("/presets", summary="List built-in stress scenarios")
def list_presets() -> dict:
    return {"presets": PRESETS}


def _expected_loss(score_obj, tier: str) -> float:
    """EL = PD(tier) × LGD(collateral mix proxy) × EAD(outstanding debt)."""
    ead = score_obj.total_outstanding_debt or 0.0
    pd = _PD_BY_TIER.get(tier, 0.1)
    # Without per-loan collateral here we use a blended LGD midpoint.
    lgd = 0.55
    return pd * lgd * ead


@router.post(
    "/run",
    summary="Run a Stress Scenario",
    description=(
        "Applies a macro shock to every client's real risk drivers, re-scores the "
        "portfolio through the production engine, and returns the tier migration, "
        "exposure-at-risk delta, and the worst-hit clients. Nothing is persisted — "
        "the scoring session is rolled back after computation."
    ),
)
def run_stress_test(req: StressRequest, db: Session = Depends(get_db)) -> dict:
    shock = req.shock
    clients = db.query(Client).all()

    before_dist = {t.value: 0 for t in RiskTier}
    after_dist = {t.value: 0 for t in RiskTier}
    before_el = 0.0
    after_el = 0.0
    migrations: List[dict] = []
    downgrades = 0

    for c in clients:
        # ── Baseline: score the UNSHOCKED client through the production engine ─
        # We deliberately re-score the baseline (rather than reading the persisted
        # seed score) so both sides of the comparison come from the SAME model —
        # otherwise a difference in methodology would masquerade as a shock effect.
        base_ctx = _build_scoring_context(c, db)
        baseline = score_single_client(base_ctx)
        base_tier = baseline.risk_tier.value
        base_score = baseline.composite_score

        # ── Apply shocks in-memory (rolled back later) ────────────────────────
        # DTI is the exposure engine's primary income driver. An income shock of
        # x% raises DTI to DTI/(1-x) (same debt, smaller income); the DTI
        # multiplier stacks on top for a direct debt-burden stress.
        eff_dti_mult = shock.dti_multiplier
        if shock.income_shock:
            eff_dti_mult *= 1.0 / (1.0 - shock.income_shock)
            if c.annual_income:
                c.annual_income = c.annual_income * (1 - shock.income_shock)
        if eff_dti_mult != 1.0 and c.debt_to_income_ratio is not None:
            c.debt_to_income_ratio = min(c.debt_to_income_ratio * eff_dti_mult, 1.5)

        # Rebuild the context so the exposure/behavioral components see the shocked
        # loan attributes, then re-score.
        shock_ctx = _build_scoring_context(c, db)
        for loan in shock_ctx.loans:
            if shock.rate_shock_bps:
                loan.interest_rate = (loan.interest_rate or 0) + shock.rate_shock_bps / 100.0
            if shock.collateral_haircut and loan.collateral_value:
                loan.collateral_value = loan.collateral_value * (1 - shock.collateral_haircut)
            if (
                shock.default_migration
                and loan.status == LoanStatus.DELINQUENT.value
                and (hash(loan.id) % 100) / 100.0 < shock.default_migration
            ):
                loan.status = LoanStatus.DEFAULT.value
                loan.days_past_due = max(loan.days_past_due or 0, 90)

        stressed = score_single_client(shock_ctx)

        before_dist[base_tier] = before_dist.get(base_tier, 0) + 1
        after_dist[stressed.risk_tier.value] += 1

        before_el += _expected_loss(baseline, base_tier)
        after_el += _expected_loss(stressed, stressed.risk_tier.value)

        moved = _TIER_ORDER.get(stressed.risk_tier.value, 0) - _TIER_ORDER.get(base_tier, 0)
        if moved > 0:
            downgrades += 1
            migrations.append({
                "client_id": c.id,
                "client_name": c.name,
                "from_tier": base_tier,
                "to_tier": stressed.risk_tier.value,
                "score_before": round(base_score, 2),
                "score_after": round(stressed.composite_score, 2),
                "score_delta": round(stressed.composite_score - base_score, 2),
                "tiers_moved": moved,
                "outstanding_debt": round(stressed.total_outstanding_debt or 0.0, 2),
            })

    # ── Discard all in-memory shocks — nothing hits the database ──────────────
    db.rollback()

    migrations.sort(key=lambda m: (m["tiers_moved"], m["score_delta"]), reverse=True)

    total = len(clients) or 1
    return {
        "scenario_name": req.scenario_name,
        "shock": shock.model_dump(),
        "clients_evaluated": len(clients),
        "downgrades": downgrades,
        "downgrade_pct": round(downgrades / total * 100, 1),
        "tier_distribution_before": before_dist,
        "tier_distribution_after": after_dist,
        "expected_loss_before_omr": round(before_el, 2),
        "expected_loss_after_omr": round(after_el, 2),
        "expected_loss_delta_omr": round(after_el - before_el, 2),
        "expected_loss_increase_pct": round(
            ((after_el - before_el) / before_el * 100) if before_el else 0.0, 1
        ),
        "top_migrations": migrations[:25],
    }
