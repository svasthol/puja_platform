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
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",  # dev: browser treats this as distinct from localhost
    ]

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

    # ---- Admin auth (P-ADMIN-AUTH — per-app_context TTL) ---------------------
    # An account that can override refunds / edit the catalogue must not carry a
    # 30-day refresh token. Admin tokens are short-lived; customer/pujari keep
    # the values above. See SPEC_AMENDMENTS §19.
    ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ADMIN_REFRESH_TOKEN_EXPIRE_DAYS: int = 1
    # TOTP (Google Authenticator) for admin/support staff — SMS OTP is DLT-blocked
    # and wrong for an internal console. Secrets are Fernet-encrypted at rest.
    TOTP_ISSUER: str = "Mana Guruji"
    TOTP_STEP_SECONDS: int = 30
    TOTP_VERIFY_WINDOW: int = 1              # ± steps tolerated for clock skew
    # Fernet key(s) for encrypting TOTP secrets. Generate: Fernet.generate_key().
    # Comma-separated for rotation (first = current/encrypt; all = decrypt).
    # Empty is fine until the first admin is provisioned (validated at use, not boot).
    TOTP_ENC_KEYS: str = ""
    ADMIN_LOGIN_RATE_LIMIT_PER_HOUR: int = 20  # per phone — TOTP brute-force guard

    # ---- Payments -----------------------------------------------------------
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # ---- SMS / OTP — multi-provider failover --------------------------------
    # Chain: SMS_PROVIDER_ORDER=fast2sms,msg91  (tries left→right on failure)
    SMS_PROVIDER_ORDER: str = "fast2sms,msg91"
    MSG91_ENABLED: bool = False                 # set true after DLT + SendOTP template ready
    FAST2SMS_API_KEY: str = ""
    FAST2SMS_OTP_ROUTE: str = "otp"            # bulkV2 route for OTP
    FAST2SMS_QUICK_ROUTE: str = "q"            # Quick SMS — no DLT header (txn fallback)
    # MSG91 SendOTP REST (NOT OTP Widget tokenAuth / widgetId):
    #   MSG91_AUTH_KEY     = dashboard API authkey
    #   MSG91_TEMPLATE_ID  = OTP → Templates id with ##OTP## (not widgetId)
    MSG91_AUTH_KEY: str = ""
    MSG91_TEMPLATE_ID: str = ""
    MSG91_TXN_TEMPLATE_ID: str = ""           # transactional Flow template (needs DLT)
    MSG91_SENDER_ID: str = "PUJAPL"

    # ---- Firebase (FCM HTTP v1) ---------------------------------------------
    FCM_SERVICE_ACCOUNT_PATH: str = ""        # primary — path to Firebase service-account JSON
    FCM_SERVER_KEY: str = ""                  # legacy fallback only (deprecated on new projects)

    # ---- Storage (S3/R2/MinIO) -----------------------------------------------
    S3_ENDPOINT_URL: str = ""
    S3_BUCKET_KYC: str = "puja-kyc-docs"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_REGION: str = "ap-south-1"
    S3_KYC_URL_EXPIRE_SECONDS: int = 300      # signed URL TTL
    S3_BUCKET_CATALOG: str = "puja-catalog"
    S3_CATALOG_PUBLIC_URL: str = ""           # CDN base, e.g. https://cdn.example.com
    S3_CATALOG_URL_EXPIRE_SECONDS: int = 600  # presigned PUT TTL
    S3_CATALOG_MAX_BYTES: int = 5_242_880     # 5 MiB — catalogue images only
    S3_KYC_MAX_BYTES: int = 5_242_880         # 5 MiB — selfie upload cap

    # ---- Partner KYC (Setu DigiLocker — vendor-agnostic via KYC_VENDOR) --------
    KYC_VENDOR: str = "setu_digilocker"
    KYC_REDIRECT_URL: str = ""                # public callback base (Setu redirect landing)
    KYC_APP_RETURN_URL: str = "managuruji://kyc/complete"
    KYC_REQUEST_TTL_MINUTES: int = 30
    KYC_RETENTION_DAYS: int = 365
    KYC_IDENTITY_PEPPER: str = ""             # HMAC pepper for digilocker_id_hash
    KYC_SETU_BASE_URL: str = "https://dg-sandbox.setu.co"
    KYC_SETU_CLIENT_ID: str = ""
    KYC_SETU_CLIENT_SECRET: str = ""
    KYC_SETU_DIGILOCKER_PRODUCT_ID: str = ""
    KYC_SETU_PAN_PRODUCT_ID: str = ""
    KYC_CALLBACK_RATE_LIMIT_PER_HOUR: int = 60
    KYC_START_RATE_LIMIT_PER_HOUR: int = 10

    # ---- Maps ----------------------------------------------------------------
    GOOGLE_MAPS_API_KEY: str = ""

    # ---- Panchangam (§23.6) --------------------------------------------------
    # Self-hosted telugu-panchangam-app / @ishubhamx/panchangam-js adapter URL.
    # Dev example: http://127.0.0.1:3001/api/panchangam (engine :3001; admin_ui :3000; API :8000).
    # Empty = worker no-op until ops wires vendor (see SPEC_AMENDMENTS §23.6).
    PANCHANGAM_VENDOR_URL: str = ""
    PANCHANGAM_API_KEY: str = ""
    PANCHANGAM_DEFAULT_CITIES: list[str] = ["Hyderabad"]

    # ---- Platform business rules (override without redeploy via platform_settings table)
    # These are DEFAULTS only — live values come from platform_settings DB table.
    DEFAULT_ADVANCE_BOOKING_AMOUNT: float = 250.0
    DEFAULT_SUPPORT_REFUND_CAP_PER_ACTION: float = 5000.0
    DEFAULT_SUPPORT_REFUND_CAP_DAILY: float = 20000.0
    SLOT_HOLD_TTL_MINUTES: int = 5
    BOOKING_PAYMENT_TTL_MINUTES: int = 15
    DISPATCH_OFFER_TTL_SECONDS: int = 120     # 2 min per offer round
    DISPATCH_MAX_ROUNDS: int = 4
    DISPATCH_RADIUS_KM: list[float] = [3.0, 6.0, 10.0, 15.0]
    PUJARI_PRESENCE_TTL_SECONDS: int = 90     # 3 missed 30s heartbeats = offline
    WS_TICKET_TTL_SECONDS: int = 30

    # ---- Monitoring (P-MONITOR) ----------------------------------------------
    METRICS_ENABLED: bool = True
    SENTRY_DSN: str = ""
    MONITOR_PAYMENT_PENDING_GRACE_MINUTES: int = 30  # added to BOOKING_PAYMENT_TTL_MINUTES
    MONITOR_CONFIRMED_NO_SHOW_GRACE_MINUTES: int = 90
    MONITOR_REFUND_STALL_ATTEMPTS: int = 6

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

    @field_validator(
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "S3_BUCKET_KYC",
        "S3_BUCKET_CATALOG",
        "S3_REGION",
        "S3_ENDPOINT_URL",
        mode="before",
    )
    @classmethod
    def strip_s3_env_strings(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            return v.strip()
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
