from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, EmailStr

from app.models.support_ticket import TicketPriority, TicketStatus, TicketCategory
from app.schemas.user import UserResponse


# Ticket Comment Schemas
class TicketCommentBase(BaseModel):
    content: str
    is_internal: bool = False


class TicketCommentCreate(TicketCommentBase):
    author_name: Optional[str] = None
    author_email: Optional[EmailStr] = None


class TicketCommentResponse(TicketCommentBase):
    id: int
    ticket_id: int
    author_id: Optional[int] = None
    author_name: Optional[str] = None
    author_email: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TicketCommentWithAuthor(TicketCommentResponse):
    author: Optional[UserResponse] = None


# Support Ticket Schemas
class SupportTicketBase(BaseModel):
    title: str
    description: str
    category: TicketCategory = TicketCategory.OTHER
    priority: TicketPriority = TicketPriority.MEDIUM


class SupportTicketCreate(SupportTicketBase):
    submitter_name: Optional[str] = None
    submitter_email: EmailStr


class SupportTicketUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[TicketCategory] = None
    priority: Optional[TicketPriority] = None
    status: Optional[TicketStatus] = None
    assigned_to_id: Optional[int] = None


class SupportTicketResponse(SupportTicketBase):
    id: int
    project_id: int
    status: TicketStatus
    ticket_number: str
    submitted_by_id: Optional[int] = None
    submitter_name: Optional[str] = None
    submitter_email: str
    assigned_to_id: Optional[int] = None
    converted_to_issue_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SupportTicketWithDetails(SupportTicketResponse):
    submitted_by: Optional[UserResponse] = None
    assigned_to: Optional[UserResponse] = None
    comments: List[TicketCommentResponse] = []


class SupportTicketList(BaseModel):
    tickets: List[SupportTicketResponse]
    total: int


# Status update response
class TicketStatusUpdate(BaseModel):
    status: TicketStatus


class TicketAssignment(BaseModel):
    assigned_to_id: Optional[int] = None


class TicketToIssueConversion(BaseModel):
    assignee_id: Optional[int] = None
    keep_ticket_open: bool = False
