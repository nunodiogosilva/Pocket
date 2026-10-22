"""DTOs for the unified item (file/folder) tree and directory operations."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ItemRead(BaseModel):
    """API representation of an ``Item``; hides the on-disk path and owner."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_size: int
    mime_type: str
    parent_id: Optional[int]
    is_folder: bool
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    created_at: datetime


class DirectoryContent(BaseModel):
    """Explicitly separated lists of folders and files."""

    folders: list[ItemRead] = Field(default_factory=list)
    files: list[ItemRead] = Field(default_factory=list)


class UploadResponse(BaseModel):
    status: str
    file_id: int
    filename: str


class CreateFolderRequest(BaseModel):
    name: str
    parent_id: Optional[int] = None


class RenameRequest(BaseModel):
    name: str


class MoveItemRequest(BaseModel):
    target_parent_id: Optional[int] = None


class BinItemRead(ItemRead):
    """Recycle-bin item with the number of days left before permanent deletion."""

    days_left: int


class StorageUsage(BaseModel):
    """Active storage consumption and file/folder counts for the user."""

    used_bytes: int
    total_bytes: int
    file_count: int
    folder_count: int


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
class SearchResult(ItemRead):
    """An item match enriched with a similarity score and an optional snippet."""

    score: float
    """Cosine similarity between the query and the best-matching part of the file (1 = identical)."""
    snippet: Optional[str] = None
    """Best-matching text from the file's content; None when only the file name matched."""


class SearchSuggestion(BaseModel):
    """A single autocomplete suggestion (folder or file)."""

    id: int
    filename: str
    is_folder: bool
    file_size: int = 0
    mime_type: str = ""
    snippet: Optional[str] = None
    parent_id: Optional[int] = None


class SearchSuggestionsResponse(BaseModel):
    """Suggestions for autocomplete, separated into folders and files."""

    folders: list[SearchSuggestion] = Field(default_factory=list)
    files: list[SearchSuggestion] = Field(default_factory=list)


# Backward-compatible aliases used across the old routers/schemas.
FileRead = ItemRead

__all__ = [
    "ItemRead",
    "FileRead",
    "DirectoryContent",
    "UploadResponse",
    "CreateFolderRequest",
    "RenameRequest",
    "MoveItemRequest",
    "BinItemRead",
    "StorageUsage",
    "SearchResult",
    "SearchSuggestion",
    "SearchSuggestionsResponse",
]
