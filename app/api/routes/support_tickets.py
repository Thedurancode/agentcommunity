import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db, get_optional_user
from app.models.user import User
from app.models.project import Project
from app.models.support_ticket import SupportTicket, TicketComment, TicketStatus
from app.models.issue import Issue
from app.schemas.support_ticket import (
    SupportTicketCreate,
    SupportTicketUpdate,
    SupportTicketResponse,
    SupportTicketWithDetails,
    SupportTicketList,
    TicketCommentCreate,
    TicketCommentResponse,
    TicketStatusUpdate,
    TicketAssignment,
    TicketToIssueConversion,
)
from app.schemas.issue import IssueResponse

router = APIRouter(prefix="/projects/{project_id}/support-tickets", tags=["support-tickets"])


def generate_ticket_number() -> str:
    """Generate a unique ticket number."""
    return f"TKT-{uuid.uuid4().hex[:8].upper()}"


async def get_project(db: AsyncSession, project_id: int) -> Project:
    """Get project or raise 404."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def check_project_access(db: AsyncSession, project_id: int, user: User) -> Project:
    """Check if user has access to project."""
    project = await get_project(db, project_id)
    if user.role != "admin" and project.owner_id != user.id:
        from app.models.team_member import TeamMember
        result = await db.execute(
            select(TeamMember).where(
                TeamMember.project_id == project_id,
                TeamMember.user_id == user.id
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return project


# Support Ticket CRUD
@router.post("", response_model=SupportTicketResponse, status_code=status.HTTP_201_CREATED)
async def create_support_ticket(
    project_id: int,
    ticket_data: SupportTicketCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user()),
):
    """Create a new support ticket. Can be created by anyone (authenticated or not)."""
    # Verify project exists
    await get_project(db, project_id)

    ticket = SupportTicket(
        project_id=project_id,
        title=ticket_data.title,
        description=ticket_data.description,
        category=ticket_data.category,
        priority=ticket_data.priority,
        submitter_name=ticket_data.submitter_name,
        submitter_email=ticket_data.submitter_email,
        submitted_by_id=current_user.id if current_user else None,
        ticket_number=generate_ticket_number(),
    )

    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)

    return ticket


@router.get("", response_model=SupportTicketList)
async def list_support_tickets(
    project_id: int,
    status_filter: Optional[TicketStatus] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List support tickets for a project."""
    await check_project_access(db, project_id, current_user)

    query = select(SupportTicket).where(SupportTicket.project_id == project_id)
    count_query = select(func.count(SupportTicket.id)).where(SupportTicket.project_id == project_id)

    if status_filter:
        query = query.where(SupportTicket.status == status_filter)
        count_query = count_query.where(SupportTicket.status == status_filter)

    query = query.order_by(SupportTicket.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    tickets = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return SupportTicketList(tickets=tickets, total=total)


@router.get("/{ticket_id}", response_model=SupportTicketWithDetails)
async def get_support_ticket(
    project_id: int,
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a support ticket with details."""
    await check_project_access(db, project_id, current_user)

    result = await db.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.submitted_by),
            selectinload(SupportTicket.assigned_to),
            selectinload(SupportTicket.comments),
        )
        .where(SupportTicket.id == ticket_id, SupportTicket.project_id == project_id)
    )
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    return ticket


@router.get("/by-number/{ticket_number}", response_model=SupportTicketWithDetails)
async def get_ticket_by_number(
    project_id: int,
    ticket_number: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a support ticket by its ticket number (public endpoint for submitters)."""
    result = await db.execute(
        select(SupportTicket)
        .options(selectinload(SupportTicket.comments))
        .where(
            SupportTicket.ticket_number == ticket_number,
            SupportTicket.project_id == project_id
        )
    )
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    # Filter out internal comments for public view
    ticket.comments = [c for c in ticket.comments if not c.is_internal]

    return ticket


@router.put("/{ticket_id}", response_model=SupportTicketResponse)
async def update_support_ticket(
    project_id: int,
    ticket_id: int,
    ticket_data: SupportTicketUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a support ticket."""
    await check_project_access(db, project_id, current_user)

    result = await db.execute(
        select(SupportTicket).where(
            SupportTicket.id == ticket_id,
            SupportTicket.project_id == project_id
        )
    )
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    update_data = ticket_data.model_dump(exclude_unset=True)

    # Handle status changes
    if "status" in update_data:
        new_status = update_data["status"]
        if new_status == TicketStatus.RESOLVED and not ticket.resolved_at:
            ticket.resolved_at = datetime.utcnow()
        elif new_status == TicketStatus.CLOSED and not ticket.closed_at:
            ticket.closed_at = datetime.utcnow()

    for field, value in update_data.items():
        setattr(ticket, field, value)

    await db.commit()
    await db.refresh(ticket)

    return ticket


@router.patch("/{ticket_id}/status", response_model=SupportTicketResponse)
async def update_ticket_status(
    project_id: int,
    ticket_id: int,
    status_update: TicketStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update just the status of a ticket."""
    await check_project_access(db, project_id, current_user)

    result = await db.execute(
        select(SupportTicket).where(
            SupportTicket.id == ticket_id,
            SupportTicket.project_id == project_id
        )
    )
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    ticket.status = status_update.status

    if status_update.status == TicketStatus.RESOLVED and not ticket.resolved_at:
        ticket.resolved_at = datetime.utcnow()
    elif status_update.status == TicketStatus.CLOSED and not ticket.closed_at:
        ticket.closed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(ticket)

    return ticket


@router.patch("/{ticket_id}/assign", response_model=SupportTicketResponse)
async def assign_ticket(
    project_id: int,
    ticket_id: int,
    assignment: TicketAssignment,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Assign a ticket to a team member."""
    await check_project_access(db, project_id, current_user)

    result = await db.execute(
        select(SupportTicket).where(
            SupportTicket.id == ticket_id,
            SupportTicket.project_id == project_id
        )
    )
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    # Verify assignee exists if provided
    if assignment.assigned_to_id:
        assignee_result = await db.execute(
            select(User).where(User.id == assignment.assigned_to_id)
        )
        if not assignee_result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignee not found")

    ticket.assigned_to_id = assignment.assigned_to_id

    # Auto-update status if assigning
    if assignment.assigned_to_id and ticket.status == TicketStatus.OPEN:
        ticket.status = TicketStatus.IN_PROGRESS

    await db.commit()
    await db.refresh(ticket)

    return ticket


@router.post("/{ticket_id}/convert-to-issue", response_model=IssueResponse)
async def convert_ticket_to_issue(
    project_id: int,
    ticket_id: int,
    conversion_data: TicketToIssueConversion,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Convert a support ticket to an issue."""
    await check_project_access(db, project_id, current_user)

    result = await db.execute(
        select(SupportTicket).where(
            SupportTicket.id == ticket_id,
            SupportTicket.project_id == project_id
        )
    )
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    if ticket.converted_to_issue_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ticket has already been converted to an issue"
        )

    # Create issue from ticket
    issue_body = f"{ticket.description}\n\n---\n*Converted from support ticket {ticket.ticket_number}*"
    if ticket.submitter_email:
        issue_body += f"\n*Submitted by: {ticket.submitter_name or 'Unknown'} ({ticket.submitter_email})*"

    issue = Issue(
        title=ticket.title,
        body=issue_body,
        project_id=project_id,
        created_by_id=current_user.id,
        assignee_id=conversion_data.assignee_id or ticket.assigned_to_id,
    )
    db.add(issue)
    await db.flush()  # Get the issue ID

    # Link ticket to issue
    ticket.converted_to_issue_id = issue.id

    # Optionally close the ticket
    if not conversion_data.keep_ticket_open:
        ticket.status = TicketStatus.CLOSED
        ticket.closed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(issue)

    return issue


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_support_ticket(
    project_id: int,
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a support ticket."""
    await check_project_access(db, project_id, current_user)

    result = await db.execute(
        select(SupportTicket).where(
            SupportTicket.id == ticket_id,
            SupportTicket.project_id == project_id
        )
    )
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    await db.delete(ticket)
    await db.commit()


# Ticket Comments
@router.post("/{ticket_id}/comments", response_model=TicketCommentResponse, status_code=status.HTTP_201_CREATED)
async def add_comment(
    project_id: int,
    ticket_id: int,
    comment_data: TicketCommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user()),
):
    """Add a comment to a ticket. Team members can add internal comments."""
    # Get ticket
    result = await db.execute(
        select(SupportTicket).where(
            SupportTicket.id == ticket_id,
            SupportTicket.project_id == project_id
        )
    )
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    # Only team members can add internal comments
    if comment_data.is_internal and not current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team members can add internal comments"
        )

    comment = TicketComment(
        ticket_id=ticket_id,
        content=comment_data.content,
        is_internal=comment_data.is_internal if current_user else False,
        author_id=current_user.id if current_user else None,
        author_name=comment_data.author_name if not current_user else None,
        author_email=comment_data.author_email if not current_user else None,
    )

    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    return comment


@router.get("/{ticket_id}/comments", response_model=list[TicketCommentResponse])
async def list_comments(
    project_id: int,
    ticket_id: int,
    include_internal: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user()),
):
    """List comments for a ticket."""
    result = await db.execute(
        select(SupportTicket).where(
            SupportTicket.id == ticket_id,
            SupportTicket.project_id == project_id
        )
    )
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    query = select(TicketComment).where(TicketComment.ticket_id == ticket_id)

    # Only show internal comments to authenticated team members
    if not current_user or not include_internal:
        query = query.where(TicketComment.is_internal == False)

    query = query.order_by(TicketComment.created_at.asc())

    result = await db.execute(query)
    comments = result.scalars().all()

    return comments


@router.delete("/{ticket_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    project_id: int,
    ticket_id: int,
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a comment."""
    await check_project_access(db, project_id, current_user)

    result = await db.execute(
        select(TicketComment).where(
            TicketComment.id == comment_id,
            TicketComment.ticket_id == ticket_id
        )
    )
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    await db.delete(comment)
    await db.commit()
