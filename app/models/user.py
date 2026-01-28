from datetime import datetime
from enum import Enum
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, DateTime, Boolean, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.team_member import TeamMember
    from app.models.post import Post
    from app.models.developer_profile import DeveloperProfile
    from app.models.blog import Blog
    from app.models.notification import Notification, NotificationPreference


class UserRole(str, Enum):
    ADMIN = "admin"
    TEAM_MEMBER = "team_member"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[str] = mapped_column(String(20))
    profile_image: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), default=UserRole.TEAM_MEMBER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # GitHub integration
    github_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    github_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    github_access_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owned_projects: Mapped[List["Project"]] = relationship("Project", back_populates="owner")
    team_memberships: Mapped[List["TeamMember"]] = relationship("TeamMember", back_populates="user")
    posts: Mapped[List["Post"]] = relationship("Post", back_populates="author", cascade="all, delete-orphan")
    developer_profile: Mapped[Optional["DeveloperProfile"]] = relationship(
        "DeveloperProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    blogs: Mapped[List["Blog"]] = relationship("Blog", back_populates="author", cascade="all, delete-orphan")
    notifications: Mapped[List["Notification"]] = relationship(
        "Notification", foreign_keys="Notification.user_id", back_populates="user", cascade="all, delete-orphan"
    )
    notification_preferences: Mapped[Optional["NotificationPreference"]] = relationship(
        "NotificationPreference", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
