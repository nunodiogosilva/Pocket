from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from dependencies import get_current_user, get_db
from models import User
from schemas import BinItemRead
from services import storage

router = APIRouter(prefix="/api/bin", tags=["bin"])


@router.get("", response_model=list[BinItemRead])
def get_bin_items(
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Lists items in the user's recycle bin along with days remaining before permanent deletion."""
    return storage.list_bin(session, user)


@router.post("/{item_id}/restore")
def restore_item(
    item_id: int,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Restores an item (and its children if folder) from the recycle bin."""
    success = storage.restore_from_bin(session, user, item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Item not found in bin or permission denied")
    return {"status": "success", "id": item_id}


@router.delete("/{item_id}")
def permanently_delete_item(
    item_id: int,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Permanently deletes an item from disk and database."""
    success = storage.hard_delete(session, user, item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Item not found or permission denied")
    return {"status": "success", "id": item_id}


@router.delete("")
def empty_bin(
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Empties all items currently in the user's recycle bin."""
    count = storage.empty_bin(session, user)
    return {"status": "success", "deleted_count": count}
