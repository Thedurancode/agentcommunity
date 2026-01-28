from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Boolean, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class NotificationType(str, Enum):
    """Types of notifications."""
    # Social
    FOLLOW = "follow"                       # Someone followed you
    UNFOLLOW = "unfollow"                   # Someone unfollowed you

    # Posts & Comments
    POST_LIKE = "post_like"                 # Someone liked your post
    POST_COMMENT = "post_comment"           # Someone commented on your post
    COMMENT_REPLY = "comment_reply"         # Someone replied to your comment
    COMMENT_LIKE = "comment_like"           # Someone liked your comment
    POST_MENTION = "post_mention"           # Someone mentioned you in a post

    # Blog
    BLOG_COMMENT = "blog_comment"           # Someone commented on your blog
    BLOG_LIKE = "blog_like"                 # Someone liked your blog

    # Project
    PROJECT_INVITE = "project_invite"       # Invited to a project
    PROJECT_ROLE_CHANGE = "project_role_change"  # Your role changed in a project
    PROJECT_REMOVED = "project_removed"     # Removed from a project
    PROJECT_UPDATE = "project_update"       # Project status changed

    # Issues & PRs
    ISSUE_ASSIGNED = "issue_assigned"       # Issue assigned to you
    ISSUE_COMMENT = "issue_comment"         # Comment on your issue
    PR_REVIEW_REQUEST = "pr_review_request" # PR review requested
    PR_MERGED = "pr_merged"                 # Your PR was merged
    PR_COMMENT = "pr_comment"               # Comment on your PR

    # Classes & Tickets
    CLASS_REMINDER = "class_reminder"       # Upcoming class reminder
    TICKET_CONFIRMED = "ticket_confirmed"   # Ticket purchase confirmed
    CLASS_CANCELLED = "class_cancelled"     # Class was cancelled

    # Support
    SUPPORT_REPLY = "support_reply"         # Reply to your support ticket
    SUPPORT_RESOLVED = "support_resolved"   # Support ticket resolved

    # System
    SYSTEM = "system"                       # System announcement
    WELCOME = "welcome"                     # Welcome message


class NotificationPriority(str, Enum):
    """Notification priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class Notification(Base):
    """User notification model."""
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Recipient
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)

    # Notification type and priority
    type: Mapped[NotificationType] = mapped_column(SQLEnum(NotificationType))
    priority: Mapped[NotificationPriority] = mapped_column(
        SQLEnum(NotificationPriority), default=NotificationPriority.NORMAL
    )

    # Content
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)

    # Optional link/action
    link: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # URL to navigate to
    action_text: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # e.g., "View Post"

    # Related entities (for reference)
    actor_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)  # Who triggered it
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # post, blog, project, etc.
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # ID of related entity

    # Status
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Email notification
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    email_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Metadata (JSON for extra data)
    extra_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], back_populates="notifications")
    actor: Mapped[Optional["User"]] = relationship("User", foreign_keys=[actor_id])


class NotificationPreference(Base):
    """User notification preferences."""
    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True)

    # Email preferences
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    email_frequency: Mapped[str] = mapped_column(String(20), default="instant")  # instant, daily, weekly, never

    # Notification type preferences (JSON - which types to receive)
    # If null, receive all types
    enabled_types: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    disabled_types: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array

    # Quiet hours (don't send during these hours)
    quiet_hours_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 0-23
    quiet_hours_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 0-23
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")

    # Category toggles
    social_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    project_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    class_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    support_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    system_notifications: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="notification_preferences")
