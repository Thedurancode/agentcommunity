from datetime import datetime
from enum import Enum
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Float, Enum as SQLEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.property import Property, PropertyContact
    from app.models.user import User


class MemoryType(str, Enum):
    """Types of memories an agent can store."""
    FACT = "fact"  # Learned facts about a contact/property
    PREFERENCE = "preference"  # Communication preferences, scheduling preferences
    COMMITMENT = "commitment"  # Things the agent/user committed to do
    RELATIONSHIP = "relationship"  # Relationships between entities
    CONTEXT = "context"  # General context about interactions
    SUMMARY = "summary"  # Conversation summaries


class MemorySourceType(str, Enum):
    """Source of where the memory was extracted from."""
    PHONE_CALL = "phone_call"
    SMS = "sms"
    NOTE = "note"
    USER_INPUT = "user_input"
    SYSTEM = "system"


class MemoryStatus(str, Enum):
    """Status of a memory."""
    ACTIVE = "active"
    ARCHIVED = "archived"
    EXPIRED = "expired"


class AgentMemory(Base):
    """
    Vector-enabled memory store for AI agents.

    Stores facts, preferences, commitments, and context learned from
    interactions with contacts and about properties.

    Uses pgvector for semantic similarity search.
    """
    __tablename__ = "agent_memories"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Scope - what this memory relates to (nullable for global memories)
    property_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=True, index=True
    )
    contact_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("property_contacts.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # Memory classification
    memory_type: Mapped[MemoryType] = mapped_column(
        SQLEnum(MemoryType), default=MemoryType.FACT, index=True
    )

    # The actual memory content (human readable)
    content: Mapped[str] = mapped_column(Text)

    # Vector embedding for semantic search (stored as JSON array for SQLite compatibility)
    # For PostgreSQL with pgvector, this would be: Vector(1536)
    # We store as Text for portability, parse to list of floats
    embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Embedding model used (for future compatibility)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    embedding_dimensions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Source tracking
    source_type: Mapped[MemorySourceType] = mapped_column(
        SQLEnum(MemorySourceType), default=MemorySourceType.SYSTEM
    )
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # ID of call, sms, note, etc.

    # Confidence and importance
    confidence: Mapped[float] = mapped_column(Float, default=1.0)  # 0.0 to 1.0
    importance: Mapped[float] = mapped_column(Float, default=0.5)  # 0.0 to 1.0, for prioritization

    # Status and lifecycle
    status: Mapped[MemoryStatus] = mapped_column(
        SQLEnum(MemoryStatus), default=MemoryStatus.ACTIVE, index=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Usage tracking
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Metadata
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON for additional data

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Who created this memory
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    # Relationships
    property: Mapped[Optional["Property"]] = relationship("Property", backref="agent_memories")
    contact: Mapped[Optional["PropertyContact"]] = relationship("PropertyContact", backref="agent_memories")
    created_by: Mapped[Optional["User"]] = relationship("User")

    # Indexes for common queries
    __table_args__ = (
        Index('ix_agent_memories_property_type', 'property_id', 'memory_type'),
        Index('ix_agent_memories_contact_type', 'contact_id', 'memory_type'),
        Index('ix_agent_memories_source', 'source_type', 'source_id'),
    )


class AgentConversation(Base):
    """
    Stores summaries and key points from conversations.

    Links to the actual conversation (call or SMS thread) and
    provides structured extraction of the conversation content.
    """
    __tablename__ = "agent_conversations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Scope
    property_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("properties.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("property_contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Conversation reference
    conversation_type: Mapped[str] = mapped_column(String(50))  # "phone_call", "sms_thread"
    source_id: Mapped[int] = mapped_column(Integer)  # ID of the call or SMS

    # Extracted content
    summary: Mapped[str] = mapped_column(Text)  # AI-generated summary
    key_points: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    action_items: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    sentiment: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # positive, negative, neutral
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # -1.0 to 1.0

    # Topics discussed
    topics: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of topics

    # Follow-up tracking
    follow_up_required: Mapped[bool] = mapped_column(default=False)
    follow_up_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    follow_up_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Embedding for the full conversation
    summary_embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    conversation_at: Mapped[datetime] = mapped_column(DateTime)  # When the conversation happened
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    property: Mapped["Property"] = relationship("Property", backref="agent_conversations")
    contact: Mapped[Optional["PropertyContact"]] = relationship("PropertyContact", backref="agent_conversations")

    __table_args__ = (
        Index('ix_agent_conversations_property_contact', 'property_id', 'contact_id'),
        Index('ix_agent_conversations_source', 'conversation_type', 'source_id'),
    )


class ContactPreference(Base):
    """
    Stores communication preferences for contacts.

    Extracted from conversations or manually set.
    """
    __tablename__ = "contact_preferences"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    contact_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("property_contacts.id", ondelete="CASCADE"), unique=True, index=True
    )

    # Communication preferences
    preferred_channel: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # phone, sms, email
    preferred_time: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # "morning", "after 5pm", etc.
    preferred_days: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # JSON array of days
    timezone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Communication style
    formality_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # formal, casual, friendly
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, default="en")

    # Do not contact settings
    do_not_call: Mapped[bool] = mapped_column(default=False)
    do_not_text: Mapped[bool] = mapped_column(default=False)
    do_not_email: Mapped[bool] = mapped_column(default=False)

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    contact: Mapped["PropertyContact"] = relationship("PropertyContact", backref="preferences")
