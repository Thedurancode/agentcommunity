from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel

from app.models.post import PostVisibility
from app.schemas.user import UserResponse


# Media schema
class PostMedia(BaseModel):
    images: List[str] = []
    videos: List[str] = []
    links: List[str] = []


# Comment schemas
class PostCommentBase(BaseModel):
    content: str


class PostCommentCreate(PostCommentBase):
    parent_id: Optional[int] = None


class PostCommentUpdate(BaseModel):
    content: str


class PostCommentResponse(PostCommentBase):
    id: int
    post_id: int
    author_id: int
    parent_id: Optional[int] = None
    likes_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PostCommentWithAuthor(PostCommentResponse):
    author: UserResponse
    is_liked: bool = False
    replies: List["PostCommentWithAuthor"] = []


# Post schemas
class PostBase(BaseModel):
    content: str
    visibility: PostVisibility = PostVisibility.PUBLIC


class PostCreate(PostBase):
    project_id: Optional[int] = None
    media: Optional[PostMedia] = None


class PostUpdate(BaseModel):
    content: Optional[str] = None
    visibility: Optional[PostVisibility] = None
    media: Optional[PostMedia] = None


class PostResponse(PostBase):
    id: int
    author_id: int
    project_id: Optional[int] = None
    media: Optional[Dict[str, Any]] = None
    likes_count: int
    comments_count: int
    saves_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PostWithDetails(PostResponse):
    author: UserResponse
    is_liked: bool = False
    is_saved: bool = False
    recent_comments: List[PostCommentWithAuthor] = []


class PostList(BaseModel):
    posts: List[PostWithDetails]
    total: int
    has_more: bool = False


# Like/Save responses
class LikeResponse(BaseModel):
    liked: bool
    likes_count: int


class SaveResponse(BaseModel):
    saved: bool
    saves_count: int


# Feed response
class FeedResponse(BaseModel):
    posts: List[PostWithDetails]
    next_cursor: Optional[str] = None
    has_more: bool = False


# Update forward reference for nested replies
PostCommentWithAuthor.model_rebuild()
