"""Semantic search endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.dependencies.db import get_db
from app.dependencies.tailscale import get_current_user
from app.models.user import User
from app.schemas.item import SearchResult, SearchSuggestionsResponse
from app.services import search_service

router = APIRouter(prefix="/api/search", tags=["Search"])


@router.get("", response_model=list[SearchResult])
def search_files(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=50),
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Semantic + keyword search over the user's accessible files."""
    return search_service.search_files(session, user, q, limit)


@router.get("/suggest", response_model=SearchSuggestionsResponse)
def suggest_files_and_folders(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(8, ge=1, le=20),
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Autocomplete suggestions, separated into folders and files."""
    return search_service.suggest_files_and_folders(session, user, q, limit)


__all__ = ["router"]
