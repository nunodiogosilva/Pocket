from typing import Optional
from sqlmodel import SQLModel
from .file import FileRead


class SearchResult(FileRead):
    score: float
    """Cosine similarity between the query and the best-matching part of the file (1 = identical)."""
    snippet: Optional[str] = None
    """Best-matching text from the file's content; None when only the file name matched."""


class SearchSuggestion(SQLModel):
    id: int
    filename: str
    is_folder: bool
    file_size: int = 0
    mime_type: str = ""
    snippet: Optional[str] = None
    parent_id: Optional[int] = None


class SearchSuggestionsResponse(SQLModel):
    """Suggestions for autocomplete while typing in search bar, separated by folders and files."""

    folders: list[SearchSuggestion] = []
    files: list[SearchSuggestion] = []
