import os

STORAGE_DIR = os.getenv("STORAGE_DIR", "./data/storage")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{STORAGE_DIR}/database.db")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "minishlab/potion-base-8M")

USER_FILES_DIR = os.path.join(STORAGE_DIR, "user_files")
UPLOAD_TMP_DIR = os.path.join(STORAGE_DIR, "tmp")

# Development mode fallback when not accessing through Tailscale Serve proxy
DEV_MODE = os.getenv("DEV_MODE", "true").lower() in ("true", "1", "yes")
DEV_USER_LOGIN = os.getenv("DEV_USER_LOGIN", "dev@bitpocket.local")
DEV_USER_NAME = os.getenv("DEV_USER_NAME", "BitPocket Developer")
DEV_USER_PROFILE_PIC = os.getenv("DEV_USER_PROFILE_PIC", None)

