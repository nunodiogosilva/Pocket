import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routers import auth, bin, files, folders, search, shared
from services import semantic_search
from services.storage import init_storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_storage()
    init_db()
    semantic_search.init_index()
    # Index files that predate search in the background so startup isn't delayed
    threading.Thread(target=semantic_search.index_missing_files, name="search-backfill", daemon=True).start()
    yield


app = FastAPI(
    title="BitPocket API",
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

app.include_router(auth.router)
app.include_router(files.router)
app.include_router(folders.router)
app.include_router(bin.router)
app.include_router(shared.router)
app.include_router(search.router)
