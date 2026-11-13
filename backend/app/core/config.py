from functools import lru_cache
from typing import Annotated
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Афиша культуры Башкортостана"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://afisha:afisha_password@localhost:5432/afisha",
        description="SQLAlchemy asyncpg connection URL",
    )
    CHECKPOINT_DB_URI: str = Field(
        default="postgresql://afisha:afisha_password@localhost:5432/afisha",
        description="psycopg connection URI for LangGraph checkpoints",
    )

    # LLM and Agent parameters
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_API_KEY: SecretStr = SecretStr("mock-key")
    LLM_MODEL_NAME: str = "gpt-4o-mini"
    EMBEDDING_MODEL_NAME: str = "text-embedding-3-small"

    # Operational limits strictly from contract
    LLM_TIMEOUT_SEC: float = Field(
        default=6.0,
        description="LLM call timeout in seconds (strictly 6.0s)",
    )
    MAX_AGENT_STEPS: int = Field(
        default=5,
        description="Maximum agent ReAct steps (strictly 5)",
    )
    MAX_DAILY_USER_BUDGET_RUB: float = Field(
        default=25.0,
        description="Maximum daily spending per user in rubles (strictly 25.0 RUB)",
    )
    MAX_DIALOG_COST_RUB: float = Field(
        default=5.0,
        description="Maximum budget per single dialog in rubles (strictly 5.0 RUB)",
    )

    # Security & Admin
    ADMIN_API_TOKEN: SecretStr = SecretStr("admin_secret_token_123")
    TELEGRAM_BACKEND_TOKEN: SecretStr = SecretStr("")
    ALLOWED_FRAME_ANCESTORS: str = "*"

    # Subscriptions retention
    SUBSCRIPTION_RETENTION_DAYS: int = 180


@lru_cache
def get_settings() -> Settings:
    return Settings()
