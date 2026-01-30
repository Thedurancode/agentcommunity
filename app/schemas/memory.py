from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field

from app.models.agent_memory import MemoryType, MemorySourceType, MemoryStatus


# ============ Memory Schemas ============

class MemoryBase(BaseModel):
    """Base schema for agent memories."""
    content: str = Field(..., description="The memory content in human-readable form")
    memory_type: MemoryType = MemoryType.FACT
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score 0-1")
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="Importance score 0-1")


class MemoryCreate(MemoryBase):
    """Schema for creating a new memory."""
    property_id: Optional[int] = None
    contact_id: Optional[int] = None
    source_type: MemorySourceType = MemorySourceType.USER_INPUT
    source_id: Optional[int] = None
    expires_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class MemoryUpdate(BaseModel):
    """Schema for updating a memory."""
    content: Optional[str] = None
    memory_type: Optional[MemoryType] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    importance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    status: Optional[MemoryStatus] = None
    expires_at: Optional[datetime] = None


class MemoryResponse(MemoryBase):
    """Response schema for a memory."""
    id: int
    property_id: Optional[int] = None
    contact_id: Optional[int] = None
    source_type: MemorySourceType
    source_id: Optional[int] = None
    status: MemoryStatus
    expires_at: Optional[datetime] = None
    access_count: int
    last_accessed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    created_by_id: Optional[int] = None

    class Config:
        from_attributes = True


class MemoryWithSimilarity(MemoryResponse):
    """Memory response with similarity score for vector search."""
    similarity: float = Field(..., description="Cosine similarity score 0-1")


class MemoryList(BaseModel):
    """List of memories."""
    memories: List[MemoryResponse]
    total: int


class MemorySearchResult(BaseModel):
    """Search results with similarity scores."""
    memories: List[MemoryWithSimilarity]
    total: int
    query: str


# ============ Conversation Schemas ============

class ConversationSummaryBase(BaseModel):
    """Base schema for conversation summaries."""
    summary: str
    key_points: Optional[List[str]] = None
    action_items: Optional[List[str]] = None
    sentiment: Optional[str] = None
    sentiment_score: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    topics: Optional[List[str]] = None


class ConversationSummaryCreate(ConversationSummaryBase):
    """Schema for creating a conversation summary."""
    property_id: int
    contact_id: Optional[int] = None
    conversation_type: str  # "phone_call" or "sms_thread"
    source_id: int
    conversation_at: datetime
    follow_up_required: bool = False
    follow_up_date: Optional[datetime] = None
    follow_up_notes: Optional[str] = None


class ConversationSummaryResponse(ConversationSummaryBase):
    """Response schema for conversation summary."""
    id: int
    property_id: int
    contact_id: Optional[int] = None
    conversation_type: str
    source_id: int
    conversation_at: datetime
    processed_at: datetime
    follow_up_required: bool
    follow_up_date: Optional[datetime] = None
    follow_up_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConversationSummaryList(BaseModel):
    """List of conversation summaries."""
    conversations: List[ConversationSummaryResponse]
    total: int


# ============ Contact Preference Schemas ============

class ContactPreferenceBase(BaseModel):
    """Base schema for contact preferences."""
    preferred_channel: Optional[str] = None
    preferred_time: Optional[str] = None
    preferred_days: Optional[List[str]] = None
    timezone: Optional[str] = None
    formality_level: Optional[str] = None
    language: Optional[str] = "en"
    do_not_call: bool = False
    do_not_text: bool = False
    do_not_email: bool = False
    notes: Optional[str] = None


class ContactPreferenceCreate(ContactPreferenceBase):
    """Schema for creating contact preferences."""
    contact_id: int


class ContactPreferenceUpdate(BaseModel):
    """Schema for updating contact preferences."""
    preferred_channel: Optional[str] = None
    preferred_time: Optional[str] = None
    preferred_days: Optional[List[str]] = None
    timezone: Optional[str] = None
    formality_level: Optional[str] = None
    language: Optional[str] = None
    do_not_call: Optional[bool] = None
    do_not_text: Optional[bool] = None
    do_not_email: Optional[bool] = None
    notes: Optional[str] = None


class ContactPreferenceResponse(ContactPreferenceBase):
    """Response schema for contact preferences."""
    id: int
    contact_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ Agent Context Schemas ============

class AgentContext(BaseModel):
    """
    Full context package for an AI agent before an interaction.

    Contains all relevant memories, conversation history, and preferences
    for a property and/or contact.
    """
    # Property context
    property_id: Optional[int] = None
    property_name: Optional[str] = None
    property_address: Optional[str] = None
    property_type: Optional[str] = None
    property_status: Optional[str] = None
    property_description: Optional[str] = None

    # Contact context
    contact_id: Optional[int] = None
    contact_name: Optional[str] = None
    contact_type: Optional[str] = None
    contact_company: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None

    # Memories (relevant facts, preferences, commitments)
    memories: List[MemoryResponse] = []

    # Recent conversations
    recent_conversations: List[ConversationSummaryResponse] = []

    # Contact preferences
    preferences: Optional[ContactPreferenceResponse] = None

    # Open commitments (things we promised to do)
    open_commitments: List[MemoryResponse] = []

    # Additional context
    additional_context: Optional[str] = None


class AgentContextRequest(BaseModel):
    """Request for agent context."""
    property_id: Optional[int] = None
    contact_id: Optional[int] = None
    query: Optional[str] = None  # Optional semantic search query
    include_memories: bool = True
    include_conversations: bool = True
    include_preferences: bool = True
    memory_limit: int = Field(default=20, ge=1, le=100)
    conversation_limit: int = Field(default=5, ge=1, le=20)


# ============ Memory Extraction Schemas ============

class MemoryExtractionRequest(BaseModel):
    """Request to extract memories from a conversation."""
    source_type: MemorySourceType
    source_id: int
    text: str  # The transcript or message content
    property_id: Optional[int] = None
    contact_id: Optional[int] = None


class ExtractedMemory(BaseModel):
    """A single extracted memory from text."""
    content: str
    memory_type: MemoryType
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)


class MemoryExtractionResult(BaseModel):
    """Result of memory extraction."""
    memories: List[ExtractedMemory]
    summary: Optional[str] = None
    key_points: Optional[List[str]] = None
    action_items: Optional[List[str]] = None
    sentiment: Optional[str] = None
    sentiment_score: Optional[float] = None


# ============ Vector Search Schemas ============

class VectorSearchRequest(BaseModel):
    """Request for semantic memory search."""
    query: str = Field(..., min_length=1, description="Search query")
    property_id: Optional[int] = None
    contact_id: Optional[int] = None
    memory_types: Optional[List[MemoryType]] = None
    limit: int = Field(default=10, ge=1, le=100)
    min_similarity: float = Field(default=0.5, ge=0.0, le=1.0)
