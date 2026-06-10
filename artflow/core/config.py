# core/config.py
import os

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Bot
    BOT_TOKEN: str
    BOT_USERNAME: str = "APIXBot"
    WEBHOOK_URL: str = "https://testapi.chillcreative.ru"
    WEBHOOK_PATH: str = "/webhook/telegram"
    WEBHOOK_SECRET: str = ""

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
    REDIS_URL: str = "redis://redis:6379"

    # CometAPI (Kling, Seedream, Gemini, Grok, Seedance, Veo, WAN)
    COMET_API_KEY: str = Field(validation_alias=AliasChoices("COMET_API_KEY", "COMET_KEY"))
    COMET_BASE_URL: str = "https://api.cometapi.com"
    MIDJOURNEY_WEBHOOK_PATH: str = "/webhook/comet/midjourney"
    MIDJOURNEY_WEBHOOK_SECRET: str = ""

    # OpenRouter (primary for migrated image/video/chat models)
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_FORCE_MIGRATED_MODELS: bool = False

    # aivideoapi.ai (HappyHorse)
    AIVIDEOAPI_KEY: str = ""

    # kie.ai (Wan 2.7 Image Pro)
    KIE_AI_KEY: str = ""

    # KIE.AI callbacks
    KIE_WEBHOOK_PATH: str = "/webhook/kie"
    KIE_WEBHOOK_SECRET: str = ""

    # Public static uploads used as stable references for KIE and Telegram.
    STATIC_UPLOAD_DIR: str = "static/upload"
    STATIC_UPLOAD_URL_PATH: str = "/static/upload"

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

    # KIE.AI photo → prompt (GPT-5.x vision via kie.ai)
    KIE_PHOTO_PROMPT_MODEL: str = "gpt-5-2"
    KIE_PHOTO_PROMPT_FALLBACK: str = "gpt-5-5"

    # KIE.AI text assistant
    KIE_ASSISTANT_MODEL: str = "gpt-5-4"
    KIE_ASSISTANT_FALLBACK: str = "claude-sonnet-4-5"
    COMET_ASSISTANT_MODEL: str = "gpt-5.4"
    COMET_ASSISTANT_FALLBACK: str = "gpt-5.4-mini"

    # Feature flags
    SUBSCRIPTION_ENABLED: bool = False
    TELEGRAM_STARS_ENABLED: bool = False
    REFERRAL_FREEZE: bool = False

    # Credits
    WELCOME_BONUS_CREDITS: int = 15
    REFERRAL_L1_CREDITS: int = 5   # бонус кредитами при регистрации реферала
    REFERRAL_WITHDRAW_MIN_RUB: float = 1000.0
    REFERRAL_EXCHANGE_MIN_RUB: float = 100.0
    REFERRAL_EXCHANGE_RUB_PER_CREDIT: float = 10.0

    # Реферальные комиссии с оплат (%)
    REFERRAL_COMMISSION_L1: float = 0.30
    REFERRAL_COMMISSION_L2: float = 0.07
    REFERRAL_COMMISSION_L3: float = 0.03

    # Polling
    POLLING_INTERVAL: float = 3.0
    POLLING_TIMEOUT: int = 600

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

    @property
    def KIE_API_KEY(self) -> str:
        """Backward-compatible alias for legacy music code."""
        return self.KIE_AI_KEY


settings = Settings()
