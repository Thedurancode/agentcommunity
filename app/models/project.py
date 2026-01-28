from datetime import datetime
from enum import Enum
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ProjectStatus(str, Enum):
    """Project development status."""
    IN_TALKS = "in_talks"           # Initial discussions, planning phase
    NOW_CODING = "now_coding"       # Active development in progress
    NEEDS_REVIEW = "needs_review"   # Code complete, awaiting review
    COMPLETE = "complete"           # Project finished

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.team_member import TeamMember
    from app.models.issue import Issue
    from app.models.pull_request import PullRequest
    from app.models.brand import Brand
    from app.models.note import Note
    from app.models.recap import Recap
    from app.models.video import Video
    from app.models.class_model import Class
    from app.models.support_ticket import SupportTicket
    from app.models.post import Post
    from app.models.episode import Episode
    from app.models.voice_note import VoiceNote
    from app.models.blog import Blog


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Project status
    status: Mapped[ProjectStatus] = mapped_column(
        SQLEnum(ProjectStatus), default=ProjectStatus.IN_TALKS
    )
    status_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Optional note about current status

    # GitHub integration
    github_repo_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    github_repo_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    github_repo_full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    github_repo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="owned_projects")
    team_members: Mapped[List["TeamMember"]] = relationship("TeamMember", back_populates="project", cascade="all, delete-orphan")
    issues: Mapped[List["Issue"]] = relationship("Issue", back_populates="project", cascade="all, delete-orphan")
    pull_requests: Mapped[List["PullRequest"]] = relationship("PullRequest", back_populates="project", cascade="all, delete-orphan")
    brand: Mapped[Optional["Brand"]] = relationship("Brand", back_populates="project", uselist=False, cascade="all, delete-orphan")
    notes: Mapped[List["Note"]] = relationship("Note", back_populates="project", cascade="all, delete-orphan")
    recap: Mapped[Optional["Recap"]] = relationship("Recap", back_populates="project", uselist=False, cascade="all, delete-orphan")
    videos: Mapped[List["Video"]] = relationship("Video", back_populates="project", cascade="all, delete-orphan")
    classes: Mapped[List["Class"]] = relationship("Class", back_populates="project", cascade="all, delete-orphan")
    support_tickets: Mapped[List["SupportTicket"]] = relationship("SupportTicket", back_populates="project", cascade="all, delete-orphan")
    posts: Mapped[List["Post"]] = relationship("Post", back_populates="project", cascade="all, delete-orphan")
    episodes: Mapped[List["Episode"]] = relationship("Episode", back_populates="project")
    voice_notes: Mapped[List["VoiceNote"]] = relationship("VoiceNote", back_populates="project", cascade="all, delete-orphan")
    blogs: Mapped[List["Blog"]] = relationship("Blog", back_populates="project", cascade="all, delete-orphan")
