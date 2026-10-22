"""Semantic-search service: embeddings, ``sqlite-vec`` KNN, and hybrid ranking.

This is the single search service for the app. It owns the low-level
infrastructure (embedding generation with ``sentence-transformers`` and the
``sqlite-vec`` virtual table) as well as the higher-level orchestration
(authorization scoping, keyword boosting, snippet generation, and autocomplete
suggestions) that previously lived in a separate ``search`` module.
"""

import logging
import os
import re
import threading
import time
from functools import lru_cache
from typing import TYPE_CHECKING, Optional

import numpy as np
from sqlmodel import Session, col, func, select

from app.config import settings

if TYPE_CHECKING:  # pragma: no cover - only needed for type hints
    from sentence_transformers import SentenceTransformer
from app.core.database import engine
from app.models.item import FileChunk, Item
from app.models.permission import FileShare
from app.models.user import User
from app.schemas.item import ItemRead, SearchResult, SearchSuggestion, SearchSuggestionsResponse

logger = logging.getLogger(__name__)

VECTOR_TABLE = "filechunk_vec"
CHUNK_WORDS = 100
MAX_CHARS = 30_000
MAX_PDF_PAGES = 50
_SNIFF_BYTES = 8192

MIN_SCORE = 0.25
CANDIDATES_PER_RESULT = 5

# sentence-transformers reconfigures its shared tokenizer on every encode() call.
_encode_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# Embeddings + sqlite-vec infrastructure
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def get_model() -> "SentenceTransformer":
    # Imported lazily so the rest of the app (and the test suite) can load
    # without the heavy sentence-transformers / torch stack being installed.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model)


def embed(texts: list[str]) -> np.ndarray:
    """Return one L2-normalised float32 vector per text."""
    with _encode_lock:
        return get_model().encode(texts, normalize_embeddings=True).astype(np.float32, copy=False)


def extract_text(path: str, filename: str, mime_type: str) -> str:
    """Extract best-effort searchable text from supported file types."""
    # Rows with a missing/empty on-disk path (stray metadata) contribute no text.
    if not path or not os.path.exists(path):
        return ""
    if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
        return _extract_pdf(path)
    if mime_type.startswith(("image/", "video/", "audio/")):
        return ""

    with open(path, "rb") as file_handle:
        data = file_handle.read(MAX_CHARS * 4)
    if b"\x00" in data[:_SNIFF_BYTES]:
        return ""
    return data.decode("utf-8", errors="ignore")[:MAX_CHARS]


def _extract_pdf(path: str) -> str:
    from pypdf import PdfReader

    parts: list[str] = []
    length = 0
    try:
        with open(path, "rb") as file_handle:
            for page_number, page in enumerate(PdfReader(file_handle).pages):
                if page_number >= MAX_PDF_PAGES or length >= MAX_CHARS:
                    break
                text = page.extract_text() or ""
                parts.append(text)
                length += len(text)
    except Exception as exc:
        logger.warning("Could not extract text from PDF %s: %s", path, exc)
    return "\n".join(parts)[:MAX_CHARS]


def init_index() -> None:
    """Create (or rebuild on dimension change) the ``sqlite-vec`` virtual table."""
    dim = get_model().get_sentence_embedding_dimension()
    with engine.begin() as conn:
        row = conn.exec_driver_sql("SELECT sql FROM sqlite_master WHERE name = ?", (VECTOR_TABLE,)).first()
        if row and f"float[{dim}]" not in row[0]:
            conn.exec_driver_sql(f"DROP TABLE {VECTOR_TABLE}")
            conn.exec_driver_sql("DELETE FROM filechunk")
        conn.exec_driver_sql(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {VECTOR_TABLE} USING vec0(embedding float[{dim}] distance_metric=cosine)"
        )


def index_file(file_id: int) -> None:
    """(Re)build the search chunks and vectors of one item (file or folder)."""
    with Session(engine) as session:
        file_meta = session.get(Item, file_id)
        if not file_meta:
            return
        filename, path, mime_type, is_folder = (
            file_meta.filename,
            file_meta.storage_path,
            file_meta.mime_type,
            file_meta.is_folder,
        )

    # Replace separators (underscore, backslash, dot, dash) with spaces.
    # The dash is escaped (\-) and the dot is not, to avoid an invalid range.
    title = re.sub(r"[_\\.\-]+", " ", filename)
    if is_folder:
        chunks = [title]
        vectors = embed([title])
    else:
        words = extract_text(path, filename, mime_type).split()
        chunks = [""] + [" ".join(words[i : i + CHUNK_WORDS]) for i in range(0, len(words), CHUNK_WORDS)]
        vectors = embed([f"{title}\n{chunk}" if chunk else title for chunk in chunks])

    for attempt in range(5):
        try:
            with Session(engine) as session:
                conn = session.connection()
                stale_ids = conn.exec_driver_sql(
                    "DELETE FROM filechunk WHERE file_id = ? RETURNING id", (file_id,)
                ).scalars().all()
                if stale_ids:
                    conn.exec_driver_sql(
                        f"DELETE FROM {VECTOR_TABLE} WHERE rowid = ?", [(chunk_id,) for chunk_id in stale_ids]
                    )
                rows = [FileChunk(file_id=file_id, chunk_index=i, text=chunk) for i, chunk in enumerate(chunks)]
                session.add_all(rows)
                session.flush()
                conn.exec_driver_sql(
                    f"INSERT INTO {VECTOR_TABLE}(rowid, embedding) VALUES (?, ?)",
                    [(row.id, vector.tobytes()) for row, vector in zip(rows, vectors)],
                )
                session.commit()
            break
        except Exception as exc:
            if "locked" in str(exc).lower() and attempt < 4:
                time.sleep(0.2 * (attempt + 1))
            else:
                logger.warning("Could not index vectors for file %s: %s", file_id, exc)
                break


