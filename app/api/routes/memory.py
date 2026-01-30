"""
API routes for agent memory management.

Provides endpoints for:
- Memory CRUD operations
- Semantic search
- Agent context retrieval
- Memory extraction from conversations
- Contact preferences
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.models.property import Property, PropertyContact, PropertyPhoneCall
from app.models.agent_memory import AgentMemory, MemoryType, MemoryStatus, MemorySourceType
from app.schemas.memory import (
    MemoryCreate, MemoryUpdate, MemoryResponse, MemoryList, MemorySearchResult,
    ConversationSummaryResponse, ConversationSummaryList,
    ContactPreferenceUpdate, ContactPreferenceResponse,
    AgentContext, AgentContextRequest,
    MemoryExtractionRequest, MemoryExtractionResult,
    VectorSearchRequest
)
from app.api.deps import get_current_user
from app.services.memory import get_memory_service
from app.services.memory_extraction import get_extraction_service


router = APIRouter(prefix="/memory", tags=["agent-memory"])


# ============ Helper Functions ============

async def verify_property_access(
    property_id: int,
    user: User,
    db: AsyncSession
) -> Property:
    """Verify user has access to property."""
    from app.models.user import UserRole

    result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    property = result.scalar_one_or_none()

    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )

    if user.role != UserRole.ADMIN and property.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this property"
        )

    return property


async def verify_contact_access(
    contact_id: int,
    user: User,
    db: AsyncSession
) -> PropertyContact:
    """Verify user has access to contact's property."""
    result = await db.execute(
        select(PropertyContact).where(PropertyContact.id == contact_id)
    )
    contact = result.scalar_one_or_none()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )

    # Verify property access
    await verify_property_access(contact.property_id, user, db)
    return contact


# ============ Memory CRUD ============

@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(
    memory_data: MemoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new memory.

    Automatically generates vector embedding for semantic search.
    """
    # Verify access if property/contact specified
    if memory_data.property_id:
        await verify_property_access(memory_data.property_id, current_user, db)
    if memory_data.contact_id:
        await verify_contact_access(memory_data.contact_id, current_user, db)

    service = get_memory_service(db)
    memory = await service.create_memory(memory_data, user_id=current_user.id)
    return memory


@router.get("", response_model=MemoryList)
async def list_memories(
    property_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    memory_type: Optional[MemoryType] = None,
    status_filter: MemoryStatus = MemoryStatus.ACTIVE,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List memories with optional filters.

    Filter by property, contact, or memory type.
    """
    # Verify access
    if property_id:
        await verify_property_access(property_id, current_user, db)
    if contact_id:
        await verify_contact_access(contact_id, current_user, db)

    service = get_memory_service(db)
    memory_types = [memory_type] if memory_type else None

    memories = await service.list_memories(
        property_id=property_id,
        contact_id=contact_id,
        memory_types=memory_types,
        status=status_filter,
        limit=limit,
        offset=skip
    )

    return MemoryList(
        memories=[MemoryResponse.model_validate(m) for m in memories],
        total=len(memories)
    )


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific memory by ID."""
    service = get_memory_service(db)
    memory = await service.get_memory(memory_id)

    if not memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found"
        )

    # Verify access
    if memory.property_id:
        await verify_property_access(memory.property_id, current_user, db)

    return memory


@router.patch("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: int,
    update_data: MemoryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a memory."""
    result = await db.execute(
        select(AgentMemory).where(AgentMemory.id == memory_id)
    )
    memory = result.scalar_one_or_none()

    if not memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found"
        )

    # Verify access
    if memory.property_id:
        await verify_property_access(memory.property_id, current_user, db)

    # Update fields
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(memory, field, value)

    # Re-generate embedding if content changed
    if "content" in update_dict:
        service = get_memory_service(db)
        if service.is_available():
            try:
                import json
                embedding = await service.generate_embedding(memory.content)
                memory.embedding = json.dumps(embedding)
            except Exception:
                pass

    await db.commit()
    await db.refresh(memory)
    return memory


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a memory."""
    service = get_memory_service(db)
    memory = await service.get_memory(memory_id)

    if not memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found"
        )

    # Verify access
    if memory.property_id:
        await verify_property_access(memory.property_id, current_user, db)

    await service.delete_memory(memory_id)
    return None


@router.post("/{memory_id}/archive", response_model=MemoryResponse)
async def archive_memory(
    memory_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Archive a memory instead of deleting."""
    service = get_memory_service(db)
    memory = await service.get_memory(memory_id)

    if not memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found"
        )

    # Verify access
    if memory.property_id:
        await verify_property_access(memory.property_id, current_user, db)

    memory = await service.archive_memory(memory_id)
    return memory


