# Pocket Backend

Lightweight, self-hosted personal cloud storage with Tailscale Identity and
`sqlite-vec` semantic search, built as a clean, layered FastAPI application.

## Architecture

```
app/
├── main.py                 # App factory, CORS, router registration, lifespan bootstrap
├── config.py               # Pydantic v2 BaseSettings (DB path, model, storage dirs)
├── api/
│   └── v1/
│       ├── router.py       # Aggregates the versioned sub-routers
│       └── endpoints/      # items (files/folders/bin/dirs/storage), search, user, shared
├── core/
│   ├── database.py         # SQLAlchemy engine + sqlite-vec C-extension loader event
│   └── storage_engine.py   # Chunked streaming file I/O + folder zipping
├── models/                 # ORM: user, item (unified tree), permission (ACL + shared links)
├── schemas/                # Pydantic DTOs (user, item, search, permission)
├── services/               # Business logic: item_service, search, sharing, auth
└── dependencies/           # DI: get_db, Tailscale identity (get_current_user)
```

## Run locally

```bash
pip install -r requirements.txt
# optional: copy .env into this directory (or rely on defaults)
uvicorn app.main:app --reload
```

## Run tests

The test suite uses dependency overrides for `get_db` and `get_current_user`, so
it runs without Tailscale, a real database, or the embedding model:

```bash
python -m unittest discover -s tests -p "test_*.py"
# or
pytest
```

## Docker

```bash
docker build -t pocket-backend .
docker run -p 127.0.0.1:8000:8000 -v ./pocket-storage:/app/pocket-storage pocket-backend
```
