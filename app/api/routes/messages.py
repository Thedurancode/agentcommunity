from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.user import User
from app.models.message import (
    Conversation, ConversationType, ConversationParticipant,
    DirectMessage, MessageStatus
)
from app.schemas.message import (
    ConversationCreate,
    ConversationResponse,
    ConversationWithDetails,
    ConversationList,
    ConversationSummary,
    MessageCreate,
    MessageUpdate,
    MessageResponse,
    MessageWithSender,
    MessageList,
    ParticipantUpdate,
    ParticipantWithUser,
    ReadReceipt,
)
from app.schemas.user import UserResponse
from app.api.deps import get_current_user

router = APIRouter(prefix="/messages", tags=["messages"])


# ============== HELPER FUNCTIONS ==============

async def get_or_create_direct_conversation(
    db: AsyncSession,
    user1_id: int,
    user2_id: int
) -> Conversation:
    """Get existing direct conversation between two users, or create one."""
    # Find existing conversation where both users are participants
    result = await db.execute(
        select(Conversation)
        .join(ConversationParticipant)
        .where(
            Conversation.type == ConversationType.DIRECT,
            ConversationParticipant.user_id.in_([user1_id, user2_id])
        )
        .group_by(Conversation.id)
        .having(func.count(ConversationParticipant.id) == 2)
    )

    # Check if both users are in the same conversation
    conversations = result.scalars().all()
    for conv in conversations:
        # Verify both users are participants
        participants_result = await db.execute(
            select(ConversationParticipant.user_id)
            .where(ConversationParticipant.conversation_id == conv.id)
        )
        participant_ids = set(participants_result.scalars().all())
        if participant_ids == {user1_id, user2_id}:
            return conv

    # Create new conversation
    conversation = Conversation(type=ConversationType.DIRECT)
    db.add(conversation)
    await db.flush()

    # Add both participants
    for user_id in [user1_id, user2_id]:
        participant = ConversationParticipant(
            conversation_id=conversation.id,
            user_id=user_id
        )
        db.add(participant)

    await db.commit()
    await db.refresh(conversation)
    return conversation


async def get_conversation_for_user(
    db: AsyncSession,
    conversation_id: int,
    user_id: int
) -> tuple[Conversation, ConversationParticipant]:
    """Get conversation and verify user is a participant."""
    result = await db.execute(
        select(Conversation, ConversationParticipant)
        .join(ConversationParticipant)
        .where(
            Conversation.id == conversation_id,
            ConversationParticipant.user_id == user_id,
            ConversationParticipant.left_at.is_(None)
        )
    )
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    return row[0], row[1]


# ============== CONVERSATION ENDPOINTS ==============

