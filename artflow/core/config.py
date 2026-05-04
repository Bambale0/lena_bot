# core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Bot
    BOT_TOKEN: str
    WEBHOOK_URL: str = "https://testapi.chillcreative.ru"
    WEBHOOK_PATH: str = "/webhook/telegram"
    WEBHOOK_SECRET: str = "change_me_secret"

    # Admin
    ADMIN_IDS: list[int] = []

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # DB
    DATABASE_URL: str = "postgresql+asyncpg://bot:password@postgres:5432/artflow"
    REDIS_URL: str = "redis://redis:6379"

    # CometAPI (Kling, Seedream, Gemini, Grok, Seedance, Veo, WAN)
    COMET_API_KEY: str
    COMET_BASE_URL: str = "https://api.cometapi.com"

    # aivideoapi.ai (HappyHorse)
    AIVIDEOAPI_KEY: str = ""

    # kie.ai (Wan 2.7 Image Pro)
    KIE_AI_KEY: str = ""

    # YooKassa
    YOOKASSA_SHOP_ID: str = ""
    YOOKASSA_SECRET_KEY: str = ""
    YOOKASSA_PROVIDER_TOKEN: str = ""

    # CryptoBot
    CRYPTOBOT_TOKEN: str = ""
    CRYPTOBOT_BASE_URL: str = "https://pay.crypt.bot/api"

    # T-Bank Acquiring
    TBANK_TERMINAL_KEY: str = ""
    TBANK_PASSWORD: str = ""
    TBANK_BASE_URL: str = "https://securepay.tinkoff.ru/v2"
    TBANK_SUCCESS_URL: str = ""
    TBANK_FAIL_URL: str = ""

    # Feature flags
    SUBSCRIPTION_ENABLED: bool = False

    # Credits
    WELCOME_BONUS_CREDITS: int = 15
    REFERRAL_L1_CREDITS: int = 20
    REFERRAL_L2_CREDITS: int = 10

    # Polling
    POLLING_INTERVAL: float = 3.0
    POLLING_TIMEOUT: int = 600


settings = Settings()
