# core/config.py
import os
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Telegram Stars checkout is retired. Historical Stars settlements remain supported.
TELEGRAM_STARS_CHECKOUT_ENABLED = False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Bot
    BOT_TOKEN: str
    BOT_USERNAME: str = "apix_ai_bot"
    WEBHOOK_URL: str = "https://testapi.chillcreative.ru"
    WEBHOOK_PATH: str = "/webhook/telegram"
    WEBHOOK_SECRET: str = ""
    TELEGRAM_STARTUP_COMMANDS_ENABLED: bool = False

    # Admin
    ADMIN_IDS: list[int] = []

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    ENV: str = "development"
    APIX_WEB_DEV_AUTH: bool = False
    WEB_PUBLIC_URL: str = "https://apixbotai.com"

    # DB
    DATABASE_URL: str = ""
    DB_BACKUP_ENABLED: bool = True
    DB_BACKUP_INTERVAL_SECONDS: int = 21600
    DB_BACKUP_DIR: str = "data/db_backups"
    DB_BACKUP_KEEP_LAST: int = 4
    REDIS_URL: str = "redis://redis:6379"

    # CometAPI (Kling, Seedream, Gemini, Grok, Seedance, Veo, WAN)
    COMET_API_KEY: str = Field(validation_alias=AliasChoices("COMET_API_KEY", "COMET_KEY"))
    COMET_BASE_URL: str = "https://api.cometapi.com"
    MIDJOURNEY_WEBHOOK_PATH: str = "/webhook/comet/midjourney"
    MIDJOURNEY_WEBHOOK_SECRET: str = ""

    # aivideoapi.ai (HappyHorse)
    AIVIDEOAPI_KEY: str = ""

    # kie.ai
    KIE_AI_KEY: str = ""
    SEEDANCE_PRIMARY_PROVIDER: Literal["kieai", "neironych"] = "neironych"
    SEEDANCE_UNCERTAIN_ROUTE_COOLDOWN_SECONDS: int = Field(default=1800, ge=180, le=86400)
    MUSIC_RECONCILE_INTERVAL_SECONDS: int = Field(default=300, ge=30, le=3600)
    MUSIC_RECONCILE_MIN_AGE_SECONDS: int = Field(default=180, ge=60, le=3600)

    # Neironych API — Seedance 2.0/2.5 production provider + admin lab
    NEIRONYCH_API_KEY: str = ""
    NEIRONYCH_API_BASE_URL: str = "https://api.xn--e1aikcel5c5a.online"
    NEIRONYCH_HTTP_TIMEOUT_SECONDS: float = 120.0
    # Nano Banana 2.1: Neironych synchronous primary, Nexus async fallback.
    NANO_BANANA_21_PRIMARY_PROVIDER: Literal["neironych", "nexus"] = "neironych"
    # Keep below APIX's current nginx proxy_read_timeout (120s); this is a paid synchronous POST.
    NEIRONYCH_IMAGE_TIMEOUT_SECONDS: float = Field(default=100.0, ge=10.0, le=600.0)
    NEIRONYCH_IMAGE_MAX_BYTES: int = Field(default=32 * 1024 * 1024, ge=1024)
    NEIRONYCH_IMAGE_MAX_PIXELS: int = Field(default=64 * 1024 * 1024, ge=4096)
    NEIRONYCH_IMAGE_RECONCILE_INTERVAL_SECONDS: int = Field(default=75, ge=30, le=3600)
    NEIRONYCH_IMAGE_RECONCILE_BATCH_SIZE: int = Field(default=60, ge=1, le=200)
    NEIRONYCH_POLL_INTERVAL_SECONDS: float = 10.0
    NEIRONYCH_POLL_TIMEOUT_SECONDS: int = 1800
    NEIRONYCH_MAX_VIDEO_BYTES: int = 250 * 1024 * 1024
    # Seedance video recovery is independent of user visits to history.
    NEIRONYCH_VIDEO_RECONCILE_INTERVAL_SECONDS: int = Field(default=90, ge=30, le=3600)
    NEIRONYCH_VIDEO_RECONCILE_MIN_AGE_SECONDS: int = Field(default=30, ge=0, le=3600)
    NEIRONYCH_VIDEO_RECONCILE_BATCH_SIZE: int = Field(default=24, ge=1, le=200)
    NEIRONYCH_VIDEO_RECONCILE_CONCURRENCY: int = Field(default=4, ge=1, le=12)
    NEIRONYCH_VIDEO_RECONCILE_TIMEOUT_SECONDS: int = Field(default=240, ge=30, le=1800)
    NEIRONYCH_VIDEO_TELEGRAM_UPLOAD_BUDGET_FRACTION: float = Field(default=0.75, ge=0.4, le=0.85)
    NEIRONYCH_VIDEO_POLL_LEASE_SECONDS: int = Field(default=600, ge=120, le=3600)
    NEIRONYCH_VIDEO_ALERT_AGE_SECONDS: int = Field(default=3600, ge=300, le=86400)
    # Deadline for a single paid Neironych Seedance request, independent of
    # other users' provider routes. The scheduler refunds after one final GET.
    SEEDANCE_AUTO_REFUND_SECONDS: int = Field(default=3600, ge=1800, le=86400)
    SEEDANCE_FINAL_STATUS_TIMEOUT_SECONDS: int = Field(default=12, ge=3, le=30)
    SEEDANCE_PROVIDER_REFUND_REVIEW_INTERVAL_SECONDS: int = Field(default=900, ge=60, le=86400)
    NEIRONYCH_VIDEO_NOTICE_LEASE_SECONDS: int = Field(default=600, ge=60, le=3600)
    NEIRONYCH_VIDEO_NOTICE_RETRY_SECONDS: int = Field(default=60, ge=15, le=3600)
    NEIRONYCH_VIDEO_NOTICE_MAX_BACKOFF_SECONDS: int = Field(default=900, ge=60, le=86400)
    NEIRONYCH_VIDEO_NOTICE_MAX_ATTEMPTS: int = Field(default=8, ge=1, le=32)
    NEIRONYCH_VIDEO_NOTICE_SCAN_ID_SPAN: int = Field(default=5000, ge=100, le=100000)
    NEIRONYCH_TEST_POLL_INTERVAL_SECONDS: float = 10.0
    NEIRONYCH_TEST_POLL_TIMEOUT_SECONDS: int = 1800
    NEIRONYCH_TEST_MAX_VIDEO_BYTES: int = 250 * 1024 * 1024

    # Higgsfield / Genjutsu
    HIGGSFIELD_CREDENTIALS: str = ""  # KEY_ID:KEY_SECRET
    HIGGSFIELD_BASE_URL: str = "https://api.higgsfield.ai"
    HIGGSFIELD_TIMEOUT_SECONDS: float = 120.0
    HIGGSFIELD_MAX_RETRIES: int = 3
    HIGGSFIELD_RETRY_BACKOFF_SECONDS: float = 1.0
    HIGGSFIELD_RETRY_MAX_BACKOFF_SECONDS: float = 30.0
    # Genjutsu renders regularly outlive the shared 600s video poll budget, so
    # polling and the stale reconcile guard are provider-scoped. The stale guard
    # must stay above the poll timeout, otherwise reconciliation refunds a task
    # that is still inside the provider polling window.
    HIGGSFIELD_POLL_INTERVAL_SECONDS: float = 5.0
    HIGGSFIELD_POLL_TIMEOUT_SECONDS: int = 1800
    HIGGSFIELD_STALE_TIMEOUT_SECONDS: int = 2400
    HIGGSFIELD_GENJUTSU_MOTION_ENDPOINT: str = "higgsfield/genjutsu/motion-transfer/v1.0"
    # Kept configurable because Higgsfield's current Object Swap docs have shipped
    # both higgsfield/... and a historical higgsfiled/... spelling.
    HIGGSFIELD_GENJUTSU_OBJECT_ENDPOINT: str = "higgsfiled/genjutsu/object-swap/v1.0"

    # KIE.AI callbacks
    KIE_WEBHOOK_PATH: str = "/webhook/kie"
    KIE_WEBHOOK_SECRET: str = ""
    KIE_WEBHOOK_HMAC_KEY: str = ""

    # Public static uploads used as stable references for KIE and Telegram.
    STATIC_UPLOAD_DIR: str = "static/upload"
    STATIC_UPLOAD_URL_PATH: str = "/static/upload"
    STATIC_UPLOAD_PUBLIC_BASE_URL: str = ""
    STATIC_UPLOAD_PUBLIC_URL_PATH: str = ""

    # CryptoBot
    CRYPTOBOT_TOKEN: str = ""
    CRYPTOBOT_BASE_URL: str = "https://pay.crypt.bot/api"

    # T-Bank Acquiring
    TBANK_TERMINAL_KEY: str = ""
    TBANK_PASSWORD: str = ""
    TBANK_BASE_URL: str = "https://securepay.tinkoff.ru/v2"
    TBANK_SUCCESS_URL: str = ""
    TBANK_FAIL_URL: str = ""

    # Lava.top
    LAVA_API_KEY: str = ""
    LAVA_API_BASE_URL: str = "https://gate.lava.top"
    LAVA_WEBHOOK_PATH: str = "/webhook/lava"
    LAVA_DEFAULT_EMAIL: str = "buyer@example.com"

    # Tribute Shop API
    TRIBUTE_API_KEY: str = ""
    TRIBUTE_API_BASE_URL: str = "https://tribute.tg/api/v1"
    TRIBUTE_WEBHOOK_PATH: str = "/webhook/tribute"
    TRIBUTE_HTTP_TIMEOUT: float = 30.0
    TRIBUTE_SUCCESS_URL: str = ""
    TRIBUTE_FAIL_URL: str = ""

    # Email auth delivery
    WEB_AUTH_EMAIL_ENABLED: bool = False
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = ""
    RESEND_FROM_NAME: str = "APIX Studio"

    # Email auth delivery (SMTP fallback)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "APIX Studio"
    SMTP_REPLY_TO: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False

    # Web registration CAPTCHA (Cloudflare Turnstile)
    WEB_CAPTCHA_ENABLED: bool = False
    WEB_CAPTCHA_PROVIDER: str = "turnstile"
    WEB_CAPTCHA_SITE_KEY: str = ""
    WEB_CAPTCHA_SECRET_KEY: str = ""

    # KIE.AI photo → prompt (GPT-5.x vision via kie.ai)
    KIE_PHOTO_PROMPT_MODEL: str = "gpt-5-2"
    KIE_PHOTO_PROMPT_FALLBACK: str = "gpt-5-5"

    # KIE.AI text assistant
    KIE_ASSISTANT_MODEL: str = "gpt-5-4"
    KIE_ASSISTANT_FALLBACK: str = "claude-sonnet-4-5"
    COMET_ASSISTANT_MODEL: str = "gpt-5.4"
    COMET_ASSISTANT_FALLBACK: str = "gpt-5.4-mini"
    COMET_VIDEO_PROMPT_MODEL: str = "qwen3.8-max"
    COMET_VIDEO_PROMPT_FPS: float = Field(default=2.0, ge=0.1, le=10.0)

    # Feature flags
    SUBSCRIPTION_ENABLED: bool = False
    TELEGRAM_STARS_ENABLED: bool = False
    REFERRAL_FREEZE: bool = False

    # Credits
    WELCOME_BONUS_CREDITS: int = 3
    REFERRAL_L1_CREDITS: int = 3
    FEED_REMIX_REWARD_RUB: float = 5.0
    REFERRAL_WITHDRAW_MIN_RUB: float = 1000.0
    REFERRAL_EXCHANGE_MIN_RUB: float = 100.0
    REFERRAL_EXCHANGE_RUB_PER_CREDIT: float = 10.0
    REFERRAL_ANTIFRAUD_ENABLED: bool = True
    REFERRAL_ANTIFRAUD_WINDOW_MINUTES: int = 60
    REFERRAL_ANTIFRAUD_MIN_L1_REFS: int = 25
    REFERRAL_ANTIFRAUD_MIN_INACTIVE_RATIO: float = 0.95

    # Referral commissions
    REFERRAL_COMMISSION_L1: float = 0.40
    REFERRAL_COMMISSION_L2: float = 0.07
    REFERRAL_COMMISSION_L3: float = 0.03

    # Polling
    POLLING_INTERVAL: float = 3.0
    POLLING_TIMEOUT: int = 600

    @model_validator(mode="after")
    def require_provider_webhook_security(self) -> "Settings":
        env = str(self.ENV or "").strip().lower()
        if env in {"prod", "production"}:
            if self.KIE_AI_KEY and not self.KIE_WEBHOOK_HMAC_KEY.strip():
                raise ValueError(
                    "KIE_WEBHOOK_HMAC_KEY is required in production when KIE_AI_KEY is configured"
                )
            if self.BOT_TOKEN and not self.WEBHOOK_SECRET.strip():
                raise ValueError("WEBHOOK_SECRET is required in production")
            if self.MIDJOURNEY_WEBHOOK_PATH and self.COMET_API_KEY and not (
                self.MIDJOURNEY_WEBHOOK_SECRET or self.WEBHOOK_SECRET
            ).strip():
                raise ValueError(
                    "MIDJOURNEY_WEBHOOK_SECRET or WEBHOOK_SECRET is required in production"
                )
        return self

    @model_validator(mode="after")
    def require_video_recovery_lease_safety(self) -> "Settings":
        minimum = self.NEIRONYCH_VIDEO_RECONCILE_TIMEOUT_SECONDS + 30
        if self.NEIRONYCH_VIDEO_NOTICE_LEASE_SECONDS <= minimum:
            raise ValueError(
                "NEIRONYCH_VIDEO_NOTICE_LEASE_SECONDS must exceed video recovery timeout + 30s"
            )
        if self.NEIRONYCH_VIDEO_POLL_LEASE_SECONDS <= minimum:
            raise ValueError(
                "NEIRONYCH_VIDEO_POLL_LEASE_SECONDS must exceed video recovery timeout + 30s"
            )
        return self

    def lava_offer_id_for_plan(self, plan_key: str) -> str:
        normalized = (plan_key or "").strip().upper().replace("-", "_")
        if not normalized:
            return ""
        key = f"LAVA_OFFER_ID_{normalized}"
        value = os.getenv(key, "")
        if value:
            return value
        env_path = ".env"
        try:
            with open(env_path, "r", encoding="utf-8") as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    if k.strip() == key:
                        return v.strip().strip("\"'")
        except FileNotFoundError:
            return ""
        return ""

    def lava_has_offer_ids(self) -> bool:
        if any(key.startswith("LAVA_OFFER_ID_") and value for key, value in os.environ.items()):
            return True
        env_path = ".env"
        try:
            with open(env_path, "r", encoding="utf-8") as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    if key.strip().startswith("LAVA_OFFER_ID_") and value.strip().strip("\"'"):
                        return True
        except FileNotFoundError:
            return False
        return False

    def lava_is_enabled(self) -> bool:
        return bool(self.LAVA_API_KEY and self.lava_has_offer_ids())

    @property
    def KIE_API_KEY(self) -> str:
        return self.KIE_AI_KEY


settings = Settings()
