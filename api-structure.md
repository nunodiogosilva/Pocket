# Pocket: Project Context & Refactoring Blueprint

## 1. Project Overview & Core Philosophy

Pocket is a universal, open-source, self-hosted personal cloud storage and file management system. Designed to be operating-system agnostic, it runs on any environment supporting Docker and Docker Compose (Linux servers, Raspberry Pi units, macOS, Windows Server).

### Key Architectural Constraints

- **Resource Budget:** Strict target under 200MB of RAM.
- **Architecture Style:** Clean Layered Architecture separating HTTP routing (`api/`), core infrastructure (`core/`), business logic (`services/`), data models (`models/`), DTO schemas (`schemas/`), and dependency injections (`dependencies/`).
- **Database & Vector Engine:** SQLite with `sqlite-vec` for native relational data storage and vector similarity search.
- **Authentication:** Delegation of identity management entirely to Tailscale Identity via proxy headers (`Tailscale-User-Login`, `Tailscale-User-Name`, `Tailscale-User-Profile-Pic`) handled exclusively through FastAPI dependency injections.

---

## 2. Target Directory & File Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                       # App factory, CORS middleware, router registration
│   ├── config.py                     # Pydantic BaseSettings (DB path, model choice)
│   │
│   ├── api/                          # HTTP routing layer
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── router.py             # Aggregates sub-routers
│   │       └── endpoints/
│   │           ├── items.py          # File & folder CRUD (triggers vector indexing on upload)
│   │           ├── search.py         # Semantic search endpoint (/semantic?q=...)
│   │           └── user.py           # User profile endpoint using Tailscale proxy headers
│   │
│   ├── core/                         # Infrastructure configuration
│   │   ├── __init__.py
│   │   ├── database.py               # SQLAlchemy engine + sqlite-vec C-extension loader event
│   │   └── storage_engine.py         # Chunked streaming file storage (Local disk)
│   │
│   ├── models/                       # Database ORM Models (SQLAlchemy / SQLModel)
│   │   ├── __init__.py
│   │   ├── user.py                   # User accounts synced from Tailscale login
│   │   ├── item.py                   # Unified self-referential File/Folder tree model
│   │   └── permission.py             # Granular file/folder sharing ACL
│   │
│   ├── schemas/                      # Pydantic validation DTOs (Request/Response)
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── item.py
│   │   └── permission.py
│   │
│   ├── services/                     # Core business logic layer
│   │   ├── __init__.py
│   │   ├── item_service.py           # Tree traversal, path validation, quota checks
│   │   ├── search_service.py         # Sentence-transformers embeddings + sqlite-vec KNN queries
│   │   └── storage_service.py        # Stream handling coordination
│   │
│   └── dependencies/                 # FastAPI Depends injection factories
│       ├── __init__.py
│       ├── db.py                     # Yields database sessions (get_db)
│       └── tailscale.py              # Extracts Tailscale header identity (get_current_user)
│
├── storage/                          # Local directory where actual file binaries live
├── tests/                            # Pytest test suite matching the app structure
│   ├── __init__.py
│   ├── conftest.py                   # Pytest fixtures (in-memory SQLite, mock Tailscale overrides)
│   ├── api/
│   │   ├── test_items.py
│   │   ├── test_search.py
│   │   └── test_user.py
│   └── unit/
│       ├── test_search_service.py
│       └── test_storage_engine.py
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

---

## 3. Detailed Component Breakdown

### A. Infrastructure & Configuration (`app/core/`, `app/config.py`)

- **`app/config.py`:** Manages environment configurations (`DATABASE_URL`, `STORAGE_DIR`, `EMBEDDING_MODEL_NAME`) using Pydantic v2 `BaseSettings`.
- **`app/core/database.py`:** Initializes the SQLite SQLAlchemy engine, binds the declarative `Base`, and hooks into the SQLite `connect` event to register the `sqlite-vec` extension.
- **`app/core/storage_engine.py`:** Manages asynchronous chunked reading and writing (`aiofiles`) to stream large files without exhausting RAM.

### B. Models & Schemas (`app/models/`, `app/schemas/`)

