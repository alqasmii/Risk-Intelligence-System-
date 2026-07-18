"""
Transaction ORM Model
======================
Represents every financial transaction associated with a client.
This is the primary input for both behavioral risk scoring and
AML anomaly detection.

Business Value: Transaction-level data is the most granular signal
available to a risk team. High-velocity, cross-border, and cash-heavy
transaction patterns are the leading indicators of fraud and money
laundering. This table feeds both the real-time anomaly detection
engine and the 90-day behavioral component of the risk score.

SQL Schema:
  TABLE transactions (
    id                TEXT PRIMARY KEY,
    client_id         TEXT REFERENCES clients(id),
    amount            REAL NOT NULL,
    currency          TEXT DEFAULT 'USD',
    transaction_type  TEXT NOT NULL,          -- CREDIT|DEBIT|WIRE|CASH|REVERSAL
    timestamp         DATETIME NOT NULL,
    location_country  TEXT,                   -- ISO alpha-2
    location_city     TEXT,
    merchant_category TEXT,                   -- MCC code description
    counterparty_id   TEXT,                   -- Anonymized counterparty reference
    status            TEXT DEFAULT 'COMPLETED'
  )

Indexes:
  idx_tx_client_ts      ON transactions(client_id, timestamp DESC)  -- behavioral lookback
  idx_tx_type_ts        ON transactions(transaction_type, timestamp)  -- AML pattern queries
  idx_tx_country        ON transactions(location_country)              -- geo-risk queries
  idx_tx_amount         ON transactions(amount)                        -- structuring detection

Cardinality: ~50M rows (active banking system); partitioned by month in production
"""

import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import relationship

from app.database import Base


class TransactionType(str, enum.Enum):
    CREDIT = "CREDIT"       # Incoming funds
    DEBIT = "DEBIT"         # Outgoing electronic payment
    WIRE = "WIRE"           # Cross-border wire transfer (enhanced monitoring)
    CASH = "CASH"           # Cash deposit/withdrawal (BSA CTR threshold applies)
    REVERSAL = "REVERSAL"   # Reversed/corrected transaction


class Transaction(Base):
    __tablename__ = "transactions"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))

    # ── Ownership ─────────────────────────────────────────────────────────────
    client_id = Column(
        String(36),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Financial Details ─────────────────────────────────────────────────────
    amount = Column(Float, nullable=False)           # Always positive; direction from type
    currency = Column(String(3), default="USD", nullable=False)
    transaction_type = Column(String(20), nullable=False, index=True)

    # ── Temporal ──────────────────────────────────────────────────────────────
    # Indexed DESC because almost all queries scan recent transactions first
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    # ── Geographic ────────────────────────────────────────────────────────────
    # Used by LOCATION_MISMATCH anomaly detection rule — consecutive transactions
    # in geographically impossible locations within a short time window
    location_country = Column(String(2), nullable=True)   # ISO alpha-2
    location_city = Column(String(100), nullable=True)

    # ── Merchant / Counterparty ───────────────────────────────────────────────
    merchant_category = Column(String(100), nullable=True)  # e.g., "GAMBLING", "CRYPTO"
    counterparty_id = Column(String(36), nullable=True)      # Anonymized reference

    # ── Status ────────────────────────────────────────────────────────────────
    status = Column(String(20), default="COMPLETED", nullable=False)

    # ── Relationships ─────────────────────────────────────────────────────────
    client = relationship("Client", back_populates="transactions")
    anomaly_flags = relationship("AnomalyFlag", back_populates="transaction")

    # ── Composite Indexes ─────────────────────────────────────────────────────
    # The most performance-critical index: nearly every behavioral query filters
    # by client_id + timestamp range (e.g., "last 90 days activity")
    __table_args__ = (
        Index("idx_tx_client_timestamp", "client_id", "timestamp"),
        Index("idx_tx_country_timestamp", "location_country", "timestamp"),
        Index("idx_tx_type_amount", "transaction_type", "amount"),
    )

    def __repr__(self) -> str:
        return (
            f"<Transaction id={self.id[:8]} client={self.client_id[:8]} "
            f"amount={self.amount:.2f} type={self.transaction_type}>"
        )
