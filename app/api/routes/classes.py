import uuid
from typing import Optional
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.user import User
from app.models.class_model import (
    Class, ClassStatus, Ticket, TicketStatus, ClassAttendee, AttendeeStatus,
    ClassDate, TicketSale, PaymentStatus, TicketTier
)
from app.models.team_member import TeamRole
from app.schemas.class_schema import (
    ClassCreate,
    ClassResponse,
    ClassUpdate,
    ClassWithDetails,
    ClassList,
    TicketCreate,
    TicketResponse,
    TicketUpdate,
    TicketList,
    TicketWithStats,
    AttendeeCreate,
    AttendeeResponse,
    AttendeeUpdate,
    AttendeeWithUser,
    AttendeeList,
    ClassDateCreate,
    ClassDateResponse,
    RegistrationResponse,
    TicketSaleCreate,
    TicketSaleResponse,
    TicketSaleUpdate,
    TicketSaleList,
    TicketSaleWithDetails,
    RefundRequest,
    SalesSummary,
    ClassHistoryItem,
    ClassHistoryList,
)
from app.models.project import Project
from app.api.deps import get_current_user
from app.api.routes.projects import check_project_access


# ============== CLASS HISTORY ROUTER (User-centric) ==============
history_router = APIRouter(prefix="/classes", tags=["class-history"])


def generate_order_number() -> str:
    """Generate a unique order number."""
    return f"ORD-{uuid.uuid4().hex[:8].upper()}"


router = APIRouter(prefix="/projects/{project_id}/classes", tags=["classes"])


# ============== CLASS ENDPOINTS ==============

