from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.user import User
from app.models.video import Video
from app.models.team_member import TeamRole
from app.schemas.video import (
    VideoCreate,
    VideoResponse,
    VideoUpdate,
    VideoWithUploader,
    VideoList,
    VideoUploadResponse,
)
from app.api.deps import get_current_user
from app.api.routes.projects import check_project_access
from app.services.storage import get_storage_service, StorageService


router = APIRouter(prefix="/projects/{project_id}/videos", tags=["videos"])


@router.post("/upload", response_model=VideoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_video(
    project_id: int,
    title: str = Form(...),
    description: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service)
):
    """
    Upload a video file to the project.

    Supported formats: MP4, WebM, OGV, MOV, AVI, MKV
    Maximum file size: 500MB
    """
    await check_project_access(project_id, current_user, db)

    # Save the video file
    file_path, file_name, file_size, mime_type = await storage.save_video(
        project_id, file
    )

    # Create video record
    video = Video(
        title=title,
        description=description,
        file_path=file_path,
        file_name=file_name,
        file_size=file_size,
        mime_type=mime_type,
        project_id=project_id,
        uploaded_by_id=current_user.id,
    )
    db.add(video)
    await db.commit()
    await db.refresh(video)

    return VideoUploadResponse(
        message="Video uploaded successfully",
        video=video,
    )


@router.post("", response_model=VideoResponse, status_code=status.HTTP_201_CREATED)
async def create_video_link(
    project_id: int,
    video_data: VideoCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a video entry with an external URL (YouTube, Vimeo, etc.).
    Use this for linking to external videos instead of uploading.
    """
    await check_project_access(project_id, current_user, db)

    if not video_data.external_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="External URL is required when not uploading a file. Use /upload endpoint for file uploads.",
        )

    video = Video(
        title=video_data.title,
        description=video_data.description,
        external_url=video_data.external_url,
        file_path="",  # No file for external links
        file_name="",
        project_id=project_id,
        uploaded_by_id=current_user.id,
    )
    db.add(video)
    await db.commit()
    await db.refresh(video)

    return video


@router.get("", response_model=VideoList)
async def list_videos(
    project_id: int,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all videos for a project."""
    await check_project_access(project_id, current_user, db)

    query = (
        select(Video)
        .where(Video.project_id == project_id)
        .order_by(Video.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(query)
    videos = result.scalars().all()

    # Get total count
    count_result = await db.execute(
        select(Video).where(Video.project_id == project_id)
    )
    total = len(count_result.scalars().all())

    return VideoList(videos=videos, total=total)


@router.get("/{video_id}", response_model=VideoWithUploader)
async def get_video(
    project_id: int,
    video_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific video."""
    await check_project_access(project_id, current_user, db)

    result = await db.execute(
        select(Video)
        .options(selectinload(Video.uploaded_by))
        .where(Video.id == video_id, Video.project_id == project_id)
    )
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )

    return video


@router.patch("/{video_id}", response_model=VideoResponse)
async def update_video(
    project_id: int,
    video_id: int,
    video_data: VideoUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update video metadata."""
    await check_project_access(project_id, current_user, db)

    result = await db.execute(
        select(Video).where(Video.id == video_id, Video.project_id == project_id)
    )
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )

    update_data = video_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(video, field, value)

    await db.commit()
    await db.refresh(video)
    return video


@router.post("/{video_id}/thumbnail", response_model=VideoResponse)
async def upload_thumbnail(
    project_id: int,
    video_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service)
):
    """Upload a thumbnail image for a video."""
    await check_project_access(project_id, current_user, db)

    result = await db.execute(
        select(Video).where(Video.id == video_id, Video.project_id == project_id)
    )
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )

    # Delete old thumbnail if exists
    if video.thumbnail_path:
        await storage.delete_file(video.thumbnail_path)

    # Save new thumbnail
    thumbnail_path = await storage.save_video_thumbnail(project_id, file, video_id)
    video.thumbnail_path = thumbnail_path

    await db.commit()
    await db.refresh(video)
    return video


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(
    project_id: int,
    video_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service)
):
    """Delete a video and its associated files."""
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER, TeamRole.DEVELOPER]
    )

    result = await db.execute(
        select(Video).where(Video.id == video_id, Video.project_id == project_id)
    )
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )

    # Delete associated files
    if video.file_path:
        await storage.delete_file(video.file_path)
    if video.thumbnail_path:
        await storage.delete_file(video.thumbnail_path)

    await db.delete(video)
    await db.commit()
    return None
