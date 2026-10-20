import os
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session
from dependencies import get_db
from models import FileMeta, User
from services import sharing, storage

router = APIRouter(prefix="/api/shared", tags=["shared"])


@router.get("/{token}")
def download_shared_file(
    token: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
):
    link = sharing.get_active_link(session, token)
    if not link:
        raise HTTPException(status_code=404, detail="Link invalid or expired")

    file_meta = session.get(FileMeta, link.file_id)
    if not file_meta or file_meta.is_deleted:
        raise HTTPException(status_code=404, detail="File or folder missing or deleted")

    sharing.record_download(session, link)

    if file_meta.is_folder:
        owner = session.get(User, file_meta.owner_id)
        if not owner:
            raise HTTPException(status_code=404, detail="Folder owner not found")
        try:
            zip_path = storage.create_folder_zip(session, owner, file_meta.id)
            background_tasks.add_task(os.remove, zip_path)
            return FileResponse(
                path=zip_path,
                filename=f"{file_meta.filename}.zip",
                media_type="application/zip",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to generate folder archive: {e}")

    if not file_meta.storage_path or not os.path.exists(file_meta.storage_path):
        raise HTTPException(status_code=404, detail="File missing on disk")

    return FileResponse(path=file_meta.storage_path, filename=file_meta.filename)
