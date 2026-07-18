"""
Pydantic Response Schemas
==========================
All API response models live here, separated from ORM models (Domain/DTO split).
Pydantic v2 provides runtime type validation, auto-serialization to JSON,
and OpenAPI schema generation — all critical for a production-grade API.

Design principle: the API layer NEVER exposes raw ORM objects. This prevents
accidental exposure of sensitive internal fields and keeps the contract stable
even when the database schema changes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────────────────────────────────────
# Client Schemas
# ──────────────────────────────────────────────────────────────────────────────

class ClientSummarySchema(BaseModel):
    id: str
    name: str
    client_type: str
    kyc_status: str
    is_pep: bool
    external_credit_score: Optional[int] = None
    annual_income: Optional[float] = None
    debt_to_income_ratio: Optional[float] = None
    country_of_residence: Optional[str] = None
    industry_sector: Optional[str] = None

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────────────────
# Risk Score Schemas
# ──────────────────────────────────────────────────────────────────────────────

class RiskComponentBreakdownSchema(BaseModel):
    """
    Explainability payload for each score component.
    Required for SR 11-7 / BCBS 239 model governance compliance —
    a risk decision must always be explainable to regulators and auditors.
    """
    credit_history_score: float = Field(..., ge=0, le=100, description="Backward-looking creditworthiness (0=best, 100=worst)")
    behavioral_score: float = Field(..., ge=0, le=100, description="Real-time transaction pattern risk")
    exposure_score: float = Field(..., ge=0, le=100, description="Balance sheet vulnerability risk")
    pep_adjustment: float = Field(default=0.0, description="Regulatory PEP compliance penalty applied")
    kyc_adjustment: float = Field(default=0.0, description="KYC compliance penalty applied")


class RiskScoreSchema(BaseModel):
    id: str
    client_id: str
    composite_score: float = Field(..., ge=0, le=100)
    risk_tier: str
    components: RiskComponentBreakdownSchema
    active_loans_count: Optional[int] = None
    total_outstanding_debt: Optional[float] = None
    transactions_analyzed: Optional[int] = None
    model_version: str
    scored_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, rs: Any) -> "RiskScoreSchema":
        return cls(
            id=rs.id,
            client_id=rs.client_id,
            composite_score=rs.composite_score,
            risk_tier=rs.risk_tier,
            components=RiskComponentBreakdownSchema(
                credit_history_score=rs.credit_history_score,
                behavioral_score=rs.behavioral_score,
                exposure_score=rs.exposure_score,
                pep_adjustment=rs.pep_adjustment,
                kyc_adjustment=rs.kyc_adjustment,
            ),
            active_loans_count=rs.active_loans_count,
            total_outstanding_debt=rs.total_outstanding_debt,
            transactions_analyzed=rs.transactions_analyzed,
            model_version=rs.model_version,
            scored_at=rs.scored_at,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Anomaly Flag Schemas
# ──────────────────────────────────────────────────────────────────────────────

class AnomalyFlagSchema(BaseModel):
    id: str
    client_id: str
    transaction_id: Optional[str] = None
    anomaly_type: str
    severity: str
    description: str
    rule_triggered: str
    flagged_amount: Optional[float] = None
    flagged_at: datetime
    status: str

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────────────────
# High-Risk Exposure Report (React Dashboard payload)
# ──────────────────────────────────────────────────────────────────────────────

class HighRiskClientSchema(BaseModel):
    """
    Denormalized view of a high-risk client — designed to be directly
    consumed by a React/Next.js Risk Heatmap component.

    Each row represents one client record with pre-joined risk score,
    anomaly count, and portfolio exposure — eliminating N+1 query patterns
    that would occur if the frontend fetched each field separately.
    """
    client_id: str
    client_name: str
    client_type: str
    risk_tier: str
    composite_score: float
    credit_history_score: float
    behavioral_score: float
    exposure_score: float
    open_anomaly_count: int = Field(default=0, description="Number of unresolved anomaly flags")
    critical_anomaly_count: int = Field(default=0, description="Critical-severity unresolved flags")
    active_loans_count: int = Field(default=0)
    total_outstanding_debt: float = Field(default=0.0)
    is_pep: bool
    kyc_status: str
    country_of_residence: Optional[str] = None
    last_scored_at: datetime


class RiskSummarySchema(BaseModel):
    """KPI cards row — top of the Risk Operations dashboard."""
    total_high_risk: int = Field(description="Clients at HIGH tier or above")
    total_critical: int = Field(description="Clients at CRITICAL tier")
    total_open_anomalies: int = Field(description="Unresolved anomaly flags across all clients")
    total_critical_anomalies: int
    total_exposure_usd: float = Field(description="Sum of outstanding debt across high-risk clients")
    portfolio_average_score: float = Field(description="Mean composite score across all scored clients")


class TierDistributionSchema(BaseModel):
    """
    Powers the Risk Heatmap grid cells and the tier breakdown bar chart.
    Each record = one cell in the Client Type × Risk Tier matrix.
    """
    risk_tier: str
    client_type: str
    count: int
    avg_score: float
    total_exposure_usd: float


class RiskHeatmapPayloadSchema(BaseModel):
    """
    Top-level JSON structure consumed by the React Risk Heatmap dashboard.

    The heatmap UI maps:
      - X-axis: risk_tier (LOW → CRITICAL)
      - Y-axis: client_type (RETAIL vs CORPORATE)
      - Cell colour intensity: average composite_score of clients in that cell
      - Cell count badge: count of clients in that cell

    The summary block feeds KPI cards at the top of the dashboard.
    """
    generated_at: datetime
    model_version: str
    total_clients_analyzed: int
    summary: RiskSummarySchema
    high_risk_clients: List[HighRiskClientSchema]
    tier_distribution: List[TierDistributionSchema]

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────────────────
# Ingestion Pipeline Schemas
# ──────────────────────────────────────────────────────────────────────────────

class PipelineRunResultSchema(BaseModel):
    """Returned by the data ingestion endpoint to confirm pipeline execution."""
    status: str
    clients_loaded: int
    transactions_loaded: int
    loans_loaded: int
    duration_seconds: float
    errors: List[str] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Batch Scoring Schemas
# ──────────────────────────────────────────────────────────────────────────────

class BatchScoringResultSchema(BaseModel):
    """Returned after a full portfolio re-scoring run."""
    status: str
    clients_scored: int
    score_distribution: Dict[str, int] = Field(
        description="Count of clients per risk tier after scoring"
    )
    duration_seconds: float
    errors: List[str] = Field(default_factory=list)


class AnomalyScanResultSchema(BaseModel):
    """Returned after an anomaly detection scan."""
    status: str
    transactions_scanned: int
    anomalies_detected: int
    breakdown_by_type: Dict[str, int]
    breakdown_by_severity: Dict[str, int]
    duration_seconds: float


# ──────────────────────────────────────────────────────────────────────────────
# AI Adverse Media Alert Schemas
# ──────────────────────────────────────────────────────────────────────────────

class AIAlertPayload(BaseModel):
    """
    Incoming payload from the n8n Adverse Media Early Warning Radar.
    Produced by an OpenAI LLM instructed to act as a Senior Credit Risk Analyst.
    """
    company_name:   str           = Field(..., min_length=1, max_length=200,
                                          description="Entity identified in the adverse media article")
    risk_score:     int           = Field(..., ge=1, le=10,
                                          description="AI severity rating: 1=minimal risk, 10=critical systemic risk")
    risk_summary:   str           = Field(..., min_length=10, max_length=1000,
                                          description="AI analyst 2-sentence risk assessment and recommended action")
    source_article: Optional[str] = Field(None, max_length=5000,
                                          description="Original article text that was analysed")


class AIAlertSchema(BaseModel):
    """Response schema for AI adverse media alerts served to the dashboard."""
    id:              str
    company_name:    str
    risk_score:      int
    risk_summary:    str
    source_article:  Optional[str] = None
    source:          str
    is_acknowledged: bool
    created_at:      datetime
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str]      = None

    model_config = {"from_attributes": True}

    @field_validator("is_acknowledged", mode="before")
    @classmethod
    def coerce_int_to_bool(cls, v: Any) -> bool:
        """SQLite stores booleans as 0/1 integers; coerce to proper bool."""
        return bool(v)
