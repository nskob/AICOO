"""Configuration management using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str

    # Telegram
    telegram_bot_token: str
    telegram_admin_chat_id: int

    # OZON Seller API
    ozon_client_id: str
    ozon_api_key: str

    # OZON Performance API (advertising)
    ozon_performance_client_id: str | None = None
    ozon_performance_api_key: str | None = None

    # Claude API
    anthropic_api_key: str

    # Application settings
    timezone: str = "Europe/Moscow"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
