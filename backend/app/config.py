"""Environment configuration for the Pocket backend.

Uses Pydantic v2 ``BaseSettings`` so every runtime knob can be provided through
environment variables (with sensible self-hosted defaults) and validated in one
place. Derived storage paths are resolved relative to ``STORAGE_DIR``.
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central, typed settings object for the whole application."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Storage / data -------------------------------------------------
    storage_dir: str = "./pocket-storage"
    database_url: Optional[str] = None
    public_base_url: str = "http://localhost:8000"

    # --- Semantic search -----------------------------------------------
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- Development fallback (when not behind Tailscale Serve) ---------
    dev_mode: bool = True
    dev_user_login: str = "dev@pocket.local"
    dev_user_name: str = "Pocket Developer"
    dev_user_profile_pic: Optional[str] = None

    # --- Derived paths (not expected to be set directly) ---------------
    @property
    def user_files_dir(self) -> str:
        return f"{self.storage_dir.rstrip('/')}/user_files"

    @property
    def upload_tmp_dir(self) -> str:
        return f"{self.storage_dir.rstrip('/')}/tmp"

    @property
    def effective_database_url(self) -> str:
        return self.database_url or f"sqlite:///{self.storage_dir.rstrip('/')}/database.db"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance for dependency injection."""
    return Settings()


# Convenience module-level singleton so ``from app.config import settings`` works.
settings = get_settings()

__all__ = ["Settings", "get_settings", "settings"]