@router.get("", response_model=ConversationList)
async def list_conversations(
    include_archived: bool = Query(False, description="Include archived conversations"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all conversations for the current user."""
    query = (
        select(Conversation, ConversationParticipant)
        .join(ConversationParticipant)
        .where(
            ConversationParticipant.user_id == current_user.id,
            ConversationParticipant.left_at.is_(None)
        )
    )

    if not include_archived:
        query = query.where(ConversationParticipant.is_archived == False)

    # Order: pinned first, then by last message
    query = query.order_by(
        ConversationParticipant.is_pinned.desc(),
        Conversation.last_message_at.desc().nullslast()
    ).offset(skip).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    conversations = []
    for conv, participant in rows:
        # Get other participants
        participants_result = await db.execute(
            select(ConversationParticipant)
            .options(selectinload(ConversationParticipant.user))
            .where(
                ConversationParticipant.conversation_id == conv.id,
                ConversationParticipant.left_at.is_(None)
            )
        )
        all_participants = participants_result.scalars().all()

        # Build participant list
        participant_list = []
        other_user = None
        for p in all_participants:
            participant_list.append(ParticipantWithUser(
                id=p.id,
                user_id=p.user_id,
                is_muted=p.is_muted,
                is_archived=p.is_archived,
                is_pinned=p.is_pinned,
                unread_count=p.unread_count,
                last_read_at=p.last_read_at,
                joined_at=p.joined_at,
                user=UserResponse.model_validate(p.user) if p.user else None
            ))
            if p.user_id != current_user.id and p.user:
                other_user = UserResponse.model_validate(p.user)

        conversations.append(ConversationWithDetails(
            id=conv.id,
            type=conv.type,
            name=conv.name,
            last_message_preview=conv.last_message_preview,
            last_message_at=conv.last_message_at,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            participants=participant_list,
            unread_count=participant.unread_count,
            other_user=other_user
        ))

    # Get total count
    count_query = (
        select(func.count(Conversation.id))
        .join(ConversationParticipant)
        .where(
            ConversationParticipant.user_id == current_user.id,
            ConversationParticipant.left_at.is_(None)
        )
    )
    if not include_archived:
        count_query = count_query.where(ConversationParticipant.is_archived == False)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return ConversationList(conversations=conversations, total=total)


@router.post("", response_model=ConversationWithDetails, status_code=status.HTTP_201_CREATED)
async def start_conversation(
    data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Start a new conversation with another user."""
    if data.recipient_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot start conversation with yourself"
        )

    # Verify recipient exists
    recipient_result = await db.execute(
        select(User).where(User.id == data.recipient_id)
    )
    recipient = recipient_result.scalar_one_or_none()
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipient not found"
        )

    # Get or create conversation
    conversation = await get_or_create_direct_conversation(
        db, current_user.id, data.recipient_id
    )

    # Send initial message if provided
    if data.initial_message:
        message = DirectMessage(
            conversation_id=conversation.id,
            sender_id=current_user.id,
            content=data.initial_message
        )
        db.add(message)

        # Update conversation
        preview = data.initial_message[:200] if len(data.initial_message) > 200 else data.initial_message
        conversation.last_message_preview = preview
        conversation.last_message_at = datetime.utcnow()

        # Update recipient's unread count
        await db.execute(
            select(ConversationParticipant)
            .where(
                ConversationParticipant.conversation_id == conversation.id,
                ConversationParticipant.user_id == data.recipient_id
            )
        )
        recipient_participant = (await db.execute(
            select(ConversationParticipant)
            .where(
                ConversationParticipant.conversation_id == conversation.id,
                ConversationParticipant.user_id == data.recipient_id
            )
        )).scalar_one()
        recipient_participant.unread_count += 1

        await db.commit()

    # Build response
    participants_result = await db.execute(
        select(ConversationParticipant)
        .options(selectinload(ConversationParticipant.user))
        .where(ConversationParticipant.conversation_id == conversation.id)
    )
    all_participants = participants_result.scalars().all()

    participant_list = []
    other_user = None
    my_unread = 0
    for p in all_participants:
        participant_list.append(ParticipantWithUser(
            id=p.id,
            user_id=p.user_id,
            is_muted=p.is_muted,
            is_archived=p.is_archived,
            is_pinned=p.is_pinned,
            unread_count=p.unread_count,
            last_read_at=p.last_read_at,
            joined_at=p.joined_at,
            user=UserResponse.model_validate(p.user) if p.user else None
        ))
        if p.user_id != current_user.id and p.user:
            other_user = UserResponse.model_validate(p.user)
        if p.user_id == current_user.id:
            my_unread = p.unread_count

    await db.refresh(conversation)

    return ConversationWithDetails(
        id=conversation.id,
        type=conversation.type,
        name=conversation.name,
        last_message_preview=conversation.last_message_preview,
        last_message_at=conversation.last_message_at,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        participants=participant_list,
        unread_count=my_unread,
        other_user=other_user
    )


