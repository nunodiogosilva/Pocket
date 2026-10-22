"""Pocket application factory.

Wires the FastAPI app together: lifespan bootstrap (storage, DB, search index),
CORS middleware, and registration of the versioned router tree. Run with
``uvicorn app.main:app``.
"""

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.database import init_db
from app.core import storage_engine
from app.services import search_service

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage_engine.init_storage()
    init_db()
    try:
        search_service.init_index()
        # Index items that predate search in the background so startup isn't delayed.
        threading.Thread(target=search_service.index_missing_files, name="search-backfill", daemon=True).start()
    except Exception:
        # A missing embedding model or offline HF cache should not block startup.
        logging.getLogger(__name__).warning("Could not initialise semantic search; continuing without it", exc_info=True)
    yield


app = FastAPI(
    title="Pocket API",
    description="Lightweight, self-hosted personal cloud storage with Tailscale Identity and sqlite-vec semantic search",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router)
