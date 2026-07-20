from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ANTHROPIC_API_KEY: str
    TELEGRAM_BOT_TOKEN: str
    DATABASE_URL: str

    TELEGRAM_MODE: str = "polling"
    WEBHOOK_URL: str = ""

    POSITION_NOTIONAL: float = 1000.0
    DEFAULT_HOLDING_DAYS: int = 10


settings = Settings()
