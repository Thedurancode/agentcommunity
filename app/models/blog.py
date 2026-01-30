from datetime import datetime
from enum import Enum
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Boolean, Enum as SQLEnum, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.project import Project


class BlogStatus(str, Enum):
    """Blog post status."""
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Blog(Base):
    """Blog post model."""
    __tablename__ = "blogs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Content
    title: Mapped[str] = mapped_column(String(500))
    slug: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Short summary
    content: Mapped[str] = mapped_column(Text)  # Main blog content (markdown/HTML)

    # Images
    cover_image: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Main cover image URL
    thumbnail: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Thumbnail for listings

    # Status and visibility
    status: Mapped[BlogStatus] = mapped_column(SQLEnum(BlogStatus), default=BlogStatus.DRAFT)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_comments: Mapped[bool] = mapped_column(Boolean, default=True)

    # SEO
    meta_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    meta_description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Categorization
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of tags
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Stats
    views_count: Mapped[int] = mapped_column(Integer, default=0)
    likes_count: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    project_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("projects.id"), nullable=True)

    # Timestamps
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ORM Relationships
    author: Mapped["User"] = relationship("User", back_populates="blogs")
    project: Mapped[Optional["Project"]] = relationship("Project", back_populates="blogs")
    comments: Mapped[List["BlogComment"]] = relationship(
        "BlogComment", back_populates="blog", cascade="all, delete-orphan"
    )
    images: Mapped[List["BlogImage"]] = relationship(
        "BlogImage", back_populates="blog", cascade="all, delete-orphan"
    )
    audio_transcripts: Mapped[List["BlogAudioTranscript"]] = relationship(
        "BlogAudioTranscript", back_populates="blog", cascade="all, delete-orphan"
    )


class BlogImage(Base):
    """Additional images for a blog post."""
    __tablename__ = "blog_images"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    blog_id: Mapped[int] = mapped_column(Integer, ForeignKey("blogs.id"))

    url: Mapped[str] = mapped_column(String(500))
    alt_text: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    blog: Mapped["Blog"] = relationship("Blog", back_populates="images")


class TranscriptStatus(str, Enum):
    """Audio transcript processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class BlogAudioTranscript(Base):
    """Audio transcripts for blog posts - supports multiple audio notes."""
    __tablename__ = "blog_audio_transcripts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    blog_id: Mapped[int] = mapped_column(Integer, ForeignKey("blogs.id"))

    # Audio file info
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Optional title for the audio
    audio_url: Mapped[str] = mapped_column(String(500))
    audio_filename: Mapped[str] = mapped_column(String(255))
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Transcription
    status: Mapped[TranscriptStatus] = mapped_column(
        SQLEnum(TranscriptStatus), default=TranscriptStatus.PENDING
    )
    transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # The transcribed text
    processing_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Ordering
    display_order: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    blog: Mapped["Blog"] = relationship("Blog", back_populates="audio_transcripts")


class BlogComment(Base):
    """Comments on blog posts."""
    __tablename__ = "blog_comments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    blog_id: Mapped[int] = mapped_column(Integer, ForeignKey("blogs.id"))

    # Comment content
    content: Mapped[str] = mapped_column(Text)

    # Author - can be registered user or guest
    author_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    guest_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    guest_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Nested comments (replies)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("blog_comments.id"), nullable=True)

    # Moderation
    is_approved: Mapped[bool] = mapped_column(Boolean, default=True)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False)

    # Stats
    likes_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    blog: Mapped["Blog"] = relationship("Blog", back_populates="comments")
    author: Mapped[Optional["User"]] = relationship("User")
    parent: Mapped[Optional["BlogComment"]] = relationship(
        "BlogComment", remote_side=[id], back_populates="replies"
    )
    replies: Mapped[List["BlogComment"]] = relationship(
        "BlogComment", back_populates="parent"
    )
