from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel

from app.schemas.user import UserResponse


class NoteBase(BaseModel):
    title: str
    content: Optional[str] = None


class NoteCreate(NoteBase):
    pass


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


class NoteResponse(NoteBase):
    id: int
    project_id: int
    created_by_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NoteWithCreator(NoteResponse):
    created_by: Optional[UserResponse] = None


class NoteList(BaseModel):
    notes: List[NoteResponse]
    total: int
