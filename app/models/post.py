from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional, List

from sqlalchemy import ForeignKey, String, Text, DateTime, Enum as SQLEnum, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.project import Project


class PostVisibility(str, Enum):
    PUBLIC = "public"  # Visible to all community members
    PROJECT = "project"  # Visible only to project members
    PRIVATE = "private"  # Visible only to author


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Author
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Optional project association (for project-specific posts)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)

    # Content
    content: Mapped[str] = mapped_column(Text)

    # Media attachments (stored as JSON array of URLs/paths)
    media: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # {"images": [], "videos": [], "links": []}

    # Visibility
    visibility: Mapped[PostVisibility] = mapped_column(SQLEnum(PostVisibility), default=PostVisibility.PUBLIC)

    # Engagement counts (denormalized for performance)
    likes_count: Mapped[int] = mapped_column(default=0)
    comments_count: Mapped[int] = mapped_column(default=0)
    saves_count: Mapped[int] = mapped_column(default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    author: Mapped["User"] = relationship("User", back_populates="posts")
    project: Mapped[Optional["Project"]] = relationship("Project", back_populates="posts")
    comments: Mapped[List["PostComment"]] = relationship("PostComment", back_populates="post", cascade="all, delete-orphan")
    likes: Mapped[List["PostLike"]] = relationship("PostLike", back_populates="post", cascade="all, delete-orphan")
    saves: Mapped[List["PostSave"]] = relationship("PostSave", back_populates="post", cascade="all, delete-orphan")


class PostComment(Base):
    __tablename__ = "post_comments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # For nested comments/replies
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("post_comments.id", ondelete="CASCADE"), nullable=True)

    content: Mapped[str] = mapped_column(Text)

    # Likes on comments
    likes_count: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    post: Mapped["Post"] = relationship("Post", back_populates="comments")
    author: Mapped["User"] = relationship("User", backref="post_comments")
    parent: Mapped[Optional["PostComment"]] = relationship("PostComment", remote_side=[id], backref="replies")
    likes: Mapped[List["CommentLike"]] = relationship("CommentLike", back_populates="comment", cascade="all, delete-orphan")


class PostLike(Base):
    __tablename__ = "post_likes"
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="unique_post_like"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    post: Mapped["Post"] = relationship("Post", back_populates="likes")
    user: Mapped["User"] = relationship("User", backref="post_likes")


class CommentLike(Base):
    __tablename__ = "comment_likes"
    __table_args__ = (
        UniqueConstraint("comment_id", "user_id", name="unique_comment_like"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    comment_id: Mapped[int] = mapped_column(ForeignKey("post_comments.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    comment: Mapped["PostComment"] = relationship("PostComment", back_populates="likes")
    user: Mapped["User"] = relationship("User", backref="comment_likes")


class PostSave(Base):
    __tablename__ = "post_saves"
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="unique_post_save"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    post: Mapped["Post"] = relationship("Post", back_populates="saves")
    user: Mapped["User"] = relationship("User", backref="saved_posts")
