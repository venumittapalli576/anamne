from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


ModelTier = Literal["claude", "gemini", "ollama", "none"]


class Settings(BaseSettings):
    """Reads from .env file.

    Recognized env vars:
      ANTHROPIC_API_KEY  — Claude API key (best quality)
      GEMINI_API_KEY     — Gemini API key (free tier available)
      MODEL              — explicit model override
      DATA_DIR           — where to store the knowledge base
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    model: str = ""  # if blank, picked automatically based on available keys
    data_dir: Path = Path.home() / ".provenance"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8765

    def resolved_model(self) -> str:
        """Pick the best available model based on what the user has set up."""
        if self.model:
            return self.model
        if self.anthropic_api_key:
            return "claude-sonnet-4-6"
        if self.gemini_api_key:
            return "gemini/gemini-2.5-flash"
        return "ollama/llama3.2"  # fallback — assumes Ollama is installed

    def model_tier(self) -> ModelTier:
        m = self.resolved_model()
        if m.startswith("claude"):
            return "claude"
        if m.startswith("gemini"):
            return "gemini"
        if m.startswith("ollama"):
            return "ollama"
        return "none"

    def has_any_key(self) -> bool:
        return bool(self.anthropic_api_key or self.gemini_api_key)


def get_settings() -> Settings:
    return Settings()
