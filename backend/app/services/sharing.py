"""Public shared-link lifecycle (Tailscale Funnel downloads)."""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session, select

from app.models.item import Item
from app.models.permission import SharedLink
from app.models.user import User
from app.services import item_service


def create_link(session: Session, item: Item, expires_in_hours: int) -> SharedLink:
    link = SharedLink(file_id=item.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_in_hours))
    session.add(link)
    session.commit()
    session.refresh(link)
    return link


def get_active_share_link(session: Session, token: str) -> Optional[SharedLink]:
    link = session.exec(select(SharedLink).where(SharedLink.token == token)).first()
    if not link or (link.expires_at and datetime.now(timezone.utc) > link.expires_at):
        return None
    return link


def get_shared_item(session: Session, link: SharedLink) -> Optional[Item]:
    item = session.get(Item, link.file_id)
    return item if item and not item.is_deleted else None


def record_download(session: Session, link: SharedLink) -> None:
    link.download_count += 1
    session.add(link)
    session.commit()


def get_item_owner(session: Session, item: Item) -> Optional[User]:
    return session.get(User, item.owner_id)


def create_shared_folder_archive(session: Session, owner: User, folder_id: int) -> str:
    return item_service.create_folder_zip(session, owner, folder_id)


def get_file_download_path(item: Item) -> Optional[str]:
    if item.storage_path and os.path.exists(item.storage_path):
        return item.storage_path
    return None


__all__ = [
    "create_link",
    "get_active_share_link",
    "get_shared_item",
    "record_download",
    "get_item_owner",
    "create_shared_folder_archive",
    "get_file_download_path",
]
