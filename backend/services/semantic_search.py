import logging
import re
from typing import Optional
from sqlmodel import Session, col, func, select
from database import engine
from models import FileChunk, FileMeta, FileShare, User
from schemas import SearchResult, SearchSuggestion, SearchSuggestionsResponse
from services.embeddings import embed, get_model
from services.text_extraction import extract_text


logger = logging.getLogger(__name__)

VECTOR_TABLE = "filechunk_vec"
CHUNK_WORDS = 100
# Cosine similarity below which a match is treated as noise (unrelated text scores up to ~0.2 with potion-base-8M)
MIN_SCORE = 0.25
# A file can own several matching chunks, so fetch more chunk candidates than requested results
CANDIDATES_PER_RESULT = 5


def init_index():
    dim = get_model().dim
    with engine.begin() as conn:
        row = conn.exec_driver_sql("SELECT sql FROM sqlite_master WHERE name = ?", (VECTOR_TABLE,)).first()
        if row and f"float[{dim}]" not in row[0]:
            # The embedding model changed size: drop stale vectors so the backfill re-indexes everything
            conn.exec_driver_sql(f"DROP TABLE {VECTOR_TABLE}")
            conn.exec_driver_sql("DELETE FROM filechunk")
        conn.exec_driver_sql(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {VECTOR_TABLE} USING vec0(embedding float[{dim}] distance_metric=cosine)"
        )


def index_file(file_id: int):
    """(Re)build the search chunks and vectors of one file or folder."""
    with Session(engine) as session:
        file_meta = session.get(FileMeta, file_id)
        if not file_meta:
            return
        filename, path, mime_type, is_folder = (
            file_meta.filename,
            file_meta.storage_path,
            file_meta.mime_type,
            file_meta.is_folder,
        )

    # Chunk 0 is the bare name so name matches stay strong; content chunks carry the name for context
    title = re.sub(r"[_\-.]+", " ", filename)
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
                stale_ids = conn.exec_driver_sql("DELETE FROM filechunk WHERE file_id = ? RETURNING id", (file_id,)).scalars().all()
                if stale_ids:
                    conn.exec_driver_sql(f"DELETE FROM {VECTOR_TABLE} WHERE rowid = ?", [(chunk_id,) for chunk_id in stale_ids])

                rows = [FileChunk(file_id=file_id, chunk_index=i, text=chunk) for i, chunk in enumerate(chunks)]
                session.add_all(rows)
                session.flush()
                conn.exec_driver_sql(
                    f"INSERT INTO {VECTOR_TABLE}(rowid, embedding) VALUES (?, ?)",
                    [(row.id, vector.tobytes()) for row, vector in zip(rows, vectors)],
                )
                session.commit()
            break
        except Exception as e:
            if "locked" in str(e).lower() and attempt < 4:
                import time
                time.sleep(0.2 * (attempt + 1))
            else:
                logger.warning(f"Could not index vectors for file {file_id}: {e}")
                break


def index_missing_files():
    """Index files and folders without search chunks (uploaded before search existed, or after a model change)."""
    with Session(engine) as session:
        file_ids = session.exec(
            select(FileMeta.id).where(
                FileMeta.is_deleted == False,
                col(FileMeta.id).not_in(select(FileChunk.file_id)),
            )
        ).all()

    for file_id in file_ids:
        try:
            index_file(file_id)
        except Exception:
            # One unreadable file must not stop the rest from being indexed
            logger.exception("Failed to index file %s for search", file_id)


def make_snippet(text: Optional[str], query_words: list[str], max_len: int = 150) -> Optional[str]:
    """Generates a concise snippet focused around matching query keywords."""
    if not text:
        return None
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return None

    lower_text = cleaned.lower()
    match_pos = -1
    for w in query_words:
        pos = lower_text.find(w.lower())
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
        snippet = snippet + "..."
    return snippet


