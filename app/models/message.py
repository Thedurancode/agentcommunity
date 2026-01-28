from datetime import datetime
from enum import Enum
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Boolean, Enum as SQLEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class ConversationType(str, Enum):
    """Type of conversation."""
    DIRECT = "direct"  # 1-on-1 conversation
    GROUP = "group"    # Group chat (future)


class MessageStatus(str, Enum):
    """Message delivery status."""
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"


class Conversation(Base):
    """
    A conversation between users.
    For direct messages, there's one conversation per pair of users.
    """
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Conversation type
    type: Mapped[ConversationType] = mapped_column(
        SQLEnum(ConversationType), default=ConversationType.DIRECT
    )

    # For group chats (future)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Last message preview for listing
    last_message_preview: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    participants: Mapped[List["ConversationParticipant"]] = relationship(
        "ConversationParticipant", back_populates="conversation", cascade="all, delete-orphan"
    )
    messages: Mapped[List["DirectMessage"]] = relationship(
        "DirectMessage", back_populates="conversation", cascade="all, delete-orphan"
    )


class ConversationParticipant(Base):
    """
    Participants in a conversation.
    Tracks per-user state like unread count and mute settings.
    """
    __tablename__ = "conversation_participants"
    __table_args__ = (
        Index("ix_conversation_user", "conversation_id", "user_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey("conversations.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)

    # User preferences for this conversation
    is_muted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)

    # Read tracking
    unread_count: Mapped[int] = mapped_column(Integer, default=0)
    last_read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_read_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Timestamps
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # For group chats

    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="participants")
    user: Mapped["User"] = relationship("User")


class DirectMessage(Base):
    """
    Individual message in a conversation.
    """
    __tablename__ = "direct_messages"
    __table_args__ = (
        Index("ix_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey("conversations.id"), index=True)
    sender_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)

    # Message content
    content: Mapped[str] = mapped_column(Text)

    # Optional attachment (JSON: {"type": "image", "url": "...", "filename": "..."})
    attachment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Reply to another message
    reply_to_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("direct_messages.id"), nullable=True
    )

    # Message status
    status: Mapped[MessageStatus] = mapped_column(
        SQLEnum(MessageStatus), default=MessageStatus.SENT
    )

    # Editing/deletion
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    sender: Mapped["User"] = relationship("User", foreign_keys=[sender_id])
    reply_to: Mapped[Optional["DirectMessage"]] = relationship(
        "DirectMessage", remote_side=[id], foreign_keys=[reply_to_id]
    )
