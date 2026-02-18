from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.db import get_session
from src.api.models import NoteCreate, NoteOut, NoteUpdate, ToggleFavoriteIn, TogglePinnedIn
from src.api.repository import create_note, delete_note, list_notes, set_favorite, set_pinned, update_note

router = APIRouter(prefix="/notes", tags=["notes"])


def _row_to_out(row) -> NoteOut:
    return NoteOut(
        id=row.id,
        title=row.title,
        content=row.content,
        tags=row.tag_names,
        pinned=row.pinned,
        favorite=row.favorite,
        createdAt=row.created_at,
        updatedAt=row.updated_at,
    )


@router.get(
    "",
    response_model=List[NoteOut],
    summary="List/search notes",
    description="List notes with optional search query and filters (tag, pinned, favorite).",
    operation_id="listNotes",
)
async def api_list_notes(
    q: Optional[str] = Query(None, description="Search query (full-text)."),
    tag: Optional[str] = Query(None, description="Filter by tag name (case-insensitive)."),
    pinned: Optional[bool] = Query(None, description="Filter by pinned status."),
    favorite: Optional[bool] = Query(None, description="Filter by favorite status."),
    session: AsyncSession = Depends(get_session),
) -> List[NoteOut]:
    rows = await list_notes(session=session, q=q, tag=tag, pinned=pinned, favorite=favorite)
    return [_row_to_out(r) for r in rows]


@router.post(
    "",
    response_model=NoteOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create note",
    description="Create a new note with optional tags and pinned/favorite flags.",
    operation_id="createNote",
)
async def api_create_note(payload: NoteCreate, session: AsyncSession = Depends(get_session)) -> NoteOut:
    row = await create_note(
        session=session,
        title=payload.title,
        content=payload.content,
        tag_names=payload.tags,
        pinned=payload.pinned,
        favorite=payload.favorite,
    )
    await session.commit()
    return _row_to_out(row)


@router.put(
    "/{id}",
    response_model=NoteOut,
    summary="Update note",
    description="Update an existing note by id. Fields omitted from payload are not modified.",
    operation_id="updateNote",
)
async def api_update_note(id: UUID, payload: NoteUpdate, session: AsyncSession = Depends(get_session)) -> NoteOut:
    row = await update_note(
        session=session,
        note_id=id,
        title=payload.title,
        content=payload.content,
        tag_names=payload.tags,
        pinned=payload.pinned,
        favorite=payload.favorite,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    await session.commit()
    return _row_to_out(row)


@router.delete(
    "/{id}",
    status_code=status.HTTP_200_OK,
    summary="Delete note",
    description="Delete a note by id.",
    operation_id="deleteNote",
)
async def api_delete_note(id: UUID, session: AsyncSession = Depends(get_session)) -> dict:
    ok = await delete_note(session=session, note_id=id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    await session.commit()
    return {"ok": True}


@router.post(
    "/{id}/pin",
    response_model=NoteOut,
    summary="Set pinned",
    description="Set pinned status for a note.",
    operation_id="togglePinned",
)
async def api_toggle_pinned(id: UUID, payload: TogglePinnedIn, session: AsyncSession = Depends(get_session)) -> NoteOut:
    row = await set_pinned(session=session, note_id=id, pinned=payload.pinned)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    await session.commit()
    return _row_to_out(row)


@router.post(
    "/{id}/favorite",
    response_model=NoteOut,
    summary="Set favorite",
    description="Set favorite status for a note.",
    operation_id="toggleFavorite",
)
async def api_toggle_favorite(
    id: UUID, payload: ToggleFavoriteIn, session: AsyncSession = Depends(get_session)
) -> NoteOut:
    row = await set_favorite(session=session, note_id=id, favorite=payload.favorite)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    await session.commit()
    return _row_to_out(row)