# ============ Semantic Search ============

@router.post("/search", response_model=MemorySearchResult)
async def search_memories(
    request: VectorSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Search memories using semantic similarity.

    Uses vector embeddings to find memories similar to the query.
    """
    # Verify access
    if request.property_id:
        await verify_property_access(request.property_id, current_user, db)
    if request.contact_id:
        await verify_contact_access(request.contact_id, current_user, db)

    service = get_memory_service(db)

    if not service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory service not available (OpenAI not configured)"
        )

    try:
        results = await service.semantic_search(request)
        return MemorySearchResult(
            memories=results,
            total=len(results),
            query=request.query
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


# ============ Agent Context ============

@router.post("/context", response_model=AgentContext)
async def get_agent_context(
    request: AgentContextRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get comprehensive context for an AI agent.

    Returns all relevant memories, conversation history, and preferences
    for a property and/or contact.
    """
    # Verify access
    if request.property_id:
        await verify_property_access(request.property_id, current_user, db)
    if request.contact_id:
        await verify_contact_access(request.contact_id, current_user, db)

    service = get_memory_service(db)
    context = await service.get_agent_context(request)
    return context


# ============ Memory Extraction ============

@router.post("/extract", response_model=MemoryExtractionResult)
async def extract_memories(
    request: MemoryExtractionRequest,
    store: bool = Query(True, description="Store extracted memories in database"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Extract memories from text using AI.

    Analyzes the provided text and extracts facts, preferences,
    commitments, and other relevant information.

    Set store=true to automatically save extracted memories.
    """
    # Verify access
    if request.property_id:
        property = await verify_property_access(request.property_id, current_user, db)
        property_context = f"{property.name} - {property.address or 'No address'}"
    else:
        property_context = None

    contact_context = None
    if request.contact_id:
        contact = await verify_contact_access(request.contact_id, current_user, db)
        contact_context = f"{contact.name} ({contact.contact_type.value if contact.contact_type else 'contact'})"

    extraction_service = get_extraction_service(db)

    if not extraction_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Extraction service not available (Anthropic not configured)"
        )

    try:
        if store:
            result = await extraction_service.process_and_store(
                request,
                user_id=current_user.id,
                property_context=property_context,
                contact_context=contact_context
            )
        else:
            result = await extraction_service.extract_memories(
                request,
                property_context=property_context,
                contact_context=contact_context
            )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extraction failed: {str(e)}"
        )


@router.post("/extract/call/{call_id}", response_model=MemoryExtractionResult)
async def extract_memories_from_call(
    call_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Extract memories from a phone call transcript.

    Automatically fetches the call transcript and extracts memories.
    """
    # Get the call
    result = await db.execute(
        select(PropertyPhoneCall).where(PropertyPhoneCall.id == call_id)
    )
    call = result.scalar_one_or_none()

    if not call:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call not found"
        )

    # Verify property access
    property = await verify_property_access(call.property_id, current_user, db)

    if not call.transcript:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Call has no transcript"
        )

    # Get contact if linked
    contact_context = None
    if call.contact_id:
        contact_result = await db.execute(
            select(PropertyContact).where(PropertyContact.id == call.contact_id)
        )
        contact = contact_result.scalar_one_or_none()
        if contact:
            contact_context = f"{contact.name} ({contact.contact_type.value if contact.contact_type else 'contact'})"

    property_context = f"{property.name} - {property.address or 'No address'}"

    # Build extraction request
    extraction_request = MemoryExtractionRequest(
        source_type=MemorySourceType.PHONE_CALL,
        source_id=call_id,
        text=call.transcript,
        property_id=call.property_id,
        contact_id=call.contact_id
    )

    extraction_service = get_extraction_service(db)

    if not extraction_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Extraction service not available"
        )

    try:
        result = await extraction_service.process_and_store(
            extraction_request,
            user_id=current_user.id,
            property_context=property_context,
            contact_context=contact_context,
            conversation_at=call.started_at or call.created_at
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extraction failed: {str(e)}"
        )


