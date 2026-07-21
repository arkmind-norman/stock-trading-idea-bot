from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ANTHROPIC_API_KEY: str
    TELEGRAM_BOT_TOKEN: str
    # Railway supplies  postgresql://...  or  postgres://...
    # asyncpg requires  postgresql+asyncpg://...
    # The validator below normalises all variants at load time.
    DATABASE_URL: str

    TELEGRAM_MODE: str = "polling"   # "polling" locally, "webhook" on Railway
    WEBHOOK_URL: str = ""            # e.g. https://your-app.railway.app

    POSITION_NOTIONAL: float = 1000.0
    DEFAULT_HOLDING_TRADING_DAYS: int = 90
    MAX_OPEN_POSITIONS_PER_USER: int = 10

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def ensure_asyncpg_scheme(cls, v: str) -> str:
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v


settings = Settings()
