import json
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.user import User
from app.models.notification import Notification, NotificationPreference, NotificationType, NotificationPriority
from app.schemas.notification import (
    NotificationCreate,
    NotificationResponse,
    NotificationWithActor,
    NotificationList,
    NotificationMarkRead,
    NotificationStats,
    NotificationPreferenceCreate,
    NotificationPreferenceUpdate,
    NotificationPreferenceResponse,
    NotificationActor,
    BulkNotificationCreate,
)
from app.api.deps import get_current_user


router = APIRouter(prefix="/notifications", tags=["notifications"])


def parse_json_list(json_str: Optional[str]) -> List[str]:
    """Parse JSON string to list."""
    if not json_str:
        return []
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return []


def to_json_str(items: Optional[List[str]]) -> Optional[str]:
    """Convert list to JSON string."""
    if items is None:
        return None
    return json.dumps(items)


# ============== NOTIFICATION ENDPOINTS ==============

@router.get("", response_model=NotificationList)
async def list_notifications(
    unread_only: bool = Query(False, description="Only show unread notifications"),
    type_filter: Optional[NotificationType] = Query(None, alias="type"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's notifications."""
    query = (
        select(Notification)
        .options(selectinload(Notification.actor))
        .where(Notification.user_id == current_user.id)
    )

    if unread_only:
        query = query.where(Notification.is_read == False)

    if type_filter:
        query = query.where(Notification.type == type_filter)

    # Count total
    count_query = select(func.count(Notification.id)).where(Notification.user_id == current_user.id)
    if unread_only:
        count_query = count_query.where(Notification.is_read == False)
    if type_filter:
        count_query = count_query.where(Notification.type == type_filter)

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Count unread
    unread_result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False
        )
    )
    unread_count = unread_result.scalar() or 0

    # Get paginated results
    query = query.order_by(Notification.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    notifications = result.scalars().all()

    # Build response
    notification_list = []
    for notif in notifications:
        actor_info = None
        if notif.actor:
            actor_info = NotificationActor(
                id=notif.actor.id,
                username=notif.actor.username,
                full_name=notif.actor.full_name,
                profile_image=notif.actor.profile_image,
            )

        notification_list.append(NotificationWithActor(
            **NotificationResponse.model_validate(notif).model_dump(),
            actor=actor_info
        ))

    return NotificationList(
        notifications=notification_list,
        total=total,
        unread_count=unread_count
    )


@router.get("/stats", response_model=NotificationStats)
async def get_notification_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get notification statistics for current user."""
    # Total count
    total_result = await db.execute(
        select(func.count(Notification.id)).where(Notification.user_id == current_user.id)
    )
    total = total_result.scalar() or 0

    # Unread count
    unread_result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False
        )
    )
    unread = unread_result.scalar() or 0

    # Count by type
    type_result = await db.execute(
        select(Notification.type, func.count(Notification.id))
        .where(Notification.user_id == current_user.id, Notification.is_read == False)
        .group_by(Notification.type)
    )
    by_type = {}
    for ntype, count in type_result:
        by_type[ntype.value] = count

    return NotificationStats(total=total, unread=unread, by_type=by_type)


@router.get("/{notification_id}", response_model=NotificationWithActor)
async def get_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific notification."""
    result = await db.execute(
        select(Notification)
        .options(selectinload(Notification.actor))
        .where(Notification.id == notification_id, Notification.user_id == current_user.id)
    )
    notif = result.scalar_one_or_none()

    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )

    actor_info = None
    if notif.actor:
        actor_info = NotificationActor(
            id=notif.actor.id,
            username=notif.actor.username,
            full_name=notif.actor.full_name,
            profile_image=notif.actor.profile_image,
        )

    return NotificationWithActor(
        **NotificationResponse.model_validate(notif).model_dump(),
        actor=actor_info
    )


