from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, field_validator

from app.models.promo_code import DiscountType, PromoCodeStatus


# PromoCode Schemas
class PromoCodeBase(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    discount_type: DiscountType
    discount_value: Decimal
    max_discount_amount: Optional[Decimal] = None
    min_purchase_amount: Optional[Decimal] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    max_uses: Optional[int] = None
    max_uses_per_user: int = 1
    project_id: Optional[int] = None
    class_id: Optional[int] = None
    applicable_tiers: Optional[str] = None  # JSON array
    first_time_only: bool = False

    @field_validator("code")
    @classmethod
    def code_uppercase(cls, v: str) -> str:
        return v.upper().strip()


class PromoCodeCreate(PromoCodeBase):
    pass


class PromoCodeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    discount_type: Optional[DiscountType] = None
    discount_value: Optional[Decimal] = None
    max_discount_amount: Optional[Decimal] = None
    min_purchase_amount: Optional[Decimal] = None
    status: Optional[PromoCodeStatus] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    max_uses: Optional[int] = None
    max_uses_per_user: Optional[int] = None
    applicable_tiers: Optional[str] = None
    first_time_only: Optional[bool] = None


class PromoCodeResponse(PromoCodeBase):
    id: int
    status: PromoCodeStatus
    current_uses: int
    created_by_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PromoCodeWithStats(PromoCodeResponse):
    """Promo code with usage statistics."""
    total_discount_given: Decimal = Decimal("0.00")
    unique_users: int = 0
    remaining_uses: Optional[int] = None


class PromoCodeList(BaseModel):
    promo_codes: List[PromoCodeResponse]
    total: int


# Validation/Apply Schemas
class PromoCodeValidate(BaseModel):
    """Request to validate a promo code."""
    code: str
    class_id: int
    ticket_id: int
    quantity: int = 1

    @field_validator("code")
    @classmethod
    def code_uppercase(cls, v: str) -> str:
        return v.upper().strip()


class PromoCodeValidationResult(BaseModel):
    """Result of promo code validation."""
    valid: bool
    code: str
    message: str
    discount_type: Optional[DiscountType] = None
    discount_value: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None  # Calculated discount
    original_amount: Optional[Decimal] = None
    final_amount: Optional[Decimal] = None


# Usage Schemas
class PromoCodeUsageResponse(BaseModel):
    id: int
    promo_code_id: int
    user_id: Optional[int] = None
    ticket_sale_id: Optional[int] = None
    discount_applied: Decimal
    original_amount: Decimal
    final_amount: Decimal
    buyer_email: Optional[str] = None
    used_at: datetime

    class Config:
        from_attributes = True


class PromoCodeUsageList(BaseModel):
    usage_records: List[PromoCodeUsageResponse]
    total: int
    total_discount: Decimal = Decimal("0.00")
