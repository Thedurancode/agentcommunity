from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

from app.models.episode_segment import SegmentType


class EpisodeSegmentBase(BaseModel):
    segment_number: int
    segment_type: SegmentType
    title: str
    description: Optional[str] = None
    start_time: int = 0
    duration_seconds: int = 120
    talking_points: Optional[str] = None  # JSON string of array
    visual_notes: Optional[str] = None
    music_cue: Optional[str] = None


class EpisodeSegmentCreate(EpisodeSegmentBase):
    episode_id: int


class EpisodeSegmentUpdate(BaseModel):
    segment_type: Optional[SegmentType] = None
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[int] = None
    duration_seconds: Optional[int] = None
    talking_points: Optional[str] = None
    visual_notes: Optional[str] = None
    music_cue: Optional[str] = None


class EpisodeSegmentResponse(EpisodeSegmentBase):
    id: int
    episode_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EpisodeSegmentList(BaseModel):
    segments: List[EpisodeSegmentResponse]
    total: int


# For episode generation
class GeneratedSegment(BaseModel):
    segment_number: int
    segment_type: SegmentType
    title: str
    description: str
    start_time: int
    duration_seconds: int
    talking_points: List[str]
    visual_notes: str
    music_cue: str


class GeneratedEpisodeStructure(BaseModel):
    episode_title: str
    total_duration_seconds: int
    segments: List[GeneratedSegment]
    project_name: Optional[str] = None
    project_description: Optional[str] = None
