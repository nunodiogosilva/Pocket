"""FastAPI dependency-injection factories."""

from app.dependencies.db import get_db
from app.dependencies.tailscale import TailscaleUser, get_current_user

__all__ = ["get_db", "TailscaleUser", "get_current_user"]
