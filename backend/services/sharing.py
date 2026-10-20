from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlmodel import Session, select
from models import FileMeta, SharedLink


def create_link(session: Session, file_meta: FileMeta, expires_in_hours: int) -> SharedLink:
    link = SharedLink(file_id=file_meta.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_in_hours))
    session.add(link)
    session.commit()
    session.refresh(link)
    return link


def get_active_link(session: Session, token: str) -> Optional[SharedLink]:
    link = session.exec(select(SharedLink).where(SharedLink.token == token)).first()
    if not link or (link.expires_at and datetime.now(timezone.utc) > link.expires_at):
        return None
    return link


def record_download(session: Session, link: SharedLink):
    link.download_count += 1
    session.add(link)
    session.commit()
