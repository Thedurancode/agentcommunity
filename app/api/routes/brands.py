from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.models.brand import Brand
from app.models.team_member import TeamRole
from app.schemas.brand import BrandCreate, BrandResponse, BrandUpdate
from app.api.deps import get_current_user
from app.api.routes.projects import check_project_access
from app.services.storage import get_storage_service, StorageService


router = APIRouter(prefix="/projects/{project_id}/brand", tags=["brands"])


@router.post("", response_model=BrandResponse, status_code=status.HTTP_201_CREATED)
async def create_brand(
    project_id: int,
    brand_data: BrandCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a brand for a project. Each project can only have one brand."""
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    # Check if brand already exists
    result = await db.execute(select(Brand).where(Brand.project_id == project_id))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project already has a brand. Use PATCH to update it.",
        )

    brand = Brand(
        name=brand_data.name,
        slogan=brand_data.slogan,
        main_logo=brand_data.main_logo,
        dark_logo=brand_data.dark_logo,
        favicon=brand_data.favicon,
        primary_color=brand_data.primary_color,
        secondary_color=brand_data.secondary_color,
        about_us=brand_data.about_us,
        company_email=brand_data.company_email,
        company_phone=brand_data.company_phone,
        website_url=brand_data.website_url,
        facebook_url=brand_data.facebook_url,
        twitter_url=brand_data.twitter_url,
        instagram_url=brand_data.instagram_url,
        linkedin_url=brand_data.linkedin_url,
        youtube_url=brand_data.youtube_url,
        tiktok_url=brand_data.tiktok_url,
        project_id=project_id,
    )
    db.add(brand)
    await db.commit()
    await db.refresh(brand)
    return brand


@router.get("", response_model=BrandResponse)
async def get_brand(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get the brand for a project."""
    await check_project_access(project_id, current_user, db)

    result = await db.execute(select(Brand).where(Brand.project_id == project_id))
    brand = result.scalar_one_or_none()

    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found for this project",
        )

    return brand


@router.patch("", response_model=BrandResponse)
async def update_brand(
    project_id: int,
    brand_data: BrandUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update the brand for a project."""
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    result = await db.execute(select(Brand).where(Brand.project_id == project_id))
    brand = result.scalar_one_or_none()

    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found for this project",
        )

    update_data = brand_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(brand, field, value)

    await db.commit()
    await db.refresh(brand)
    return brand


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service)
):
    """Delete the brand for a project."""
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER]
    )

    result = await db.execute(select(Brand).where(Brand.project_id == project_id))
    brand = result.scalar_one_or_none()

    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found for this project",
        )

    # Delete uploaded files
    await storage.delete_brand_assets(project_id)

    await db.delete(brand)
    await db.commit()
    return None


@router.post("/upload/{logo_type}", response_model=BrandResponse)
async def upload_brand_logo(
    project_id: int,
    logo_type: Literal["main", "dark", "favicon"],
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service)
):
    """
    Upload a logo file for the brand.

    - **logo_type**: Type of logo - "main", "dark", or "favicon"
    - **file**: Image file (JPEG, PNG, GIF, WebP, SVG, ICO). Max 5MB.
    """
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    # Get or create brand
    result = await db.execute(select(Brand).where(Brand.project_id == project_id))
    brand = result.scalar_one_or_none()

    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found. Create a brand first before uploading logos.",
        )

    # Delete old file if exists
    old_file_path = getattr(brand, f"{logo_type}_logo" if logo_type != "favicon" else "favicon")
    if old_file_path:
        await storage.delete_file(old_file_path)

    # Save new file
    file_path = await storage.save_brand_logo(project_id, file, logo_type)

    # Update brand with new file path
    if logo_type == "main":
        brand.main_logo = file_path
    elif logo_type == "dark":
        brand.dark_logo = file_path
    elif logo_type == "favicon":
        brand.favicon = file_path

    await db.commit()
    await db.refresh(brand)
    return brand


@router.delete("/upload/{logo_type}", response_model=BrandResponse)
async def delete_brand_logo(
    project_id: int,
    logo_type: Literal["main", "dark", "favicon"],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service)
):
    """Delete a specific logo from the brand."""
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    result = await db.execute(select(Brand).where(Brand.project_id == project_id))
    brand = result.scalar_one_or_none()

    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found for this project",
        )

    # Get current file path
    if logo_type == "main":
        file_path = brand.main_logo
        brand.main_logo = None
    elif logo_type == "dark":
        file_path = brand.dark_logo
        brand.dark_logo = None
    elif logo_type == "favicon":
        file_path = brand.favicon
        brand.favicon = None

    # Delete file
    if file_path:
        await storage.delete_file(file_path)

    await db.commit()
    await db.refresh(brand)
    return brand
