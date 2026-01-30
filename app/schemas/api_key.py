from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class APIKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Friendly name for the API key")


class APIKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class APIKeyCreatedResponse(BaseModel):
    """Response when creating a new API key - includes the full key (only shown once)"""
    id: int
    name: str
    key: str = Field(..., description="The full API key - save this, it won't be shown again")
    key_prefix: str
    created_at: datetime

    model_config = {"from_attributes": True}
