from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Boolean, Enum as SQLEnum, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User
    from app.models.class_model import Class


class DiscountType(str, Enum):
    """Type of discount."""
    PERCENTAGE = "percentage"  # e.g., 20% off
    FIXED_AMOUNT = "fixed_amount"  # e.g., $10 off


class PromoCodeStatus(str, Enum):
    """Status of promo code."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"
    EXHAUSTED = "exhausted"  # Max uses reached


class PromoCode(Base):
    """
    Promo/discount code for ticket purchases.
    Can be percentage or fixed amount discount.
    """
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Code info
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)  # The actual code (e.g., "SAVE20")
    name: Mapped[str] = mapped_column(String(255))  # Friendly name (e.g., "Summer Sale 20%")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Discount details
    discount_type: Mapped[DiscountType] = mapped_column(SQLEnum(DiscountType))
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # 20 for 20% or $20
    max_discount_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)  # Cap for percentage discounts
    min_purchase_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)  # Minimum order to apply

    # Status
    status: Mapped[PromoCodeStatus] = mapped_column(
        SQLEnum(PromoCodeStatus), default=PromoCodeStatus.ACTIVE
    )

    # Validity period
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Usage limits
    max_uses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Total uses allowed
    max_uses_per_user: Mapped[int] = mapped_column(Integer, default=1)  # Uses per user
    current_uses: Mapped[int] = mapped_column(Integer, default=0)

    # Scope restrictions
    project_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=True
    )  # If set, only valid for this project
    class_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("classes.id"), nullable=True
    )  # If set, only valid for this class

    # Applicable ticket tiers (JSON array, null = all tiers)
    applicable_tiers: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # First-time buyers only
    first_time_only: Mapped[bool] = mapped_column(Boolean, default=False)

    # Created by
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project: Mapped[Optional["Project"]] = relationship("Project")
    class_: Mapped[Optional["Class"]] = relationship("Class")
    created_by: Mapped[Optional["User"]] = relationship("User")
    usage_records: Mapped[List["PromoCodeUsage"]] = relationship(
        "PromoCodeUsage", back_populates="promo_code", cascade="all, delete-orphan"
    )


class PromoCodeUsage(Base):
    """
    Track usage of promo codes.
    """
    __tablename__ = "promo_code_usage"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    promo_code_id: Mapped[int] = mapped_column(Integer, ForeignKey("promo_codes.id"), index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # What it was applied to
    ticket_sale_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("ticket_sales.id"), nullable=True
    )

    # Amount saved
    discount_applied: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    original_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    final_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    # Buyer info (for guest checkouts)
    buyer_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    used_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    promo_code: Mapped["PromoCode"] = relationship("PromoCode", back_populates="usage_records")
    user: Mapped[Optional["User"]] = relationship("User")