@router.get("/{conversation_id}", response_model=ConversationWithDetails)
async def get_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific conversation."""
    conversation, my_participant = await get_conversation_for_user(
        db, conversation_id, current_user.id
    )

    # Get all participants
    participants_result = await db.execute(
        select(ConversationParticipant)
        .options(selectinload(ConversationParticipant.user))
        .where(
            ConversationParticipant.conversation_id == conversation.id,
            ConversationParticipant.left_at.is_(None)
        )
    )
    all_participants = participants_result.scalars().all()

    participant_list = []
    other_user = None
    for p in all_participants:
        participant_list.append(ParticipantWithUser(
            id=p.id,
            user_id=p.user_id,
            is_muted=p.is_muted,
            is_archived=p.is_archived,
            is_pinned=p.is_pinned,
            unread_count=p.unread_count,
            last_read_at=p.last_read_at,
            joined_at=p.joined_at,
            user=UserResponse.model_validate(p.user) if p.user else None
        ))
        if p.user_id != current_user.id and p.user:
            other_user = UserResponse.model_validate(p.user)

    return ConversationWithDetails(
        id=conversation.id,
        type=conversation.type,
        name=conversation.name,
        last_message_preview=conversation.last_message_preview,
        last_message_at=conversation.last_message_at,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        participants=participant_list,
        unread_count=my_participant.unread_count,
        other_user=other_user
    )


@router.patch("/{conversation_id}/settings", response_model=ParticipantWithUser)
async def update_conversation_settings(
    conversation_id: int,
    settings: ParticipantUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update conversation settings (mute, archive, pin)."""
    _, participant = await get_conversation_for_user(db, conversation_id, current_user.id)

    update_data = settings.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(participant, field, value)

    await db.commit()
    await db.refresh(participant)

    # Get user info
    user_result = await db.execute(
        select(User).where(User.id == participant.user_id)
    )
    user = user_result.scalar_one()

    return ParticipantWithUser(
        id=participant.id,
        user_id=participant.user_id,
        is_muted=participant.is_muted,
        is_archived=participant.is_archived,
        is_pinned=participant.is_pinned,
        unread_count=participant.unread_count,
        last_read_at=participant.last_read_at,
        joined_at=participant.joined_at,
        user=UserResponse.model_validate(user)
    )


# ============== MESSAGE ENDPOINTS ==============

@router.get("/{conversation_id}/messages", response_model=MessageList)
async def list_messages(
    conversation_id: int,
    before_id: Optional[int] = Query(None, description="Get messages before this ID"),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get messages in a conversation (newest first)."""
    await get_conversation_for_user(db, conversation_id, current_user.id)

    query = (
        select(DirectMessage)
        .options(selectinload(DirectMessage.sender))
        .where(
            DirectMessage.conversation_id == conversation_id,
            DirectMessage.is_deleted == False
        )
    )

    if before_id:
        query = query.where(DirectMessage.id < before_id)

    query = query.order_by(DirectMessage.created_at.desc()).limit(limit + 1)

    result = await db.execute(query)
    messages = result.scalars().all()

    has_more = len(messages) > limit
    if has_more:
        messages = messages[:limit]

    # Build response (reverse to chronological order)
    message_list = []
    for msg in reversed(messages):
        reply_to = None
        if msg.reply_to_id:
            reply_result = await db.execute(
                select(DirectMessage).where(DirectMessage.id == msg.reply_to_id)
            )
            reply_msg = reply_result.scalar_one_or_none()
            if reply_msg:
                reply_to = MessageResponse.model_validate(reply_msg)

        message_list.append(MessageWithSender(
            id=msg.id,
            conversation_id=msg.conversation_id,
            sender_id=msg.sender_id,
            content=msg.content,
            attachment=msg.attachment,
            reply_to_id=msg.reply_to_id,
            status=msg.status,
            is_edited=msg.is_edited,
            edited_at=msg.edited_at,
            is_deleted=msg.is_deleted,
            created_at=msg.created_at,
            sender=UserResponse.model_validate(msg.sender) if msg.sender else None,
            reply_to=reply_to
        ))

    # Get total count
    count_result = await db.execute(
        select(func.count(DirectMessage.id))
        .where(
            DirectMessage.conversation_id == conversation_id,
            DirectMessage.is_deleted == False
        )
    )
    total = count_result.scalar() or 0

    return MessageList(messages=message_list, total=total, has_more=has_more)


@router.post("/{conversation_id}/messages", response_model=MessageWithSender, status_code=status.HTTP_201_CREATED)
async def send_message(
    conversation_id: int,
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a message in a conversation."""
    conversation, _ = await get_conversation_for_user(db, conversation_id, current_user.id)

    # Validate reply_to if provided
    if data.reply_to_id:
        reply_result = await db.execute(
            select(DirectMessage).where(
                DirectMessage.id == data.reply_to_id,
                DirectMessage.conversation_id == conversation_id
            )
        )
        if not reply_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reply message not found in this conversation"
            )

    # Create message
    message = DirectMessage(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        content=data.content,
        attachment=data.attachment,
        reply_to_id=data.reply_to_id
    )
    db.add(message)

    # Update conversation
    preview = data.content[:200] if len(data.content) > 200 else data.content
    conversation.last_message_preview = preview
    conversation.last_message_at = datetime.utcnow()

    # Update unread counts for other participants
    participants_result = await db.execute(
        select(ConversationParticipant)
        .where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id != current_user.id,
            ConversationParticipant.left_at.is_(None)
        )
    )
    for participant in participants_result.scalars().all():
        participant.unread_count += 1

    await db.commit()
    await db.refresh(message)

    # Get reply_to if exists
    reply_to = None
    if message.reply_to_id:
        reply_result = await db.execute(
            select(DirectMessage).where(DirectMessage.id == message.reply_to_id)
        )
        reply_msg = reply_result.scalar_one_or_none()
        if reply_msg:
            reply_to = MessageResponse.model_validate(reply_msg)

    return MessageWithSender(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        content=message.content,
        attachment=message.attachment,
        reply_to_id=message.reply_to_id,
        status=message.status,
        is_edited=message.is_edited,
        edited_at=message.edited_at,
        is_deleted=message.is_deleted,
        created_at=message.created_at,
        sender=UserResponse.model_validate(current_user),
        reply_to=reply_to
    )


