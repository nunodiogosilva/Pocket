"""Item (file/folder) business logic: tree ops, uploads, trash, storage, ACL.

This is the domain service behind the ``items`` endpoints. It owns tree
traversal, parent/path validation, folder-size aggregation, quota/storage stats,
recycle-bin lifecycle, and explicit sharing with a Tailnet user.
"""

import os
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import UploadFile
from sqlmodel import Session, col, func, select

from app.config import settings
from app.core import storage_engine
from app.models.item import Item
from app.models.permission import FileShare
from app.models.user import User
from app.schemas.item import (
    BinItemRead,
    DirectoryContent,
    ItemRead,
)
from app.schemas.permission import SharedDirectoryContent, SharedItemRead
from app.services import search_service as vec

_folder_lock = threading.Lock()
BIN_RETENTION_DAYS = 30


# --------------------------------------------------------------------------- #
# Read helpers
# --------------------------------------------------------------------------- #
def compute_folder_sizes(session: Session, folder_ids: list[int], include_deleted: bool = False) -> dict[int, int]:
    """Compute recursive total file sizes for the given folder IDs."""
    if not folder_ids:
        return {}

    query = select(Item.id, Item.parent_id, Item.file_size, Item.is_folder)
    if not include_deleted:
        query = query.where(Item.is_deleted == False)

    rows = session.exec(query).all()
    children_map: dict[int, list[int]] = {}
    size_map: dict[int, int] = {}
    is_folder_map: dict[int, bool] = {}

    for fid, pid, size, is_folder in rows:
        size_map[fid] = size or 0
        is_folder_map[fid] = bool(is_folder)
        if pid is not None:
            children_map.setdefault(pid, []).append(fid)

    def get_size(f_id: int) -> int:
        total = 0
        for child_id in children_map.get(f_id, []):
            if is_folder_map.get(child_id):
                total += get_size(child_id)
            else:
                total += size_map.get(child_id, 0)
        return total

    return {f_id: get_size(f_id) for f_id in folder_ids}


def list_directory(session: Session, owner: User, parent_id: Optional[int]) -> DirectoryContent:
    """Return a directory's folders and files, strictly separated."""
    folders = session.exec(
        select(Item)
        .where(
            Item.owner_id == owner.id,
            Item.parent_id == parent_id,
            Item.is_folder == True,
            Item.is_deleted == False,
        )
        .order_by(func.lower(Item.filename))
    ).all()
    files = session.exec(
        select(Item)
        .where(
            Item.owner_id == owner.id,
            Item.parent_id == parent_id,
            Item.is_folder == False,
            Item.is_deleted == False,
        )
        .order_by(func.lower(Item.filename))
    ).all()

    folder_sizes = compute_folder_sizes(session, [f.id for f in folders], include_deleted=False)
    folder_reads = [
        ItemRead.model_validate(f).model_copy(update={"file_size": folder_sizes.get(f.id, 0)})
        for f in folders
    ]
    file_reads = [ItemRead.model_validate(f) for f in files]
    return DirectoryContent(folders=folder_reads, files=file_reads)


def list_shared_with_me(session: Session, user: User, parent_id: Optional[int] = None) -> SharedDirectoryContent:
    """List items explicitly shared with this user, separated by type."""
    folders: list[SharedItemRead] = []
    files: list[SharedItemRead] = []

    if parent_id is not None:
        parent_item = get_accessible_item(session, user, parent_id)
        if not parent_item:
            return SharedDirectoryContent(folders=[], files=[])

        owner = session.get(User, parent_item.owner_id)
        owner_login = owner.login if owner else "unknown"
        owner_name = owner.name if owner else None

        items = session.exec(
            select(Item)
            .where(Item.parent_id == parent_id, Item.is_deleted == False)
            .order_by(func.lower(Item.filename))
        ).all()

        for item in items:
            base = ItemRead.model_validate(item).model_dump()
            shared_item = SharedItemRead(**base, shared_by=owner_login, shared_by_name=owner_name, permission="read")
            (folders if item.is_folder else files).append(shared_item)
    else:
        shares_rows = session.exec(
            select(FileShare, Item, User)
            .join(Item, FileShare.file_id == Item.id)
            .join(User, Item.owner_id == User.id)
            .where(
                (FileShare.shared_with_user_id == user.id) | (FileShare.shared_with_login == user.login),
                Item.is_deleted == False,
            )
            .order_by(func.lower(Item.filename))
        ).all()

        for share, item, owner in shares_rows:
            base = ItemRead.model_validate(item).model_dump()
            shared_item = SharedItemRead(**base, shared_by=owner.login, shared_by_name=owner.name, permission=share.permission)
            (folders if item.is_folder else files).append(shared_item)

    if folders:
        folder_sizes = compute_folder_sizes(session, [f.id for f in folders], include_deleted=False)
        for f in folders:
            f.file_size = folder_sizes.get(f.id, 0)

    return SharedDirectoryContent(folders=folders, files=files)


