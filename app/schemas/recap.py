from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class CommitSummary(BaseModel):
    sha: str
    message: str
    author: str
    date: datetime
    url: Optional[str] = None


class IssueSummary(BaseModel):
    id: int
    title: str
    state: str
    created_at: datetime
    github_issue_number: Optional[int] = None
    github_issue_url: Optional[str] = None


class NoteSummary(BaseModel):
    id: int
    title: str
    created_at: datetime
    created_by: Optional[str] = None


class RecapBase(BaseModel):
    summary: Optional[str] = None


class RecapCreate(RecapBase):
    pass


class RecapUpdate(BaseModel):
    summary: Optional[str] = None


class RecapResponse(RecapBase):
    id: int
    project_id: int
    recent_commits: List[CommitSummary] = []
    recent_issues: List[IssueSummary] = []
    recent_notes: List[NoteSummary] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RecapRefreshResponse(BaseModel):
    message: str
    commits_updated: int
    issues_updated: int
    notes_updated: int


class AISummaryResponse(BaseModel):
    summary: str
    saved: bool
