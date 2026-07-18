"""ORM Models package — import all models here so SQLAlchemy registers them."""
from app.models.client import Client, ClientType
from app.models.transaction import Transaction, TransactionType
from app.models.loan import Loan, LoanType, LoanStatus
from app.models.risk_score import RiskScore, RiskTier
from app.models.anomaly import AnomalyFlag, AnomalyType, AnomalySeverity
from app.models.ai_alert import AIAlert, AIAlertSource

__all__ = [
    "Client", "ClientType",
    "Transaction", "TransactionType",
    "Loan", "LoanType", "LoanStatus",
    "RiskScore", "RiskTier",
    "AnomalyFlag", "AnomalyType", "AnomalySeverity",
    "AIAlert", "AIAlertSource",
]
