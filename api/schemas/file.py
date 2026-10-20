from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel


class FileRead(SQLModel):
    """API representation of FileMeta; hides the on-disk path and owner."""

    id: int
    filename: str
    file_size: int
    mime_type: str
    parent_id: Optional[int]
    is_folder: bool
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    created_at: datetime


class DirectoryContent(SQLModel):
    """Explicitly separated lists of folders and files."""

    folders: list[FileRead] = []
    files: list[FileRead] = []


class SharedItemRead(FileRead):
    """File or folder shared with the user, including sharer information."""

    shared_by: str
    shared_by_name: Optional[str] = None
    permission: str = "read"


class SharedDirectoryContent(SQLModel):
    """Separated folders and files shared with the user."""

    folders: list[SharedItemRead] = []
    files: list[SharedItemRead] = []


class UploadResponse(SQLModel):
    status: str
    file_id: int
    filename: str


class CreateFolderRequest(SQLModel):
    name: str
    parent_id: Optional[int] = None


class RenameRequest(SQLModel):
    name: str


class BinItemRead(FileRead):
    days_left: int


class StorageUsage(SQLModel):
    used_bytes: int
    total_bytes: int
    file_count: int
    folder_count: int
