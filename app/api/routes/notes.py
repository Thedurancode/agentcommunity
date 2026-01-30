from typing import Optional
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.user import User
from app.models.note import Note, NoteAudioTranscript, TranscriptStatus
from app.models.team_member import TeamRole
from app.schemas.note import (
    NoteCreate,
    NoteResponse,
    NoteUpdate,
    NoteWithCreator,
    NoteWithDetails,
    NoteList,
    NoteAudioTranscriptResponse,
    NoteAudioTranscriptList,
)
from app.api.deps import get_current_user
from app.api.routes.projects import check_project_access
from app.services.recap import get_recap_service
from app.services.transcription import get_transcription_service


router = APIRouter(prefix="/projects/{project_id}/notes", tags=["notes"])


# Audio upload settings
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".mp4", ".m4a", ".wav", ".webm", ".ogg", ".flac"}
MAX_AUDIO_FILE_SIZE = 100 * 1024 * 1024  # 100MB


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


@router.get("/{note_id}", response_model=NoteWithDetails)
async def get_note(
    project_id: int,
    note_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific note with audio transcripts."""
    await check_project_access(project_id, current_user, db)

    result = await db.execute(
        select(Note)
        .options(selectinload(Note.created_by), selectinload(Note.audio_transcripts))
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


# ============== NOTE AUDIO TRANSCRIPTS ==============

async def process_note_audio_transcript(transcript_id: int, db_url: str):
    """Background task to transcribe audio and update the transcript record."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import select

    engine = create_async_engine(db_url)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as db:
        # Get transcript record
        result = await db.execute(
            select(NoteAudioTranscript).where(NoteAudioTranscript.id == transcript_id)
        )
        transcript_record = result.scalar_one_or_none()
        if not transcript_record:
            return

        try:
            # Update status to processing
            transcript_record.status = TranscriptStatus.PROCESSING
            await db.commit()

            # Get file path from URL (assumes local storage)
            file_path = transcript_record.audio_url.replace("/uploads/", "uploads/")

            # Transcribe
            transcription_service = get_transcription_service()
            if not transcription_service.is_available():
                raise ValueError("Transcription service not configured")

            transcript_text = await transcription_service.transcribe_file(file_path)
            transcript_record.transcript = transcript_text

            # Mark as completed
            transcript_record.status = TranscriptStatus.COMPLETED
            transcript_record.processed_at = datetime.utcnow()

        except Exception as e:
            transcript_record.status = TranscriptStatus.FAILED
            transcript_record.processing_error = str(e)

        await db.commit()

    await engine.dispose()


@router.post("/{note_id}/audio", response_model=NoteAudioTranscriptResponse, status_code=status.HTTP_201_CREATED)
async def upload_note_audio(
    project_id: int,
    note_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload an audio file for a note.
    The audio will be automatically transcribed in the background.
    You can upload multiple audio files per note.

    Supports: mp3, mp4, m4a, wav, webm, ogg, flac (up to 100MB)
    """
    await check_project_access(project_id, current_user, db)

    # Verify note exists and belongs to project
    result = await db.execute(
        select(Note).where(Note.id == note_id, Note.project_id == project_id)
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    # Validate file extension
    file_ext = Path(file.filename).suffix.lower() if file.filename else ""
    if file_ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_AUDIO_EXTENSIONS)}",
        )

    # Read and check file size
    content = await file.read()
    if len(content) > MAX_AUDIO_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Max size: {MAX_AUDIO_FILE_SIZE / 1024 / 1024:.0f}MB",
        )

    # Save file
    upload_dir = Path("uploads/note_audio")
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{project_id}_{note_id}_{file.filename}"
    file_path = upload_dir / filename

    with open(file_path, "wb") as f:
        f.write(content)

    # Get current max display_order
    order_result = await db.execute(
        select(func.max(NoteAudioTranscript.display_order)).where(
            NoteAudioTranscript.note_id == note_id
        )
    )
    max_order = order_result.scalar() or 0

    # Create transcript record
    transcript_record = NoteAudioTranscript(
        note_id=note_id,
        title=title,
        audio_url=f"/uploads/note_audio/{filename}",
        audio_filename=file.filename or filename,
        file_size_bytes=len(content),
        status=TranscriptStatus.PENDING,
        display_order=max_order + 1,
    )
    db.add(transcript_record)
    await db.commit()
    await db.refresh(transcript_record)

    # Start background transcription
    from app.core.config import settings
    background_tasks.add_task(process_note_audio_transcript, transcript_record.id, settings.DATABASE_URL)

    return transcript_record


@router.get("/{note_id}/audio", response_model=NoteAudioTranscriptList)
async def list_note_audio_transcripts(
    project_id: int,
    note_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all audio transcripts for a note."""
    await check_project_access(project_id, current_user, db)

    # Verify note exists
    result = await db.execute(
        select(Note).where(Note.id == note_id, Note.project_id == project_id)
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    # Get transcripts
    transcripts_result = await db.execute(
        select(NoteAudioTranscript)
        .where(NoteAudioTranscript.note_id == note_id)
        .order_by(NoteAudioTranscript.display_order)
    )
    transcripts = transcripts_result.scalars().all()

    return NoteAudioTranscriptList(
        transcripts=[NoteAudioTranscriptResponse.model_validate(t) for t in transcripts],
        total=len(transcripts),
    )


@router.get("/{note_id}/audio/{transcript_id}", response_model=NoteAudioTranscriptResponse)
async def get_note_audio_transcript(
    project_id: int,
    note_id: int,
    transcript_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific audio transcript."""
    await check_project_access(project_id, current_user, db)

    result = await db.execute(
        select(NoteAudioTranscript).where(
            NoteAudioTranscript.id == transcript_id,
            NoteAudioTranscript.note_id == note_id,
        )
    )
    transcript = result.scalar_one_or_none()

    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio transcript not found",
        )

    return transcript


@router.post("/{note_id}/audio/{transcript_id}/reprocess", response_model=NoteAudioTranscriptResponse)
async def reprocess_note_audio(
    project_id: int,
    note_id: int,
    transcript_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-process transcription for an audio file."""
    await check_project_access(project_id, current_user, db)

    # Get transcript
    result = await db.execute(
        select(NoteAudioTranscript).where(
            NoteAudioTranscript.id == transcript_id,
            NoteAudioTranscript.note_id == note_id,
        )
    )
    transcript = result.scalar_one_or_none()

    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio transcript not found",
        )

    # Reset status
    transcript.status = TranscriptStatus.PENDING
    transcript.processing_error = None
    transcript.transcript = None
    await db.commit()
    await db.refresh(transcript)

    # Start background transcription
    from app.core.config import settings
    background_tasks.add_task(process_note_audio_transcript, transcript.id, settings.DATABASE_URL)

    return transcript


@router.delete("/{note_id}/audio/{transcript_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note_audio(
    project_id: int,
    note_id: int,
    transcript_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an audio transcript and its file."""
    import os

    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER, TeamRole.DEVELOPER]
    )

    # Get transcript
    result = await db.execute(
        select(NoteAudioTranscript).where(
            NoteAudioTranscript.id == transcript_id,
            NoteAudioTranscript.note_id == note_id,
        )
    )
    transcript = result.scalar_one_or_none()

    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio transcript not found",
        )

    # Delete audio file
    file_path = transcript.audio_url.replace("/uploads/", "uploads/")
    if os.path.exists(file_path):
        os.remove(file_path)

    await db.delete(transcript)
    await db.commit()
    return None


@router.get("/{note_id}/combined-transcript")
async def get_combined_note_transcript(
    project_id: int,
    note_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all completed transcripts combined into a single text.
    Useful for including in note content or generating summaries.
    """
    await check_project_access(project_id, current_user, db)

    # Verify note exists
    result = await db.execute(
        select(Note).where(Note.id == note_id, Note.project_id == project_id)
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    # Get completed transcripts
    transcripts_result = await db.execute(
        select(NoteAudioTranscript)
        .where(
            NoteAudioTranscript.note_id == note_id,
            NoteAudioTranscript.status == TranscriptStatus.COMPLETED,
        )
        .order_by(NoteAudioTranscript.display_order)
    )
    transcripts = transcripts_result.scalars().all()

    # Combine transcripts
    combined_parts = []
    for t in transcripts:
        if t.transcript:
            header = f"## {t.title}" if t.title else f"## Audio Note {t.display_order}"
            combined_parts.append(f"{header}\n\n{t.transcript}")

    combined_text = "\n\n---\n\n".join(combined_parts) if combined_parts else ""

    return {
        "note_id": note_id,
        "transcript_count": len(transcripts),
        "combined_transcript": combined_text,
    }
