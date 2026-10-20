from datetime import datetime, timedelta, timezone
import os
import shutil
import tempfile
import uuid
import zipfile
from typing import Optional
from fastapi import UploadFile
from sqlmodel import Session, col, func, select
from config import UPLOAD_TMP_DIR, USER_FILES_DIR
from models import FileChunk, FileMeta, FileShare, SharedLink, User
from schemas import BinItemRead, DirectoryContent, SharedDirectoryContent, SharedItemRead


def init_storage():
    os.makedirs(USER_FILES_DIR, exist_ok=True)
    os.makedirs(UPLOAD_TMP_DIR, exist_ok=True)
    # Spool incoming uploads on the SSD instead of the container's SD-card-backed /tmp
    tempfile.tempdir = UPLOAD_TMP_DIR


def list_directory(session: Session, owner: User, parent_id: Optional[int]) -> DirectoryContent:
    """Returns directory contents with folders and files strictly separated, excluding deleted items."""
    folders = session.exec(
        select(FileMeta)
        .where(
            FileMeta.owner_id == owner.id,
            FileMeta.parent_id == parent_id,
            FileMeta.is_folder == True,
            FileMeta.is_deleted == False,
        )
        .order_by(func.lower(FileMeta.filename))
    ).all()
    files = session.exec(
        select(FileMeta)
        .where(
            FileMeta.owner_id == owner.id,
            FileMeta.parent_id == parent_id,
            FileMeta.is_folder == False,
            FileMeta.is_deleted == False,
        )
        .order_by(func.lower(FileMeta.filename))
    ).all()
    return DirectoryContent(folders=list(folders), files=list(files))


def list_shared_with_me(session: Session, user: User, parent_id: Optional[int] = None) -> SharedDirectoryContent:
    """Lists folders and files explicitly shared with this user, separated by type."""
    folders: list[SharedItemRead] = []
    files: list[SharedItemRead] = []

    if parent_id is not None:
        parent_folder = get_accessible_file(session, user, parent_id)
        if not parent_folder:
            return SharedDirectoryContent(folders=[], files=[])

        owner = session.get(User, parent_folder.owner_id)
        owner_login = owner.login if owner else "unknown"
        owner_name = owner.name if owner else None

        items = session.exec(
            select(FileMeta)
            .where(
                FileMeta.parent_id == parent_id,
                FileMeta.is_deleted == False,
            )
            .order_by(func.lower(FileMeta.filename))
        ).all()

        for item in items:
            shared_item = SharedItemRead.model_validate(
                item,
                update={
                    "shared_by": owner_login,
                    "shared_by_name": owner_name,
                    "permission": "read",
                },
            )
            if item.is_folder:
                folders.append(shared_item)
            else:
                files.append(shared_item)
    else:
        shares_rows = session.exec(
            select(FileShare, FileMeta, User)
            .join(FileMeta, FileShare.file_id == FileMeta.id)
            .join(User, FileMeta.owner_id == User.id)
            .where(
                (FileShare.shared_with_user_id == user.id) | (FileShare.shared_with_login == user.login),
                FileMeta.is_deleted == False,
            )
            .order_by(func.lower(FileMeta.filename))
        ).all()

        for share, file_meta, owner in shares_rows:
            shared_item = SharedItemRead.model_validate(
                file_meta,
                update={
                    "shared_by": owner.login,
                    "shared_by_name": owner.name,
                    "permission": share.permission,
                },
            )
            if file_meta.is_folder:
                folders.append(shared_item)
            else:
                files.append(shared_item)

    return SharedDirectoryContent(folders=folders, files=files)


def list_files(
    session: Session, owner: User, parent_id: Optional[int], is_folder: Optional[bool] = None
) -> list[FileMeta]:
    statement = select(FileMeta).where(
        FileMeta.owner_id == owner.id,
        FileMeta.parent_id == parent_id,
        FileMeta.is_deleted == False,
    )
    if is_folder is not None:
        statement = statement.where(FileMeta.is_folder == is_folder)
    statement = statement.order_by(col(FileMeta.is_folder).desc(), func.lower(FileMeta.filename))
    return list(session.exec(statement).all())


