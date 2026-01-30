from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Enum as SQLEnum, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class TranscriptionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class VoiceNote(Base):
    __tablename__ = "voice_notes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255))

    # Audio file info
    audio_url: Mapped[str] = mapped_column(String(500))
    audio_filename: Mapped[str] = mapped_column(String(255))
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Transcription
    transcription_status: Mapped[TranscriptionStatus] = mapped_column(
        SQLEnum(TranscriptionStatus), default=TranscriptionStatus.PENDING
    )
    raw_transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # AI-organized content
    organized_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Markdown formatted
    extracted_tasks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of tasks
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Sentiment analysis
    sentiment: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # positive, negative, neutral, mixed
    sentiment_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sentiment_emotions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of emotions
    sentiment_tone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sentiment_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Processing info
    processing_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"))
    uploaded_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="voice_notes")
    uploaded_by: Mapped["User"] = relationship("User")