def search(session: Session, user: User, query: str, limit: int) -> list[SearchResult]:
    """Hybrid semantic vector and keyword search strictly restricted to files owned by or shared with the user.
    
    Combines sqlite-vec dense cosine vector similarity with exact keyword matching
    to guarantee both semantic concept recall and exact keyword precision.
    """
    q_clean = query.strip()
    if not q_clean:
        return []

    # 1. Quick pre-check: determine if the user has any authorized files
    authorized_chunks_sql = """
        SELECT fc.id
        FROM filechunk fc
        JOIN filemeta fm ON fc.file_id = fm.id
        LEFT JOIN fileshare fs ON fm.id = fs.file_id
        WHERE (fm.owner_id = ? OR fs.shared_with_user_id = ? OR fs.shared_with_login = ?)
          AND (fm.is_deleted = 0)
    """
    conn = session.connection()
    authorized_chunk_ids = conn.exec_driver_sql(
        authorized_chunks_sql, (user.id, user.id, user.login)
    ).scalars().all()

    if not authorized_chunk_ids:
        return []

    query_vector = embed([q_clean])[0]
    candidate_limit = limit * CANDIDATES_PER_RESULT

    # 2. Strict scoped vector similarity search in sqlite-vec
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

    # 3. Exact keyword hits in authorized chunks & file/folder names
    q_words = [w.lower() for w in re.findall(r"\w+", q_clean) if len(w) >= 2]
    keyword_chunk_ids: set[int] = set()
    if q_words:
        kw_conditions = " OR ".join(["LOWER(fc.text) LIKE ? OR LOWER(fm.filename) LIKE ?" for _ in q_words])
        kw_params: list = [user.id, user.id, user.login]
        for w in q_words:
            kw_params.extend([f"%{w}%", f"%{w}%"])

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

    all_candidate_chunk_ids = set(distance_by_chunk.keys()) | keyword_chunk_ids
    if not all_candidate_chunk_ids:
        return []

    # 4. Retrieve relational file metadata with strict access verification
    shared_files_subquery = select(FileShare.file_id).where(
        (FileShare.shared_with_user_id == user.id) | (FileShare.shared_with_login == user.login)
    )

    rows = session.exec(
        select(FileChunk, FileMeta)
        .join(FileMeta, col(FileMeta.id) == col(FileChunk.file_id))
        .where(
            col(FileChunk.id).in_(list(all_candidate_chunk_ids)),
            FileMeta.is_deleted == False,
            (col(FileMeta.owner_id) == user.id) | col(FileMeta.id).in_(shared_files_subquery),
        )
    ).all()

    # 5. Score each candidate chunk (dense vector + keyword presence boost)
    best: dict[int, tuple[float, FileChunk, FileMeta]] = {}
    for chunk, file_meta in rows:
        base_dist = distance_by_chunk.get(chunk.id, 0.75)
        score = 1.0 - base_dist
        text_lower = (chunk.text or "").lower()
        fn_lower = file_meta.filename.lower()

        # Keyword match boost
        matched_words = [w for w in q_words if w in text_lower or w in fn_lower]
        if matched_words:
            boost = 0.35 + 0.1 * min(len(matched_words) - 1, 3)
            score = min(1.0, score + boost)

        if score < MIN_SCORE:
            continue

        if file_meta.id not in best or score > best[file_meta.id][0]:
            best[file_meta.id] = (score, chunk, file_meta)

    results: list[SearchResult] = []
    for score, chunk, file_meta in sorted(best.values(), key=lambda match: match[0], reverse=True)[:limit]:
        snippet = make_snippet(chunk.text, q_words)
        results.append(SearchResult.model_validate(file_meta, update={"score": score, "snippet": snippet}))

    return results


def get_suggestions(session: Session, user: User, query: str, limit: int = 8) -> SearchSuggestionsResponse:
    """Provides semantic and substring suggestions while typing in the search bar, separated into folders and files."""
    q = query.strip()
    if not q:
        return SearchSuggestionsResponse(folders=[], files=[])

    shared_subquery = select(FileShare.file_id).where(
        (FileShare.shared_with_user_id == user.id) | (FileShare.shared_with_login == user.login)
    )

    folder_suggestions_map: dict[int, SearchSuggestion] = {}
    file_suggestions_map: dict[int, SearchSuggestion] = {}

    # 1. Direct name matches (instant substring lookup)
    folders_stmt = (
        select(FileMeta)
        .where(
            FileMeta.is_folder == True,
            FileMeta.is_deleted == False,
            (FileMeta.owner_id == user.id) | (FileMeta.id.in_(shared_subquery)),
            func.lower(FileMeta.filename).contains(q.lower()),
        )
        .order_by(func.lower(FileMeta.filename))
        .limit(limit)
    )
    for f in session.exec(folders_stmt).all():
        folder_suggestions_map[f.id] = SearchSuggestion(
            id=f.id,
            filename=f.filename,
            is_folder=True,
            parent_id=f.parent_id,
        )

    files_stmt = (
        select(FileMeta)
        .where(
            FileMeta.is_folder == False,
            FileMeta.is_deleted == False,
            (FileMeta.owner_id == user.id) | (FileMeta.id.in_(shared_subquery)),
            func.lower(FileMeta.filename).contains(q.lower()),
        )
        .order_by(func.lower(FileMeta.filename))
        .limit(limit)
    )
    for f in session.exec(files_stmt).all():
        file_suggestions_map[f.id] = SearchSuggestion(
            id=f.id,
            filename=f.filename,
            is_folder=False,
            file_size=f.file_size,
            mime_type=f.mime_type,
            parent_id=f.parent_id,
        )

    # 2. Enrich with Semantic Vector Search matches (content + semantic meaning)
    try:
        semantic_results = search(session, user, q, limit=limit)
        for res in semantic_results:
            if res.is_folder:
                if res.id not in folder_suggestions_map and len(folder_suggestions_map) < limit:
                    folder_suggestions_map[res.id] = SearchSuggestion(
                        id=res.id,
                        filename=res.filename,
                        is_folder=True,
                        parent_id=res.parent_id,
                    )
            else:
                if res.id not in file_suggestions_map:
                    if len(file_suggestions_map) < limit:
                        file_suggestions_map[res.id] = SearchSuggestion(
                            id=res.id,
                            filename=res.filename,
                            is_folder=False,
                            file_size=res.file_size,
                            mime_type=res.mime_type,
                            snippet=res.snippet,
                            parent_id=res.parent_id,
                        )
                elif not file_suggestions_map[res.id].snippet and res.snippet:
                    # Update snippet if previously missing
                    file_suggestions_map[res.id].snippet = res.snippet
    except Exception as exc:
        logger.warning("Semantic suggestions failed: %s", exc)

    return SearchSuggestionsResponse(
        folders=list(folder_suggestions_map.values())[:limit],
        files=list(file_suggestions_map.values())[:limit],
    )



