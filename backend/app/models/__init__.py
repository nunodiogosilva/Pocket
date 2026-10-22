"""Register all ORM tables by importing their domain modules.

Importing this package ensures ``SQLModel.metadata`` is fully populated before
``create_all`` runs (database bootstrap and test fixtures rely on this).
"""

from app.models.item import FileChunk, Item
from app.models.permission import FileShare, SharedLink
from app.models.user import User

# Backward-compatible alias: the old codebase referred to the tree node as FileMeta.
FileMeta = Item

__all__ = ["User", "Item", "FileMeta", "FileChunk", "FileShare", "SharedLink"]
