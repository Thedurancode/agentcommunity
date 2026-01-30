# Database models - All models must be imported here for SQLAlchemy to create tables

from app.models.user import User, UserRole
from app.models.project import Project, ProjectStatus
from app.models.team_member import TeamMember, TeamRole
from app.models.issue import Issue, IssueState
from app.models.pull_request import PullRequest, PRState
from app.models.brand import Brand
from app.models.note import Note
from app.models.recap import Recap
from app.models.video import Video
from app.models.post import Post, PostComment, PostLike, CommentLike, PostSave, PostVisibility
from app.models.episode import Episode
from app.models.episode_segment import EpisodeSegment, SegmentType
from app.models.voice_note import VoiceNote, TranscriptionStatus
from app.models.class_model import (
    Class, ClassStatus, ClassDate, Ticket, TicketStatus, TicketTier,
    ClassAttendee, AttendeeStatus, TicketSale, PaymentStatus
)
from app.models.support_ticket import SupportTicket, TicketComment, TicketPriority, TicketStatus as SupportTicketStatus, TicketCategory
from app.models.developer_profile import DeveloperProfile, DeveloperFollow, DeveloperStatus
from app.models.blog import Blog, BlogImage, BlogComment, BlogStatus
from app.models.notification import Notification, NotificationPreference, NotificationType, NotificationPriority
from app.models.message import Conversation, ConversationParticipant, DirectMessage, ConversationType, MessageStatus
from app.models.property import Property, PropertyContact, PropertyContract, PropertyPhase, PropertyNote, PropertyPhoneCall, PropertySMS, PropertyEnrichment, PropertyStatus, ContactType, ContractStatus, ContractType, PhaseStatus, CallStatus, SMSStatus, SMSDirection
from app.models.api_key import APIKey

__all__ = [
    # User
    "User", "UserRole",
    # Project
    "Project", "ProjectStatus",
    # Team
    "TeamMember", "TeamRole",
    # Issues & PRs
    "Issue", "IssueState",
    "PullRequest", "PRState",
    # Brand
    "Brand",
    # Notes & Recap
    "Note", "Recap",
    # Video
    "Video",
    # Posts/Feed
    "Post", "PostComment", "PostLike", "CommentLike", "PostSave", "PostVisibility",
    # Episodes
    "Episode", "EpisodeSegment", "SegmentType",
    # Voice Notes
    "VoiceNote", "TranscriptionStatus",
    # Classes
    "Class", "ClassStatus", "ClassDate", "Ticket", "TicketStatus", "TicketTier",
    "ClassAttendee", "AttendeeStatus", "TicketSale", "PaymentStatus",
    # Support
    "SupportTicket", "TicketComment", "TicketPriority", "SupportTicketStatus", "TicketCategory",
    # Developer Profiles
    "DeveloperProfile", "DeveloperFollow", "DeveloperStatus",
    # Blog
    "Blog", "BlogImage", "BlogComment", "BlogStatus",
    # Notifications
    "Notification", "NotificationPreference", "NotificationType", "NotificationPriority",
    # Messages
    "Conversation", "ConversationParticipant", "DirectMessage", "ConversationType", "MessageStatus",
    # Properties
    "Property", "PropertyContact", "PropertyContract", "PropertyPhase", "PropertyNote", "PropertyPhoneCall", "PropertySMS",
    "PropertyStatus", "ContactType", "ContractStatus", "ContractType", "PhaseStatus", "CallStatus", "SMSStatus", "SMSDirection",
    # API Keys
    "APIKey",
]
