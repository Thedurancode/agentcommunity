from datetime import datetime
from typing import Optional
import json

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_current_admin
from app.core.database import get_db
from app.models.user import User
from app.models.episode import Episode
from app.models.episode_segment import EpisodeSegment
from app.schemas.episode import (
    EpisodeCreate,
    EpisodeUpdate,
    EpisodeResponse,
    EpisodeList,
)
from app.schemas.episode_segment import (
    EpisodeSegmentResponse,
    EpisodeSegmentList,
    GeneratedEpisodeStructure,
)
from app.services.episode_generator import (
    generate_episode_structure,
    generate_episode_from_project,
    create_segments_from_structure,
)

router = APIRouter(prefix="/episodes", tags=["episodes"])


@router.post("", response_model=EpisodeResponse, status_code=status.HTTP_201_CREATED)
async def create_episode(
    episode_data: EpisodeCreate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new episode. Admin only. Set auto_generate_segments=true to auto-create TV show segments."""
    episode = Episode(
        title=episode_data.title,
        description=episode_data.description,
        episode_number=episode_data.episode_number,
        season_number=episode_data.season_number,
        image_url=episode_data.image_url,
        video_url=episode_data.video_url,
        audio_url=episode_data.audio_url,
        duration_seconds=episode_data.duration_seconds,
        project_id=episode_data.project_id,
    )
    db.add(episode)
    await db.commit()
    await db.refresh(episode)

    # Auto-generate segments if requested and project is linked
    if episode_data.auto_generate_segments and episode_data.project_id:
        try:
            structure = await generate_episode_from_project(db, episode.id, episode.project_id)
            await create_segments_from_structure(db, episode.id, structure)
            episode.duration_seconds = structure.total_duration_seconds
            await db.commit()
            await db.refresh(episode)
        except ValueError:
            # If generation fails, episode is still created without segments
            pass

    return episode


@router.get("", response_model=EpisodeList)
async def list_episodes(
    published_only: bool = Query(True, description="Only show published episodes"),
    season: Optional[int] = Query(None, description="Filter by season number"),
    project_id: Optional[int] = Query(None, description="Filter by project"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List episodes. Public endpoint for published episodes."""
    query = select(Episode)
    count_query = select(func.count(Episode.id))

    if published_only:
        query = query.where(Episode.is_published == True)
        count_query = count_query.where(Episode.is_published == True)

    if season is not None:
        query = query.where(Episode.season_number == season)
        count_query = count_query.where(Episode.season_number == season)

    if project_id is not None:
        query = query.where(Episode.project_id == project_id)
        count_query = count_query.where(Episode.project_id == project_id)

    query = query.order_by(
        Episode.season_number.desc().nullslast(),
        Episode.episode_number.desc().nullslast(),
        Episode.created_at.desc()
    ).offset(skip).limit(limit)

    result = await db.execute(query)
    episodes = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return EpisodeList(episodes=episodes, total=total)


@router.get("/all", response_model=EpisodeList)
async def list_all_episodes(
    season: Optional[int] = Query(None, description="Filter by season number"),
    project_id: Optional[int] = Query(None, description="Filter by project"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all episodes including unpublished. Admin only."""
    query = select(Episode)
    count_query = select(func.count(Episode.id))

    if season is not None:
        query = query.where(Episode.season_number == season)
        count_query = count_query.where(Episode.season_number == season)

    if project_id is not None:
        query = query.where(Episode.project_id == project_id)
        count_query = count_query.where(Episode.project_id == project_id)

    query = query.order_by(
        Episode.season_number.desc().nullslast(),
        Episode.episode_number.desc().nullslast(),
        Episode.created_at.desc()
    ).offset(skip).limit(limit)

    result = await db.execute(query)
    episodes = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return EpisodeList(episodes=episodes, total=total)


@router.get("/{episode_id}", response_model=EpisodeResponse)
async def get_episode(
    episode_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific episode."""
    result = await db.execute(select(Episode).where(Episode.id == episode_id))
    episode = result.scalar_one_or_none()

    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found",
        )

    # Only return unpublished episodes to admins
    if not episode.is_published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found",
        )

    return episode


@router.get("/{episode_id}/admin", response_model=EpisodeResponse)
async def get_episode_admin(
    episode_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific episode including unpublished. Admin only."""
    result = await db.execute(select(Episode).where(Episode.id == episode_id))
    episode = result.scalar_one_or_none()

    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found",
        )

    return episode


@router.patch("/{episode_id}", response_model=EpisodeResponse)
async def update_episode(
    episode_id: int,
    episode_data: EpisodeUpdate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update an episode. Admin only."""
    result = await db.execute(select(Episode).where(Episode.id == episode_id))
    episode = result.scalar_one_or_none()

    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found",
        )

    update_data = episode_data.model_dump(exclude_unset=True)

    # Handle publishing
    if "is_published" in update_data:
        if update_data["is_published"] and not episode.is_published:
            episode.published_at = datetime.utcnow()
        elif not update_data["is_published"]:
            episode.published_at = None

    for field, value in update_data.items():
        setattr(episode, field, value)

    await db.commit()
    await db.refresh(episode)
    return episode


@router.post("/{episode_id}/publish", response_model=EpisodeResponse)
async def publish_episode(
    episode_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Publish an episode. Admin only."""
    result = await db.execute(select(Episode).where(Episode.id == episode_id))
    episode = result.scalar_one_or_none()

    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found",
        )

    if episode.is_published:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Episode is already published",
        )

    episode.is_published = True
    episode.published_at = datetime.utcnow()

    await db.commit()
    await db.refresh(episode)
    return episode


@router.post("/{episode_id}/unpublish", response_model=EpisodeResponse)
async def unpublish_episode(
    episode_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Unpublish an episode. Admin only."""
    result = await db.execute(select(Episode).where(Episode.id == episode_id))
    episode = result.scalar_one_or_none()

    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found",
        )

    if not episode.is_published:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Episode is not published",
        )

    episode.is_published = False
    episode.published_at = None

    await db.commit()
    await db.refresh(episode)
    return episode