def get_owned_file(session: Session, owner: User, file_id: int, include_deleted: bool = False) -> Optional[FileMeta]:
    file_meta = session.get(FileMeta, file_id)
    if not file_meta or file_meta.owner_id != owner.id:
        return None
    if not include_deleted and file_meta.is_deleted:
        return None
    return file_meta


def get_accessible_file(session: Session, user: User, file_id: int, include_deleted: bool = False) -> Optional[FileMeta]:
    file_meta = session.get(FileMeta, file_id)
    if not file_meta:
        return None
    if not include_deleted and file_meta.is_deleted:
        return None
    if file_meta.owner_id == user.id:
        return file_meta

    # Check if explicitly shared with this user via user ID or Tailscale login
    share = session.exec(
        select(FileShare).where(
            FileShare.file_id == file_id,
            (FileShare.shared_with_user_id == user.id) | (FileShare.shared_with_login == user.login),
        )
    ).first()
    return file_meta if share else None


import threading
import time

_folder_lock = threading.Lock()


def resolve_or_create_folder_path(
    session: Session, owner: User, folder_path: str, base_parent_id: Optional[int]
) -> Optional[int]:
    """Resolves or recursively creates folders for a given path relative to base_parent_id."""
    normalized = folder_path.replace("\\", "/").strip("/")
    parts = [p.strip() for p in normalized.split("/") if p.strip() and p.strip() not in (".", "..")]
    if not parts:
        return base_parent_id

    # Prevent race conditions and SQLite locks when concurrent uploads resolve/create the same folder path
    with _folder_lock:
        current_parent_id = base_parent_id
        for part in parts:
            folder = session.exec(
                select(FileMeta).where(
                    FileMeta.owner_id == owner.id,
                    FileMeta.parent_id == current_parent_id,
                    FileMeta.filename == part,
                    FileMeta.is_folder == True,
                    FileMeta.is_deleted == False,
                )
            ).first()

            if not folder:
                folder = FileMeta(
                    filename=part,
                    storage_path="",
                    file_size=0,
                    mime_type="inode/directory",
                    parent_id=current_parent_id,
                    is_folder=True,
                    is_deleted=False,
                    owner_id=owner.id,
                )
                session.add(folder)
                for attempt in range(5):
                    try:
                        session.commit()
                        session.refresh(folder)
                        break
                    except Exception as e:
                        if "locked" in str(e).lower() and attempt < 4:
                            session.rollback()
                            time.sleep(0.15 * (attempt + 1))
                            session.add(folder)
                        else:
                            raise

            current_parent_id = folder.id

        return current_parent_id


def create_folder(session: Session, owner: User, name: str, parent_id: Optional[int]) -> FileMeta:
    """Explicitly creates a new folder in the specified parent."""
    clean_name = os.path.basename(name.strip().replace("\\", "/")) or "New Folder"

    with _folder_lock:
        existing = session.exec(
            select(FileMeta).where(
                FileMeta.owner_id == owner.id,
                FileMeta.parent_id == parent_id,
                FileMeta.filename == clean_name,
                FileMeta.is_folder == True,
                FileMeta.is_deleted == False,
            )
        ).first()
        if existing:
            return existing

        folder = FileMeta(
            filename=clean_name,
            storage_path="",
            file_size=0,
            mime_type="inode/directory",
            parent_id=parent_id,
            is_folder=True,
            is_deleted=False,
            owner_id=owner.id,
        )
        session.add(folder)
        for attempt in range(5):
            try:
                session.commit()
                session.refresh(folder)
                break
            except Exception as e:
                if "locked" in str(e).lower() and attempt < 4:
                    session.rollback()
                    time.sleep(0.15 * (attempt + 1))
                    session.add(folder)
                else:
                    raise
        return folder


