from datetime import datetime, date, time
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, EmailStr

from app.models.class_model import ClassStatus, TicketStatus, AttendeeStatus, TicketTier, PaymentStatus
from app.schemas.user import UserResponse


# Class Date Schemas
class ClassDateBase(BaseModel):
    session_date: date
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    title: Optional[str] = None
    description: Optional[str] = None


class ClassDateCreate(ClassDateBase):
    pass


class ClassDateResponse(ClassDateBase):
    id: int
    class_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# Ticket Schemas
class TicketBase(BaseModel):
    name: str
    description: Optional[str] = None
    tier: TicketTier = TicketTier.GENERAL
    tier_order: int = 100
    price: Decimal = Decimal("0.00")
    original_price: Optional[Decimal] = None
    currency: str = "USD"
    quantity_total: Optional[int] = None
    max_per_order: int = 10
    sale_start: Optional[datetime] = None
    sale_end: Optional[datetime] = None
    benefits: Optional[str] = None


class TicketCreate(TicketBase):
    pass


class TicketUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tier: Optional[TicketTier] = None
    tier_order: Optional[int] = None
    price: Optional[Decimal] = None
    original_price: Optional[Decimal] = None
    currency: Optional[str] = None
    quantity_total: Optional[int] = None
    max_per_order: Optional[int] = None
    status: Optional[TicketStatus] = None
    sale_start: Optional[datetime] = None
    sale_end: Optional[datetime] = None
    benefits: Optional[str] = None


class TicketResponse(TicketBase):
    id: int
    class_id: int
    status: TicketStatus
    quantity_sold: int
    quantity_available: Optional[int] = None
    is_on_sale: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TicketWithStats(TicketResponse):
    """Ticket with sales statistics."""
    total_revenue: Decimal = Decimal("0.00")
    sales_count: int = 0


class TicketList(BaseModel):
    tickets: List[TicketResponse]
    total: int


# Ticket Sale Schemas
class TicketSaleBase(BaseModel):
    buyer_email: EmailStr
    buyer_name: str
    buyer_phone: Optional[str] = None
    quantity: int = 1
    discount_code: Optional[str] = None
    notes: Optional[str] = None


class TicketSaleCreate(TicketSaleBase):
    ticket_id: int
    payment_method: Optional[str] = None


class TicketSaleUpdate(BaseModel):
    payment_status: Optional[PaymentStatus] = None
    payment_reference: Optional[str] = None
    payment_intent_id: Optional[str] = None
    notes: Optional[str] = None


class TicketSaleResponse(TicketSaleBase):
    id: int
    order_number: str
    ticket_id: int
    class_id: int
    buyer_id: Optional[int] = None
    unit_price: Decimal
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    currency: str
    payment_status: PaymentStatus
    payment_method: Optional[str] = None
    payment_reference: Optional[str] = None
    paid_at: Optional[datetime] = None
    refund_amount: Optional[Decimal] = None
    refund_reason: Optional[str] = None
    refunded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TicketSaleWithDetails(TicketSaleResponse):
    """Sale with ticket and class details."""
    ticket: Optional[TicketResponse] = None


class TicketSaleList(BaseModel):
    sales: List[TicketSaleResponse]
    total: int
    total_revenue: Decimal = Decimal("0.00")


class RefundRequest(BaseModel):
    """Request to refund a ticket sale."""
    amount: Optional[Decimal] = None  # None = full refund
    reason: str


# Sales Summary
class SalesSummary(BaseModel):
    """Summary of ticket sales for a class."""
    class_id: int
    total_sales: int
    total_revenue: Decimal
    tickets_sold: int
    currency: str
    sales_by_tier: dict = {}
    sales_by_status: dict = {}


# Attendee Schemas
class AttendeeBase(BaseModel):
    email: EmailStr
    full_name: str
    phone: Optional[str] = None
    notes: Optional[str] = None


class AttendeeCreate(AttendeeBase):
    ticket_id: Optional[int] = None
    user_id: Optional[int] = None


class AttendeeUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[AttendeeStatus] = None
    notes: Optional[str] = None


class AttendeeResponse(AttendeeBase):
    id: int
    class_id: int
    user_id: Optional[int] = None
    ticket_id: Optional[int] = None
    status: AttendeeStatus
    amount_paid: Decimal
    payment_status: Optional[str] = None
    payment_reference: Optional[str] = None
    registered_at: datetime
    confirmed_at: Optional[datetime] = None
    attended_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AttendeeWithUser(AttendeeResponse):
    user: Optional[UserResponse] = None
    ticket: Optional[TicketResponse] = None


class AttendeeList(BaseModel):
    attendees: List[AttendeeResponse]
    total: int


# Class Schemas
class ClassBase(BaseModel):
    title: str
    description: Optional[str] = None
    curriculum: Optional[str] = None
    syllabus_url: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    timezone: Optional[str] = "UTC"
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None
    location: Optional[str] = None
    is_online: bool = False
    meeting_url: Optional[str] = None
    max_students: Optional[int] = None
    instructor_name: Optional[str] = None
    instructor_id: Optional[int] = None


class ClassCreate(ClassBase):
    pass


class ClassUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ClassStatus] = None
    curriculum: Optional[str] = None
    syllabus_url: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    timezone: Optional[str] = None
    is_recurring: Optional[bool] = None
    recurrence_pattern: Optional[str] = None
    location: Optional[str] = None
    is_online: Optional[bool] = None
    meeting_url: Optional[str] = None
    max_students: Optional[int] = None
    instructor_name: Optional[str] = None
    instructor_id: Optional[int] = None


class ClassResponse(ClassBase):
    id: int
    project_id: int
    status: ClassStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ClassWithDetails(ClassResponse):
    instructor: Optional[UserResponse] = None
    tickets: List[TicketResponse] = []
    dates: List[ClassDateResponse] = []
    attendee_count: Optional[int] = None


class ClassList(BaseModel):
    classes: List[ClassResponse]
    total: int


# Registration response
class RegistrationResponse(BaseModel):
    message: str
    attendee: AttendeeResponse


# Class History Schemas
class ClassHistoryItem(BaseModel):
    """A class that a user has attended or is registered for."""
    id: int
    class_id: int
    title: str
    description: Optional[str] = None
    status: ClassStatus
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    location: Optional[str] = None
    is_online: bool = False
    instructor_name: Optional[str] = None
    project_id: int
    project_name: Optional[str] = None

    # Attendee info
    attendee_status: AttendeeStatus
    ticket_name: Optional[str] = None
    ticket_tier: Optional[TicketTier] = None
    amount_paid: Decimal
    registered_at: datetime
    confirmed_at: Optional[datetime] = None
    attended_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ClassHistoryList(BaseModel):
    """List of classes a user has taken."""
    classes: List[ClassHistoryItem]
    total: int
    attended_count: int = 0
    registered_count: int = 0
    upcoming_count: int = 0
