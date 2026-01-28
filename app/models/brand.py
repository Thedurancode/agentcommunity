from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.project import Project


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    slogan: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Logo assets (URLs or file paths)
    main_logo: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    dark_logo: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Additional brand assets
    favicon: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    secondary_color: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Company information
    about_us: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    company_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    company_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Social media links
    website_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    facebook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    twitter_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    instagram_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    youtube_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    tiktok_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), unique=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="brand")
