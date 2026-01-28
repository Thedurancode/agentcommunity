from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel

from app.models.message import ConversationType, MessageStatus
from app.schemas.user import UserResponse


# Message Schemas
class MessageBase(BaseModel):
    content: str
    attachment: Optional[str] = None  # JSON string
    reply_to_id: Optional[int] = None


class MessageCreate(MessageBase):
    pass


class MessageUpdate(BaseModel):
    content: str


class MessageResponse(MessageBase):
    id: int
    conversation_id: int
    sender_id: int
    status: MessageStatus
    is_edited: bool = False
    edited_at: Optional[datetime] = None
    is_deleted: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class MessageWithSender(MessageResponse):
    """Message with sender details."""
    sender: Optional[UserResponse] = None
    reply_to: Optional["MessageResponse"] = None


class MessageList(BaseModel):
    messages: List[MessageWithSender]
    total: int
    has_more: bool = False


# Participant Schemas
class ParticipantResponse(BaseModel):
    id: int
    user_id: int
    is_muted: bool = False
    is_archived: bool = False
    is_pinned: bool = False
    unread_count: int = 0
    last_read_at: Optional[datetime] = None
    joined_at: datetime

    class Config:
        from_attributes = True


class ParticipantWithUser(ParticipantResponse):
    user: Optional[UserResponse] = None


class ParticipantUpdate(BaseModel):
    is_muted: Optional[bool] = None
    is_archived: Optional[bool] = None
    is_pinned: Optional[bool] = None


# Conversation Schemas
class ConversationBase(BaseModel):
    type: ConversationType = ConversationType.DIRECT
    name: Optional[str] = None


class ConversationCreate(BaseModel):
    """Start a new conversation with a user."""
    recipient_id: int
    initial_message: Optional[str] = None


class ConversationResponse(ConversationBase):
    id: int
    last_message_preview: Optional[str] = None
    last_message_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConversationWithDetails(ConversationResponse):
    """Conversation with participants and unread info."""
    participants: List[ParticipantWithUser] = []
    unread_count: int = 0
    other_user: Optional[UserResponse] = None  # For direct messages


class ConversationList(BaseModel):
    conversations: List[ConversationWithDetails]
    total: int


class ConversationSummary(BaseModel):
    """Quick summary for conversation list."""
    id: int
    type: ConversationType
    name: Optional[str] = None
    other_user: Optional[UserResponse] = None
    last_message_preview: Optional[str] = None
    last_message_at: Optional[datetime] = None
    unread_count: int = 0
    is_muted: bool = False
    is_pinned: bool = False

    class Config:
        from_attributes = True


# Typing indicator
class TypingIndicator(BaseModel):
    conversation_id: int
    user_id: int
    is_typing: bool


# Read receipt
class ReadReceipt(BaseModel):
    conversation_id: int
    message_id: Optional[int] = None  # Mark all up to this message as read