def list_items(
    session: Session, owner: User, parent_id: Optional[int], is_folder: Optional[bool] = None
) -> list[Item]:
    statement = select(Item).where(
        Item.owner_id == owner.id,
        Item.parent_id == parent_id,
        Item.is_deleted == False,
    )
    if is_folder is not None:
        statement = statement.where(Item.is_folder == is_folder)
    statement = statement.order_by(col(Item.is_folder).desc(), func.lower(Item.filename))
    return list(session.exec(statement).all())


def get_owned_item(session: Session, owner: User, item_id: int, include_deleted: bool = False) -> Optional[Item]:
    item = session.get(Item, item_id)
    if not item or item.owner_id != owner.id:
        return None
    if not include_deleted and item.is_deleted:
        return None
    return item


def get_accessible_item(session: Session, user: User, item_id: int, include_deleted: bool = False) -> Optional[Item]:
    item = session.get(Item, item_id)
    if not item:
        return None
    if not include_deleted and item.is_deleted:
        return None
    if item.owner_id == user.id:
        return item

    def has_share(shared_item_id: int) -> bool:
        return session.exec(
            select(FileShare).where(
                FileShare.file_id == shared_item_id,
                (FileShare.shared_with_user_id == user.id) | (FileShare.shared_with_login == user.login),
            )
        ).first() is not None

    if has_share(item_id):
        return item

    # Sharing a folder grants access to its descendants.
    ancestor_id = item.parent_id
    visited: set[int] = set()
    while ancestor_id is not None and ancestor_id not in visited:
        visited.add(ancestor_id)
        ancestor = session.get(Item, ancestor_id)
        if not ancestor or ancestor.is_deleted or not ancestor.is_folder:
            return None
        if has_share(ancestor.id):
            return item
        ancestor_id = ancestor.parent_id

    return None


# --------------------------------------------------------------------------- #
# Write helpers
# --------------------------------------------------------------------------- #
def _commit_with_retry(session: Session, obj) -> None:
    for attempt in range(5):
        try:
            session.commit()
            session.refresh(obj)
            break
        except Exception as e:
            if "locked" in str(e).lower() and attempt < 4:
                session.rollback()
                time.sleep(0.15 * (attempt + 1))
                session.add(obj)
            else:
                raise


