from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

from app.models.voice_note import TranscriptionStatus


class ExtractedTask(BaseModel):
    title: str
    description: str
    priority: str  # high, medium, low


class VoiceNoteBase(BaseModel):
    title: str


class VoiceNoteCreate(VoiceNoteBase):
    project_id: int


class VoiceNoteUpdate(BaseModel):
    title: Optional[str] = None


class VoiceNoteResponse(VoiceNoteBase):
    id: int
    audio_url: str
    audio_filename: str
    duration_seconds: Optional[float] = None
    file_size_bytes: Optional[int] = None
    transcription_status: TranscriptionStatus
    raw_transcript: Optional[str] = None
    organized_notes: Optional[str] = None
    extracted_tasks: Optional[str] = None  # JSON string
    summary: Optional[str] = None
    processing_error: Optional[str] = None
    processed_at: Optional[datetime] = None
    project_id: int
    uploaded_by_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VoiceNoteList(BaseModel):
    voice_notes: List[VoiceNoteResponse]
    total: int


class VoiceNoteWithTasks(VoiceNoteResponse):
    """Response that includes parsed tasks as a list"""
    parsed_tasks: List[ExtractedTask] = []


class TranscriptionRequest(BaseModel):
    """Request to re-process transcription"""
    language: Optional[str] = None  # e.g., 'en', 'es'
