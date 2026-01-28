from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, HttpUrl

from app.models.developer_profile import DeveloperStatus


# Developer Profile Schemas
class DeveloperProfileBase(BaseModel):
    headline: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    timezone: Optional[str] = None
    status: DeveloperStatus = DeveloperStatus.AVAILABLE
    status_message: Optional[str] = None
    website_url: Optional[str] = None
    twitter_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    youtube_url: Optional[str] = None
    twitch_url: Optional[str] = None
    is_public: bool = True
    show_email: bool = False
    show_projects: bool = True
    pinned_message: Optional[str] = None


class DeveloperProfileCreate(DeveloperProfileBase):
    skills: Optional[List[str]] = None
    expertise_areas: Optional[List[str]] = None


class DeveloperProfileUpdate(BaseModel):
    headline: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    timezone: Optional[str] = None
    status: Optional[DeveloperStatus] = None
    status_message: Optional[str] = None
    skills: Optional[List[str]] = None
    expertise_areas: Optional[List[str]] = None
    website_url: Optional[str] = None
    twitter_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    youtube_url: Optional[str] = None
    twitch_url: Optional[str] = None
    is_public: Optional[bool] = None
    show_email: Optional[bool] = None
    show_projects: Optional[bool] = None
    featured_project_id: Optional[int] = None
    pinned_message: Optional[str] = None


class DeveloperProfileResponse(DeveloperProfileBase):
    id: int
    user_id: int
    skills: Optional[List[str]] = None
    expertise_areas: Optional[List[str]] = None
    projects_count: int = 0
    contributions_count: int = 0
    followers_count: int = 0
    following_count: int = 0
    featured_project_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Combined user + profile for feed
class DeveloperUserInfo(BaseModel):
    """Basic user info for the profile card."""
    id: int
    username: str
    full_name: Optional[str] = None
    profile_image: Optional[str] = None
    github_username: Optional[str] = None

    class Config:
        from_attributes = True


class DeveloperFeedItem(BaseModel):
    """Developer profile card for the community feed."""
    user: DeveloperUserInfo
    profile: DeveloperProfileResponse
    recent_projects: List[dict] = []  # Simplified project info
    is_following: bool = False


class DeveloperFeedList(BaseModel):
    """Paginated list of developers."""
    developers: List[DeveloperFeedItem]
    total: int


# Follow schemas
class FollowResponse(BaseModel):
    id: int
    follower_id: int
    following_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class FollowStats(BaseModel):
    followers_count: int
    following_count: int
    is_following: bool = False
    is_followed_by: bool = False


# Search/Filter
class DeveloperSearchParams(BaseModel):
    query: Optional[str] = None  # Search in name, username, bio
    skills: Optional[List[str]] = None
    status: Optional[DeveloperStatus] = None
    location: Optional[str] = None


# Simple project info for feed
class ProjectSummary(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    github_url: Optional[str] = None

    class Config:
        from_attributes = True
