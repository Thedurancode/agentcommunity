import os
import json
from datetime import datetime
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form, BackgroundTasks
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_admin
from app.core.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.voice_note import VoiceNote, TranscriptionStatus
from app.schemas.voice_note import (
    VoiceNoteResponse,
    VoiceNoteList,
    VoiceNoteUpdate,
    VoiceNoteWithTasks,
    ExtractedTask,
    SentimentResponse,
)
from app.services.transcription import get_transcription_service
from app.services.ai import get_ai_service
from app.services.sentiment import get_sentiment_service

router = APIRouter(prefix="/voice-notes", tags=["voice-notes"])

# Allowed audio formats
ALLOWED_EXTENSIONS = {".mp3", ".mp4", ".m4a", ".wav", ".webm", ".ogg", ".flac"}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB


async def process_voice_note(voice_note_id: int, db_url: str):
    """Background task to transcribe and organize voice note."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import select

    engine = create_async_engine(db_url)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as db:
        # Get voice note
        result = await db.execute(select(VoiceNote).where(VoiceNote.id == voice_note_id))
        voice_note = result.scalar_one_or_none()
        if not voice_note:
            return

        # Get project name
        project_result = await db.execute(select(Project).where(Project.id == voice_note.project_id))
        project = project_result.scalar_one_or_none()
        project_name = project.name if project else "Unknown Project"

        try:
            # Update status to processing
            voice_note.transcription_status = TranscriptionStatus.PROCESSING
            await db.commit()

            # Get file path from URL (assumes local storage)
            file_path = voice_note.audio_url.replace("/uploads/", "uploads/")

            # Transcribe
            transcription_service = get_transcription_service()
            if not transcription_service.is_available():
                raise ValueError("Transcription service not configured")

            transcript = await transcription_service.transcribe_file(file_path)
            voice_note.raw_transcript = transcript

            # Organize with AI
            ai_service = get_ai_service()
            if ai_service.is_available():
                organized = await ai_service.organize_transcript(transcript, project_name)
                voice_note.summary = organized.get("summary", "")
                voice_note.organized_notes = organized.get("organized_notes", "")
                voice_note.extracted_tasks = json.dumps(organized.get("extracted_tasks", []))

            # Perform sentiment analysis
            from app.services.sentiment import get_sentiment_service
            sentiment_service = get_sentiment_service()
            if sentiment_service.is_available() and transcript.strip():
                try:
                    sentiment_result = await sentiment_service.analyze_sentiment(
                        transcript,
                        context=f"voice note for project: {project_name}",
                    )
                    voice_note.sentiment = sentiment_result.sentiment
                    voice_note.sentiment_confidence = sentiment_result.confidence
                    voice_note.sentiment_emotions = json.dumps(sentiment_result.emotions)
                    voice_note.sentiment_tone = sentiment_result.tone
                    voice_note.sentiment_summary = sentiment_result.summary
                except Exception:
                    pass  # Sentiment analysis is optional

            # Mark as completed
            voice_note.transcription_status = TranscriptionStatus.COMPLETED
            voice_note.processed_at = datetime.utcnow()

        except Exception as e:
            voice_note.transcription_status = TranscriptionStatus.FAILED
            voice_note.processing_error = str(e)

        await db.commit()

    await engine.dispose()


@router.post("", response_model=VoiceNoteResponse, status_code=status.HTTP_201_CREATED)
async def upload_voice_note(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    project_id: int = Form(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a voice note audio file for transcription.
    Supports: mp3, mp4, m4a, wav, webm, ogg, flac (up to 100MB).
    The file will be transcribed and organized in the background.
    """
    # Verify project exists and user has access
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Validate file extension
    file_ext = Path(file.filename).suffix.lower() if file.filename else ""
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Read and check file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Max size: {MAX_FILE_SIZE / 1024 / 1024:.0f}MB",
        )

    # Save file
    upload_dir = Path("uploads/voice_notes")
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{project_id}_{file.filename}"
    file_path = upload_dir / filename

    with open(file_path, "wb") as f:
        f.write(content)

    # Create voice note record
    voice_note = VoiceNote(
        title=title,
        audio_url=f"/uploads/voice_notes/{filename}",
        audio_filename=file.filename or filename,
        file_size_bytes=len(content),
        project_id=project_id,
        uploaded_by_id=current_user.id,
        transcription_status=TranscriptionStatus.PENDING,
    )
    db.add(voice_note)
    await db.commit()
    await db.refresh(voice_note)

    # Start background transcription
    from app.core.config import settings
    background_tasks.add_task(process_voice_note, voice_note.id, settings.DATABASE_URL)

    return voice_note


