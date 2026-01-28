from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class PRState(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"


class PullRequest(Base):
    __tablename__ = "pull_requests"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    state: Mapped[PRState] = mapped_column(SQLEnum(PRState), default=PRState.OPEN)

    # Branch info
    head_branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    base_branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # GitHub integration
    github_pr_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    github_pr_number: Mapped[Optional[int]] = mapped_column(nullable=True)
    github_pr_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"))
    author_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    merged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="pull_requests")
    author: Mapped[Optional["User"]] = relationship("User", foreign_keys=[author_id])
