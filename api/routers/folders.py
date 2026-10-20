import os
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlmodel import Session
from config import PUBLIC_BASE_URL
from dependencies import get_current_user, get_db
from models import User
from schemas import (
    CreateFolderRequest,
    FileRead,
    RenameRequest,
    ShareLinkResponse,
    ShareUserRequest,
    ShareUserResponse,
)
from services import semantic_search, sharing, storage

router = APIRouter(prefix="/api/folders", tags=["folders"])


@router.post("", response_model=FileRead)
def create_folder(
    payload: CreateFolderRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Explicitly creates a new directory/folder under parent_id."""
    if payload.parent_id is not None:
        parent = storage.get_owned_file(session, user, payload.parent_id)
        if not parent or not parent.is_folder:
            raise HTTPException(status_code=404, detail="Parent folder not found")

    folder = storage.create_folder(session, user, payload.name, payload.parent_id)
    background_tasks.add_task(semantic_search.index_file, folder.id)
    return folder


@router.get("", response_model=list[FileRead])
def list_folders(
    parent_id: Optional[int] = None,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Lists only folders owned by the authenticated Tailscale user."""
    return storage.list_files(session, user, parent_id, is_folder=True)


@router.get("/{folder_id}", response_model=FileRead)
def get_folder(
    folder_id: int,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retrieves folder metadata if owned or shared."""
    folder = storage.get_accessible_file(session, user, folder_id)
    if not folder or not folder.is_folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


@router.get("/{folder_id}/download")
def download_folder(
    folder_id: int,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Packages the folder and all its contents into a zip archive and streams it."""
    folder = storage.get_accessible_file(session, user, folder_id)
    if not folder or not folder.is_folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    try:
        zip_path = storage.create_folder_zip(session, user, folder_id)
        background_tasks.add_task(os.remove, zip_path)
        return FileResponse(
            path=zip_path,
            filename=f"{folder.filename}.zip",
            media_type="application/zip",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate folder zip: {e}")


@router.patch("/{folder_id}/rename", response_model=FileRead)
def rename_folder(
    folder_id: int,
    payload: RenameRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Renames an owned folder."""
    try:
        updated = storage.rename_item(session, user, folder_id, payload.name, is_folder=True)
        background_tasks.add_task(semantic_search.index_file, folder_id)
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{folder_id}/share", response_model=ShareLinkResponse)
def create_folder_share_link(
    folder_id: int,
    expires_in_hours: int = Query(24, ge=1, le=24 * 365),
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generates an unguessable public share token for the folder."""
    folder = storage.get_owned_file(session, user, folder_id)
    if not folder or not folder.is_folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    link = sharing.create_link(session, folder, expires_in_hours)
    return ShareLinkResponse(share_url=f"{PUBLIC_BASE_URL}/api/shared/{link.token}", expires_at=link.expires_at)


@router.post("/{folder_id}/share-user", response_model=ShareUserResponse)
def share_folder_with_user(
    folder_id: int,
    payload: ShareUserRequest,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Explicitly shares a folder with another user on the Tailnet."""
    folder = storage.get_owned_file(session, user, folder_id)
    if not folder or not folder.is_folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    share = storage.share_file_with_user(session, user, folder_id, payload.login, payload.permission)
    if not share:
        raise HTTPException(status_code=404, detail="Folder not found or permission denied")
    return ShareUserResponse(status="success", file_id=folder_id, shared_with_login=payload.login)


@router.delete("/{folder_id}")
def delete_folder(
    folder_id: int,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Moves an owned folder and its contents to the recycle bin."""
    success = storage.soft_delete(session, user, folder_id)
    if not success:
        raise HTTPException(status_code=404, detail="Folder not found or permission denied")
    return {"status": "success", "folder_id": folder_id}
