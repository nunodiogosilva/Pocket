from fastapi import APIRouter, Depends, Query
from sqlmodel import Session
from dependencies import get_current_user, get_db
from models import User
from schemas import SearchResult, SearchSuggestionsResponse
from services import semantic_search

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=list[SearchResult])
def search_files(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=50),
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return semantic_search.search(session, user, q, limit)


@router.get("/suggest", response_model=SearchSuggestionsResponse)
def suggest_files_and_folders(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(8, ge=1, le=20),
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return semantic_search.get_suggestions(session, user, q, limit)

