from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ANTHROPIC_API_KEY: str
    TELEGRAM_BOT_TOKEN: str
    DATABASE_URL: str
    # Railway Postgres plugin also exposes a private-network URL that needs no
    # SSL and is faster than the public DATABASE_URL.  We prefer it when set.
    DATABASE_PRIVATE_URL: str = ""

    TELEGRAM_MODE: str = "polling"   # "polling" locally, "webhook" on Railway
    WEBHOOK_URL: str = ""            # e.g. https://your-app.railway.app

    POSITION_NOTIONAL: float = 1000.0
    DEFAULT_HOLDING_TRADING_DAYS: int = 90
    MAX_OPEN_POSITIONS_PER_USER: int = 10

    @model_validator(mode="before")
    @classmethod
    def prefer_private_url(cls, values: dict) -> dict:
        """Use the Railway private-network URL when available (no SSL required)."""
        private = values.get("DATABASE_PRIVATE_URL", "")
        if private:
            values["DATABASE_URL"] = private
        return values

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def ensure_asyncpg_scheme(cls, v: str) -> str:
        """Convert postgres:// or postgresql:// → postgresql+asyncpg://."""
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://") and "+asyncpg" not in v:
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v


settings = Settings()
