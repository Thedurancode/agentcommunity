from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.user import User
from app.models.note import Note
from app.models.team_member import TeamRole
from app.schemas.note import NoteCreate, NoteResponse, NoteUpdate, NoteWithCreator, NoteList
from app.api.deps import get_current_user
from app.api.routes.projects import check_project_access
from app.services.recap import get_recap_service


router = APIRouter(prefix="/projects/{project_id}/notes", tags=["notes"])


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    project_id: int,
    note_data: NoteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new note for a project."""
    await check_project_access(project_id, current_user, db)

    note = Note(
        title=note_data.title,
        content=note_data.content,
        project_id=project_id,
        created_by_id=current_user.id,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)

    # Update recap
    recap_service = get_recap_service(db)
    await recap_service.update_recent_notes(project_id)

    return note


@router.get("", response_model=NoteList)
async def list_notes(
    project_id: int,
    search: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all notes for a project."""
    await check_project_access(project_id, current_user, db)

    query = select(Note).where(Note.project_id == project_id)

    if search:
        query = query.where(
            Note.title.ilike(f"%{search}%") | Note.content.ilike(f"%{search}%")
        )

    query = query.order_by(Note.updated_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    notes = result.scalars().all()

    # Get total count
    count_query = select(Note).where(Note.project_id == project_id)
    if search:
        count_query = count_query.where(
            Note.title.ilike(f"%{search}%") | Note.content.ilike(f"%{search}%")
        )
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    return NoteList(notes=notes, total=total)


@router.get("/{note_id}", response_model=NoteWithCreator)
async def get_note(
    project_id: int,
    note_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific note."""
    await check_project_access(project_id, current_user, db)

    result = await db.execute(
        select(Note)
        .options(selectinload(Note.created_by))
        .where(Note.id == note_id, Note.project_id == project_id)
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    return note


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(
    project_id: int,
    note_id: int,
    note_data: NoteUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a note."""
    await check_project_access(project_id, current_user, db)

    result = await db.execute(
        select(Note).where(Note.id == note_id, Note.project_id == project_id)
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    update_data = note_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(note, field, value)

    await db.commit()
    await db.refresh(note)

    # Update recap
    recap_service = get_recap_service(db)
    await recap_service.update_recent_notes(project_id)

    return note


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    project_id: int,
    note_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a note."""
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER, TeamRole.DEVELOPER]
    )

    result = await db.execute(
        select(Note).where(Note.id == note_id, Note.project_id == project_id)
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    await db.delete(note)
    await db.commit()

    # Update recap
    recap_service = get_recap_service(db)
    await recap_service.update_recent_notes(project_id)

    return None