- **`app/models/item.py`:** Unified self-referential tree model handling both files and folders using a `parent_id` foreign key.
- **`app/models/user.py`:** Tracks user profiles synced from Tailscale headers.
- **`app/models/permission.py`:** Handles access control lists (ACL) for file sharing.
- **`app/schemas/`:** Pydantic DTOs for strict input validation and response serialization.

### C. Services & Dependency Injection (`app/services/`, `app/dependencies/`)

- **`app/services/search_service.py`:** Encodes assets using `sentence-transformers` (`all-MiniLM-L6-v2`) and executes KNN distance queries against `sqlite-vec` virtual tables (`vec0`).
- **`app/dependencies/db.py`:** Yields isolated database sessions (`get_db`) for HTTP request cycles.
- **`app/dependencies/tailscale.py`:** Validates and extracts `Tailscale-User-Login`, `Tailscale-User-Name`, and `Tailscale-User-Profile-Pic` headers, returning a typed `TailscaleUser` object.

---

## 4. Step-by-Step AI Refactoring Prompt

You can copy and paste the block below directly into an AI assistant along with your codebase to execute the refactor:

```
Please refactor my existing Pocket project to match the clean, layered architecture specified below.

### Target Directory & Module Structure
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                       # App factory, CORS middleware, router registration
│   ├── config.py                     # Pydantic BaseSettings (DB path, model choice)
│   │
│   ├── api/                          # HTTP routing layer
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── router.py             # Aggregates sub-routers
│   │       └── endpoints/
│   │           ├── items.py          # File & folder CRUD (triggers vector indexing on upload)
│   │           ├── search.py         # Semantic search endpoint (/semantic?q=...)
│   │           └── user.py           # User profile endpoint using Tailscale proxy headers
│   │
│   ├── core/                         # Infrastructure configuration
│   │   ├── __init__.py
│   │   ├── database.py               # SQLAlchemy engine + sqlite-vec C-extension loader event
│   │   └── storage_engine.py         # Chunked streaming file storage (Local disk)
│   │
│   ├── models/                       # Database ORM Models (SQLAlchemy / SQLModel)
│   │   ├── __init__.py
│   │   ├── user.py                   # User accounts synced from Tailscale login
│   │   ├── item.py                   # Unified self-referential File/Folder tree model
│   │   └── permission.py             # Granular file/folder sharing ACL
│   │
│   ├── schemas/                      # Pydantic validation DTOs (Request/Response)
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── item.py
│   │   └── permission.py
│   │
│   ├── services/                     # Core business logic layer
│   │   ├── __init__.py
│   │   ├── item_service.py           # Tree traversal, path validation, quota checks
│   │   ├── search_service.py         # Sentence-transformers embeddings + sqlite-vec KNN queries
│   │   └── storage_service.py        # Stream handling coordination
│   │
│   └── dependencies/                 # FastAPI Depends injection factories
│       ├── __init__.py
│       ├── db.py                     # Yields database sessions (get_db)
│       └── tailscale.py              # Extracts Tailscale header identity (get_current_user)
│
├── storage/                          # Local directory where actual file binaries live
├── tests/                            # Pytest test suite matching the app structure
│   ├── __init__.py
│   ├── conftest.py                   # Pytest fixtures (in-memory SQLite, mock Tailscale overrides)
│   ├── api/
│   │   ├── test_items.py
│   │   ├── test_search.py
│   │   └── test_user.py
│   └── unit/
│       ├── test_search_service.py
│       └── test_storage_engine.py
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

### Refactoring Rules & Constraints:
1. Move database session generation (`get_db`) strictly into `app/dependencies/db.py` and keep engine setup and `sqlite-vec` hook extension logic in `app/core/database.py`.
2. Consolidate file and folder ORM models into a unified self-referential tree model (`app/models/item.py`) with `parent_id` foreign keys.
3. Keep Tailscale header authentication (`Tailscale-User-Login`, `Tailscale-User-Name`, `Tailscale-User-Profile-Pic`) isolated inside `app/dependencies/tailscale.py`.
4. Ensure semantic search uses `sqlite-vec` virtual tables (`vec0`) and `sentence-transformers` via `app/services/search_service.py`.
5. Update all tests in `tests/` to use dependency overrides for `get_db` and `get_current_user` so they can run cleanly without external dependencies.

