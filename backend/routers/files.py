import os
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session
from config import PUBLIC_BASE_URL
from dependencies import get_current_user, get_db
from models import User
from schemas import (
    CreateFolderRequest,
    DirectoryContent,
    FileRead,
    RenameRequest,
    SharedDirectoryContent,
    ShareLinkResponse,
    ShareUserRequest,
    ShareUserResponse,
    UploadResponse,
)
from services import semantic_search, sharing, storage

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("", response_model=DirectoryContent)
def list_directory(
    parent_id: Optional[int] = None,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Lists files and folders strictly separated into {folders: [...], files: [...]}."""
    return storage.list_directory(session, user, parent_id)


@router.get("/shared-with-me", response_model=SharedDirectoryContent)
def list_shared_with_me(
    parent_id: Optional[int] = None,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Lists folders and files explicitly shared with this user, separated by type."""
    return storage.list_shared_with_me(session, user, parent_id)


# Backward compatible folder creation on /api/files/folder
@router.post("/folder", response_model=FileRead)
def create_folder_legacy(
    payload: CreateFolderRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Creates a new folder under parent_id (legacy compatibility endpoint)."""
    if payload.parent_id is not None:
        parent = storage.get_owned_file(session, user, payload.parent_id)
        if not parent or not parent.is_folder:
            raise HTTPException(status_code=404, detail="Parent folder not found")

    folder = storage.create_folder(session, user, payload.name, payload.parent_id)
    background_tasks.add_task(semantic_search.index_file, folder.id)
    return folder


@router.get("/{file_id}", response_model=FileRead)
def get_file(
    file_id: int,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retrieves file metadata if the file is owned by or shared with the user."""
    file_meta = storage.get_accessible_file(session, user, file_id)
    if not file_meta or file_meta.is_folder:
        raise HTTPException(status_code=404, detail="File not found")
    return file_meta


@router.get("/{file_id}/download")
def download_file(
    file_id: int,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Streams file content directly to the client with inline disposition for client-side previews."""
    file_meta = storage.get_accessible_file(session, user, file_id)
    if not file_meta or not file_meta.storage_path or not os.path.exists(file_meta.storage_path):
        raise HTTPException(status_code=404, detail="File missing or not found")

    return FileResponse(
        path=file_meta.storage_path,
        filename=file_meta.filename,
        media_type=file_meta.mime_type or "application/octet-stream",
        content_disposition_type="inline",
    )


@router.post("/upload", response_model=UploadResponse)
def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    parent_id: Optional[int] = Form(None),
    relative_path: Optional[str] = Form(None),
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Uploads a file, preserving directory hierarchy if relative_path is provided (folder upload)."""
    if parent_id is not None:
        parent = storage.get_owned_file(session, user, parent_id)
        if not parent or not parent.is_folder:
            raise HTTPException(status_code=404, detail="Parent folder not found")

    db_file = storage.save_upload(session, user, file, parent_id, relative_path)
    # Index in background after the response is sent so uploads stay fast
    background_tasks.add_task(semantic_search.index_file, db_file.id)
    return UploadResponse(status="success", file_id=db_file.id, filename=db_file.filename)


@router.patch("/{file_id}/rename", response_model=FileRead)
def rename_file(
    file_id: int,
    payload: RenameRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Renames an owned file."""
    try:
        updated = storage.rename_item(session, user, file_id, payload.name, is_folder=False)
        background_tasks.add_task(semantic_search.index_file, file_id)
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{file_id}/share", response_model=ShareLinkResponse)
def create_share_link(
    file_id: int,
    expires_in_hours: int = Query(24, ge=1, le=24 * 365),
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generates an unguessable public share token for public Funnel ingress."""
    file_meta = storage.get_owned_file(session, user, file_id)
    if not file_meta:
        raise HTTPException(status_code=404, detail="File not found")

    link = sharing.create_link(session, file_meta, expires_in_hours)
    return ShareLinkResponse(share_url=f"{PUBLIC_BASE_URL}/api/shared/{link.token}", expires_at=link.expires_at)


@router.post("/{file_id}/share-user", response_model=ShareUserResponse)
def share_file_with_user(
    file_id: int,
    payload: ShareUserRequest,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Explicitly shares a file with another user on the Tailnet."""
    share = storage.share_file_with_user(session, user, file_id, payload.login, payload.permission)
    if not share:
        raise HTTPException(status_code=404, detail="File not found or permission denied")
    return ShareUserResponse(status="success", file_id=file_id, shared_with_login=payload.login)


@router.delete("/{file_id}")
def delete_file(
    file_id: int,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Moves an owned file to the recycle bin."""
    success = storage.soft_delete(session, user, file_id)
    if not success:
        raise HTTPException(status_code=404, detail="File not found or permission denied")
    return {"status": "success", "file_id": file_id}