def resolve_or_create_folder_path(
    session: Session, owner: User, folder_path: str, base_parent_id: Optional[int]
) -> Optional[int]:
    """Resolve or recursively create folders for a path relative to ``base_parent_id``."""
    normalized = folder_path.replace("\\", "/").strip("/")
    parts = [p.strip() for p in normalized.split("/") if p.strip() and p.strip() not in (".", "..")]
    if not parts:
        return base_parent_id

    with _folder_lock:
        current_parent_id = base_parent_id
        for part in parts:
            folder = session.exec(
                select(Item).where(
                    Item.owner_id == owner.id,
                    Item.parent_id == current_parent_id,
                    Item.filename == part,
                    Item.is_folder == True,
                    Item.is_deleted == False,
                )
            ).first()

            if not folder:
                folder = Item(
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
                _commit_with_retry(session, folder)

            current_parent_id = folder.id

        return current_parent_id


def create_folder(session: Session, owner: User, name: str, parent_id: Optional[int]) -> Item:
    """Create a new folder under ``parent_id`` (idempotent on duplicate names)."""
    clean_name = os.path.basename(name.strip().replace("\\", "/")) or "New Folder"

    with _folder_lock:
        existing = session.exec(
            select(Item).where(
                Item.owner_id == owner.id,
                Item.parent_id == parent_id,
                Item.filename == clean_name,
                Item.is_folder == True,
                Item.is_deleted == False,
            )
        ).first()
        if existing:
            return existing

        folder = Item(
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
        _commit_with_retry(session, folder)
        return folder


def save_upload(
    session: Session,
    owner: User,
    upload: UploadFile,
    parent_id: Optional[int],
    relative_path: Optional[str] = None,
) -> Item:
    """Save an uploaded file, creating nested folders when ``relative_path`` is given."""
    target_parent_id = parent_id
    filename = upload.filename or "untitled"

    if relative_path:
        normalized = relative_path.replace("\\", "/").strip("/")
        parts = [p.strip() for p in normalized.split("/") if p.strip() and p.strip() not in (".", "..")]
        if len(parts) > 1:
            folder_hierarchy = "/".join(parts[:-1])
            filename = parts[-1]
            target_parent_id = resolve_or_create_folder_path(session, owner, folder_hierarchy, parent_id)
        elif len(parts) == 1:
            filename = parts[0]

    clean_filename = os.path.basename(filename.replace("\\", "/")) or "untitled"
    file_path = storage_engine.allocate_storage_path(owner.id)
    storage_engine.stream_to_disk(upload.file, file_path)

    db_item = Item(
        filename=clean_filename,
        storage_path=file_path,
        file_size=os.path.getsize(file_path),
        mime_type=upload.content_type or "application/octet-stream",
        parent_id=target_parent_id,
        is_folder=False,
        is_deleted=False,
        owner_id=owner.id,
    )
    session.add(db_item)
    _commit_with_retry(session, db_item)
    return db_item


def rename_item(session: Session, owner: User, item_id: int, new_name: str, is_folder: Optional[bool] = None) -> Item:
    """Rename an owned item and guard against same-directory collisions."""
    clean_name = os.path.basename(new_name.strip().replace("\\", "/"))
    if not clean_name:
        raise ValueError("New name cannot be empty")

    item = get_owned_item(session, owner, item_id)
    if not item:
        raise ValueError("Item not found")
    if is_folder is not None and item.is_folder != is_folder:
        raise ValueError("Item type mismatch")

    collision = session.exec(
        select(Item).where(
            Item.owner_id == owner.id,
            Item.parent_id == item.parent_id,
            Item.filename == clean_name,
            Item.is_deleted == False,
            Item.id != item_id,
        )
    ).first()
    if collision:
        raise ValueError(f"An item named '{clean_name}' already exists in this directory")

    item.filename = clean_name
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def move_item(session: Session, owner: User, item_id: int, target_parent_id: Optional[int]) -> Item:
    """Move an owned item into another folder (or root) with cycle/collision guards."""
    item = get_owned_item(session, owner, item_id)
    if not item or item.is_deleted:
        raise ValueError("Item not found")

    if target_parent_id is not None:
        target = get_owned_item(session, owner, target_parent_id)
        if not target or target.is_deleted:
            raise ValueError("Destination folder not found")
        if not target.is_folder:
            raise ValueError("Destination must be a folder, cannot move into a file")

        if item.is_folder:
            if item.id == target_parent_id:
                raise ValueError("Cannot move a folder into itself")
            curr = target
            while curr is not None:
                if curr.id == item.id:
                    raise ValueError("Cannot move a folder into one of its subfolders")
                curr = session.get(Item, curr.parent_id) if curr.parent_id else None

    collision = session.exec(
        select(Item).where(
            Item.owner_id == owner.id,
            Item.parent_id == target_parent_id,
            Item.filename == item.filename,
            Item.is_deleted == False,
            Item.id != item_id,
        )
    ).first()
    if collision:
        raise ValueError(f"An item named '{item.filename}' already exists in destination folder")

    item.parent_id = target_parent_id
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


# --------------------------------------------------------------------------- #
# Archive / trash / storage / sharing
# --------------------------------------------------------------------------- #
def create_folder_zip(session: Session, user: User, folder_id: int) -> str:
    """Package a folder and all its contents recursively into a temp zip archive."""
    folder = get_accessible_item(session, user, folder_id)
    if not folder or not folder.is_folder:
        raise ValueError("Folder not found or inaccessible")

    folder_paths: dict[int, str] = {folder.id: folder.filename}
    entries: list[tuple[str, Optional[str]]] = []
    queue = [folder.id]
    while queue:
        curr_parent_id = queue.pop(0)
        curr_dir_path = folder_paths[curr_parent_id]

        subfolders = session.exec(
            select(Item).where(
                Item.parent_id == curr_parent_id, Item.is_folder == True, Item.is_deleted == False
            )
        ).all()
        for sf in subfolders:
            rel_path = f"{curr_dir_path}/{sf.filename}"
            folder_paths[sf.id] = rel_path
            queue.append(sf.id)
            entries.append((f"{rel_path}/", None))

        child_files = session.exec(
            select(Item).where(
                Item.parent_id == curr_parent_id, Item.is_folder == False, Item.is_deleted == False
            )
        ).all()
        for cf in child_files:
            if cf.storage_path and os.path.exists(cf.storage_path):
                entries.append((f"{curr_dir_path}/{cf.filename}", cf.storage_path))

    return storage_engine.create_folder_zip(entries, folder.filename)


def soft_delete(session: Session, owner: User, item_id: int) -> bool:
    """Move an item (and its recursive contents) to the recycle bin."""
    item = get_owned_item(session, owner, item_id)
    if not item:
        return False

    now = datetime.now(timezone.utc)
    target_ids = [item_id]

    if item.is_folder:
        queue = [item_id]
        while queue:
            curr_id = queue.pop(0)
            children = session.exec(
                select(Item.id).where(
                    Item.owner_id == owner.id, Item.parent_id == curr_id, Item.is_deleted == False
                )
            ).all()
            target_ids.extend(children)
            queue.extend(children)

    for target_id in target_ids:
        target = session.get(Item, target_id)
        if target:
            target.is_deleted = True
            target.deleted_at = now
            session.add(target)

    session.commit()
    return True


def purge_expired_bin(session: Session) -> int:
    """Permanently delete bin items older than the retention window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=BIN_RETENTION_DAYS)
    expired_items = session.exec(
        select(Item.id).where(
            Item.is_deleted == True,
            Item.deleted_at != None,
            Item.deleted_at <= cutoff,
        )
    ).all()

    count = 0
    for target_id in expired_items:
        if session.get(Item, target_id):
            hard_delete(session, None, target_id)
            count += 1
    return count


def list_bin(session: Session, owner: User) -> list[BinItemRead]:
    """List deleted items with the days remaining before permanent deletion."""
    purge_expired_bin(session)
    now = datetime.now(timezone.utc)

    deleted_items = session.exec(
        select(Item)
        .where(Item.owner_id == owner.id, Item.is_deleted == True)
        .order_by(col(Item.deleted_at).desc())
    ).all()

    deleted_ids = {item.id for item in deleted_items}
    root_deleted = [
        item for item in deleted_items
        if item.parent_id is None or item.parent_id not in deleted_ids
    ]

    folder_ids = [item.id for item in root_deleted if item.is_folder]
    folder_sizes = compute_folder_sizes(session, folder_ids, include_deleted=True) if folder_ids else {}

    results: list[BinItemRead] = []
    for item in root_deleted:
        days_left = BIN_RETENTION_DAYS
        if item.deleted_at:
            delta_days = (now - item.deleted_at).total_seconds() / 86400.0
            days_left = max(0, BIN_RETENTION_DAYS - int(delta_days))

        results.append(
            BinItemRead(
                id=item.id,
                filename=item.filename,
                file_size=folder_sizes.get(item.id, item.file_size) if item.is_folder else item.file_size,
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


def restore_from_bin(session: Session, owner: User, item_id: int) -> bool:
    """Restore an item (and children) from the bin to its original parent (or root)."""
    item = session.get(Item, item_id)
    if not item or item.owner_id != owner.id or not item.is_deleted:
        return False

    if item.parent_id is not None:
        parent = session.get(Item, item.parent_id)
        if not parent or parent.is_deleted:
            item.parent_id = None

    target_ids = [item_id]
    if item.is_folder:
        queue = [item_id]
        while queue:
            curr_id = queue.pop(0)
            children = session.exec(
                select(Item.id).where(Item.owner_id == owner.id, Item.parent_id == curr_id)
            ).all()
            target_ids.extend(children)
            queue.extend(children)

    for target_id in target_ids:
        target = session.get(Item, target_id)
        if target:
            target.is_deleted = False
            target.deleted_at = None
            session.add(target)

    session.commit()
    return True


def hard_delete(session: Session, owner: Optional[User], item_id: int) -> bool:
    """Permanently delete an item, its subtree, vectors, shares, and on-disk file."""
    item = session.get(Item, item_id)
    if not item:
        return False
    if owner and item.owner_id != owner.id:
        return False

    all_target_ids = [item_id]
    if item.is_folder:
        queue = [item_id]
        while queue:
            current_id = queue.pop(0)
            children = session.exec(select(Item.id).where(Item.parent_id == current_id)).all()
            all_target_ids.extend(children)
            queue.extend(children)

    # Delete deepest children first to satisfy foreign key constraints.
    all_target_ids.reverse()

    conn = session.connection()
    for target_id in all_target_ids:
        target = session.get(Item, target_id)
        if target:
            if not target.is_folder and target.storage_path and os.path.exists(target.storage_path):
                storage_engine.remove_path(target.storage_path)
            vec.delete_index_for(target_id)
            conn.exec_driver_sql("DELETE FROM fileshare WHERE file_id = ?", (target_id,))
            conn.exec_driver_sql("DELETE FROM sharedlink WHERE file_id = ?", (target_id,))
            session.delete(target)
            session.flush()

    session.commit()
    return True


def empty_bin(session: Session, owner: User) -> int:
    """Permanently delete all items in the user's recycle bin."""
    purge_expired_bin(session)
    deleted_items = session.exec(
        select(Item.id).where(Item.owner_id == owner.id, Item.is_deleted == True)
    ).all()

    count = 0
    for target_id in deleted_items:
        if session.get(Item, target_id):
            hard_delete(session, owner, target_id)
            count += 1
    return count


def get_user_storage(session: Session, user: User) -> dict:
    """Active storage used, total capacity, and file/folder counts for the user."""
    used_bytes = session.exec(
        select(func.coalesce(func.sum(Item.file_size), 0)).where(
            Item.owner_id == user.id, Item.is_folder == False, Item.is_deleted == False
        )
    ).one()

    file_count = session.exec(
        select(func.count(Item.id)).where(
            Item.owner_id == user.id, Item.is_folder == False, Item.is_deleted == False
        )
    ).one()

    folder_count = session.exec(
        select(func.count(Item.id)).where(
            Item.owner_id == user.id, Item.is_folder == True, Item.is_deleted == False
        )
    ).one()

    try:
        disk = shutil.disk_usage(settings.user_files_dir)
        total_bytes = disk.total
    except Exception:
        total_bytes = 50 * 1024 * 1024 * 1024

    return {
        "used_bytes": int(used_bytes),
        "total_bytes": int(total_bytes),
        "file_count": int(file_count),
        "folder_count": int(folder_count),
    }


def share_with_user(
    session: Session, owner: User, item_id: int, target_login: str, permission: str = "read"
) -> Optional[FileShare]:
    """Grant (or update) a Tailnet user read/write access to an item (an ACL entry)."""
    item = get_owned_item(session, owner, item_id)
    if not item:
        return None

    target_user = session.exec(select(User).where(User.login == target_login)).first()
    target_user_id = target_user.id if target_user else None

    existing = session.exec(
        select(FileShare).where(
            FileShare.file_id == item_id,
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
        file_id=item_id,
        shared_with_user_id=target_user_id,
        shared_with_login=target_login,
        permission=permission,
    )
    session.add(share)
    session.commit()
    session.refresh(share)
    return share


# Backward-compatible alias used by some tests.
def delete_file(session: Session, owner: Optional[User], item_id: int) -> bool:
    return hard_delete(session, owner, item_id)


__all__ = [
    "compute_folder_sizes",
    "list_directory",
    "list_shared_with_me",
    "list_items",
    "get_owned_item",
    "get_accessible_item",
    "resolve_or_create_folder_path",
    "create_folder",
    "save_upload",
    "rename_item",
    "move_item",
    "create_folder_zip",
    "soft_delete",
    "purge_expired_bin",
    "list_bin",
    "restore_from_bin",
    "hard_delete",
    "empty_bin",
    "get_user_storage",
    "share_with_user",
    "delete_file",
]
