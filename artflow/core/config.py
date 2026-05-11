# core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

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

    # DB
    DATABASE_URL: str = ""
    REDIS_URL: str = "redis://redis:6379"

    # CometAPI (Kling, Seedream, Gemini, Grok, Seedance, Veo, WAN)
    COMET_API_KEY: str
    COMET_BASE_URL: str = "https://api.cometapi.com"

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

    # KIE.AI photo → prompt (GPT-5.x vision via kie.ai)
    KIE_PHOTO_PROMPT_MODEL: str = "gpt-5-2"
    KIE_PHOTO_PROMPT_FALLBACK: str = "gpt-5-5"

    # KIE.AI text assistant
    KIE_ASSISTANT_MODEL: str = "gpt-5-4"
    KIE_ASSISTANT_FALLBACK: str = "gpt-5-4"

    # Feature flags
    SUBSCRIPTION_ENABLED: bool = False

    # Credits
    WELCOME_BONUS_CREDITS: int = 15
    REFERRAL_L1_CREDITS: int = 5   # бонус кредитами при регистрации реферала
    REFERRAL_WITHDRAW_MIN_RUB: float = 1000.0

    # Реферальные комиссии с оплат (%)
    REFERRAL_COMMISSION_L1: float = 0.30
    REFERRAL_COMMISSION_L2: float = 0.07
    REFERRAL_COMMISSION_L3: float = 0.03

    # Polling
    POLLING_INTERVAL: float = 3.0
    POLLING_TIMEOUT: int = 600

    @property
    def KIE_API_KEY(self) -> str:
        """Backward-compatible alias for legacy music code."""
        return self.KIE_AI_KEY


settings = Settings()
