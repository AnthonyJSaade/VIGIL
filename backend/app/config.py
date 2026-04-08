"""Application settings loaded from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    db_path: str = "vigil.db"
    demo_repos_path: Path = Path(__file__).resolve().parent.parent.parent / "demo-repos"

    model_config = {"env_prefix": "VIGIL_"}


settings = Settings()
