from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional, List

from sqlalchemy import ForeignKey, String, Text, DateTime, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User
    from app.models.issue import Issue


class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_ON_CUSTOMER = "waiting_on_customer"
    WAITING_ON_TEAM = "waiting_on_team"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketCategory(str, Enum):
    BUG = "bug"
    FEATURE_REQUEST = "feature_request"
    QUESTION = "question"
    DOCUMENTATION = "documentation"
    OTHER = "other"


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)

    # Ticket details
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[TicketCategory] = mapped_column(SQLEnum(TicketCategory), default=TicketCategory.OTHER)
    priority: Mapped[TicketPriority] = mapped_column(SQLEnum(TicketPriority), default=TicketPriority.MEDIUM)
    status: Mapped[TicketStatus] = mapped_column(SQLEnum(TicketStatus), default=TicketStatus.OPEN, index=True)

    # Submitter info (can be a registered user or just contact info)
    submitted_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitter_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    submitter_email: Mapped[str] = mapped_column(String(255))

    # Assignment
    assigned_to_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Tracking
    ticket_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)

    # Conversion to issue
    converted_to_issue_id: Mapped[Optional[int]] = mapped_column(ForeignKey("issues.id", ondelete="SET NULL"), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="support_tickets")
    submitted_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[submitted_by_id], backref="submitted_tickets")
    assigned_to: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assigned_to_id], backref="assigned_tickets")
    comments: Mapped[List["TicketComment"]] = relationship("TicketComment", back_populates="ticket", cascade="all, delete-orphan")
    converted_to_issue: Mapped[Optional["Issue"]] = relationship("Issue", foreign_keys=[converted_to_issue_id])


class TicketComment(Base):
    __tablename__ = "ticket_comments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("support_tickets.id", ondelete="CASCADE"), index=True)

    content: Mapped[str] = mapped_column(Text)
    is_internal: Mapped[bool] = mapped_column(default=False)  # Internal notes not visible to submitter

    # Author info
    author_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    author_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    author_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    ticket: Mapped["SupportTicket"] = relationship("SupportTicket", back_populates="comments")
    author: Mapped[Optional["User"]] = relationship("User", backref="ticket_comments")
