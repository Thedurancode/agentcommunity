from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel

from app.models.notification import NotificationType, NotificationPriority


# Actor info (who triggered the notification)
class NotificationActor(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    profile_image: Optional[str] = None

    class Config:
        from_attributes = True


# Notification Schemas
class NotificationBase(BaseModel):
    type: NotificationType
    title: str
    message: str
    link: Optional[str] = None
    action_text: Optional[str] = None


class NotificationCreate(NotificationBase):
    user_id: int
    priority: NotificationPriority = NotificationPriority.NORMAL
    actor_id: Optional[int] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    extra_data: Optional[str] = None


class NotificationResponse(NotificationBase):
    id: int
    user_id: int
    priority: NotificationPriority
    actor_id: Optional[int] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationWithActor(NotificationResponse):
    actor: Optional[NotificationActor] = None


class NotificationList(BaseModel):
    notifications: List[NotificationWithActor]
    total: int
    unread_count: int


class NotificationMarkRead(BaseModel):
    notification_ids: List[int]


class NotificationMarkAllRead(BaseModel):
    before_date: Optional[datetime] = None


# Notification Preferences Schemas
class NotificationPreferenceBase(BaseModel):
    email_enabled: bool = True
    email_frequency: str = "instant"  # instant, daily, weekly, never
    quiet_hours_start: Optional[int] = None
    quiet_hours_end: Optional[int] = None
    timezone: str = "UTC"
    social_notifications: bool = True
    project_notifications: bool = True
    class_notifications: bool = True
    support_notifications: bool = True
    system_notifications: bool = True


class NotificationPreferenceCreate(NotificationPreferenceBase):
    enabled_types: Optional[List[str]] = None
    disabled_types: Optional[List[str]] = None


class NotificationPreferenceUpdate(BaseModel):
    email_enabled: Optional[bool] = None
    email_frequency: Optional[str] = None
    enabled_types: Optional[List[str]] = None
    disabled_types: Optional[List[str]] = None
    quiet_hours_start: Optional[int] = None
    quiet_hours_end: Optional[int] = None
    timezone: Optional[str] = None
    social_notifications: Optional[bool] = None
    project_notifications: Optional[bool] = None
    class_notifications: Optional[bool] = None
    support_notifications: Optional[bool] = None
    system_notifications: Optional[bool] = None


class NotificationPreferenceResponse(NotificationPreferenceBase):
    id: int
    user_id: int
    enabled_types: Optional[List[str]] = None
    disabled_types: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Notification Stats
class NotificationStats(BaseModel):
    total: int
    unread: int
    by_type: dict = {}


# Bulk notification creation
class BulkNotificationCreate(BaseModel):
    user_ids: List[int]
    type: NotificationType
    title: str
    message: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    link: Optional[str] = None
    action_text: Optional[str] = None
    actor_id: Optional[int] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
