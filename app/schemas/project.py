from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel

from app.models.project import ProjectStatus
from app.schemas.user import UserResponse


class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    status: ProjectStatus = ProjectStatus.IN_TALKS
    status_note: Optional[str] = None


class ProjectCreate(ProjectBase):
    github_repo_full_name: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None
    status_note: Optional[str] = None
    github_repo_full_name: Optional[str] = None


class ProjectResponse(ProjectBase):
    id: int
    github_repo_id: Optional[int] = None
    github_repo_name: Optional[str] = None
    github_repo_full_name: Optional[str] = None
    github_repo_url: Optional[str] = None
    owner_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectWithOwner(ProjectResponse):
    owner: UserResponse


class ProjectList(BaseModel):
    projects: List[ProjectResponse]
    total: int
