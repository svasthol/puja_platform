"""
Application settings — loaded from environment variables or a .env file.
All secrets (DB password, JWT secret, Razorpay keys) MUST be env vars;
never hardcode them here. See .env.example for the required variables.
"""
from functools import lru_cache
from pydantic import PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application ---------------------------------------------------------
    APP_ENV: str = "development"              # development | staging | production
    APP_NAME: str = "Puja Booking Platform"
    DEBUG: bool = False
    SECRET_KEY: str                           # min 32 chars; generate with: openssl rand -hex 32
    API_V1_PREFIX: str = "/v1"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]

    # ---- Database ------------------------------------------------------------
    DATABASE_URL: PostgresDsn                 # e.g. postgresql+psycopg://user:pass@localhost:5432/puja_platform
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 5
    DATABASE_POOL_RECYCLE: int = 1800         # seconds; keeps conn alive through PgBouncer idle timeout

    # ---- Redis ---------------------------------------------------------------
    REDIS_URL: RedisDsn = "redis://localhost:6379/0"  # type: ignore[assignment]
    REDIS_DB_CACHE: int = 0
    REDIS_DB_CELERY: int = 1
    REDIS_DB_PRESENCE: int = 2

    # ---- Auth ----------------------------------------------------------------
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    OTP_EXPIRE_MINUTES: int = 10
    OTP_MAX_ATTEMPTS: int = 5
    OTP_RATE_LIMIT_PER_HOUR: int = 5         # per phone number

    # ---- Payments -----------------------------------------------------------
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # ---- SMS / OTP ----------------------------------------------------------
    MSG91_AUTH_KEY: str = ""
    MSG91_TEMPLATE_ID: str = ""
    MSG91_SENDER_ID: str = "PUJAPL"

    # ---- Firebase -----------------------------------------------------------
    FCM_SERVER_KEY: str = ""                  # or use service account JSON path
    FCM_SERVICE_ACCOUNT_PATH: str = ""

    # ---- Storage (S3/R2/MinIO) -----------------------------------------------
    S3_ENDPOINT_URL: str = ""
    S3_BUCKET_KYC: str = "puja-kyc-docs"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_REGION: str = "ap-south-1"
    S3_KYC_URL_EXPIRE_SECONDS: int = 300      # signed URL TTL

    # ---- Maps ----------------------------------------------------------------
    GOOGLE_MAPS_API_KEY: str = ""

    # ---- Platform business rules (override without redeploy via platform_settings table)
    # These are DEFAULTS only — live values come from platform_settings DB table.
    DEFAULT_ADVANCE_BOOKING_AMOUNT: float = 250.0
    SLOT_HOLD_TTL_MINUTES: int = 5
    BOOKING_PAYMENT_TTL_MINUTES: int = 15
    DISPATCH_OFFER_TTL_SECONDS: int = 120     # 2 min per offer round
    DISPATCH_MAX_ROUNDS: int = 4
    DISPATCH_RADIUS_KM: list[float] = [3.0, 6.0, 10.0, 15.0]
    PUJARI_PRESENCE_TTL_SECONDS: int = 90     # 3 missed 30s heartbeats = offline
    WS_TICKET_TTL_SECONDS: int = 30

    # ---- Timezone (Asia/Kolkata for all business logic) ----------------------
    PLATFORM_TIMEZONE: str = "Asia/Kolkata"  # never use server default; use this explicitly

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        # Ensure the URL uses the psycopg3 driver prefix, not psycopg2
        if v.startswith("postgresql://") or v.startswith("postgresql+psycopg2"):
            v = v.replace("postgresql+psycopg2", "postgresql+psycopg")
            if not v.startswith("postgresql+psycopg"):
                v = v.replace("postgresql://", "postgresql+psycopg://")
        return v

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
