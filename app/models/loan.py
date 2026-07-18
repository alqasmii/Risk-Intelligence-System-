"""
Loan Portfolio ORM Model
=========================
Represents individual loan facilities within a client's credit portfolio.
Feeds both the Credit History component (delinquency/default status) and
the Exposure component (utilization, interest rate risk) of the risk score.

Business Value: Loan portfolio quality is the single most predictive
indicator of credit loss. Tracking outstanding balances, delinquency
aging, and interest rate exposure allows the risk engine to calculate
Expected Loss (EL = PD × LGD × EAD) — the fundamental measure of
credit risk capital requirements under Basel III.

SQL Schema:
  TABLE loans (
    id                  TEXT PRIMARY KEY,
    client_id           TEXT REFERENCES clients(id),
    loan_type           TEXT NOT NULL,          -- MORTGAGE|PERSONAL|COMMERCIAL|REVOLVING|AUTO
    loan_amount         REAL NOT NULL,           -- Original principal (USD)
    outstanding_balance REAL NOT NULL,           -- Current remaining balance
    interest_rate       REAL NOT NULL,           -- Annual rate (%)
    status              TEXT DEFAULT 'CURRENT',  -- CURRENT|DELINQUENT|DEFAULT|PAID_OFF
    origination_date    DATE NOT NULL,
    maturity_date       DATE NOT NULL,
    days_past_due       INTEGER DEFAULT 0,       -- DPD — regulatory aging bucket
    collateral_type     TEXT,                    -- NONE|PROPERTY|VEHICLE|SECURITIES
    collateral_value    REAL                     -- Current market value of collateral
  )

Indexes:
  idx_loans_client         ON loans(client_id)
  idx_loans_status         ON loans(status)
  idx_loans_client_status  ON loans(client_id, status)     -- most frequent join pattern
"""

import enum
from datetime import datetime, date, timezone
from uuid import uuid4

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class LoanType(str, enum.Enum):
    MORTGAGE = "MORTGAGE"       # Secured; collateral = property
    PERSONAL = "PERSONAL"       # Unsecured; highest LGD
    COMMERCIAL = "COMMERCIAL"   # Business lending; tied to business cash flows
    REVOLVING = "REVOLVING"     # Credit lines/cards; balance fluctuates
    AUTO = "AUTO"               # Secured; collateral = vehicle


class LoanStatus(str, enum.Enum):
    CURRENT = "CURRENT"           # Up to date payments
    DELINQUENT = "DELINQUENT"    # 30–89 days past due (DPD)
    DEFAULT = "DEFAULT"           # 90+ DPD or formal default event
    PAID_OFF = "PAID_OFF"         # Fully repaid
    RESTRUCTURED = "RESTRUCTURED" # Distressed restructuring / forbearance


class Loan(Base):
    __tablename__ = "loans"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))

    # ── Ownership ─────────────────────────────────────────────────────────────
    client_id = Column(
        String(36),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Loan Terms ────────────────────────────────────────────────────────────
    loan_type = Column(String(20), nullable=False)
    loan_amount = Column(Float, nullable=False)           # Original principal
    outstanding_balance = Column(Float, nullable=False)   # Current remaining debt
    interest_rate = Column(Float, nullable=False)         # Annual % (e.g., 6.5)
    origination_date = Column(Date, nullable=False)
    maturity_date = Column(Date, nullable=False)

    # ── Portfolio Quality ─────────────────────────────────────────────────────
    # DPD (Days Past Due) is the primary regulatory aging metric under IFRS 9
    status = Column(String(20), default=LoanStatus.CURRENT.value, nullable=False, index=True)
    days_past_due = Column(Integer, default=0, nullable=False)

    # ── Collateral ────────────────────────────────────────────────────────────
    # Collateral reduces Loss-Given-Default (LGD) — a core Basel input
    collateral_type = Column(String(20), nullable=True)   # NONE | PROPERTY | VEHICLE | SECURITIES
    collateral_value = Column(Float, nullable=True)        # Current market value

    # ── Audit ─────────────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # ── Relationships ─────────────────────────────────────────────────────────
    client = relationship("Client", back_populates="loans")

    # ── Composite Indexes ─────────────────────────────────────────────────────
    __table_args__ = (
        Index("idx_loans_client_status", "client_id", "status"),
        Index("idx_loans_status_dpd", "status", "days_past_due"),
    )

    @property
    def utilization_rate(self) -> float:
        """Outstanding balance as fraction of original principal."""
        if self.loan_amount and self.loan_amount > 0:
            return round(self.outstanding_balance / self.loan_amount, 4)
        return 0.0

    def __repr__(self) -> str:
        return (
            f"<Loan id={self.id[:8]} type={self.loan_type} "
            f"balance={self.outstanding_balance:.2f} status={self.status}>"
        )
