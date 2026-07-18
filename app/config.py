"""
Application Configuration
==========================
Centralizes all tunable risk parameters using Pydantic v2 BaseSettings.

Any value can be overridden via environment variable or a .env file,
allowing Risk Officers to tune scoring thresholds and AML detection
parameters without code changes — supporting rapid regulatory and
policy updates without a deployment cycle.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Application Metadata ──────────────────────────────────────────────────
    APP_NAME: str = "Automated Risk Intelligence System"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # ── Database ──────────────────────────────────────────────────────────────
    # SQLite for local dev; set DATABASE_URL to PostgreSQL on Vercel / production.
    # Default uses /tmp so the file is writable on serverless platforms (Vercel,
    # Lambda) where the project root is read-only. Override via .env locally.
    DATABASE_URL: str = "sqlite:////tmp/risk_intelligence.db"

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Comma-separated list of allowed origins, or a single URL.
    # Set to your Vercel deployment URL in production.
    FRONTEND_URL: str = "http://localhost:3000"

    # ── Risk Scoring Thresholds ───────────────────────────────────────────────
    # Scores ∈ [0, 100] where 100 = maximum risk.
    # Tier boundaries align with Basel III Internal Ratings-Based (IRB) approach.
    MEDIUM_RISK_THRESHOLD: float = 35.0       # Standard monitoring → quarterly review
    HIGH_RISK_THRESHOLD: float = 55.0         # Monthly review + credit limit freeze
    VERY_HIGH_RISK_THRESHOLD: float = 70.0    # Senior risk committee escalation
    CRITICAL_RISK_THRESHOLD: float = 85.0     # Immediate hold + relationship manager alert

    # Component weights — MUST sum to 1.0
    CREDIT_HISTORY_WEIGHT: float = 0.40       # Backward-looking creditworthiness
    BEHAVIORAL_WEIGHT: float = 0.30           # Real-time transaction patterns
    EXPOSURE_WEIGHT: float = 0.30             # Balance sheet vulnerability

    # ── Anomaly Detection Parameters ─────────────────────────────────────────
    # Velocity: transaction burst detection
    VELOCITY_WINDOW_MINUTES: int = 60
    VELOCITY_MAX_TRANSACTIONS: int = 8        # > N transactions in window → flag

    # Structuring: "smurfing" / layering detection (FATF Recommendation 16)
    AML_REPORTING_THRESHOLD: float = 10_000.00   # USD CTR filing threshold (BSA)
    STRUCTURING_LOWER_BOUND: float = 9_000.00    # "Just below threshold" detection
    STRUCTURING_MIN_COUNT: int = 3               # Minimum occurrences to flag

    # Location mismatch: geographic impossibility window
    LOCATION_MISMATCH_WINDOW_HOURS: float = 2.0

    # ── Behavioral Analysis ───────────────────────────────────────────────────
    BEHAVIORAL_LOOKBACK_DAYS: int = 90
    RECENT_TRANSACTION_DAYS: int = 30

    # ── Exposure Thresholds ───────────────────────────────────────────────────
    HIGH_DTI_THRESHOLD: float = 0.45      # Debt-to-Income > 45% → elevated risk
    CRITICAL_DTI_THRESHOLD: float = 0.60  # DTI > 60% → critical exposure

    @property
    def cors_origins(self) -> list[str]:
        """Parse FRONTEND_URL (comma-separated) into a list of allowed origins.

        In development the localhost dev-server origins are always included so
        the app works out of the box. In production only the explicitly
        configured origins are allowed — no wildcard — because the API uses
        credentialed CORS (allow_credentials=True), which the CORS spec
        forbids combining with a "*" origin.
        """
        configured = [o.strip() for o in self.FRONTEND_URL.split(",") if o.strip()]
        if self.ENVIRONMENT.lower() in ("development", "dev", "local"):
            dev_origins = [
                "http://localhost:3000",
                "http://localhost:5173",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
            ]
            for o in dev_origins:
                if o not in configured:
                    configured.append(o)
        return configured


settings = Settings()
