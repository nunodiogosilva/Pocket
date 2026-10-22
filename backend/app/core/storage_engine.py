"""Low-level, chunked file storage and archive helpers.

This module owns the raw byte-pipeline (streaming uploads to disk, zipping a
folder tree) so that higher-level services never buffer an entire upload or
archive in memory — a hard requirement under the <200MB RAM budget.
"""

import os
import shutil
import tempfile
import uuid
import zipfile
from typing import BinaryIO, Optional

from app.config import settings


def init_storage() -> None:
    """Ensure the on-disk storage tree exists and spool temp files on the SSD."""
    os.makedirs(settings.user_files_dir, exist_ok=True)
    os.makedirs(settings.upload_tmp_dir, exist_ok=True)
    # Spool incoming uploads on the SSD instead of the container's SD-card-backed /tmp.
    tempfile.tempdir = settings.upload_tmp_dir


def allocate_storage_path(owner_id: int) -> str:
    """Return a unique, collision-free on-disk path for a new upload."""
    user_dir = os.path.join(settings.user_files_dir, str(owner_id))
    os.makedirs(user_dir, exist_ok=True)
    return os.path.join(user_dir, uuid.uuid4().hex)


def stream_to_disk(source: BinaryIO, destination_path: str, chunk_size: int = 1024 * 1024) -> int:
    """Copy a binary stream to ``destination_path`` in 1MiB chunks; return bytes written."""
    with open(destination_path, "wb") as buffer:
        shutil.copyfileobj(source, buffer, chunk_size)
    return os.path.getsize(destination_path)


def create_folder_zip(file_entries: list[tuple[str, Optional[str]]], folder_display_name: str) -> str:
    """Package ``(relative_path, source_path_or_None)`` entries into a temp zip.

    Entries with a ``None`` source represent empty directory markers. Returns the
    absolute path of the created ``.zip`` for the caller to stream and clean up.
    """
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip", dir=settings.upload_tmp_dir)
    temp_zip.close()

    with zipfile.ZipFile(temp_zip.name, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for relative_path, source_path in file_entries:
            if source_path is None:
                zf.writestr(relative_path, "")
            elif os.path.exists(source_path):
                zf.write(source_path, arcname=relative_path)

    return temp_zip.name


def remove_path(path: str) -> None:
    """Best-effort removal of a temporary artifact (e.g. a generated zip)."""
    try:
        os.remove(path)
    except OSError:
        pass


__all__ = [
    "init_storage",
    "allocate_storage_path",
    "stream_to_disk",
    "create_folder_zip",
    "remove_path",
]
