from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel

from app.models.team_member import TeamRole
from app.schemas.user import UserResponse


class TeamMemberBase(BaseModel):
    user_id: int
    role: TeamRole = TeamRole.DEVELOPER


class TeamMemberCreate(TeamMemberBase):
    pass


class TeamMemberUpdate(BaseModel):
    role: Optional[TeamRole] = None


class TeamMemberResponse(TeamMemberBase):
    id: int
    project_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TeamMemberWithUser(TeamMemberResponse):
    user: UserResponse


class TeamMemberList(BaseModel):
    team_members: List[TeamMemberWithUser]
    total: int
