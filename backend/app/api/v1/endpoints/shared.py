"""Public shared-link download (Tailscale Funnel ingress, no auth header)."""

import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.dependencies.db import get_db
from app.services import sharing as sharing_service

router = APIRouter(prefix="/api/shared", tags=["Shared"])


@router.get("/{token}")
def download_shared_item(
    token: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
):
    """Stream a shared item (file) or folder (zipped) via its public token."""
    link = sharing_service.get_active_share_link(session, token)
    if not link:
        raise HTTPException(status_code=404, detail="Link invalid or expired")

    item = sharing_service.get_shared_item(session, link)
    if not item:
        raise HTTPException(status_code=404, detail="Item missing or deleted")

    sharing_service.record_download(session, link)

    if item.is_folder:
        owner = sharing_service.get_item_owner(session, item)
        if not owner:
            raise HTTPException(status_code=404, detail="Folder owner not found")
        try:
            zip_path = sharing_service.create_shared_folder_archive(session, owner, item.id)
            background_tasks.add_task(os.remove, zip_path)
            return FileResponse(
                path=zip_path,
                filename=f"{item.filename}.zip",
                media_type="application/zip",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to generate folder archive: {e}") from e

    file_path = sharing_service.get_file_download_path(item)
    if not file_path:
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(path=file_path, filename=item.filename)


__all__ = ["router"]
