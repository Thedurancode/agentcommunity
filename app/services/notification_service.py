"""
Notification Service - Helper functions for creating notifications throughout the app.

Usage:
    from app.services.notification_service import NotificationService

    # In an endpoint or service:
    await NotificationService.notify_follow(db, follower_user, followed_user)
    await NotificationService.notify_post_comment(db, commenter, post)
"""

from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.models.notification import Notification, NotificationType, NotificationPriority


class NotificationService:
    """Service for creating notifications."""

    @staticmethod
    async def create_notification(
        db: AsyncSession,
        user_id: int,
        notification_type: NotificationType,
        title: str,
        message: str,
        actor_id: Optional[int] = None,
        link: Optional[str] = None,
        action_text: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        extra_data: Optional[str] = None,
    ) -> Notification:
        """Create a single notification."""
        notif = Notification(
            user_id=user_id,
            type=notification_type,
            priority=priority,
            title=title,
            message=message,
            link=link,
            action_text=action_text,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            extra_data=extra_data,
        )
        db.add(notif)
        await db.flush()  # Get the ID without committing
        return notif

    @staticmethod
    async def create_bulk_notifications(
        db: AsyncSession,
        user_ids: List[int],
        notification_type: NotificationType,
        title: str,
        message: str,
        **kwargs
    ) -> int:
        """Create notifications for multiple users."""
        count = 0
        for user_id in user_ids:
            await NotificationService.create_notification(
                db=db,
                user_id=user_id,
                notification_type=notification_type,
                title=title,
                message=message,
                **kwargs
            )
            count += 1
        return count

    # ============== SOCIAL NOTIFICATIONS ==============

    @staticmethod
    async def notify_follow(
        db: AsyncSession,
        follower: User,
        followed_user_id: int
    ) -> Notification:
        """Notify user that someone followed them."""
        return await NotificationService.create_notification(
            db=db,
            user_id=followed_user_id,
            notification_type=NotificationType.FOLLOW,
            title="New Follower",
            message=f"{follower.username} started following you",
            actor_id=follower.id,
            link=f"/developers/{follower.id}",
            action_text="View Profile",
            entity_type="user",
            entity_id=follower.id,
        )

    @staticmethod
    async def notify_post_like(
        db: AsyncSession,
        liker: User,
        post_author_id: int,
        post_id: int
    ) -> Optional[Notification]:
        """Notify user that someone liked their post."""
        if liker.id == post_author_id:
            return None  # Don't notify self-likes

        return await NotificationService.create_notification(
            db=db,
            user_id=post_author_id,
            notification_type=NotificationType.POST_LIKE,
            title="Post Liked",
            message=f"{liker.username} liked your post",
            actor_id=liker.id,
            link=f"/feed/posts/{post_id}",
            action_text="View Post",
            entity_type="post",
            entity_id=post_id,
        )

    @staticmethod
    async def notify_post_comment(
        db: AsyncSession,
        commenter: User,
        post_author_id: int,
        post_id: int,
        comment_preview: str = ""
    ) -> Optional[Notification]:
        """Notify user that someone commented on their post."""
        if commenter.id == post_author_id:
            return None

        preview = comment_preview[:50] + "..." if len(comment_preview) > 50 else comment_preview

        return await NotificationService.create_notification(
            db=db,
            user_id=post_author_id,
            notification_type=NotificationType.POST_COMMENT,
            title="New Comment",
            message=f"{commenter.username} commented: {preview}",
            actor_id=commenter.id,
            link=f"/feed/posts/{post_id}",
            action_text="View Comment",
            entity_type="post",
            entity_id=post_id,
        )

    @staticmethod
    async def notify_comment_reply(
        db: AsyncSession,
        replier: User,
        original_commenter_id: int,
        post_id: int,
        comment_id: int,
        reply_preview: str = ""
    ) -> Optional[Notification]:
        """Notify user that someone replied to their comment."""
        if replier.id == original_commenter_id:
            return None

        preview = reply_preview[:50] + "..." if len(reply_preview) > 50 else reply_preview

        return await NotificationService.create_notification(
            db=db,
            user_id=original_commenter_id,
            notification_type=NotificationType.COMMENT_REPLY,
            title="New Reply",
            message=f"{replier.username} replied: {preview}",
            actor_id=replier.id,
            link=f"/feed/posts/{post_id}#comment-{comment_id}",
            action_text="View Reply",
            entity_type="comment",
            entity_id=comment_id,
        )

    # ============== BLOG NOTIFICATIONS ==============

    @staticmethod
    async def notify_blog_comment(
        db: AsyncSession,
        commenter_name: str,
        blog_author_id: int,
        blog_id: int,
        blog_title: str,
        commenter_id: Optional[int] = None
    ) -> Optional[Notification]:
        """Notify blog author of a new comment."""
        if commenter_id == blog_author_id:
            return None

        return await NotificationService.create_notification(
            db=db,
            user_id=blog_author_id,
            notification_type=NotificationType.BLOG_COMMENT,
            title="New Blog Comment",
            message=f"{commenter_name} commented on '{blog_title}'",
            actor_id=commenter_id,
            link=f"/blogs/{blog_id}",
            action_text="View Comment",
            entity_type="blog",
            entity_id=blog_id,
        )

    @staticmethod
    async def notify_blog_like(
        db: AsyncSession,
        liker: User,
        blog_author_id: int,
        blog_id: int,
        blog_title: str
    ) -> Optional[Notification]:
        """Notify blog author that someone liked their blog."""
        if liker.id == blog_author_id:
            return None

        return await NotificationService.create_notification(
            db=db,
            user_id=blog_author_id,
            notification_type=NotificationType.BLOG_LIKE,
            title="Blog Liked",
            message=f"{liker.username} liked '{blog_title}'",
            actor_id=liker.id,
            link=f"/blogs/{blog_id}",
            action_text="View Blog",
            entity_type="blog",
            entity_id=blog_id,
        )

    # ============== PROJECT NOTIFICATIONS ==============

    @staticmethod
    async def notify_project_invite(
        db: AsyncSession,
        inviter: User,
        invitee_id: int,
        project_id: int,
        project_name: str,
        role: str
    ) -> Notification:
        """Notify user they've been invited to a project."""
        return await NotificationService.create_notification(
            db=db,
            user_id=invitee_id,
            notification_type=NotificationType.PROJECT_INVITE,
            title="Project Invitation",
            message=f"{inviter.username} invited you to join '{project_name}' as {role}",
            actor_id=inviter.id,
            link=f"/projects/{project_id}",
            action_text="View Project",
            entity_type="project",
            entity_id=project_id,
            priority=NotificationPriority.HIGH,
        )

    @staticmethod
    async def notify_project_role_change(
        db: AsyncSession,
        user_id: int,
        project_id: int,
        project_name: str,
        new_role: str
    ) -> Notification:
        """Notify user their role changed in a project."""
        return await NotificationService.create_notification(
            db=db,
            user_id=user_id,
            notification_type=NotificationType.PROJECT_ROLE_CHANGE,
            title="Role Updated",
            message=f"Your role in '{project_name}' changed to {new_role}",
            link=f"/projects/{project_id}",
            action_text="View Project",
            entity_type="project",
            entity_id=project_id,
        )

    @staticmethod
    async def notify_issue_assigned(
        db: AsyncSession,
        assigner: User,
        assignee_id: int,
        project_id: int,
        issue_id: int,
        issue_title: str
    ) -> Optional[Notification]:
        """Notify user they've been assigned an issue."""
        if assigner.id == assignee_id:
            return None

        return await NotificationService.create_notification(
            db=db,
            user_id=assignee_id,
            notification_type=NotificationType.ISSUE_ASSIGNED,
            title="Issue Assigned",
            message=f"{assigner.username} assigned you: '{issue_title}'",
            actor_id=assigner.id,
            link=f"/projects/{project_id}/issues/{issue_id}",
            action_text="View Issue",
            entity_type="issue",
            entity_id=issue_id,
            priority=NotificationPriority.HIGH,
        )

    # ============== CLASS NOTIFICATIONS ==============

    @staticmethod
    async def notify_ticket_confirmed(
        db: AsyncSession,
        user_id: int,
        class_id: int,
        class_title: str,
        order_number: str
    ) -> Notification:
        """Notify user their ticket purchase is confirmed."""
        return await NotificationService.create_notification(
            db=db,
            user_id=user_id,
            notification_type=NotificationType.TICKET_CONFIRMED,
            title="Ticket Confirmed",
            message=f"Your ticket for '{class_title}' is confirmed! Order: {order_number}",
            link=f"/classes/{class_id}",
            action_text="View Details",
            entity_type="class",
            entity_id=class_id,
            priority=NotificationPriority.HIGH,
        )

    @staticmethod
    async def notify_class_reminder(
        db: AsyncSession,
        user_id: int,
        class_id: int,
        class_title: str,
        time_until: str
    ) -> Notification:
        """Send a class reminder notification."""
        return await NotificationService.create_notification(
            db=db,
            user_id=user_id,
            notification_type=NotificationType.CLASS_REMINDER,
            title="Class Reminder",
            message=f"'{class_title}' starts in {time_until}",
            link=f"/classes/{class_id}",
            action_text="View Class",
            entity_type="class",
            entity_id=class_id,
            priority=NotificationPriority.HIGH,
        )

    # ============== SUPPORT NOTIFICATIONS ==============

    @staticmethod
    async def notify_support_reply(
        db: AsyncSession,
        user_id: int,
        ticket_id: int,
        ticket_subject: str
    ) -> Notification:
        """Notify user of a reply to their support ticket."""
        return await NotificationService.create_notification(
            db=db,
            user_id=user_id,
            notification_type=NotificationType.SUPPORT_REPLY,
            title="Support Reply",
            message=f"New reply on your ticket: '{ticket_subject}'",
            link=f"/support/{ticket_id}",
            action_text="View Ticket",
            entity_type="support_ticket",
            entity_id=ticket_id,
        )

    @staticmethod
    async def notify_support_resolved(
        db: AsyncSession,
        user_id: int,
        ticket_id: int,
        ticket_subject: str
    ) -> Notification:
        """Notify user their support ticket was resolved."""
        return await NotificationService.create_notification(
            db=db,
            user_id=user_id,
            notification_type=NotificationType.SUPPORT_RESOLVED,
            title="Ticket Resolved",
            message=f"Your ticket '{ticket_subject}' has been resolved",
            link=f"/support/{ticket_id}",
            action_text="View Ticket",
            entity_type="support_ticket",
            entity_id=ticket_id,
        )

    # ============== SYSTEM NOTIFICATIONS ==============

    @staticmethod
    async def notify_welcome(
        db: AsyncSession,
        user_id: int,
        username: str
    ) -> Notification:
        """Send welcome notification to new user."""
        return await NotificationService.create_notification(
            db=db,
            user_id=user_id,
            notification_type=NotificationType.WELCOME,
            title="Welcome to Code Live OS!",
            message=f"Hi {username}! Welcome to our community. Start by creating your developer profile.",
            link="/developers/me",
            action_text="Create Profile",
        )

    @staticmethod
    async def notify_system_announcement(
        db: AsyncSession,
        user_ids: List[int],
        title: str,
        message: str,
        link: Optional[str] = None
    ) -> int:
        """Send system announcement to multiple users."""
        return await NotificationService.create_bulk_notifications(
            db=db,
            user_ids=user_ids,
            notification_type=NotificationType.SYSTEM,
            title=title,
            message=message,
            link=link,
            priority=NotificationPriority.HIGH,
        )