def save_upload(
    session: Session,
    owner: User,
    upload: UploadFile,
    parent_id: Optional[int],
    relative_path: Optional[str] = None,
) -> FileMeta:
    """Saves an uploaded file, creating any required nested folders if relative_path is provided."""
    target_parent_id = parent_id
    filename = upload.filename or "untitled"

    if relative_path:
        normalized = relative_path.replace("\\", "/").strip("/")
        parts = [p.strip() for p in normalized.split("/") if p.strip() and p.strip() not in (".", "..")]
        if len(parts) > 1:
            folder_hierarchy = "/".join(parts[:-1])
            filename = parts[-1]
            target_parent_id = resolve_or_create_folder_path(
                session, owner, folder_hierarchy, parent_id
            )
        elif len(parts) == 1:
            filename = parts[0]

    clean_filename = os.path.basename(filename.replace("\\", "/")) or "untitled"
    user_dir = os.path.join(USER_FILES_DIR, str(owner.id))
    os.makedirs(user_dir, exist_ok=True)
    file_path = os.path.join(user_dir, uuid.uuid4().hex)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload.file, buffer, 1024 * 1024)

    db_file = FileMeta(
        filename=clean_filename,
        storage_path=file_path,
        file_size=os.path.getsize(file_path),
        mime_type=upload.content_type or "application/octet-stream",
        parent_id=target_parent_id,
        is_folder=False,
        is_deleted=False,
        owner_id=owner.id,
    )
    session.add(db_file)
    for attempt in range(5):
        try:
            session.commit()
            session.refresh(db_file)
            break
        except Exception as e:
            if "locked" in str(e).lower() and attempt < 4:
                session.rollback()
                time.sleep(0.15 * (attempt + 1))
                session.add(db_file)
            else:
                raise
    return db_file


