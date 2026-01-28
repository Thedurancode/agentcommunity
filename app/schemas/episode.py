from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class EpisodeBase(BaseModel):
    title: str
    description: Optional[str] = None
    episode_number: Optional[int] = None
    season_number: Optional[int] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    audio_url: Optional[str] = None
    duration_seconds: Optional[int] = None


class EpisodeCreate(EpisodeBase):
    project_id: Optional[int] = None
    auto_generate_segments: bool = False  # Auto-generate TV show segments if project linked


class EpisodeUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    episode_number: Optional[int] = None
    season_number: Optional[int] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    audio_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    project_id: Optional[int] = None
    is_published: Optional[bool] = None


class EpisodeResponse(EpisodeBase):
    id: int
    project_id: Optional[int] = None
    is_published: bool
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EpisodeList(BaseModel):
    episodes: List[EpisodeResponse]
    total: int