def index_missing_files() -> None:
    """Index items without search chunks (background backfill)."""
    with Session(engine) as session:
        file_ids = session.exec(
            select(Item.id).where(
                Item.is_deleted == False,
                col(Item.id).not_in(select(FileChunk.file_id)),
            )
        ).all()
    for file_id in file_ids:
        try:
            index_file(file_id)
        except Exception:
            logger.exception("Failed to index file %s for search", file_id)


def delete_index_for(file_id: int) -> None:
    """Remove chunks and vectors for a permanently-deleted item."""
    with Session(engine) as session:
        conn = session.connection()
        stale_ids = conn.exec_driver_sql(
            "DELETE FROM filechunk WHERE file_id = ? RETURNING id", (file_id,)
        ).scalars().all()
        if stale_ids:
            conn.exec_driver_sql(f"DELETE FROM {VECTOR_TABLE} WHERE rowid = ?", [(cid,) for cid in stale_ids])
        session.commit()


# --------------------------------------------------------------------------- #
# Search orchestration (hybrid vector + keyword ranking)
# --------------------------------------------------------------------------- #
def make_snippet(text: Optional[str], query_words: list[str], max_len: int = 150) -> Optional[str]:
    """Generate a concise snippet focused around matching query keywords."""
    if not text:
        return None
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return None
    lower_text = cleaned.lower()
    match_pos = -1
    for word in query_words:
        pos = lower_text.find(word.lower())
        if pos != -1 and (match_pos == -1 or pos < match_pos):
            match_pos = pos
    if match_pos == -1 or len(cleaned) <= max_len:
        return cleaned[:max_len] + ("..." if len(cleaned) > max_len else "")
    start = max(0, match_pos - 40)
    end = min(len(cleaned), match_pos + 110)
    snippet = cleaned[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(cleaned):
        snippet += "..."
    return snippet


def _authorized_chunks_sql() -> str:
    return """
        SELECT fc.id
        FROM filechunk fc
        JOIN filemeta fm ON fc.file_id = fm.id
        LEFT JOIN fileshare fs ON fm.id = fs.file_id
        WHERE (fm.owner_id = ? OR fs.shared_with_user_id = ? OR fs.shared_with_login = ?)
          AND (fm.is_deleted = 0)
    """


def search(session: Session, user: User, query: str, limit: int) -> list[SearchResult]:
    """Hybrid vector and keyword search scoped to items accessible by the user."""
    q_clean = query.strip()
    if not q_clean:
        return []

    authorized_chunks_sql = _authorized_chunks_sql()
    conn = session.connection()
    authorized_chunk_ids = conn.exec_driver_sql(
        authorized_chunks_sql, (user.id, user.id, user.login)
    ).scalars().all()
    if not authorized_chunk_ids:
        return []

    query_vector = embed([q_clean])[0]
    candidate_limit = limit * CANDIDATES_PER_RESULT
    matches = conn.exec_driver_sql(
        f"""
        SELECT rowid, distance
        FROM {VECTOR_TABLE}
        WHERE rowid IN ({authorized_chunks_sql})
          AND embedding MATCH ?
        ORDER BY distance
        LIMIT ?
        """,
        (user.id, user.id, user.login, query_vector.tobytes(), candidate_limit),
    ).all()
    distance_by_chunk = {chunk_id: distance for chunk_id, distance in matches}

    query_words = [word.lower() for word in re.findall(r"\w+", q_clean) if len(word) >= 2]
    keyword_chunk_ids: set[int] = set()
    if query_words:
        kw_conditions = " OR ".join(["LOWER(fc.text) LIKE ? OR LOWER(fm.filename) LIKE ?" for _ in query_words])
        kw_params: list = [user.id, user.id, user.login]
        for word in query_words:
            kw_params.extend([f"%{word}%", f"%{word}%"])
        kw_sql = f"""
            SELECT fc.id
            FROM filechunk fc
            JOIN filemeta fm ON fc.file_id = fm.id
            LEFT JOIN fileshare fs ON fm.id = fs.file_id
            WHERE (fm.owner_id = ? OR fs.shared_with_user_id = ? OR fs.shared_with_login = ?)
              AND (fm.is_deleted = 0)
              AND ({kw_conditions})
            LIMIT 50
        """
        keyword_chunk_ids = set(conn.exec_driver_sql(kw_sql, tuple(kw_params)).scalars().all())

    all_candidate_chunk_ids = set(distance_by_chunk) | keyword_chunk_ids
    if not all_candidate_chunk_ids:
        return []
    shared_items_subquery = select(FileShare.file_id).where(
        (FileShare.shared_with_user_id == user.id) | (FileShare.shared_with_login == user.login)
    )
    rows = session.exec(
        select(FileChunk, Item)
        .join(Item, col(Item.id) == col(FileChunk.file_id))
        .where(
            col(FileChunk.id).in_(list(all_candidate_chunk_ids)),
            Item.is_deleted == False,
            (col(Item.owner_id) == user.id) | col(Item.id).in_(shared_items_subquery),
        )
    ).all()

    best: dict[int, tuple[float, FileChunk, Item]] = {}
    for chunk, item in rows:
        score = 1.0 - distance_by_chunk.get(chunk.id, 0.75)
        text_lower = (chunk.text or "").lower()
        filename_lower = item.filename.lower()
        matched_words = [word for word in query_words if word in text_lower or word in filename_lower]
        if matched_words:
            score = min(1.0, score + 0.35 + 0.1 * min(len(matched_words) - 1, 3))
        if score >= MIN_SCORE and (item.id not in best or score > best[item.id][0]):
            best[item.id] = (score, chunk, item)

    results: list[SearchResult] = []
    for score, chunk, item in sorted(best.values(), key=lambda match: match[0], reverse=True)[:limit]:
        base = ItemRead.model_validate(item)
        results.append(
            SearchResult(**base.model_dump(), score=score, snippet=make_snippet(chunk.text, query_words))
        )
    return results


def get_suggestions(session: Session, user: User, query: str, limit: int = 8) -> SearchSuggestionsResponse:
    """Return direct-name matches enriched with semantic search results."""
    q = query.strip()
    if not q:
        return SearchSuggestionsResponse(folders=[], files=[])
    shared_subquery = select(FileShare.file_id).where(
        (FileShare.shared_with_user_id == user.id) | (FileShare.shared_with_login == user.login)
    )
    folder_suggestions: dict[int, SearchSuggestion] = {}
    file_suggestions: dict[int, SearchSuggestion] = {}
    folders_stmt = (
        select(Item)
        .where(
            Item.is_folder == True,
            Item.is_deleted == False,
            (Item.owner_id == user.id) | (Item.id.in_(shared_subquery)),
            func.lower(Item.filename).contains(q.lower()),
        )
        .order_by(func.lower(Item.filename))
        .limit(limit)
    )
    for folder in session.exec(folders_stmt).all():
        folder_suggestions[folder.id] = SearchSuggestion(
            id=folder.id, filename=folder.filename, is_folder=True, parent_id=folder.parent_id
        )
    items_stmt = (
        select(Item)
        .where(
            Item.is_folder == False,
            Item.is_deleted == False,
            (Item.owner_id == user.id) | (Item.id.in_(shared_subquery)),
            func.lower(Item.filename).contains(q.lower()),
        )
        .order_by(func.lower(Item.filename))
        .limit(limit)
    )
    for item in session.exec(items_stmt).all():
        file_suggestions[item.id] = SearchSuggestion(
            id=item.id,
            filename=item.filename,
            is_folder=False,
            file_size=item.file_size,
            mime_type=item.mime_type,
            parent_id=item.parent_id,
        )
    try:
        for result in search(session, user, q, limit=limit):
            if result.is_folder:
                if result.id not in folder_suggestions and len(folder_suggestions) < limit:
                    folder_suggestions[result.id] = SearchSuggestion(
                        id=result.id, filename=result.filename, is_folder=True, parent_id=result.parent_id
                    )
            elif result.id not in file_suggestions:
                if len(file_suggestions) < limit:
                    file_suggestions[result.id] = SearchSuggestion(
                        id=result.id,
                        filename=result.filename,
                        is_folder=False,
                        file_size=result.file_size,
                        mime_type=result.mime_type,
                        snippet=result.snippet,
                        parent_id=result.parent_id,
                    )
                elif not file_suggestions[result.id].snippet and result.snippet:
                    file_suggestions[result.id].snippet = result.snippet
    except Exception as exc:
        logger.warning("Semantic suggestions failed: %s", exc)

    return SearchSuggestionsResponse(
        folders=list(folder_suggestions.values())[:limit],
        files=list(file_suggestions.values())[:limit],
    )


def search_files(session: Session, user: User, query: str, limit: int) -> list[SearchResult]:
    return search(session, user, query, limit)


def suggest_files_and_folders(
    session: Session, user: User, query: str, limit: int
) -> SearchSuggestionsResponse:
    return get_suggestions(session, user, query, limit)


__all__ = [
    # infrastructure
    "VECTOR_TABLE",
    "CHUNK_WORDS",
    "get_model",
    "embed",
    "extract_text",
    "init_index",
    "index_file",
    "index_missing_files",
    "delete_index_for",
    # orchestration
    "make_snippet",
    "search",
    "get_suggestions",
    "search_files",
    "suggest_files_and_folders",
]
