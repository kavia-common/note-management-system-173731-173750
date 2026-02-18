from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class NoteBase(BaseModel):
    """Shared note fields."""

    title: str = Field(..., description="Note title.", max_length=500)
    content: str = Field(..., description="Note content/body.")
    tags: List[str] = Field(default_factory=list, description="List of tag names attached to the note.")
    pinned: bool = Field(default=False, description="Whether the note is pinned.")
    favorite: bool = Field(default=False, description="Whether the note is favorited.")


class NoteCreate(NoteBase):
    """Create payload for a note."""


class NoteUpdate(BaseModel):
    """Update payload for a note. All fields are optional; absent fields are not modified."""

    title: Optional[str] = Field(None, description="Note title.", max_length=500)
    content: Optional[str] = Field(None, description="Note content/body.")
    tags: Optional[List[str]] = Field(None, description="List of tag names attached to the note.")
    pinned: Optional[bool] = Field(None, description="Whether the note is pinned.")
    favorite: Optional[bool] = Field(None, description="Whether the note is favorited.")


class NoteOut(BaseModel):
    """Serialized note returned to the frontend."""

    id: UUID = Field(..., description="Note id (UUID).")
    title: str = Field(..., description="Note title.")
    content: str = Field(..., description="Note content/body.")
    tags: List[str] = Field(default_factory=list, description="List of tag names attached to the note.")
    pinned: bool = Field(..., description="Whether the note is pinned.")
    favorite: bool = Field(..., description="Whether the note is favorited.")
    createdAt: datetime = Field(..., description="Creation timestamp (UTC).")
    updatedAt: datetime = Field(..., description="Last update timestamp (UTC).")


class TogglePinnedIn(BaseModel):
    """Payload to set pinned status."""

    pinned: bool = Field(..., description="Desired pinned state.")


class ToggleFavoriteIn(BaseModel):
    """Payload to set favorite status."""

    favorite: bool = Field(..., description="Desired favorite state.")
