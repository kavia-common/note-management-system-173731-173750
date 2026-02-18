from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import Boolean, Column, DateTime, MetaData, Table, Text, and_, delete, desc, func, insert, or_, select, update
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

metadata = MetaData()

# NOTE: We map to existing DB tables as discovered in notes_database:
# - notes(id uuid, title text, content text, is_pinned bool, is_favorited bool, created_at timestamptz, updated_at timestamptz, search_vector tsvector)
# - tags(id uuid, name text, created_at timestamptz)
# - note_tags(note_id uuid, tag_id uuid, created_at timestamptz)

notes = Table(
    "notes",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column("title", Text, nullable=False),
    Column("content", Text, nullable=False),
    Column("is_pinned", Boolean, nullable=False),
    Column("is_favorited", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

tags = Table(
    "tags",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column("name", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

note_tags = Table(
    "note_tags",
    metadata,
    Column("note_id", PG_UUID(as_uuid=True), primary_key=True),
    Column("tag_id", PG_UUID(as_uuid=True), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


@dataclass(frozen=True)
class NoteRow:
    id: UUID
    title: str
    content: str
    pinned: bool
    favorite: bool
    created_at: datetime
    updated_at: datetime
    tag_names: List[str]


async def _get_tag_names_for_notes(session: AsyncSession, note_ids: List[UUID]) -> dict[UUID, List[str]]:
    if not note_ids:
        return {}
    q = (
        select(note_tags.c.note_id, tags.c.name)
        .select_from(note_tags.join(tags, note_tags.c.tag_id == tags.c.id))
        .where(note_tags.c.note_id.in_(note_ids))
        .order_by(tags.c.name.asc())
    )
    res = await session.execute(q)
    mapping: dict[UUID, List[str]] = {}
    for note_id, name in res.all():
        mapping.setdefault(note_id, []).append(name)
    return mapping


async def list_notes(
    session: AsyncSession,
    q: Optional[str] = None,
    tag: Optional[str] = None,
    pinned: Optional[bool] = None,
    favorite: Optional[bool] = None,
) -> List[NoteRow]:
    """
    List/search notes.

    - q: full-text search if possible (search_vector exists), fallback to ILIKE.
    - tag: filter notes that have a tag name (case-insensitive).
    - pinned/favorite: boolean filters.
    """
    where_clauses = []
    if pinned is not None:
        where_clauses.append(notes.c.is_pinned.is_(pinned))
    if favorite is not None:
        where_clauses.append(notes.c.is_favorited.is_(favorite))

    base = select(notes).select_from(notes)

    if tag:
        # Join through note_tags/tags and filter by lower(tags.name) == lower(:tag)
        base = base.select_from(
            notes.join(note_tags, note_tags.c.note_id == notes.c.id).join(tags, tags.c.id == note_tags.c.tag_id)
        )
        where_clauses.append(func.lower(tags.c.name) == func.lower(tag))

    if q:
        # Use full-text search if search_vector index exists; keep it simple with websearch_to_tsquery.
        # If the DB doesn't support it, we still have ILIKE fallback.
        # We can safely OR them: vector matches OR title/content ILIKE.
        where_clauses.append(
            or_(
                func.to_tsvector("simple", func.coalesce(notes.c.title, "") + " " + func.coalesce(notes.c.content, "")).op(
                    "@@"
                )(func.websearch_to_tsquery("simple", q)),
                notes.c.title.ilike(f"%{q}%"),
                notes.c.content.ilike(f"%{q}%"),
            )
        )

    if where_clauses:
        base = base.where(and_(*where_clauses))

    # Order: pinned desc, favorited desc, created desc (nice UX)
    base = base.order_by(desc(notes.c.is_pinned), desc(notes.c.is_favorited), desc(notes.c.created_at))

    res = await session.execute(base)
    rows = res.mappings().all()

    note_ids = [r["id"] for r in rows]
    tags_map = await _get_tag_names_for_notes(session, note_ids)

    out: List[NoteRow] = []
    for r in rows:
        out.append(
            NoteRow(
                id=r["id"],
                title=r["title"],
                content=r["content"],
                pinned=bool(r["is_pinned"]),
                favorite=bool(r["is_favorited"]),
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                tag_names=tags_map.get(r["id"], []),
            )
        )
    return out


async def get_note(session: AsyncSession, note_id: UUID) -> Optional[NoteRow]:
    res = await session.execute(select(notes).where(notes.c.id == note_id))
    r = res.mappings().first()
    if not r:
        return None
    tags_map = await _get_tag_names_for_notes(session, [note_id])
    return NoteRow(
        id=r["id"],
        title=r["title"],
        content=r["content"],
        pinned=bool(r["is_pinned"]),
        favorite=bool(r["is_favorited"]),
        created_at=r["created_at"],
        updated_at=r["updated_at"],
        tag_names=tags_map.get(note_id, []),
    )


async def _upsert_tags(session: AsyncSession, tag_names: List[str]) -> List[UUID]:
    """
    Ensure tags exist (case-insensitive uniqueness enforced by DB).
    Returns list of tag ids in same order as provided tag_names (after normalization).
    """
    clean = []
    for t in tag_names:
        t2 = (t or "").strip()
        if t2:
            clean.append(t2)
    # Deduplicate while preserving order (case-insensitive)
    seen = set()
    uniq: List[str] = []
    for t in clean:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            uniq.append(t)

    if not uniq:
        return []

    ids: List[UUID] = []
    for name in uniq:
        # Insert if not exists, then select id
        await session.execute(
            insert(tags)
            .values(name=name)
            .on_conflict_do_nothing(index_elements=[func.lower(tags.c.name)])  # matches idx_tags_name_unique_ci
        )
        res = await session.execute(select(tags.c.id).where(func.lower(tags.c.name) == func.lower(name)))
        tag_id = res.scalar_one()
        ids.append(tag_id)
    return ids


async def _set_note_tags(session: AsyncSession, note_id: UUID, tag_names: List[str]) -> List[str]:
    """
    Replace all tags for a note with provided list.
    Returns normalized tag names (unique, trimmed) used.
    """
    clean = []
    for t in tag_names or []:
        t2 = (t or "").strip()
        if t2:
            clean.append(t2)

    # Deduplicate by lower name, preserve order
    seen = set()
    uniq: List[str] = []
    for t in clean:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(t)

    # Clear existing links
    await session.execute(delete(note_tags).where(note_tags.c.note_id == note_id))

    tag_ids = await _upsert_tags(session, uniq)
    for tag_id in tag_ids:
        await session.execute(insert(note_tags).values(note_id=note_id, tag_id=tag_id))
    return uniq


async def create_note(
    session: AsyncSession,
    title: str,
    content: str,
    tag_names: List[str],
    pinned: bool,
    favorite: bool,
) -> NoteRow:
    res = await session.execute(
        insert(notes)
        .values(
            title=title,
            content=content,
            is_pinned=pinned,
            is_favorited=favorite,
        )
        .returning(
            notes.c.id,
            notes.c.title,
            notes.c.content,
            notes.c.is_pinned,
            notes.c.is_favorited,
            notes.c.created_at,
            notes.c.updated_at,
        )
    )
    r = res.mappings().one()
    note_id = r["id"]

    normalized_tags = await _set_note_tags(session, note_id, tag_names)

    return NoteRow(
        id=note_id,
        title=r["title"],
        content=r["content"],
        pinned=bool(r["is_pinned"]),
        favorite=bool(r["is_favorited"]),
        created_at=r["created_at"],
        updated_at=r["updated_at"],
        tag_names=normalized_tags,
    )


async def update_note(
    session: AsyncSession,
    note_id: UUID,
    title: Optional[str],
    content: Optional[str],
    tag_names: Optional[List[str]],
    pinned: Optional[bool],
    favorite: Optional[bool],
) -> Optional[NoteRow]:
    values = {}
    if title is not None:
        values["title"] = title
    if content is not None:
        values["content"] = content
    if pinned is not None:
        values["is_pinned"] = pinned
    if favorite is not None:
        values["is_favorited"] = favorite

    if values:
        res = await session.execute(
            update(notes)
            .where(notes.c.id == note_id)
            .values(**values)
            .returning(
                notes.c.id,
                notes.c.title,
                notes.c.content,
                notes.c.is_pinned,
                notes.c.is_favorited,
                notes.c.created_at,
                notes.c.updated_at,
            )
        )
        updated = res.mappings().first()
        if not updated:
            return None
    else:
        # Ensure note exists
        res = await session.execute(select(notes).where(notes.c.id == note_id))
        updated = res.mappings().first()
        if not updated:
            return None

    normalized_tags: List[str]
    if tag_names is not None:
        normalized_tags = await _set_note_tags(session, note_id, tag_names)
    else:
        tags_map = await _get_tag_names_for_notes(session, [note_id])
        normalized_tags = tags_map.get(note_id, [])

    return NoteRow(
        id=updated["id"],
        title=updated["title"],
        content=updated["content"],
        pinned=bool(updated["is_pinned"]),
        favorite=bool(updated["is_favorited"]),
        created_at=updated["created_at"],
        updated_at=updated["updated_at"],
        tag_names=normalized_tags,
    )


async def delete_note(session: AsyncSession, note_id: UUID) -> bool:
    res = await session.execute(delete(notes).where(notes.c.id == note_id).returning(notes.c.id))
    deleted_id = res.scalar()
    return deleted_id is not None


async def set_pinned(session: AsyncSession, note_id: UUID, pinned: bool) -> Optional[NoteRow]:
    return await update_note(session, note_id=note_id, title=None, content=None, tag_names=None, pinned=pinned, favorite=None)


async def set_favorite(session: AsyncSession, note_id: UUID, favorite: bool) -> Optional[NoteRow]:
    return await update_note(
        session, note_id=note_id, title=None, content=None, tag_names=None, pinned=None, favorite=favorite
    )
