from datetime import datetime
from enum import Enum
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Boolean, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.project import Project


class DeveloperStatus(str, Enum):
    """Developer availability status."""
    AVAILABLE = "available"
    BUSY = "busy"
    OPEN_TO_WORK = "open_to_work"
    HIRING = "hiring"
    NOT_AVAILABLE = "not_available"


class DeveloperProfile(Base):
    """
    Extended developer profile for the community feed.
    One-to-one relationship with User.
    """
    __tablename__ = "developer_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True)

    # Profile basics
    headline: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # e.g., "Full Stack Developer"
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Status
    status: Mapped[DeveloperStatus] = mapped_column(
        SQLEnum(DeveloperStatus), default=DeveloperStatus.AVAILABLE
    )
    status_message: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Skills and expertise (JSON array stored as text)
    skills: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array: ["Python", "React", "AWS"]
    expertise_areas: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON: ["Backend", "DevOps"]

    # Social links
    website_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    twitter_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    youtube_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    twitch_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Community stats (can be updated periodically)
    projects_count: Mapped[int] = mapped_column(Integer, default=0)
    contributions_count: Mapped[int] = mapped_column(Integer, default=0)
    followers_count: Mapped[int] = mapped_column(Integer, default=0)
    following_count: Mapped[int] = mapped_column(Integer, default=0)

    # Visibility settings
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    show_email: Mapped[bool] = mapped_column(Boolean, default=False)
    show_projects: Mapped[bool] = mapped_column(Boolean, default=True)

    # Featured content
    featured_project_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=True
    )
    pinned_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="developer_profile")
    featured_project: Mapped[Optional["Project"]] = relationship("Project")


class DeveloperFollow(Base):
    """Track developer follows for the feed."""
    __tablename__ = "developer_follows"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    follower_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    following_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    follower: Mapped["User"] = relationship("User", foreign_keys=[follower_id])
    following: Mapped["User"] = relationship("User", foreign_keys=[following_id])
