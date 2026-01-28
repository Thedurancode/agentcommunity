from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class BrandBase(BaseModel):
    name: str
    slogan: Optional[str] = None
    main_logo: Optional[str] = None
    dark_logo: Optional[str] = None
    favicon: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    about_us: Optional[str] = None
    company_email: Optional[str] = None
    company_phone: Optional[str] = None
    website_url: Optional[str] = None
    facebook_url: Optional[str] = None
    twitter_url: Optional[str] = None
    instagram_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    youtube_url: Optional[str] = None
    tiktok_url: Optional[str] = None


class BrandCreate(BrandBase):
    pass


class BrandUpdate(BaseModel):
    name: Optional[str] = None
    slogan: Optional[str] = None
    main_logo: Optional[str] = None
    dark_logo: Optional[str] = None
    favicon: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    about_us: Optional[str] = None
    company_email: Optional[str] = None
    company_phone: Optional[str] = None
    website_url: Optional[str] = None
    facebook_url: Optional[str] = None
    twitter_url: Optional[str] = None
    instagram_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    youtube_url: Optional[str] = None
    tiktok_url: Optional[str] = None


class BrandResponse(BrandBase):
    id: int
    project_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
