from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel

from app.models.issue import IssueState
from app.schemas.user import UserResponse


class IssueBase(BaseModel):
    title: str
    body: Optional[str] = None


class IssueCreate(IssueBase):
    assignee_id: Optional[int] = None


class IssueUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    state: Optional[IssueState] = None
    assignee_id: Optional[int] = None


class IssueResponse(IssueBase):
    id: int
    state: IssueState
    project_id: int
    assignee_id: Optional[int] = None
    created_by_id: Optional[int] = None
    github_issue_id: Optional[int] = None
    github_issue_number: Optional[int] = None
    github_issue_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class IssueWithDetails(IssueResponse):
    assignee: Optional[UserResponse] = None
    created_by: Optional[UserResponse] = None


class IssueList(BaseModel):
    issues: List[IssueResponse]
    total: int
