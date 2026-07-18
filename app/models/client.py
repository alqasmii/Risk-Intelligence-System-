"""
Client ORM Model
================
Represents both Retail (individual) and Corporate (business) clients.

Business Value: The distinction between client types is foundational to
risk scoring — corporate clients are assessed on industry sector, years
in operation, and revenue concentration risk, while retail clients are
scored against personal income and consumer debt metrics.

SQL Schema:
  TABLE clients (
    id                   TEXT PRIMARY KEY,   -- UUID v4
    client_type          TEXT NOT NULL,      -- RETAIL | CORPORATE
    name                 TEXT NOT NULL,
    external_credit_score INTEGER,           -- 300–850 FICO-equivalent
    annual_income        REAL,               -- USD
    debt_to_income_ratio REAL,               -- 0.0–1.0
    country_of_residence TEXT,               -- ISO 3166-1 alpha-2
    industry_sector      TEXT,               -- Corporate: NAICS sector
    years_in_operation   INTEGER,            -- Corporate: years since founding
    is_pep               INTEGER DEFAULT 0,  -- Politically Exposed Person flag
    kyc_status           TEXT DEFAULT 'VERIFIED',
    created_at           DATETIME,
    updated_at           DATETIME
  )

Indexes:
  idx_clients_type       ON clients(client_type)
  idx_clients_kyc        ON clients(kyc_status)
  idx_clients_pep        ON clients(is_pep)

Cardinality: ~500K rows (retail bank), ~50K rows (corporate bank)
"""

import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, Index, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class ClientType(str, enum.Enum):
    RETAIL = "RETAIL"
    CORPORATE = "CORPORATE"


class Client(Base):
    __tablename__ = "clients"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))

    # ── Identity ──────────────────────────────────────────────────────────────
    client_type = Column(Enum(ClientType), nullable=False, index=True)
    name = Column(String(200), nullable=False)

    # ── Credit Profile ────────────────────────────────────────────────────────
    # External score from credit bureaus (Experian, Equifax, TransUnion)
    # FICO range: 300 (worst) → 850 (best); None = unrated / thin file
    external_credit_score = Column(Integer, nullable=True)

    # ── Financial Metrics ─────────────────────────────────────────────────────
    annual_income = Column(Float, nullable=True)   # USD; gross annual
    # Debt-to-Income: total monthly debt payments / gross monthly income
    # Basel III Pillar 2 key indicator; >45% considered elevated risk
    debt_to_income_ratio = Column(Float, nullable=True)

    # ── Geographic & Sector ───────────────────────────────────────────────────
    country_of_residence = Column(String(2), nullable=True)   # ISO alpha-2
    industry_sector = Column(String(100), nullable=True)       # Corporate only
    years_in_operation = Column(Integer, nullable=True)        # Corporate only

    # ── Compliance Flags ──────────────────────────────────────────────────────
    # Politically Exposed Person — FATF Recommendation 12 mandates enhanced
    # due diligence for all PEPs; any PEP flag adds mandatory risk penalty
    is_pep = Column(Boolean, default=False, nullable=False)

    # KYC status: VERIFIED | PENDING | EXPIRED | REJECTED
    # Unverified KYC is a BSA/AML compliance violation — triggers max penalty
    kyc_status = Column(String(20), default="VERIFIED", nullable=False, index=True)

    # ── Audit ─────────────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    transactions = relationship("Transaction", back_populates="client", lazy="dynamic")
    loans = relationship("Loan", back_populates="client", lazy="select")
    risk_scores = relationship("RiskScore", back_populates="client", lazy="select")
    anomaly_flags = relationship("AnomalyFlag", back_populates="client", lazy="dynamic")

    # ── Composite Indexes ─────────────────────────────────────────────────────
    __table_args__ = (
        Index("idx_clients_type_kyc", "client_type", "kyc_status"),
        Index("idx_clients_pep", "is_pep"),
    )

    def __repr__(self) -> str:
        return f"<Client id={self.id[:8]} name={self.name!r} type={self.client_type}>"