@router.patch("/{conversation_id}/messages/{message_id}", response_model=MessageResponse)
async def edit_message(
    conversation_id: int,
    message_id: int,
    data: MessageUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Edit a message (only by sender)."""
    await get_conversation_for_user(db, conversation_id, current_user.id)

    result = await db.execute(
        select(DirectMessage).where(
            DirectMessage.id == message_id,
            DirectMessage.conversation_id == conversation_id
        )
    )
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    if message.sender_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Can only edit your own messages")

    if message.is_deleted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot edit deleted message")

    message.content = data.content
    message.is_edited = True
    message.edited_at = datetime.utcnow()

    await db.commit()
    await db.refresh(message)
    return message


@router.delete("/{conversation_id}/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    conversation_id: int,
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a message (soft delete, only by sender)."""
    await get_conversation_for_user(db, conversation_id, current_user.id)

    result = await db.execute(
        select(DirectMessage).where(
            DirectMessage.id == message_id,
            DirectMessage.conversation_id == conversation_id
        )
    )
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    if message.sender_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Can only delete your own messages")

    message.is_deleted = True
    message.deleted_at = datetime.utcnow()
    message.content = "[Message deleted]"

    await db.commit()
    return None


@router.post("/{conversation_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_as_read(
    conversation_id: int,
    data: Optional[ReadReceipt] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark conversation as read."""
    _, participant = await get_conversation_for_user(db, conversation_id, current_user.id)

    participant.unread_count = 0
    participant.last_read_at = datetime.utcnow()

    if data and data.message_id:
        participant.last_read_message_id = data.message_id

    await db.commit()
    return None


# ============== UNREAD COUNT ==============

@router.get("/unread/count")
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get total unread message count across all conversations."""
    result = await db.execute(
        select(func.sum(ConversationParticipant.unread_count))
        .where(
            ConversationParticipant.user_id == current_user.id,
            ConversationParticipant.left_at.is_(None),
            ConversationParticipant.is_muted == False
        )
    )
    total_unread = result.scalar() or 0

    # Get count of conversations with unread
    conv_result = await db.execute(
        select(func.count(ConversationParticipant.id))
        .where(
            ConversationParticipant.user_id == current_user.id,
            ConversationParticipant.left_at.is_(None),
            ConversationParticipant.unread_count > 0
        )
    )
    conversations_with_unread = conv_result.scalar() or 0

    return {
        "total_unread": total_unread,
        "conversations_with_unread": conversations_with_unread
    }