@router.post("", response_model=ClassResponse, status_code=status.HTTP_201_CREATED)
async def create_class(
    project_id: int,
    class_data: ClassCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new class for a project."""
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    class_obj = Class(
        **class_data.model_dump(),
        project_id=project_id,
    )
    db.add(class_obj)
    await db.commit()
    await db.refresh(class_obj)
    return class_obj


@router.get("", response_model=ClassList)
async def list_classes(
    project_id: int,
    status_filter: Optional[ClassStatus] = Query(None, alias="status"),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all classes for a project."""
    await check_project_access(project_id, current_user, db)

    query = select(Class).where(Class.project_id == project_id)

    if status_filter:
        query = query.where(Class.status == status_filter)

    query = query.order_by(Class.start_date.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    classes = result.scalars().all()

    # Get total count
    count_query = select(Class).where(Class.project_id == project_id)
    if status_filter:
        count_query = count_query.where(Class.status == status_filter)
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    return ClassList(classes=classes, total=total)


@router.get("/{class_id}", response_model=ClassWithDetails)
async def get_class(
    project_id: int,
    class_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific class with all details."""
    await check_project_access(project_id, current_user, db)

    result = await db.execute(
        select(Class)
        .options(
            selectinload(Class.instructor),
            selectinload(Class.tickets),
            selectinload(Class.dates),
        )
        .where(Class.id == class_id, Class.project_id == project_id)
    )
    class_obj = result.scalar_one_or_none()

    if not class_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class not found",
        )

    # Get attendee count
    count_result = await db.execute(
        select(func.count(ClassAttendee.id))
        .where(ClassAttendee.class_id == class_id)
    )
    attendee_count = count_result.scalar()

    response = ClassWithDetails.model_validate(class_obj)
    response.attendee_count = attendee_count
    return response


@router.patch("/{class_id}", response_model=ClassResponse)
async def update_class(
    project_id: int,
    class_id: int,
    class_data: ClassUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a class."""
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    result = await db.execute(
        select(Class).where(Class.id == class_id, Class.project_id == project_id)
    )
    class_obj = result.scalar_one_or_none()

    if not class_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class not found",
        )

    update_data = class_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(class_obj, field, value)

    await db.commit()
    await db.refresh(class_obj)
    return class_obj


@router.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_class(
    project_id: int,
    class_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a class."""
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER]
    )

    result = await db.execute(
        select(Class).where(Class.id == class_id, Class.project_id == project_id)
    )
    class_obj = result.scalar_one_or_none()

    if not class_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class not found",
        )

    await db.delete(class_obj)
    await db.commit()
    return None


# ============== CLASS DATES ENDPOINTS ==============

@router.post("/{class_id}/dates", response_model=ClassDateResponse, status_code=status.HTTP_201_CREATED)
async def add_class_date(
    project_id: int,
    class_id: int,
    date_data: ClassDateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add a session date to a class."""
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    # Verify class exists
    result = await db.execute(
        select(Class).where(Class.id == class_id, Class.project_id == project_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")

    class_date = ClassDate(
        **date_data.model_dump(),
        class_id=class_id,
    )
    db.add(class_date)
    await db.commit()
    await db.refresh(class_date)
    return class_date


@router.delete("/{class_id}/dates/{date_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_class_date(
    project_id: int,
    class_id: int,
    date_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a class session date."""
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    result = await db.execute(
        select(ClassDate).where(ClassDate.id == date_id, ClassDate.class_id == class_id)
    )
    class_date = result.scalar_one_or_none()

    if not class_date:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class date not found")

    await db.delete(class_date)
    await db.commit()
    return None


# ============== TICKET ENDPOINTS ==============

@router.post("/{class_id}/tickets", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    project_id: int,
    class_id: int,
    ticket_data: TicketCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a ticket type for a class."""
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    # Verify class exists
    result = await db.execute(
        select(Class).where(Class.id == class_id, Class.project_id == project_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")

    ticket = Ticket(
        **ticket_data.model_dump(),
        class_id=class_id,
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.get("/{class_id}/tickets", response_model=TicketList)
async def list_tickets(
    project_id: int,
    class_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all tickets for a class."""
    await check_project_access(project_id, current_user, db)

    result = await db.execute(
        select(Ticket).where(Ticket.class_id == class_id)
    )
    tickets = result.scalars().all()

    return TicketList(tickets=tickets, total=len(tickets))


@router.patch("/{class_id}/tickets/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
    project_id: int,
    class_id: int,
    ticket_id: int,
    ticket_data: TicketUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a ticket."""
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.class_id == class_id)
    )
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    update_data = ticket_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(ticket, field, value)

    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.delete("/{class_id}/tickets/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ticket(
    project_id: int,
    class_id: int,
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a ticket type."""
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.class_id == class_id)
    )
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    await db.delete(ticket)
    await db.commit()
    return None


# ============== ATTENDEE ENDPOINTS ==============

@router.post("/{class_id}/register", response_model=RegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register_for_class(
    project_id: int,
    class_id: int,
    attendee_data: AttendeeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Register a student for a class."""
    await check_project_access(project_id, current_user, db)

    # Verify class exists and is published
    result = await db.execute(
        select(Class).where(Class.id == class_id, Class.project_id == project_id)
    )
    class_obj = result.scalar_one_or_none()

    if not class_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")

    if class_obj.status not in [ClassStatus.PUBLISHED, ClassStatus.ONGOING]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Class is not open for registration"
        )

    # Check capacity
    if class_obj.max_students:
        count_result = await db.execute(
            select(func.count(ClassAttendee.id))
            .where(
                ClassAttendee.class_id == class_id,
                ClassAttendee.status != AttendeeStatus.CANCELLED
            )
        )
        current_count = count_result.scalar()
        if current_count >= class_obj.max_students:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Class is full"
            )

    # Check if already registered
    existing = await db.execute(
        select(ClassAttendee).where(
            ClassAttendee.class_id == class_id,
            ClassAttendee.email == attendee_data.email,
            ClassAttendee.status != AttendeeStatus.CANCELLED
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered for this class"
        )

    # If ticket specified, check availability
    ticket = None
    if attendee_data.ticket_id:
        ticket_result = await db.execute(
            select(Ticket).where(Ticket.id == attendee_data.ticket_id, Ticket.class_id == class_id)
        )
        ticket = ticket_result.scalar_one_or_none()

        if not ticket:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

        if ticket.status != TicketStatus.AVAILABLE:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ticket not available")

        if ticket.quantity_total and ticket.quantity_sold >= ticket.quantity_total:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ticket sold out")

        # Update ticket sold count
        ticket.quantity_sold += 1
        if ticket.quantity_total and ticket.quantity_sold >= ticket.quantity_total:
            ticket.status = TicketStatus.SOLD_OUT

    attendee = ClassAttendee(
        class_id=class_id,
        email=attendee_data.email,
        full_name=attendee_data.full_name,
        phone=attendee_data.phone,
        notes=attendee_data.notes,
        user_id=attendee_data.user_id,
        ticket_id=attendee_data.ticket_id,
        amount_paid=ticket.price if ticket else 0,
    )
    db.add(attendee)
    await db.commit()
    await db.refresh(attendee)

    return RegistrationResponse(
        message="Successfully registered for class",
        attendee=attendee
    )


@router.get("/{class_id}/attendees", response_model=AttendeeList)
async def list_attendees(
    project_id: int,
    class_id: int,
    status_filter: Optional[AttendeeStatus] = Query(None, alias="status"),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all attendees for a class."""
    await check_project_access(project_id, current_user, db)

    query = select(ClassAttendee).where(ClassAttendee.class_id == class_id)

    if status_filter:
        query = query.where(ClassAttendee.status == status_filter)

    query = query.order_by(ClassAttendee.registered_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    attendees = result.scalars().all()

    # Get total
    count_query = select(ClassAttendee).where(ClassAttendee.class_id == class_id)
    if status_filter:
        count_query = count_query.where(ClassAttendee.status == status_filter)
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    return AttendeeList(attendees=attendees, total=total)


@router.get("/{class_id}/attendees/{attendee_id}", response_model=AttendeeWithUser)
async def get_attendee(
    project_id: int,
    class_id: int,
    attendee_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get attendee details."""
    await check_project_access(project_id, current_user, db)

    result = await db.execute(
        select(ClassAttendee)
        .options(selectinload(ClassAttendee.user), selectinload(ClassAttendee.ticket))
        .where(ClassAttendee.id == attendee_id, ClassAttendee.class_id == class_id)
    )
    attendee = result.scalar_one_or_none()

    if not attendee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendee not found")

    return attendee


@router.patch("/{class_id}/attendees/{attendee_id}", response_model=AttendeeResponse)
async def update_attendee(
    project_id: int,
    class_id: int,
    attendee_id: int,
    attendee_data: AttendeeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update attendee information or status."""
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    result = await db.execute(
        select(ClassAttendee).where(ClassAttendee.id == attendee_id, ClassAttendee.class_id == class_id)
    )
    attendee = result.scalar_one_or_none()

    if not attendee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendee not found")

    update_data = attendee_data.model_dump(exclude_unset=True)

    # Handle status transitions
    if "status" in update_data:
        new_status = update_data["status"]
        if new_status == AttendeeStatus.CONFIRMED and not attendee.confirmed_at:
            attendee.confirmed_at = datetime.utcnow()
        elif new_status == AttendeeStatus.ATTENDED and not attendee.attended_at:
            attendee.attended_at = datetime.utcnow()

    for field, value in update_data.items():
        setattr(attendee, field, value)

    await db.commit()
    await db.refresh(attendee)
    return attendee


@router.post("/{class_id}/attendees/{attendee_id}/check-in", response_model=AttendeeResponse)
async def check_in_attendee(
    project_id: int,
    class_id: int,
    attendee_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark an attendee as attended (check-in)."""
    await check_project_access(project_id, current_user, db)

    result = await db.execute(
        select(ClassAttendee).where(ClassAttendee.id == attendee_id, ClassAttendee.class_id == class_id)
    )
    attendee = result.scalar_one_or_none()

    if not attendee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendee not found")

    attendee.status = AttendeeStatus.ATTENDED
    attendee.attended_at = datetime.utcnow()

    await db.commit()
    await db.refresh(attendee)
    return attendee


@router.delete("/{class_id}/attendees/{attendee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_registration(
    project_id: int,
    class_id: int,
    attendee_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Cancel a registration (soft delete - sets status to cancelled)."""
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    result = await db.execute(
        select(ClassAttendee).where(ClassAttendee.id == attendee_id, ClassAttendee.class_id == class_id)
    )
    attendee = result.scalar_one_or_none()

    if not attendee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendee not found")

    # Restore ticket count if applicable
    if attendee.ticket_id:
        ticket_result = await db.execute(
            select(Ticket).where(Ticket.id == attendee.ticket_id)
        )
        ticket = ticket_result.scalar_one_or_none()
        if ticket and ticket.quantity_sold > 0:
            ticket.quantity_sold -= 1
            if ticket.status == TicketStatus.SOLD_OUT:
                ticket.status = TicketStatus.AVAILABLE

    attendee.status = AttendeeStatus.CANCELLED

    await db.commit()
    return None


# ============== TICKET SALES ENDPOINTS ==============

@router.post("/{class_id}/sales", response_model=TicketSaleResponse, status_code=status.HTTP_201_CREATED)
async def purchase_ticket(
    project_id: int,
    class_id: int,
    sale_data: TicketSaleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Purchase a ticket for a class.
    Creates a new ticket sale record and updates ticket inventory.
    """
    await check_project_access(project_id, current_user, db)

    # Verify class exists and is published
    result = await db.execute(
        select(Class).where(Class.id == class_id, Class.project_id == project_id)
    )
    class_obj = result.scalar_one_or_none()

    if not class_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")

    if class_obj.status not in [ClassStatus.PUBLISHED, ClassStatus.ONGOING]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Class is not open for ticket sales"
        )

    # Get and validate ticket
    ticket_result = await db.execute(
        select(Ticket).where(Ticket.id == sale_data.ticket_id, Ticket.class_id == class_id)
    )
    ticket = ticket_result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    if ticket.status != TicketStatus.AVAILABLE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ticket is not available")

    # Check sale period
    now = datetime.utcnow()
    if ticket.sale_start and now < ticket.sale_start:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ticket sales have not started yet")
    if ticket.sale_end and now > ticket.sale_end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ticket sales have ended")

    # Check quantity limits
    if sale_data.quantity > ticket.max_per_order:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {ticket.max_per_order} tickets per order"
        )

    if ticket.quantity_total:
        available = ticket.quantity_total - ticket.quantity_sold
        if sale_data.quantity > available:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Only {available} tickets available"
            )

    # Calculate pricing
    unit_price = ticket.price
    subtotal = unit_price * sale_data.quantity
    discount_amount = Decimal("0.00")
    tax_amount = Decimal("0.00")  # Could add tax calculation logic here
    total_amount = subtotal - discount_amount + tax_amount

    # Create sale record
    sale = TicketSale(
        order_number=generate_order_number(),
        ticket_id=ticket.id,
        class_id=class_id,
        buyer_id=current_user.id,
        buyer_email=sale_data.buyer_email,
        buyer_name=sale_data.buyer_name,
        buyer_phone=sale_data.buyer_phone,
        quantity=sale_data.quantity,
        unit_price=unit_price,
        subtotal=subtotal,
        discount_amount=discount_amount,
        discount_code=sale_data.discount_code,
        tax_amount=tax_amount,
        total_amount=total_amount,
        currency=ticket.currency,
        payment_status=PaymentStatus.PENDING,
        payment_method=sale_data.payment_method,
        notes=sale_data.notes,
    )
    db.add(sale)

    # Update ticket sold count
    ticket.quantity_sold += sale_data.quantity
    if ticket.quantity_total and ticket.quantity_sold >= ticket.quantity_total:
        ticket.status = TicketStatus.SOLD_OUT

    await db.commit()
    await db.refresh(sale)
    return sale


@router.get("/{class_id}/sales", response_model=TicketSaleList)
async def list_ticket_sales(
    project_id: int,
    class_id: int,
    ticket_id: Optional[int] = Query(None, description="Filter by ticket tier"),
    payment_status: Optional[PaymentStatus] = Query(None, description="Filter by payment status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all ticket sales for a class."""
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    query = select(TicketSale).where(TicketSale.class_id == class_id)
    count_query = select(func.count(TicketSale.id)).where(TicketSale.class_id == class_id)
    revenue_query = select(func.sum(TicketSale.total_amount)).where(
        TicketSale.class_id == class_id,
        TicketSale.payment_status == PaymentStatus.COMPLETED
    )

    if ticket_id:
        query = query.where(TicketSale.ticket_id == ticket_id)
        count_query = count_query.where(TicketSale.ticket_id == ticket_id)
        revenue_query = revenue_query.where(TicketSale.ticket_id == ticket_id)

    if payment_status:
        query = query.where(TicketSale.payment_status == payment_status)
        count_query = count_query.where(TicketSale.payment_status == payment_status)

    query = query.order_by(TicketSale.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    sales = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    revenue_result = await db.execute(revenue_query)
    total_revenue = revenue_result.scalar() or Decimal("0.00")

    return TicketSaleList(sales=sales, total=total, total_revenue=total_revenue)


@router.get("/{class_id}/sales/{sale_id}", response_model=TicketSaleWithDetails)
async def get_ticket_sale(
    project_id: int,
    class_id: int,
    sale_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get details of a specific ticket sale."""
    await check_project_access(project_id, current_user, db)

    result = await db.execute(
        select(TicketSale)
        .options(selectinload(TicketSale.ticket))
        .where(TicketSale.id == sale_id, TicketSale.class_id == class_id)
    )
    sale = result.scalar_one_or_none()

    if not sale:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found")

    # Check if user owns this sale or is admin
    if sale.buyer_id != current_user.id and not current_user.is_admin:
        # Check project access
        await check_project_access(
            project_id,
            current_user,
            db,
            required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
        )

    return sale


@router.patch("/{class_id}/sales/{sale_id}", response_model=TicketSaleResponse)
async def update_ticket_sale(
    project_id: int,
    class_id: int,
    sale_id: int,
    sale_data: TicketSaleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a ticket sale (payment status, reference, etc.).
    Admin/maintainer only.
    """
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    result = await db.execute(
        select(TicketSale).where(TicketSale.id == sale_id, TicketSale.class_id == class_id)
    )
    sale = result.scalar_one_or_none()

    if not sale:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found")

    update_data = sale_data.model_dump(exclude_unset=True)

    # Handle payment completion
    if "payment_status" in update_data:
        new_status = update_data["payment_status"]
        if new_status == PaymentStatus.COMPLETED and sale.payment_status != PaymentStatus.COMPLETED:
            sale.paid_at = datetime.utcnow()

    for field, value in update_data.items():
        setattr(sale, field, value)

    await db.commit()
    await db.refresh(sale)
    return sale


@router.post("/{class_id}/sales/{sale_id}/confirm-payment", response_model=TicketSaleResponse)
async def confirm_payment(
    project_id: int,
    class_id: int,
    sale_id: int,
    payment_reference: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Confirm payment for a ticket sale.
    This also creates the attendee record(s).
    """
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    result = await db.execute(
        select(TicketSale)
        .options(selectinload(TicketSale.ticket))
        .where(TicketSale.id == sale_id, TicketSale.class_id == class_id)
    )
    sale = result.scalar_one_or_none()

    if not sale:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found")

    if sale.payment_status == PaymentStatus.COMPLETED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment already confirmed")

    # Update sale
    sale.payment_status = PaymentStatus.COMPLETED
    sale.paid_at = datetime.utcnow()
    if payment_reference:
        sale.payment_reference = payment_reference

    # Create attendee records for each ticket purchased
    for _ in range(sale.quantity):
        attendee = ClassAttendee(
            class_id=class_id,
            user_id=sale.buyer_id,
            ticket_id=sale.ticket_id,
            email=sale.buyer_email,
            full_name=sale.buyer_name,
            phone=sale.buyer_phone,
            status=AttendeeStatus.CONFIRMED,
            amount_paid=sale.unit_price,
            payment_status="completed",
            payment_reference=sale.order_number,
            confirmed_at=datetime.utcnow(),
        )
        db.add(attendee)

    await db.commit()
    await db.refresh(sale)
    return sale


@router.post("/{class_id}/sales/{sale_id}/refund", response_model=TicketSaleResponse)
async def refund_ticket_sale(
    project_id: int,
    class_id: int,
    sale_id: int,
    refund_data: RefundRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Process a refund for a ticket sale.
    Full or partial refund supported.
    """
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER]
    )

    result = await db.execute(
        select(TicketSale)
        .options(selectinload(TicketSale.ticket))
        .where(TicketSale.id == sale_id, TicketSale.class_id == class_id)
    )
    sale = result.scalar_one_or_none()

    if not sale:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found")

    if sale.payment_status not in [PaymentStatus.COMPLETED, PaymentStatus.PARTIALLY_REFUNDED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only refund completed payments"
        )

    # Determine refund amount
    refund_amount = refund_data.amount if refund_data.amount else sale.total_amount

    # Check valid refund amount
    already_refunded = sale.refund_amount or Decimal("0.00")
    max_refundable = sale.total_amount - already_refunded

    if refund_amount > max_refundable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum refundable amount is {max_refundable}"
        )

    # Update sale
    new_refund_total = already_refunded + refund_amount
    sale.refund_amount = new_refund_total
    sale.refund_reason = refund_data.reason
    sale.refunded_at = datetime.utcnow()

    if new_refund_total >= sale.total_amount:
        sale.payment_status = PaymentStatus.REFUNDED
        # Restore ticket inventory
        if sale.ticket:
            sale.ticket.quantity_sold = max(0, sale.ticket.quantity_sold - sale.quantity)
            if sale.ticket.status == TicketStatus.SOLD_OUT:
                sale.ticket.status = TicketStatus.AVAILABLE
    else:
        sale.payment_status = PaymentStatus.PARTIALLY_REFUNDED

    await db.commit()
    await db.refresh(sale)
    return sale


@router.get("/{class_id}/sales-summary", response_model=SalesSummary)
async def get_sales_summary(
    project_id: int,
    class_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get sales summary for a class."""
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    # Total sales count
    count_result = await db.execute(
        select(func.count(TicketSale.id)).where(TicketSale.class_id == class_id)
    )
    total_sales = count_result.scalar() or 0

    # Total revenue (completed payments)
    revenue_result = await db.execute(
        select(func.sum(TicketSale.total_amount)).where(
            TicketSale.class_id == class_id,
            TicketSale.payment_status == PaymentStatus.COMPLETED
        )
    )
    total_revenue = revenue_result.scalar() or Decimal("0.00")

    # Total tickets sold
    tickets_result = await db.execute(
        select(func.sum(TicketSale.quantity)).where(
            TicketSale.class_id == class_id,
            TicketSale.payment_status == PaymentStatus.COMPLETED
        )
    )
    tickets_sold = tickets_result.scalar() or 0

    # Get class currency
    class_result = await db.execute(select(Class).where(Class.id == class_id))
    class_obj = class_result.scalar_one_or_none()
    currency = "USD"

    # Sales by tier
    tier_result = await db.execute(
        select(Ticket.tier, func.sum(TicketSale.quantity), func.sum(TicketSale.total_amount))
        .join(Ticket, TicketSale.ticket_id == Ticket.id)
        .where(
            TicketSale.class_id == class_id,
            TicketSale.payment_status == PaymentStatus.COMPLETED
        )
        .group_by(Ticket.tier)
    )
    sales_by_tier = {}
    for tier, qty, amount in tier_result:
        sales_by_tier[tier.value if tier else "unknown"] = {
            "quantity": qty or 0,
            "revenue": float(amount or 0)
        }

    # Sales by status
    status_result = await db.execute(
        select(TicketSale.payment_status, func.count(TicketSale.id))
        .where(TicketSale.class_id == class_id)
        .group_by(TicketSale.payment_status)
    )
    sales_by_status = {}
    for stat, count in status_result:
        sales_by_status[stat.value if stat else "unknown"] = count

    return SalesSummary(
        class_id=class_id,
        total_sales=total_sales,
        total_revenue=total_revenue,
        tickets_sold=tickets_sold,
        currency=currency,
        sales_by_tier=sales_by_tier,
        sales_by_status=sales_by_status,
    )


@router.get("/{class_id}/tickets-with-stats", response_model=list[TicketWithStats])
async def list_tickets_with_stats(
    project_id: int,
    class_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all tickets for a class with sales statistics."""
    await check_project_access(project_id, current_user, db)

    # Get tickets
    result = await db.execute(
        select(Ticket)
        .where(Ticket.class_id == class_id)
        .order_by(Ticket.tier_order)
    )
    tickets = result.scalars().all()

    # Get sales stats for each ticket
    response = []
    for ticket in tickets:
        # Get sales count and revenue
        stats_result = await db.execute(
            select(
                func.count(TicketSale.id),
                func.sum(TicketSale.total_amount)
            ).where(
                TicketSale.ticket_id == ticket.id,
                TicketSale.payment_status == PaymentStatus.COMPLETED
            )
        )
        sales_count, total_revenue = stats_result.one()

        # Calculate availability
        quantity_available = None
        if ticket.quantity_total:
            quantity_available = ticket.quantity_total - ticket.quantity_sold

        # Check if on sale
        now = datetime.utcnow()
        is_on_sale = True
        if ticket.sale_start and now < ticket.sale_start:
            is_on_sale = False
        if ticket.sale_end and now > ticket.sale_end:
            is_on_sale = False
        if ticket.status != TicketStatus.AVAILABLE:
            is_on_sale = False

        ticket_response = TicketWithStats.model_validate(ticket)
        ticket_response.quantity_available = quantity_available
        ticket_response.is_on_sale = is_on_sale
        ticket_response.sales_count = sales_count or 0
        ticket_response.total_revenue = total_revenue or Decimal("0.00")
        response.append(ticket_response)

    return response


# ============== CLASS HISTORY ENDPOINTS ==============

@history_router.get("/my-history", response_model=ClassHistoryList)
async def get_my_class_history(
    status_filter: Optional[AttendeeStatus] = Query(None, alias="status", description="Filter by attendance status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the current user's class history.
    Shows all classes they've registered for, attended, or are upcoming.
    """
    # Base query joining attendee with class, ticket, and project
    query = (
        select(ClassAttendee, Class, Ticket, Project)
        .join(Class, ClassAttendee.class_id == Class.id)
        .outerjoin(Ticket, ClassAttendee.ticket_id == Ticket.id)
        .join(Project, Class.project_id == Project.id)
        .where(ClassAttendee.user_id == current_user.id)
    )

    if status_filter:
        query = query.where(ClassAttendee.status == status_filter)

    # Order by registration date, most recent first
    query = query.order_by(ClassAttendee.registered_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    # Build response
    classes = []
    for attendee, class_obj, ticket, project in rows:
        item = ClassHistoryItem(
            id=attendee.id,
            class_id=class_obj.id,
            title=class_obj.title,
            description=class_obj.description,
            status=class_obj.status,
            start_date=class_obj.start_date,
            end_date=class_obj.end_date,
            location=class_obj.location,
            is_online=class_obj.is_online,
            instructor_name=class_obj.instructor_name,
            project_id=project.id,
            project_name=project.name,
            attendee_status=attendee.status,
            ticket_name=ticket.name if ticket else None,
            ticket_tier=ticket.tier if ticket else None,
            amount_paid=attendee.amount_paid,
            registered_at=attendee.registered_at,
            confirmed_at=attendee.confirmed_at,
            attended_at=attendee.attended_at,
        )
        classes.append(item)

    # Get counts
    count_query = (
        select(func.count(ClassAttendee.id))
        .where(ClassAttendee.user_id == current_user.id)
    )
    if status_filter:
        count_query = count_query.where(ClassAttendee.status == status_filter)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Attended count
    attended_result = await db.execute(
        select(func.count(ClassAttendee.id))
        .where(
            ClassAttendee.user_id == current_user.id,
            ClassAttendee.status == AttendeeStatus.ATTENDED
        )
    )
    attended_count = attended_result.scalar() or 0

    # Registered/Confirmed count (upcoming)
    registered_result = await db.execute(
        select(func.count(ClassAttendee.id))
        .where(
            ClassAttendee.user_id == current_user.id,
            ClassAttendee.status.in_([AttendeeStatus.REGISTERED, AttendeeStatus.CONFIRMED])
        )
    )
    registered_count = registered_result.scalar() or 0

    # Upcoming (classes that haven't started yet)
    now = datetime.utcnow().date()
    upcoming_result = await db.execute(
        select(func.count(ClassAttendee.id))
        .join(Class, ClassAttendee.class_id == Class.id)
        .where(
            ClassAttendee.user_id == current_user.id,
            ClassAttendee.status.in_([AttendeeStatus.REGISTERED, AttendeeStatus.CONFIRMED]),
            Class.start_date >= now
        )
    )
    upcoming_count = upcoming_result.scalar() or 0

    return ClassHistoryList(
        classes=classes,
        total=total,
        attended_count=attended_count,
        registered_count=registered_count,
        upcoming_count=upcoming_count,
    )


@history_router.get("/users/{user_id}/history", response_model=ClassHistoryList)
async def get_user_class_history(
    user_id: int,
    status_filter: Optional[AttendeeStatus] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get class history for a specific user (admin only).
    """
    from app.models.user import UserRole

    # Only admins can view other users' history
    if current_user.id != user_id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this user's class history"
        )

    # Same query as my-history but for specific user
    query = (
        select(ClassAttendee, Class, Ticket, Project)
        .join(Class, ClassAttendee.class_id == Class.id)
        .outerjoin(Ticket, ClassAttendee.ticket_id == Ticket.id)
        .join(Project, Class.project_id == Project.id)
        .where(ClassAttendee.user_id == user_id)
    )

    if status_filter:
        query = query.where(ClassAttendee.status == status_filter)

    query = query.order_by(ClassAttendee.registered_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    classes = []
    for attendee, class_obj, ticket, project in rows:
        item = ClassHistoryItem(
            id=attendee.id,
            class_id=class_obj.id,
            title=class_obj.title,
            description=class_obj.description,
            status=class_obj.status,
            start_date=class_obj.start_date,
            end_date=class_obj.end_date,
            location=class_obj.location,
            is_online=class_obj.is_online,
            instructor_name=class_obj.instructor_name,
            project_id=project.id,
            project_name=project.name,
            attendee_status=attendee.status,
            ticket_name=ticket.name if ticket else None,
            ticket_tier=ticket.tier if ticket else None,
            amount_paid=attendee.amount_paid,
            registered_at=attendee.registered_at,
            confirmed_at=attendee.confirmed_at,
            attended_at=attendee.attended_at,
        )
        classes.append(item)

    # Get counts
    count_result = await db.execute(
        select(func.count(ClassAttendee.id)).where(ClassAttendee.user_id == user_id)
    )
    total = count_result.scalar() or 0

    attended_result = await db.execute(
        select(func.count(ClassAttendee.id))
        .where(
            ClassAttendee.user_id == user_id,
            ClassAttendee.status == AttendeeStatus.ATTENDED
        )
    )
    attended_count = attended_result.scalar() or 0

    registered_result = await db.execute(
        select(func.count(ClassAttendee.id))
        .where(
            ClassAttendee.user_id == user_id,
            ClassAttendee.status.in_([AttendeeStatus.REGISTERED, AttendeeStatus.CONFIRMED])
        )
    )
    registered_count = registered_result.scalar() or 0

    now = datetime.utcnow().date()
    upcoming_result = await db.execute(
        select(func.count(ClassAttendee.id))
        .join(Class, ClassAttendee.class_id == Class.id)
        .where(
            ClassAttendee.user_id == user_id,
            ClassAttendee.status.in_([AttendeeStatus.REGISTERED, AttendeeStatus.CONFIRMED]),
            Class.start_date >= now
        )
    )
    upcoming_count = upcoming_result.scalar() or 0

    return ClassHistoryList(
        classes=classes,
        total=total,
        attended_count=attended_count,
        registered_count=registered_count,
        upcoming_count=upcoming_count,
    )
