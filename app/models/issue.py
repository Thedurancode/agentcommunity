from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class IssueState(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    state: Mapped[IssueState] = mapped_column(SQLEnum(IssueState), default=IssueState.OPEN)

    # GitHub integration
    github_issue_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    github_issue_number: Mapped[Optional[int]] = mapped_column(nullable=True)
    github_issue_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"))
    assignee_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="issues")
    assignee: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assignee_id])
    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_id])
