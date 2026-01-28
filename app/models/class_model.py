from datetime import datetime, date, time
from decimal import Decimal
from enum import Enum
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Numeric, Date, Time, Enum as SQLEnum, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class ClassStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ONGOING = "ongoing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TicketStatus(str, Enum):
    AVAILABLE = "available"
    SOLD_OUT = "sold_out"
    EXPIRED = "expired"


class TicketTier(str, Enum):
    """Ticket tier levels for prioritization and display."""
    VIP = "vip"
    PREMIUM = "premium"
    EARLY_BIRD = "early_bird"
    GENERAL = "general"
    STUDENT = "student"
    FREE = "free"


class PaymentStatus(str, Enum):
    """Payment status for ticket sales."""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class AttendeeStatus(str, Enum):
    REGISTERED = "registered"
    CONFIRMED = "confirmed"
    ATTENDED = "attended"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"


class Class(Base):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[ClassStatus] = mapped_column(SQLEnum(ClassStatus), default=ClassStatus.DRAFT)

    # Curriculum
    curriculum: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    syllabus_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Schedule
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    start_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    end_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="UTC")
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurrence_pattern: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # e.g., "weekly", "daily"

    # Location
    location: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    meeting_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Capacity
    max_students: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Instructor
    instructor_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    instructor_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="classes")
    instructor: Mapped[Optional["User"]] = relationship("User")
    tickets: Mapped[List["Ticket"]] = relationship("Ticket", back_populates="class_", cascade="all, delete-orphan")
    attendees: Mapped[List["ClassAttendee"]] = relationship("ClassAttendee", back_populates="class_", cascade="all, delete-orphan")
    dates: Mapped[List["ClassDate"]] = relationship("ClassDate", back_populates="class_", cascade="all, delete-orphan")
    ticket_sales: Mapped[List["TicketSale"]] = relationship("TicketSale", back_populates="class_", cascade="all, delete-orphan")


class ClassDate(Base):
    """Individual session dates for a class (for multi-session classes)."""
    __tablename__ = "class_dates"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    class_id: Mapped[int] = mapped_column(Integer, ForeignKey("classes.id"))

    session_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    end_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # e.g., "Session 1: Introduction"
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    class_: Mapped["Class"] = relationship("Class", back_populates="dates")


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255))  # e.g., "Early Bird", "Regular", "VIP"
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[TicketStatus] = mapped_column(SQLEnum(TicketStatus), default=TicketStatus.AVAILABLE)

    # Ticket tier for categorization and display order
    tier: Mapped[TicketTier] = mapped_column(SQLEnum(TicketTier), default=TicketTier.GENERAL)
    tier_order: Mapped[int] = mapped_column(Integer, default=100)  # Lower = higher priority display

    # Pricing
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    original_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)  # For showing discounts
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Availability
    quantity_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # null = unlimited
    quantity_sold: Mapped[int] = mapped_column(Integer, default=0)
    max_per_order: Mapped[int] = mapped_column(Integer, default=10)  # Max tickets per single order

    # Sale period
    sale_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sale_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Benefits/perks for this tier
    benefits: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list or markdown

    class_id: Mapped[int] = mapped_column(Integer, ForeignKey("classes.id"))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    class_: Mapped["Class"] = relationship("Class", back_populates="tickets")
    sales: Mapped[List["TicketSale"]] = relationship("TicketSale", back_populates="ticket")


class ClassAttendee(Base):
    __tablename__ = "class_attendees"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    class_id: Mapped[int] = mapped_column(Integer, ForeignKey("classes.id"))
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    ticket_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tickets.id"), nullable=True)

    # For non-registered users
    email: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    status: Mapped[AttendeeStatus] = mapped_column(SQLEnum(AttendeeStatus), default=AttendeeStatus.REGISTERED)

    # Payment info
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    payment_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # pending, completed, refunded
    payment_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    registered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    attended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    class_: Mapped["Class"] = relationship("Class", back_populates="attendees")
    user: Mapped[Optional["User"]] = relationship("User")
    ticket: Mapped[Optional["Ticket"]] = relationship("Ticket")


class TicketSale(Base):
    """Individual ticket sale/order record."""
    __tablename__ = "ticket_sales"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Order reference
    order_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)

    # Ticket and class
    ticket_id: Mapped[int] = mapped_column(Integer, ForeignKey("tickets.id"))
    class_id: Mapped[int] = mapped_column(Integer, ForeignKey("classes.id"))

    # Buyer info
    buyer_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    buyer_email: Mapped[str] = mapped_column(String(255))
    buyer_name: Mapped[str] = mapped_column(String(255))
    buyer_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Order details
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # Price at time of purchase
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    discount_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Payment
    payment_status: Mapped[PaymentStatus] = mapped_column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING)
    payment_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # stripe, paypal, cash, etc.
    payment_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payment_intent_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # For Stripe
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Refund info
    refund_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    refund_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refunded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Additional info
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON for extra data

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="sales")
    class_: Mapped["Class"] = relationship("Class", back_populates="ticket_sales")
    buyer: Mapped[Optional["User"]] = relationship("User")
