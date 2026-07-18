"""
Anomaly Flag ORM Model
=======================
Records every suspicious pattern detected by the Anomaly Detection Engine.
Each row represents one distinct rule violation linked to a specific
transaction or a time-window over a client's activity.

Business Value: This table is the primary output of the AML/Fraud monitoring
module. In a production system it would feed:
  - A SAR (Suspicious Activity Report) generation workflow
  - A case-management system (investigator assignment)
  - Real-time customer account suspension triggers
  - Regulatory reporting to FinCEN / FATF-member FIUs

SQL Schema:
  TABLE anomaly_flags (
    id                TEXT PRIMARY KEY,
    client_id         TEXT REFERENCES clients(id),
    transaction_id    TEXT REFERENCES transactions(id),  -- NULL for pattern flags
    anomaly_type      TEXT NOT NULL,   -- VELOCITY|STRUCTURING|LOCATION_MISMATCH|LARGE_CASH|...
    severity          TEXT NOT NULL,   -- LOW|MEDIUM|HIGH|CRITICAL
    description       TEXT NOT NULL,   -- Human-readable explanation for investigators
    rule_triggered    TEXT NOT NULL,   -- Machine-readable rule identifier (e.g., "AML-V-001")
    flagged_amount    REAL,            -- The amount(s) involved
    flagged_at        DATETIME NOT NULL,
    status            TEXT DEFAULT 'OPEN',  -- OPEN|UNDER_REVIEW|RESOLVED|FALSE_POSITIVE
    resolved_at       DATETIME,
    investigator_note TEXT
  )

Indexes:
  idx_af_client_flagged   ON anomaly_flags(client_id, flagged_at DESC)
  idx_af_type             ON anomaly_flags(anomaly_type)
  idx_af_severity         ON anomaly_flags(severity)
  idx_af_status           ON anomaly_flags(status)
"""

import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class AnomalyType(str, enum.Enum):
    VELOCITY = "VELOCITY"                    # Rapid burst of transactions in short window
    STRUCTURING = "STRUCTURING"              # Multiple transactions just below CTR threshold
    LOCATION_MISMATCH = "LOCATION_MISMATCH" # Geographically impossible consecutive transactions
    LARGE_CASH = "LARGE_CASH"               # Single cash transaction > reporting threshold
    HIGH_RISK_COUNTERPARTY = "HIGH_RISK_COUNTERPARTY"  # Transfer to/from flagged entity
    ROUND_AMOUNT_PATTERN = "ROUND_AMOUNT_PATTERN"       # Artificial round-number activity
    DORMANT_ACCOUNT_SPIKE = "DORMANT_ACCOUNT_SPIKE"    # Sudden activity after 90-day inactivity


class AnomalySeverity(str, enum.Enum):
    LOW = "LOW"           # Informational — log and monitor
    MEDIUM = "MEDIUM"     # Standard review — assign analyst within 5 business days
    HIGH = "HIGH"         # Priority review — assign analyst within 24 hours
    CRITICAL = "CRITICAL" # Immediate — consider account hold, file SAR within 30 days


class AnomalyFlag(Base):
    __tablename__ = "anomaly_flags"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))

    # ── Ownership ─────────────────────────────────────────────────────────────
    client_id = Column(
        String(36),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # NULL for pattern-level flags that span multiple transactions
    transaction_id = Column(
        String(36),
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Detection Details ─────────────────────────────────────────────────────
    anomaly_type = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), nullable=False, index=True)

    # Human-readable for case-management system / investigator UI
    description = Column(Text, nullable=False)

    # Machine-readable rule code for reporting/automation (e.g., "AML-STR-001")
    rule_triggered = Column(String(50), nullable=False)

    # Stores the amount(s) involved — critical for SAR narrative generation
    flagged_amount = Column(Float, nullable=True)

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    flagged_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    status = Column(String(20), default="OPEN", nullable=False, index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    investigator_note = Column(Text, nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    client = relationship("Client", back_populates="anomaly_flags")
    transaction = relationship("Transaction", back_populates="anomaly_flags")

    # ── Composite Indexes ─────────────────────────────────────────────────────
    __table_args__ = (
        Index("idx_af_client_flagged_at", "client_id", "flagged_at"),
        Index("idx_af_severity_status", "severity", "status"),
        Index("idx_af_type_status", "anomaly_type", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<AnomalyFlag rule={self.rule_triggered} "
            f"severity={self.severity} status={self.status}>"
        )
