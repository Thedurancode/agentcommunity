from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, HttpUrl

from app.schemas.user import UserResponse


class VideoBase(BaseModel):
    title: str
    description: Optional[str] = None


class VideoCreate(VideoBase):
    external_url: Optional[str] = None


class VideoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    external_url: Optional[str] = None


class VideoResponse(VideoBase):
    id: int
    file_path: str
    file_name: str
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    duration: Optional[int] = None
    thumbnail_path: Optional[str] = None
    external_url: Optional[str] = None
    project_id: int
    uploaded_by_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VideoWithUploader(VideoResponse):
    uploaded_by: Optional[UserResponse] = None


class VideoList(BaseModel):
    videos: List[VideoResponse]
    total: int


class VideoUploadResponse(BaseModel):
    message: str
    video: VideoResponse
