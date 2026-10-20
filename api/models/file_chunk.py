from typing import Optional
from sqlmodel import SQLModel, Field


class FileChunk(SQLModel, table=True):
    """A piece of a file's searchable text; its embedding lives in the sqlite-vec table under the same id."""

    id: Optional[int] = Field(default=None, primary_key=True)
    file_id: int = Field(foreign_key="filemeta.id", index=True)
    chunk_index: int
    text: str