def rename_item(
    session: Session,
    owner: User,
    item_id: int,
    new_name: str,
    is_folder: Optional[bool] = None,
) -> FileMeta:
    """Renames an owned file or folder and updates its metadata."""
    clean_name = os.path.basename(new_name.strip().replace("\\", "/"))
    if not clean_name:
        raise ValueError("New name cannot be empty")

    item = get_owned_file(session, owner, item_id)
    if not item:
        raise ValueError("Item not found")

    if is_folder is not None and item.is_folder != is_folder:
        raise ValueError("Item type mismatch")

    # Check for name collisions in the same parent directory
    collision = session.exec(
        select(FileMeta).where(
            FileMeta.owner_id == owner.id,
            FileMeta.parent_id == item.parent_id,
            FileMeta.filename == clean_name,
            FileMeta.is_deleted == False,
            FileMeta.id != item_id,
        )
    ).first()
    if collision:
        raise ValueError(f"An item named '{clean_name}' already exists in this directory")

    item.filename = clean_name
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def create_folder_zip(session: Session, user: User, folder_id: int) -> str:
    """Packages a folder and all its contents recursively into a zip archive."""
    folder = get_accessible_file(session, user, folder_id)
    if not folder or not folder.is_folder:
        raise ValueError("Folder not found or inaccessible")

    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip", dir=UPLOAD_TMP_DIR)
    temp_zip_path = temp_zip.name
    temp_zip.close()

    # Track directory relative paths inside the archive: {folder_id: relative_path}
    folder_paths: dict[int, str] = {folder.id: folder.filename}

    with zipfile.ZipFile(temp_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        queue = [folder.id]
        while queue:
            curr_parent_id = queue.pop(0)
            curr_dir_path = folder_paths[curr_parent_id]

            # 1. Fetch child folders
            subfolders = session.exec(
                select(FileMeta).where(
                    FileMeta.parent_id == curr_parent_id,
                    FileMeta.is_folder == True,
                    FileMeta.is_deleted == False,
                )
            ).all()
            for sf in subfolders:
                rel_path = f"{curr_dir_path}/{sf.filename}"
                folder_paths[sf.id] = rel_path
                queue.append(sf.id)
                # Store folder directory marker
                zf.writestr(f"{rel_path}/", "")

            # 2. Fetch child files
            child_files = session.exec(
                select(FileMeta).where(
                    FileMeta.parent_id == curr_parent_id,
                    FileMeta.is_folder == False,
                    FileMeta.is_deleted == False,
                )
            ).all()
            for cf in child_files:
                if cf.storage_path and os.path.exists(cf.storage_path):
                    rel_file_path = f"{curr_dir_path}/{cf.filename}"
                    zf.write(cf.storage_path, arcname=rel_file_path)

    return temp_zip_path


def soft_delete(session: Session, owner: User, file_id: int) -> bool:
    """Moves a file or folder (and its recursive contents) to the recycle bin."""
    item = get_owned_file(session, owner, file_id)
    if not item:
        return False

    now = datetime.now(timezone.utc)
    target_ids = [file_id]

    if item.is_folder:
        queue = [file_id]
        while queue:
            curr_id = queue.pop(0)
            children = session.exec(
                select(FileMeta.id).where(
                    FileMeta.owner_id == owner.id,
                    FileMeta.parent_id == curr_id,
                    FileMeta.is_deleted == False,
                )
            ).all()
            target_ids.extend(children)
            queue.extend(children)

    for target_id in target_ids:
        target = session.get(FileMeta, target_id)
        if target:
            target.is_deleted = True
            target.deleted_at = now
            session.add(target)

    session.commit()
    return True


def purge_expired_bin(session: Session) -> int:
    """Automatically and permanently deletes items in the bin older than 30 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    expired_items = session.exec(
        select(FileMeta.id).where(
            FileMeta.is_deleted == True,
            FileMeta.deleted_at != None,
            FileMeta.deleted_at <= cutoff,
        )
    ).all()

    count = 0
    for target_id in expired_items:
        if session.get(FileMeta, target_id):
            hard_delete(session, None, target_id)
            count += 1
    return count


def list_bin(session: Session, owner: User) -> list[BinItemRead]:
    """Lists deleted items in the bin with remaining retention days."""
    purge_expired_bin(session)
    now = datetime.now(timezone.utc)

    deleted_items = session.exec(
        select(FileMeta)
        .where(
            FileMeta.owner_id == owner.id,
            FileMeta.is_deleted == True,
        )
        .order_by(col(FileMeta.deleted_at).desc())
    ).all()

    deleted_ids = {item.id for item in deleted_items}
    # Show only root-level deleted items (parent not also deleted)
    root_deleted = [
        item for item in deleted_items
        if item.parent_id is None or item.parent_id not in deleted_ids
    ]

    results: list[BinItemRead] = []
    for item in root_deleted:
        days_left = 30
        if item.deleted_at:
            delta_days = (now - item.deleted_at).total_seconds() / 86400.0
            days_left = max(0, 30 - int(delta_days))

        results.append(
            BinItemRead(
                id=item.id,
                filename=item.filename,
                file_size=item.file_size,
                mime_type=item.mime_type,
                parent_id=item.parent_id,
                is_folder=item.is_folder,
                is_deleted=item.is_deleted,
                deleted_at=item.deleted_at,
                created_at=item.created_at,
                days_left=days_left,
            )
        )

    return results


def restore_from_bin(session: Session, owner: User, file_id: int) -> bool:
    """Restores an item from the bin back to its original parent (or root if parent was deleted)."""
    item = session.get(FileMeta, file_id)
    if not item or item.owner_id != owner.id or not item.is_deleted:
        return False

    # If original parent is deleted or no longer exists, restore to root
    if item.parent_id is not None:
        parent = session.get(FileMeta, item.parent_id)
        if not parent or parent.is_deleted:
            item.parent_id = None

    target_ids = [file_id]
    if item.is_folder:
        queue = [file_id]
        while queue:
            curr_id = queue.pop(0)
            children = session.exec(
                select(FileMeta.id).where(
                    FileMeta.owner_id == owner.id,
                    FileMeta.parent_id == curr_id,
                )
            ).all()
            target_ids.extend(children)
            queue.extend(children)

    for target_id in target_ids:
        target = session.get(FileMeta, target_id)
        if target:
            target.is_deleted = False
            target.deleted_at = None
            session.add(target)

    session.commit()
    return True


def hard_delete(session: Session, owner: Optional[User], file_id: int) -> bool:
    """Permanently deletes a file or recursively deletes a folder and all its contents."""
    file_meta = session.get(FileMeta, file_id)
    if not file_meta:
        return False
    if owner and file_meta.owner_id != owner.id:
        return False

    all_target_ids = [file_id]
    if file_meta.is_folder:
        queue = [file_id]
        while queue:
            current_id = queue.pop(0)
            children = session.exec(
                select(FileMeta.id).where(FileMeta.parent_id == current_id)
            ).all()
            all_target_ids.extend(children)
            queue.extend(children)

    # Delete deepest children first to satisfy foreign key constraints
    all_target_ids.reverse()

    conn = session.connection()

    for target_id in all_target_ids:
        target = session.get(FileMeta, target_id)
        if target:
            if not target.is_folder and target.storage_path and os.path.exists(target.storage_path):
                try:
                    os.remove(target.storage_path)
                except OSError:
                    pass

            stale_ids = conn.exec_driver_sql(
                "DELETE FROM filechunk WHERE file_id = ? RETURNING id", (target_id,)
            ).scalars().all()
            if stale_ids:
                conn.exec_driver_sql(
                    "DELETE FROM filechunk_vec WHERE rowid = ?", [(cid,) for cid in stale_ids]
                )

            conn.exec_driver_sql("DELETE FROM fileshare WHERE file_id = ?", (target_id,))
            conn.exec_driver_sql("DELETE FROM sharedlink WHERE file_id = ?", (target_id,))

            session.delete(target)
            session.flush()

    session.commit()
    return True


# Backward compatible alias for tests and existing code
def delete_file(session: Session, owner: Optional[User], file_id: int) -> bool:
    return hard_delete(session, owner, file_id)


def empty_bin(session: Session, owner: User) -> int:
    """Permanently deletes all items in the user's recycle bin."""
    purge_expired_bin(session)
    deleted_items = session.exec(
        select(FileMeta.id).where(
            FileMeta.owner_id == owner.id,
            FileMeta.is_deleted == True,
        )
    ).all()

    count = 0
    for target_id in deleted_items:
        if session.get(FileMeta, target_id):
            hard_delete(session, owner, target_id)
            count += 1
    return count


def get_user_storage(session: Session, user: User) -> dict:
    """Calculates active storage used, total storage, and file/folder counts for the user."""
    used_bytes = session.exec(
        select(func.coalesce(func.sum(FileMeta.file_size), 0)).where(
            FileMeta.owner_id == user.id,
            FileMeta.is_folder == False,
            FileMeta.is_deleted == False,
        )
    ).one()

    file_count = session.exec(
        select(func.count(FileMeta.id)).where(
            FileMeta.owner_id == user.id,
            FileMeta.is_folder == False,
            FileMeta.is_deleted == False,
        )
    ).one()

    folder_count = session.exec(
        select(func.count(FileMeta.id)).where(
            FileMeta.owner_id == user.id,
            FileMeta.is_folder == True,
            FileMeta.is_deleted == False,
        )
    ).one()

    try:
        disk = shutil.disk_usage(USER_FILES_DIR)
        total_bytes = disk.total
    except Exception:
        total_bytes = 50 * 1024 * 1024 * 1024

    return {
        "used_bytes": int(used_bytes),
        "total_bytes": int(total_bytes),
        "file_count": int(file_count),
        "folder_count": int(folder_count),
    }


def share_file_with_user(
    session: Session, owner: User, file_id: int, target_login: str, permission: str = "read"
) -> Optional[FileShare]:
    file_meta = get_owned_file(session, owner, file_id)
    if not file_meta:
        return None

    target_user = session.exec(select(User).where(User.login == target_login)).first()
    target_user_id = target_user.id if target_user else None

    existing = session.exec(
        select(FileShare).where(
            FileShare.file_id == file_id,
            (FileShare.shared_with_login == target_login)
            | (FileShare.shared_with_user_id == target_user_id if target_user_id else False),
        )
    ).first()

    if existing:
        existing.permission = permission
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    share = FileShare(
        file_id=file_id,
        shared_with_user_id=target_user_id,
        shared_with_login=target_login,
        permission=permission,
    )
    session.add(share)
    session.commit()
    session.refresh(share)
    return share
