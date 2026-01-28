from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.project import Project


class Recap(Base):
    __tablename__ = "recaps"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Last 5 commits from GitHub
    recent_commits: Mapped[Optional[List[dict]]] = mapped_column(JSON, nullable=True, default=list)

    # Last 5 issues (local + GitHub synced)
    recent_issues: Mapped[Optional[List[dict]]] = mapped_column(JSON, nullable=True, default=list)

    # Last 5 notes
    recent_notes: Mapped[Optional[List[dict]]] = mapped_column(JSON, nullable=True, default=list)

    # Summary text (can be AI-generated or manual)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), unique=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="recap")
