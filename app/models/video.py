from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # File info
    file_path: Mapped[str] = mapped_column(String(500))
    file_name: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)  # in bytes
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # in seconds

    # Thumbnail
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # External video URL (for YouTube, Vimeo, etc.)
    external_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"))
    uploaded_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="videos")
    uploaded_by: Mapped[Optional["User"]] = relationship("User")
