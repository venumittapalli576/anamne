from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Reads from .env file.

    Env vars: ANTHROPIC_API_KEY, MODEL (optional), DATA_DIR (optional).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    anthropic_api_key: str = ""
    model: str = "claude-sonnet-4-6"
    data_dir: Path = Path.home() / ".provenance"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8765


def get_settings() -> Settings:
    return Settings()
