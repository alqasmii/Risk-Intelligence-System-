"""
Risk Score ORM Model
=====================
Persists every computed risk score with its full component breakdown.
Storing scores as immutable records (not updates) creates a complete
audit trail — essential for regulatory review under BCBS 239.

Business Value: A persisted score history enables:
  1. Trend analysis — is a client's risk trajectory improving or deteriorating?
  2. Back-testing — did the model predict the clients who subsequently defaulted?
  3. Regulatory defence — auditors can see exactly what score was in place
     when a credit decision was made and which factors drove it.
  4. Model governance — comparing score distributions before/after threshold changes.

SQL Schema:
  TABLE risk_scores (
    id                     TEXT PRIMARY KEY,
    client_id              TEXT REFERENCES clients(id),
    composite_score        REAL NOT NULL,        -- 0–100; higher = greater risk
    risk_tier              TEXT NOT NULL,         -- LOW|MEDIUM|HIGH|VERY_HIGH|CRITICAL
    credit_history_score   REAL NOT NULL,         -- Component 1 (weight 0.40)
    behavioral_score       REAL NOT NULL,         -- Component 2 (weight 0.30)
    exposure_score         REAL NOT NULL,         -- Component 3 (weight 0.30)
    pep_adjustment         REAL NOT NULL,         -- Compliance penalty
    kyc_adjustment         REAL NOT NULL,         -- KYC compliance penalty
    scored_at              DATETIME NOT NULL,
    model_version          TEXT DEFAULT '1.0.0',
    active_loans_count     INTEGER,
    total_outstanding_debt REAL,
    transactions_analyzed  INTEGER
  )

Indexes:
  idx_rs_client_scored    ON risk_scores(client_id, scored_at DESC)
  idx_rs_tier             ON risk_scores(risk_tier)
  idx_rs_score_desc       ON risk_scores(composite_score DESC)
"""

import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class RiskTier(str, enum.Enum):
    LOW = "LOW"               # Score  0–34:  standard monitoring
    MEDIUM = "MEDIUM"         # Score 35–54:  quarterly review
    HIGH = "HIGH"             # Score 55–69:  monthly review + credit freeze
    VERY_HIGH = "VERY_HIGH"   # Score 70–84:  senior committee escalation
    CRITICAL = "CRITICAL"     # Score 85–100: immediate hold + RM alert


class RiskScore(Base):
    __tablename__ = "risk_scores"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))

    # ── Ownership ─────────────────────────────────────────────────────────────
    client_id = Column(
        String(36),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Composite Score ───────────────────────────────────────────────────────
    composite_score = Column(Float, nullable=False)   # Final weighted score 0–100
    risk_tier = Column(String(20), nullable=False, index=True)

    # ── Component Breakdown ───────────────────────────────────────────────────
    # Storing raw components allows Risk Officers to drill into what drove
    # a score change — required for model explainability / SR 11-7 compliance
    credit_history_score = Column(Float, nullable=False)  # 0–100; 40% weight
    behavioral_score = Column(Float, nullable=False)       # 0–100; 30% weight
    exposure_score = Column(Float, nullable=False)         # 0–100; 30% weight

    # ── Compliance Adjustments ────────────────────────────────────────────────
    pep_adjustment = Column(Float, nullable=False, default=0.0)   # flat penalty points
    kyc_adjustment = Column(Float, nullable=False, default=0.0)   # flat penalty points

    # ── Metadata ──────────────────────────────────────────────────────────────
    scored_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    model_version = Column(String(20), default="1.0.0", nullable=False)

    # ── Scoring Context (snapshot at time of scoring) ─────────────────────────
    active_loans_count = Column(Integer, nullable=True)
    total_outstanding_debt = Column(Float, nullable=True)
    transactions_analyzed = Column(Integer, nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    client = relationship("Client", back_populates="risk_scores")

    # ── Composite Indexes ─────────────────────────────────────────────────────
    __table_args__ = (
        Index("idx_rs_client_scored_at", "client_id", "scored_at"),
        Index("idx_rs_tier_score", "risk_tier", "composite_score"),
    )

    def __repr__(self) -> str:
        return (
            f"<RiskScore client={self.client_id[:8]} "
            f"score={self.composite_score:.1f} tier={self.risk_tier} "
            f"at={self.scored_at}>"
        )
