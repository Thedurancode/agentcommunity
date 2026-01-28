from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel

from app.models.pull_request import PRState
from app.schemas.user import UserResponse


class PullRequestBase(BaseModel):
    title: str
    body: Optional[str] = None
    head_branch: Optional[str] = None
    base_branch: Optional[str] = None


class PullRequestCreate(PullRequestBase):
    pass


class PullRequestUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    state: Optional[PRState] = None


class PullRequestResponse(PullRequestBase):
    id: int
    state: PRState
    project_id: int
    author_id: Optional[int] = None
    github_pr_id: Optional[int] = None
    github_pr_number: Optional[int] = None
    github_pr_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    merged_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PullRequestWithAuthor(PullRequestResponse):
    author: Optional[UserResponse] = None


class PullRequestList(BaseModel):
    pull_requests: List[PullRequestResponse]
    total: int