# ============ Conversation Summaries ============

@router.get("/conversations", response_model=ConversationSummaryList)
async def list_conversations(
    property_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List conversation summaries."""
    # Verify access
    if property_id:
        await verify_property_access(property_id, current_user, db)
    if contact_id:
        await verify_contact_access(contact_id, current_user, db)

    service = get_memory_service(db)
    conversations = await service.get_recent_conversations(
        property_id=property_id,
        contact_id=contact_id,
        limit=limit
    )

    return ConversationSummaryList(
        conversations=[service._conversation_to_response(c) for c in conversations],
        total=len(conversations)
    )


# ============ Contact Preferences ============

@router.get("/contacts/{contact_id}/preferences", response_model=ContactPreferenceResponse)
async def get_contact_preferences(
    contact_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get communication preferences for a contact."""
    await verify_contact_access(contact_id, current_user, db)

    service = get_memory_service(db)
    pref = await service.get_or_create_preferences(contact_id)
    return ContactPreferenceResponse.model_validate(pref)


@router.patch("/contacts/{contact_id}/preferences", response_model=ContactPreferenceResponse)
async def update_contact_preferences(
    contact_id: int,
    update_data: ContactPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update communication preferences for a contact."""
    await verify_contact_access(contact_id, current_user, db)

    service = get_memory_service(db)
    pref = await service.update_preferences(contact_id, update_data)
    return ContactPreferenceResponse.model_validate(pref)


# ============ Property-scoped endpoints ============

@router.get("/properties/{property_id}/memories", response_model=MemoryList)
async def list_property_memories(
    property_id: int,
    memory_type: Optional[MemoryType] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all memories for a property."""
    await verify_property_access(property_id, current_user, db)

    service = get_memory_service(db)
    memory_types = [memory_type] if memory_type else None

    memories = await service.list_memories(
        property_id=property_id,
        memory_types=memory_types,
        limit=limit
    )

    return MemoryList(
        memories=[MemoryResponse.model_validate(m) for m in memories],
        total=len(memories)
    )


@router.get("/properties/{property_id}/contacts/{contact_id}/memories", response_model=MemoryList)
async def list_contact_memories(
    property_id: int,
    contact_id: int,
    memory_type: Optional[MemoryType] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all memories for a specific contact."""
    await verify_property_access(property_id, current_user, db)
    await verify_contact_access(contact_id, current_user, db)

    service = get_memory_service(db)
    memory_types = [memory_type] if memory_type else None

    memories = await service.list_memories(
        contact_id=contact_id,
        memory_types=memory_types,
        limit=limit
    )

    return MemoryList(
        memories=[MemoryResponse.model_validate(m) for m in memories],
        total=len(memories)
    )


@router.post("/properties/{property_id}/contacts/{contact_id}/context", response_model=AgentContext)
async def get_contact_context(
    property_id: int,
    contact_id: int,
    query: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get full agent context for a contact.

    Shortcut for getting context with both property and contact specified.
    """
    await verify_property_access(property_id, current_user, db)
    await verify_contact_access(contact_id, current_user, db)

    service = get_memory_service(db)
    request = AgentContextRequest(
        property_id=property_id,
        contact_id=contact_id,
        query=query
    )
    return await service.get_agent_context(request)
