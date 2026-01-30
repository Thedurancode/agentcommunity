"""
Memory service for AI agents.

Handles:
- Creating and storing memories with vector embeddings
- Semantic search using cosine similarity
- Memory retrieval for agent context
"""
import json
from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.agent_memory import (
    AgentMemory, AgentConversation, ContactPreference,
    MemoryType, MemorySourceType, MemoryStatus
)
from app.models.property import Property, PropertyContact
from app.schemas.memory import (
    MemoryCreate, MemoryResponse, MemoryWithSimilarity,
    ConversationSummaryCreate, ConversationSummaryResponse,
    ContactPreferenceCreate, ContactPreferenceUpdate, ContactPreferenceResponse,
    AgentContext, AgentContextRequest,
    VectorSearchRequest
)


# Embedding configuration
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


class MemoryService:
    """Service for managing agent memories with vector embeddings."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._openai_client = None

    @property
    def openai_client(self):
        """Lazy-load OpenAI client."""
        if self._openai_client is None:
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY not configured")
            from openai import AsyncOpenAI
            self._openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._openai_client

    def is_available(self) -> bool:
        """Check if the memory service is available (OpenAI configured)."""
        return bool(settings.OPENAI_API_KEY)

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for text using OpenAI."""
        response = await self.openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
            dimensions=EMBEDDING_DIMENSIONS
        )
        return response.data[0].embedding

    def _serialize_embedding(self, embedding: List[float]) -> str:
        """Serialize embedding to JSON string for storage."""
        return json.dumps(embedding)

    def _deserialize_embedding(self, embedding_str: str) -> List[float]:
        """Deserialize embedding from JSON string."""
        return json.loads(embedding_str)

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        import numpy as np
        a = np.array(vec1)
        b = np.array(vec2)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    # ============ Memory CRUD ============

    async def create_memory(
        self,
        memory_data: MemoryCreate,
        user_id: Optional[int] = None,
        generate_embedding: bool = True
    ) -> AgentMemory:
        """Create a new memory with optional embedding."""
        # Generate embedding if requested
        embedding_str = None
        if generate_embedding and self.is_available():
            try:
                embedding = await self.generate_embedding(memory_data.content)
                embedding_str = self._serialize_embedding(embedding)
            except Exception:
                # Continue without embedding if it fails
                pass

        # Serialize metadata
        metadata_json = None
        if memory_data.metadata:
            metadata_json = json.dumps(memory_data.metadata)

        memory = AgentMemory(
            property_id=memory_data.property_id,
            contact_id=memory_data.contact_id,
            memory_type=memory_data.memory_type,
            content=memory_data.content,
            embedding=embedding_str,
            embedding_model=EMBEDDING_MODEL if embedding_str else None,
            embedding_dimensions=EMBEDDING_DIMENSIONS if embedding_str else None,
            source_type=memory_data.source_type,
            source_id=memory_data.source_id,
            confidence=memory_data.confidence,
            importance=memory_data.importance,
            status=MemoryStatus.ACTIVE,
            expires_at=memory_data.expires_at,
            metadata_json=metadata_json,
            created_by_id=user_id,
        )

        self.db.add(memory)
        await self.db.commit()
        await self.db.refresh(memory)
        return memory

    async def get_memory(self, memory_id: int) -> Optional[AgentMemory]:
        """Get a memory by ID."""
        result = await self.db.execute(
            select(AgentMemory).where(AgentMemory.id == memory_id)
        )
        return result.scalar_one_or_none()

    async def update_memory_access(self, memory: AgentMemory) -> None:
        """Update memory access tracking."""
        memory.access_count += 1
        memory.last_accessed_at = datetime.utcnow()
        await self.db.commit()

    async def list_memories(
        self,
        property_id: Optional[int] = None,
        contact_id: Optional[int] = None,
        memory_types: Optional[List[MemoryType]] = None,
        status: MemoryStatus = MemoryStatus.ACTIVE,
        limit: int = 50,
        offset: int = 0
    ) -> List[AgentMemory]:
        """List memories with filters."""
        query = select(AgentMemory).where(AgentMemory.status == status)

        if property_id is not None:
            query = query.where(AgentMemory.property_id == property_id)
        if contact_id is not None:
            query = query.where(AgentMemory.contact_id == contact_id)
        if memory_types:
            query = query.where(AgentMemory.memory_type.in_(memory_types))

        query = query.order_by(
            AgentMemory.importance.desc(),
            AgentMemory.created_at.desc()
        ).offset(offset).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def delete_memory(self, memory_id: int) -> bool:
        """Delete a memory."""
        result = await self.db.execute(
            select(AgentMemory).where(AgentMemory.id == memory_id)
        )
        memory = result.scalar_one_or_none()
        if memory:
            await self.db.delete(memory)
            await self.db.commit()
            return True
        return False

    async def archive_memory(self, memory_id: int) -> Optional[AgentMemory]:
        """Archive a memory instead of deleting."""
        result = await self.db.execute(
            select(AgentMemory).where(AgentMemory.id == memory_id)
        )
        memory = result.scalar_one_or_none()
        if memory:
            memory.status = MemoryStatus.ARCHIVED
            await self.db.commit()
            await self.db.refresh(memory)
        return memory

    # ============ Vector Search ============

    async def semantic_search(
        self,
        request: VectorSearchRequest
    ) -> List[MemoryWithSimilarity]:
        """
        Search memories using semantic similarity.

        For SQLite: Uses in-memory cosine similarity calculation.
        For PostgreSQL with pgvector: Could use native vector operations.
        """
        if not self.is_available():
            raise ValueError("Memory service not available (OpenAI not configured)")

        # Generate query embedding
        query_embedding = await self.generate_embedding(request.query)

        # Build base query
        query = select(AgentMemory).where(
            AgentMemory.status == MemoryStatus.ACTIVE,
            AgentMemory.embedding.isnot(None)
        )

        if request.property_id is not None:
            query = query.where(AgentMemory.property_id == request.property_id)
        if request.contact_id is not None:
            query = query.where(AgentMemory.contact_id == request.contact_id)
        if request.memory_types:
            query = query.where(AgentMemory.memory_type.in_(request.memory_types))

        # Get all matching memories
        result = await self.db.execute(query)
        memories = result.scalars().all()

        # Calculate similarities in Python (for SQLite compatibility)
        scored_memories = []
        for memory in memories:
            if memory.embedding:
                mem_embedding = self._deserialize_embedding(memory.embedding)
                similarity = self._cosine_similarity(query_embedding, mem_embedding)
                if similarity >= request.min_similarity:
                    scored_memories.append((memory, similarity))

        # Sort by similarity and limit
        scored_memories.sort(key=lambda x: x[1], reverse=True)
        scored_memories = scored_memories[:request.limit]

        # Convert to response format
        results = []
        for memory, similarity in scored_memories:
            # Update access tracking
            await self.update_memory_access(memory)

            response = MemoryWithSimilarity(
                id=memory.id,
                property_id=memory.property_id,
                contact_id=memory.contact_id,
                memory_type=memory.memory_type,
                content=memory.content,
                confidence=memory.confidence,
                importance=memory.importance,
                source_type=memory.source_type,
                source_id=memory.source_id,
                status=memory.status,
                expires_at=memory.expires_at,
                access_count=memory.access_count,
                last_accessed_at=memory.last_accessed_at,
                created_at=memory.created_at,
                updated_at=memory.updated_at,
                created_by_id=memory.created_by_id,
                similarity=similarity
            )
            results.append(response)

        return results

    # ============ Conversation Summaries ============

    async def create_conversation_summary(
        self,
        summary_data: ConversationSummaryCreate
    ) -> AgentConversation:
        """Create a conversation summary."""
        # Generate embedding for summary
        embedding_str = None
        if self.is_available():
            try:
                embedding = await self.generate_embedding(summary_data.summary)
                embedding_str = self._serialize_embedding(embedding)
            except Exception:
                pass

        conversation = AgentConversation(
            property_id=summary_data.property_id,
            contact_id=summary_data.contact_id,
            conversation_type=summary_data.conversation_type,
            source_id=summary_data.source_id,
            summary=summary_data.summary,
            key_points=json.dumps(summary_data.key_points) if summary_data.key_points else None,
            action_items=json.dumps(summary_data.action_items) if summary_data.action_items else None,
            sentiment=summary_data.sentiment,
            sentiment_score=summary_data.sentiment_score,
            topics=json.dumps(summary_data.topics) if summary_data.topics else None,
            follow_up_required=summary_data.follow_up_required,
            follow_up_date=summary_data.follow_up_date,
            follow_up_notes=summary_data.follow_up_notes,
            summary_embedding=embedding_str,
            conversation_at=summary_data.conversation_at,
        )

        self.db.add(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)
        return conversation

    async def get_recent_conversations(
        self,
        property_id: Optional[int] = None,
        contact_id: Optional[int] = None,
        limit: int = 5
    ) -> List[AgentConversation]:
        """Get recent conversation summaries."""
        query = select(AgentConversation)

        conditions = []
        if property_id is not None:
            conditions.append(AgentConversation.property_id == property_id)
        if contact_id is not None:
            conditions.append(AgentConversation.contact_id == contact_id)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(AgentConversation.conversation_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ============ Contact Preferences ============

    async def get_or_create_preferences(
        self,
        contact_id: int
    ) -> ContactPreference:
        """Get or create contact preferences."""
        result = await self.db.execute(
            select(ContactPreference).where(ContactPreference.contact_id == contact_id)
        )
        pref = result.scalar_one_or_none()

        if not pref:
            pref = ContactPreference(contact_id=contact_id)
            self.db.add(pref)
            await self.db.commit()
            await self.db.refresh(pref)

        return pref

    async def update_preferences(
        self,
        contact_id: int,
        update_data: ContactPreferenceUpdate
    ) -> ContactPreference:
        """Update contact preferences."""
        pref = await self.get_or_create_preferences(contact_id)

        update_dict = update_data.model_dump(exclude_unset=True)

        # Handle preferred_days as JSON
        if "preferred_days" in update_dict and update_dict["preferred_days"] is not None:
            update_dict["preferred_days"] = json.dumps(update_dict["preferred_days"])

        for field, value in update_dict.items():
            setattr(pref, field, value)

        await self.db.commit()
        await self.db.refresh(pref)
        return pref

    # ============ Agent Context ============

    async def get_agent_context(
        self,
        request: AgentContextRequest
    ) -> AgentContext:
        """
        Build comprehensive context for an AI agent.

        Gathers all relevant memories, conversations, and preferences
        for a property and/or contact.
        """
        context = AgentContext()

        # Load property details
        if request.property_id:
            result = await self.db.execute(
                select(Property)
                .options(selectinload(Property.contacts))
                .where(Property.id == request.property_id)
            )
            property = result.scalar_one_or_none()
            if property:
                context.property_id = property.id
                context.property_name = property.name
                context.property_address = ", ".join(filter(None, [
                    property.address, property.city, property.state, property.zip_code
                ])) or None
                context.property_type = property.property_type
                context.property_status = property.status.value if property.status else None
                context.property_description = property.description

        # Load contact details
        if request.contact_id:
            result = await self.db.execute(
                select(PropertyContact).where(PropertyContact.id == request.contact_id)
            )
            contact = result.scalar_one_or_none()
            if contact:
                context.contact_id = contact.id
                context.contact_name = contact.name
                context.contact_type = contact.contact_type.value if contact.contact_type else None
                context.contact_company = contact.company
                context.contact_phone = contact.phone
                context.contact_email = contact.email

        # Load memories
        if request.include_memories:
            if request.query and self.is_available():
                # Use semantic search if query provided
                search_request = VectorSearchRequest(
                    query=request.query,
                    property_id=request.property_id,
                    contact_id=request.contact_id,
                    limit=request.memory_limit
                )
                memories = await self.semantic_search(search_request)
                context.memories = memories
            else:
                # Get all relevant memories
                memories = await self.list_memories(
                    property_id=request.property_id,
                    contact_id=request.contact_id,
                    limit=request.memory_limit
                )
                context.memories = [MemoryResponse.model_validate(m) for m in memories]

            # Separate out open commitments
            context.open_commitments = [
                m for m in context.memories
                if m.memory_type == MemoryType.COMMITMENT
            ]

        # Load recent conversations
        if request.include_conversations:
            conversations = await self.get_recent_conversations(
                property_id=request.property_id,
                contact_id=request.contact_id,
                limit=request.conversation_limit
            )
            context.recent_conversations = [
                self._conversation_to_response(c) for c in conversations
            ]

        # Load preferences
        if request.include_preferences and request.contact_id:
            pref = await self.get_or_create_preferences(request.contact_id)
            context.preferences = ContactPreferenceResponse.model_validate(pref)

        return context

    def _conversation_to_response(
        self,
        conv: AgentConversation
    ) -> ConversationSummaryResponse:
        """Convert AgentConversation to response schema."""
        return ConversationSummaryResponse(
            id=conv.id,
            property_id=conv.property_id,
            contact_id=conv.contact_id,
            conversation_type=conv.conversation_type,
            source_id=conv.source_id,
            summary=conv.summary,
            key_points=json.loads(conv.key_points) if conv.key_points else None,
            action_items=json.loads(conv.action_items) if conv.action_items else None,
            sentiment=conv.sentiment,
            sentiment_score=conv.sentiment_score,
            topics=json.loads(conv.topics) if conv.topics else None,
            conversation_at=conv.conversation_at,
            processed_at=conv.processed_at,
            follow_up_required=conv.follow_up_required,
            follow_up_date=conv.follow_up_date,
            follow_up_notes=conv.follow_up_notes,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        )


def get_memory_service(db: AsyncSession) -> MemoryService:
    """Get memory service instance."""
    return MemoryService(db)
