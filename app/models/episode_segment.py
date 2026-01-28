from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.episode import Episode


class SegmentType(str, Enum):
    INTRO = "intro"
    PROBLEM_REVEAL = "problem_reveal"
    TEAM_INTRO = "team_intro"
    CHALLENGE = "challenge"
    SOLUTION_DESIGN = "solution_design"
    BUILD_MONTAGE = "build_montage"
    TRANSFORMATION = "transformation"
    REVEAL = "reveal"
    OUTRO = "outro"
    COMMERCIAL_BREAK = "commercial_break"


class EpisodeSegment(Base):
    __tablename__ = "episode_segments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    episode_id: Mapped[int] = mapped_column(Integer, ForeignKey("episodes.id", ondelete="CASCADE"))

    # Segment info
    segment_number: Mapped[int] = mapped_column(Integer)
    segment_type: Mapped[SegmentType] = mapped_column(SQLEnum(SegmentType))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timing (in seconds)
    start_time: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=120)  # 2 min default

    # Content hints for production
    talking_points: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    visual_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    music_cue: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    episode: Mapped["Episode"] = relationship("Episode", back_populates="segments")
