from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel

from app.models.note import TranscriptStatus
from app.schemas.user import UserResponse


# Note Audio Transcript Schemas
class NoteAudioTranscriptResponse(BaseModel):
    """Response for note audio transcript."""
    id: int
    note_id: int
    title: Optional[str] = None
    audio_url: str
    audio_filename: str
    duration_seconds: Optional[float] = None
    file_size_bytes: Optional[int] = None
    status: TranscriptStatus
    transcript: Optional[str] = None
    processing_error: Optional[str] = None
    display_order: int
    created_at: datetime
    processed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class NoteAudioTranscriptList(BaseModel):
    """List of audio transcripts."""
    transcripts: List[NoteAudioTranscriptResponse]
    total: int


class NoteBase(BaseModel):
    title: str
    content: Optional[str] = None


class NoteCreate(NoteBase):
    pass


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


class NoteResponse(NoteBase):
    id: int
    project_id: int
    created_by_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NoteWithCreator(NoteResponse):
    created_by: Optional[UserResponse] = None


class NoteWithDetails(NoteWithCreator):
    """Note with all details including audio transcripts."""
    audio_transcripts: List[NoteAudioTranscriptResponse] = []


class NoteList(BaseModel):
    notes: List[NoteResponse]
    total: int