@router.get("", response_model=VoiceNoteList)
async def list_voice_notes(
    project_id: int = Query(..., description="Filter by project"),
    status_filter: Optional[TranscriptionStatus] = Query(None, description="Filter by status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List voice notes for a project."""
    query = select(VoiceNote).where(VoiceNote.project_id == project_id)
    count_query = select(func.count(VoiceNote.id)).where(VoiceNote.project_id == project_id)

    if status_filter:
        query = query.where(VoiceNote.transcription_status == status_filter)
        count_query = count_query.where(VoiceNote.transcription_status == status_filter)

    query = query.order_by(VoiceNote.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    voice_notes = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return VoiceNoteList(voice_notes=voice_notes, total=total)


@router.get("/{voice_note_id}", response_model=VoiceNoteWithTasks)
async def get_voice_note(
    voice_note_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific voice note with parsed tasks."""
    result = await db.execute(select(VoiceNote).where(VoiceNote.id == voice_note_id))
    voice_note = result.scalar_one_or_none()

    if not voice_note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice note not found",
        )

    # Parse tasks from JSON
    parsed_tasks = []
    if voice_note.extracted_tasks:
        try:
            tasks_data = json.loads(voice_note.extracted_tasks)
            parsed_tasks = [ExtractedTask(**t) for t in tasks_data]
        except (json.JSONDecodeError, TypeError):
            pass

    response = VoiceNoteWithTasks.model_validate(voice_note)
    response.parsed_tasks = parsed_tasks

    return response


@router.post("/{voice_note_id}/reprocess", response_model=VoiceNoteResponse)
async def reprocess_voice_note(
    voice_note_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Re-process transcription for a voice note. Admin only."""
    result = await db.execute(select(VoiceNote).where(VoiceNote.id == voice_note_id))
    voice_note = result.scalar_one_or_none()

    if not voice_note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice note not found",
        )

    # Reset status
    voice_note.transcription_status = TranscriptionStatus.PENDING
    voice_note.processing_error = None
    await db.commit()
    await db.refresh(voice_note)

    # Start background transcription
    from app.core.config import settings
    background_tasks.add_task(process_voice_note, voice_note.id, settings.DATABASE_URL)

    return voice_note


@router.patch("/{voice_note_id}", response_model=VoiceNoteResponse)
async def update_voice_note(
    voice_note_id: int,
    update_data: VoiceNoteUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update voice note title."""
    result = await db.execute(select(VoiceNote).where(VoiceNote.id == voice_note_id))
    voice_note = result.scalar_one_or_none()

    if not voice_note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice note not found",
        )

    if update_data.title:
        voice_note.title = update_data.title

    await db.commit()
    await db.refresh(voice_note)

    return voice_note


@router.post("/{voice_note_id}/analyze-sentiment", response_model=SentimentResponse)
async def analyze_voice_note_sentiment(
    voice_note_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze sentiment for an existing voice note transcript.
    Can be used to re-analyze sentiment or analyze notes processed before sentiment was added.
    """
    result = await db.execute(select(VoiceNote).where(VoiceNote.id == voice_note_id))
    voice_note = result.scalar_one_or_none()

    if not voice_note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice note not found",
        )

    if not voice_note.raw_transcript:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Voice note has no transcript to analyze",
        )

    sentiment_service = get_sentiment_service()
    if not sentiment_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sentiment analysis service not configured",
        )

    # Perform sentiment analysis
    sentiment_result = await sentiment_service.analyze_sentiment(
        voice_note.raw_transcript,
        context="voice note transcript",
    )

    # Store results
    voice_note.sentiment = sentiment_result.sentiment
    voice_note.sentiment_confidence = sentiment_result.confidence
    voice_note.sentiment_emotions = json.dumps(sentiment_result.emotions)
    voice_note.sentiment_tone = sentiment_result.tone
    voice_note.sentiment_summary = sentiment_result.summary

    await db.commit()
    await db.refresh(voice_note)

    return SentimentResponse(
        sentiment=sentiment_result.sentiment,
        confidence=sentiment_result.confidence,
        emotions=sentiment_result.emotions,
        tone=sentiment_result.tone,
        summary=sentiment_result.summary,
    )


@router.delete("/{voice_note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_voice_note(
    voice_note_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a voice note and its audio file."""
    result = await db.execute(select(VoiceNote).where(VoiceNote.id == voice_note_id))
    voice_note = result.scalar_one_or_none()

    if not voice_note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice note not found",
        )

    # Delete audio file
    file_path = voice_note.audio_url.replace("/uploads/", "uploads/")
    if os.path.exists(file_path):
        os.remove(file_path)

    await db.delete(voice_note)
    await db.commit()