@router.delete("/{episode_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_episode(
    episode_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete an episode. Admin only."""
    result = await db.execute(select(Episode).where(Episode.id == episode_id))
    episode = result.scalar_one_or_none()

    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found",
        )

    await db.delete(episode)
    await db.commit()


# ============ Segment Generation Endpoints ============

@router.post("/{episode_id}/generate-structure", response_model=GeneratedEpisodeStructure)
async def generate_episode_structure_endpoint(
    episode_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a TV show style episode structure (8 minutes, 4x2-min segments).
    Uses the episode's linked project data if available.
    Returns the structure without saving - use /create-segments to persist.
    Admin only.
    """
    result = await db.execute(select(Episode).where(Episode.id == episode_id))
    episode = result.scalar_one_or_none()

    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found",
        )

    if episode.project_id:
        # Generate from project data
        try:
            structure = await generate_episode_from_project(db, episode_id, episode.project_id)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
    else:
        # Generate basic structure
        structure = generate_episode_structure(episode_title=episode.title)

    return structure


@router.post("/{episode_id}/create-segments", response_model=EpisodeSegmentList)
async def create_episode_segments(
    episode_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate and persist episode segments for a TV show style episode.
    Creates 4 segments of 2 minutes each (8 minutes total).
    Admin only.
    """
    result = await db.execute(select(Episode).where(Episode.id == episode_id))
    episode = result.scalar_one_or_none()

    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found",
        )

    # Check if segments already exist
    existing_result = await db.execute(
        select(func.count(EpisodeSegment.id)).where(EpisodeSegment.episode_id == episode_id)
    )
    existing_count = existing_result.scalar()

    if existing_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Episode already has {existing_count} segments. Delete them first.",
        )

    # Generate structure
    if episode.project_id:
        try:
            structure = await generate_episode_from_project(db, episode_id, episode.project_id)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
    else:
        structure = generate_episode_structure(episode_title=episode.title)

    # Create segments
    segments = await create_segments_from_structure(db, episode_id, structure)

    # Update episode duration
    episode.duration_seconds = structure.total_duration_seconds
    await db.commit()

    return EpisodeSegmentList(
        segments=[EpisodeSegmentResponse.model_validate(s) for s in segments],
        total=len(segments)
    )


@router.get("/{episode_id}/segments", response_model=EpisodeSegmentList)
async def get_episode_segments(
    episode_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get all segments for an episode."""
    result = await db.execute(select(Episode).where(Episode.id == episode_id))
    episode = result.scalar_one_or_none()

    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found",
        )

    segments_result = await db.execute(
        select(EpisodeSegment)
        .where(EpisodeSegment.episode_id == episode_id)
        .order_by(EpisodeSegment.segment_number)
    )
    segments = segments_result.scalars().all()

    return EpisodeSegmentList(segments=segments, total=len(segments))


@router.delete("/{episode_id}/segments", status_code=status.HTTP_204_NO_CONTENT)
async def delete_episode_segments(
    episode_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete all segments for an episode. Admin only."""
    result = await db.execute(select(Episode).where(Episode.id == episode_id))
    episode = result.scalar_one_or_none()

    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found",
        )

    await db.execute(
        EpisodeSegment.__table__.delete().where(EpisodeSegment.episode_id == episode_id)
    )
    await db.commit()