@router.post("/mark-read", response_model=dict)
async def mark_notifications_read(
    data: NotificationMarkRead,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark specific notifications as read."""
    now = datetime.utcnow()

    result = await db.execute(
        update(Notification)
        .where(
            Notification.id.in_(data.notification_ids),
            Notification.user_id == current_user.id,
            Notification.is_read == False
        )
        .values(is_read=True, read_at=now)
    )

    await db.commit()

    return {"marked_read": result.rowcount}


@router.post("/mark-all-read", response_model=dict)
async def mark_all_notifications_read(
    before_date: Optional[datetime] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark all notifications as read."""
    now = datetime.utcnow()

    query = (
        update(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.is_read == False
        )
    )

    if before_date:
        query = query.where(Notification.created_at <= before_date)

    result = await db.execute(query.values(is_read=True, read_at=now))
    await db.commit()

    return {"marked_read": result.rowcount}


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a notification."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id
        )
    )
    notif = result.scalar_one_or_none()

    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )

    await db.delete(notif)
    await db.commit()
    return None


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_notifications(
    read_only: bool = Query(True, description="Only delete read notifications"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete all notifications (or only read ones)."""
    query = select(Notification).where(Notification.user_id == current_user.id)

    if read_only:
        query = query.where(Notification.is_read == True)

    result = await db.execute(query)
    notifications = result.scalars().all()

    for notif in notifications:
        await db.delete(notif)

    await db.commit()
    return None


# ============== PREFERENCE ENDPOINTS ==============

@router.get("/preferences/me", response_model=NotificationPreferenceResponse)
async def get_my_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's notification preferences."""
    result = await db.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == current_user.id)
    )
    prefs = result.scalar_one_or_none()

    if not prefs:
        # Create default preferences
        prefs = NotificationPreference(user_id=current_user.id)
        db.add(prefs)
        await db.commit()
        await db.refresh(prefs)

    response = NotificationPreferenceResponse.model_validate(prefs)
    response.enabled_types = parse_json_list(prefs.enabled_types)
    response.disabled_types = parse_json_list(prefs.disabled_types)
    return response


@router.patch("/preferences/me", response_model=NotificationPreferenceResponse)
async def update_my_preferences(
    data: NotificationPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update current user's notification preferences."""
    result = await db.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == current_user.id)
    )
    prefs = result.scalar_one_or_none()

    if not prefs:
        prefs = NotificationPreference(user_id=current_user.id)
        db.add(prefs)

    update_data = data.model_dump(exclude_unset=True)

    # Handle JSON fields
    if "enabled_types" in update_data:
        update_data["enabled_types"] = to_json_str(update_data["enabled_types"])
    if "disabled_types" in update_data:
        update_data["disabled_types"] = to_json_str(update_data["disabled_types"])

    for field, value in update_data.items():
        setattr(prefs, field, value)

    await db.commit()
    await db.refresh(prefs)

    response = NotificationPreferenceResponse.model_validate(prefs)
    response.enabled_types = parse_json_list(prefs.enabled_types)
    response.disabled_types = parse_json_list(prefs.disabled_types)
    return response


# ============== ADMIN ENDPOINTS ==============

@router.post("/send", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
async def send_notification(
    data: NotificationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a notification to a user (admin only)."""
    if current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    # Verify target user exists
    user_result = await db.execute(select(User).where(User.id == data.user_id))
    if not user_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target user not found"
        )

    notif = Notification(
        user_id=data.user_id,
        type=data.type,
        priority=data.priority,
        title=data.title,
        message=data.message,
        link=data.link,
        action_text=data.action_text,
        actor_id=data.actor_id or current_user.id,
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        extra_data=data.extra_data,
    )
    db.add(notif)
    await db.commit()
    await db.refresh(notif)
    return notif


@router.post("/send-bulk", response_model=dict, status_code=status.HTTP_201_CREATED)
async def send_bulk_notifications(
    data: BulkNotificationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send notifications to multiple users (admin only)."""
    if current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    created = 0
    for user_id in data.user_ids:
        # Verify user exists
        user_result = await db.execute(select(User).where(User.id == user_id))
        if not user_result.scalar_one_or_none():
            continue

        notif = Notification(
            user_id=user_id,
            type=data.type,
            priority=data.priority,
            title=data.title,
            message=data.message,
            link=data.link,
            action_text=data.action_text,
            actor_id=data.actor_id or current_user.id,
            entity_type=data.entity_type,
            entity_id=data.entity_id,
        )
        db.add(notif)
        created += 1

    await db.commit()
    return {"sent": created, "total_requested": len(data.user_ids)}
