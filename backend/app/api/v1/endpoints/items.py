"""Item endpoints: unified file & folder CRUD, trash, directories, and storage.

Everything lives on a single ``router`` prefixed with ``/api/items``. File and
folder operations share the same resource surface (the service layer
discriminates by ``is_folder``), and the auxiliary domains — recycle bin,
directory listing, and storage usage — are exposed as sub-paths under the same
prefix so the whole module has one router.

Static paths (``/bin``, ``/directory``, ``/storage``) are declared before the
``/{item_id}`` wildcard so they take precedence in route resolution.
"""

import os
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.config import settings
from app.dependencies.db import get_db
from app.dependencies.tailscale import get_current_user
from app.models.user import User
from app.schemas.item import (
    BinItemRead,
    CreateFolderRequest,
    DirectoryContent,
    ItemRead,
    MoveItemRequest,
    RenameRequest,
    StorageUsage,
    UploadResponse,
)
from app.schemas.permission import (
    ShareLinkResponse,
    ShareUserRequest,
    ShareUserResponse,
    SharedDirectoryContent,
)
from app.services import item_service, sharing as sharing_service, search_service


def _ensure_parent_folder(session: Session, user: User, parent_id: Optional[int]) -> None:
    """404 if ``parent_id`` points at a folder the user does not own."""
    if parent_id is None:
        return
    parent = item_service.get_owned_item(session, user, parent_id)
    if not parent or not parent.is_folder:
        raise HTTPException(status_code=404, detail="Parent folder not found")


router = APIRouter(prefix="/api/items", tags=["items"])


# --------------------------------------------------------------------------- #
# Items — files and folders share the same resource surface
# --------------------------------------------------------------------------- #
@router.get("", response_model=list[ItemRead])
def list_items(
    parent_id: Optional[int] = None,
    type: Literal["file", "folder"] = Query("all"),
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List items owned by the user under ``parent_id`` (or root).

    Filter with ``type=file`` or ``type=folder``; omit for both.
    """
    is_folder = None if type == "all" else type == "folder"
    return item_service.list_items(session, user, parent_id, is_folder=is_folder)


@router.get("/shared-with-me", response_model=SharedDirectoryContent)
def list_shared_with_me(
    parent_id: Optional[int] = None,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List folders and files explicitly shared with this user."""
    return item_service.list_shared_with_me(session, user, parent_id)


@router.post("", response_model=ItemRead)
def create_folder(
    payload: CreateFolderRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new folder under ``parent_id``."""
    _ensure_parent_folder(session, user, payload.parent_id)
    try:
        folder = item_service.create_folder(session, user, payload.name, payload.parent_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    background_tasks.add_task(search_service.index_file, folder.id)
    return folder


@router.post("/upload", response_model=UploadResponse)
def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    parent_id: Optional[int] = Form(None),
    relative_path: Optional[str] = Form(None),
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload a file, preserving directory hierarchy when ``relative_path`` is set."""
    _ensure_parent_folder(session, user, parent_id)
    db_item = item_service.save_upload(session, user, file, parent_id, relative_path)
    background_tasks.add_task(search_service.index_file, db_item.id)
    return UploadResponse(status="success", file_id=db_item.id, filename=db_item.filename)


# --------------------------------------------------------------------------- #
# Recycle bin (static paths must precede ``/{item_id}``)
# --------------------------------------------------------------------------- #
@router.get("/bin", response_model=list[BinItemRead])
def get_bin_items(session: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """List items in the user's recycle bin with days remaining."""
    return item_service.list_bin(session, user)


@router.post("/bin/{item_id}")
def restore_item(
    item_id: int,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Restore an item (and children) from the recycle bin."""
    success = item_service.restore_from_bin(session, user, item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Item not found in bin or permission denied")
    return {"status": "success", "id": item_id}


@router.delete("/bin/{item_id}")
def permanently_delete_item(
    item_id: int,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Permanently delete an item from disk and database."""
    success = item_service.hard_delete(session, user, item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Item not found or permission denied")
    return {"status": "success", "id": item_id}


@router.delete("/bin")
def empty_bin(session: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Empty the user's recycle bin."""
    count = item_service.empty_bin(session, user)
    return {"status": "success", "deleted_count": count}


# --------------------------------------------------------------------------- #
# Directory listing & storage
# --------------------------------------------------------------------------- #
@router.get("/directory", response_model=DirectoryContent)
def get_directory_contents(
    parent_id: Optional[int] = None,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List folders and files in a directory (or the user's root)."""
    return item_service.list_directory(session, user, parent_id)


@router.get("/storage", response_model=StorageUsage)
def get_current_user_storage(session: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Return the user's active storage consumption and item counts."""
    return StorageUsage(**item_service.get_user_storage(session, user))


# --------------------------------------------------------------------------- #
# Per-item operations (wildcard ``/{item_id}``)
# --------------------------------------------------------------------------- #
@router.get("/{item_id}", response_model=ItemRead)
def get_item(
    item_id: int,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get metadata for a file or folder owned by or shared with the user."""
    item = item_service.get_accessible_item(session, user, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.get("/{item_id}/download")
def download_item(
    item_id: int,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stream file content, or a zip archive for folders."""
    item = item_service.get_accessible_item(session, user, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if item.is_folder:
        try:
            zip_path = item_service.create_folder_zip(session, user, item_id)
            background_tasks.add_task(os.remove, zip_path)
            return FileResponse(path=zip_path, filename=f"{item.filename}.zip", media_type="application/zip")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to generate folder zip: {e}") from e

    if not item.storage_path or not os.path.exists(item.storage_path):
        raise HTTPException(status_code=404, detail="File missing or not found")
    return FileResponse(
        path=item.storage_path,
        filename=item.filename,
        media_type=item.mime_type or "application/octet-stream",
        content_disposition_type="inline",
    )


@router.patch("/{item_id}/rename", response_model=ItemRead)
def rename_item(
    item_id: int,
    payload: RenameRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Rename an owned file or folder."""
    try:
        updated = item_service.rename_item(session, user, item_id, payload.name)
        background_tasks.add_task(search_service.index_file, item_id)
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.patch("/{item_id}/move", response_model=ItemRead)
def move_item(
    item_id: int,
    payload: MoveItemRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Move an owned file or folder to another parent directory (or root)."""
    try:
        updated = item_service.move_item(session, user, item_id, payload.target_parent_id)
        background_tasks.add_task(search_service.index_file, item_id)
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{item_id}/share", response_model=ShareLinkResponse)
def create_share_link(
    item_id: int,
    expires_in_hours: int = Query(24, ge=1, le=24 * 365),
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate an unguessable public share token for Funnel ingress."""
    item = item_service.get_owned_item(session, user, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    link = sharing_service.create_link(session, item, expires_in_hours)
    return ShareLinkResponse(share_url=f"{settings.public_base_url}/api/shared/{link.token}", expires_at=link.expires_at)


@router.post("/{item_id}/share-user", response_model=ShareUserResponse)
def share_item_with_user(
    item_id: int,
    payload: ShareUserRequest,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Share a file or folder with another user on the Tailnet."""
    share = item_service.share_with_user(session, user, item_id, payload.login, payload.permission)
    if not share:
        raise HTTPException(status_code=404, detail="Item not found or permission denied")
    return ShareUserResponse(status="success", file_id=item_id, shared_with_login=payload.login)


@router.delete("/{item_id}")
def delete_item(
    item_id: int,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Move an owned file or folder to the recycle bin."""
    success = item_service.soft_delete(session, user, item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Item not found or permission denied")
    return {"status": "success", "id": item_id}


__all__ = ["router"]
