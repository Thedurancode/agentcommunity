from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, EmailStr

from app.models.blog import BlogStatus
from app.schemas.user import UserResponse


# Blog Image Schemas
class BlogImageBase(BaseModel):
    url: str
    alt_text: Optional[str] = None
    caption: Optional[str] = None
    display_order: int = 0


class BlogImageCreate(BlogImageBase):
    pass


class BlogImageResponse(BlogImageBase):
    id: int
    blog_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# Blog Comment Schemas
class BlogCommentBase(BaseModel):
    content: str


class BlogCommentCreate(BlogCommentBase):
    parent_id: Optional[int] = None
    # For guest comments
    guest_name: Optional[str] = None
    guest_email: Optional[EmailStr] = None


class BlogCommentUpdate(BaseModel):
    content: Optional[str] = None
    is_approved: Optional[bool] = None
    is_flagged: Optional[bool] = None


class BlogCommentAuthor(BaseModel):
    """Simplified author info for comments."""
    id: Optional[int] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    profile_image: Optional[str] = None
    guest_name: Optional[str] = None

    class Config:
        from_attributes = True


class BlogCommentResponse(BlogCommentBase):
    id: int
    blog_id: int
    author_id: Optional[int] = None
    guest_name: Optional[str] = None
    parent_id: Optional[int] = None
    is_approved: bool
    is_flagged: bool
    likes_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BlogCommentWithAuthor(BlogCommentResponse):
    author: Optional[BlogCommentAuthor] = None


class BlogCommentWithReplies(BlogCommentWithAuthor):
    replies: List["BlogCommentWithAuthor"] = []


class BlogCommentList(BaseModel):
    comments: List[BlogCommentWithReplies]
    total: int


# Blog Schemas
class BlogBase(BaseModel):
    title: str
    excerpt: Optional[str] = None
    content: str
    cover_image: Optional[str] = None
    thumbnail: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    category: Optional[str] = None
    allow_comments: bool = True


class BlogCreate(BlogBase):
    slug: Optional[str] = None  # Auto-generated if not provided
    tags: Optional[List[str]] = None
    status: BlogStatus = BlogStatus.DRAFT
    project_id: Optional[int] = None


class BlogUpdate(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    excerpt: Optional[str] = None
    content: Optional[str] = None
    cover_image: Optional[str] = None
    thumbnail: Optional[str] = None
    status: Optional[BlogStatus] = None
    is_featured: Optional[bool] = None
    allow_comments: Optional[bool] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    tags: Optional[List[str]] = None
    category: Optional[str] = None


class BlogResponse(BlogBase):
    id: int
    slug: str
    status: BlogStatus
    is_featured: bool
    tags: Optional[List[str]] = None
    views_count: int
    likes_count: int
    author_id: int
    project_id: Optional[int] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BlogAuthor(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    profile_image: Optional[str] = None

    class Config:
        from_attributes = True


class BlogWithAuthor(BlogResponse):
    author: BlogAuthor


class BlogWithDetails(BlogWithAuthor):
    images: List[BlogImageResponse] = []
    comments_count: int = 0


class BlogList(BaseModel):
    blogs: List[BlogWithAuthor]
    total: int


# Blog Feed (public)
class BlogFeedItem(BaseModel):
    id: int
    title: str
    slug: str
    excerpt: Optional[str] = None
    cover_image: Optional[str] = None
    thumbnail: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    views_count: int
    likes_count: int
    author: BlogAuthor
    published_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class BlogFeed(BaseModel):
    blogs: List[BlogFeedItem]
    total: int
