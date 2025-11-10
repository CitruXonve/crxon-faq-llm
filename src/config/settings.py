import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""
    project_root: Path = Path(__file__).parent.parent.parent
    KB_DIRECTORY: str = os.path.join(
        project_root, '.knowledge_sources')

    """Claude API settings"""
    CLAUDE_MODEL: str

    model_config = SettingsConfigDict(
        env_file=os.path.join(Path(__file__).parent.parent.parent, '.env'),
        env_file_encoding='utf-8',
        extra='ignore'
    )


# Create a global settings instance
# settings = (
#     Settings(_env_file=".env.test")
#     if os.getenv("RUN_HANDLER_ENV") == "test"
#     else Settings()
# )
settings = Settings()
