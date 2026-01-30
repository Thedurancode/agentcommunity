from datetime import datetime
from enum import Enum
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Boolean, Enum as SQLEnum, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class TranscriptStatus(str, Enum):
    """Audio transcript processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"))
    created_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="notes")
    created_by: Mapped[Optional["User"]] = relationship("User")
    audio_transcripts: Mapped[List["NoteAudioTranscript"]] = relationship(
        "NoteAudioTranscript", back_populates="note", cascade="all, delete-orphan"
    )


class NoteAudioTranscript(Base):
    """Audio transcripts for notes - supports multiple audio recordings."""
    __tablename__ = "note_audio_transcripts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    note_id: Mapped[int] = mapped_column(Integer, ForeignKey("notes.id"))

    # Audio file info
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    audio_url: Mapped[str] = mapped_column(String(500))
    audio_filename: Mapped[str] = mapped_column(String(255))
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Transcription
    status: Mapped[TranscriptStatus] = mapped_column(
        SQLEnum(TranscriptStatus), default=TranscriptStatus.PENDING
    )
    transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processing_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Ordering
    display_order: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    note: Mapped["Note"] = relationship("Note", back_populates="audio_transcripts")
