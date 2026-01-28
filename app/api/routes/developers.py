import json
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.developer_profile import DeveloperProfile, DeveloperFollow, DeveloperStatus
from app.schemas.developer_profile import (
    DeveloperProfileCreate,
    DeveloperProfileUpdate,
    DeveloperProfileResponse,
    DeveloperFeedItem,
    DeveloperFeedList,
    DeveloperUserInfo,
    FollowResponse,
    FollowStats,
    ProjectSummary,
)
from app.api.deps import get_current_user


router = APIRouter(prefix="/developers", tags=["developers"])


def parse_json_list(json_str: Optional[str]) -> List[str]:
    """Parse a JSON string to a list, return empty list if invalid."""
    if not json_str:
        return []
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return []


def to_json_str(items: Optional[List[str]]) -> Optional[str]:
    """Convert a list to JSON string."""
    if items is None:
        return None
    return json.dumps(items)


# ============== PROFILE ENDPOINTS ==============

@router.get("/me", response_model=DeveloperProfileResponse)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get the current user's developer profile."""
    result = await db.execute(
        select(DeveloperProfile).where(DeveloperProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Developer profile not found. Create one first."
        )

    # Parse JSON fields
    response = DeveloperProfileResponse.model_validate(profile)
    response.skills = parse_json_list(profile.skills)
    response.expertise_areas = parse_json_list(profile.expertise_areas)
    return response


@router.post("/me", response_model=DeveloperProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_my_profile(
    profile_data: DeveloperProfileCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create developer profile for current user."""
    # Check if profile already exists
    existing = await db.execute(
        select(DeveloperProfile).where(DeveloperProfile.user_id == current_user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile already exists. Use PATCH to update."
        )

    # Count user's projects
    projects_result = await db.execute(
        select(func.count(Project.id)).where(Project.owner_id == current_user.id)
    )
    projects_count = projects_result.scalar() or 0

    profile = DeveloperProfile(
        user_id=current_user.id,
        headline=profile_data.headline,
        bio=profile_data.bio,
        location=profile_data.location,
        timezone=profile_data.timezone,
        status=profile_data.status,
        status_message=profile_data.status_message,
        skills=to_json_str(profile_data.skills),
        expertise_areas=to_json_str(profile_data.expertise_areas),
        website_url=profile_data.website_url,
        twitter_url=profile_data.twitter_url,
        linkedin_url=profile_data.linkedin_url,
        youtube_url=profile_data.youtube_url,
        twitch_url=profile_data.twitch_url,
        is_public=profile_data.is_public,
        show_email=profile_data.show_email,
        show_projects=profile_data.show_projects,
        pinned_message=profile_data.pinned_message,
        projects_count=projects_count,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    response = DeveloperProfileResponse.model_validate(profile)
    response.skills = parse_json_list(profile.skills)
    response.expertise_areas = parse_json_list(profile.expertise_areas)
    return response


@router.patch("/me", response_model=DeveloperProfileResponse)
async def update_my_profile(
    profile_data: DeveloperProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update current user's developer profile."""
    result = await db.execute(
        select(DeveloperProfile).where(DeveloperProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Developer profile not found. Create one first."
        )

    update_data = profile_data.model_dump(exclude_unset=True)

    # Handle JSON fields
    if "skills" in update_data:
        update_data["skills"] = to_json_str(update_data["skills"])
    if "expertise_areas" in update_data:
        update_data["expertise_areas"] = to_json_str(update_data["expertise_areas"])

    for field, value in update_data.items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)

    response = DeveloperProfileResponse.model_validate(profile)
    response.skills = parse_json_list(profile.skills)
    response.expertise_areas = parse_json_list(profile.expertise_areas)
    return response


# ============== FEED ENDPOINTS ==============

@router.get("/feed", response_model=DeveloperFeedList)
async def get_developers_feed(
    query: Optional[str] = Query(None, description="Search in name, username, bio"),
    skills: Optional[str] = Query(None, description="Comma-separated skills to filter"),
    status_filter: Optional[DeveloperStatus] = Query(None, alias="status"),
    location: Optional[str] = Query(None, description="Filter by location"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the community developers feed.
    Returns public profiles with user info and recent projects.
    """
    # Base query for public profiles
    base_query = (
        select(DeveloperProfile)
        .options(selectinload(DeveloperProfile.user))
        .where(DeveloperProfile.is_public == True)
    )

    # Search filter
    if query:
        search_term = f"%{query}%"
        base_query = base_query.join(User).where(
            or_(
                User.username.ilike(search_term),
                User.full_name.ilike(search_term),
                DeveloperProfile.bio.ilike(search_term),
                DeveloperProfile.headline.ilike(search_term),
            )
        )

    # Status filter
    if status_filter:
        base_query = base_query.where(DeveloperProfile.status == status_filter)

    # Location filter
    if location:
        base_query = base_query.where(DeveloperProfile.location.ilike(f"%{location}%"))

    # Skills filter (search in JSON field)
    if skills:
        skill_list = [s.strip().lower() for s in skills.split(",")]
        for skill in skill_list:
            base_query = base_query.where(
                func.lower(DeveloperProfile.skills).contains(skill)
            )

    # Count total
    count_query = select(func.count()).select_from(base_query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Get paginated results
    base_query = base_query.order_by(DeveloperProfile.updated_at.desc()).offset(skip).limit(limit)
    result = await db.execute(base_query)
    profiles = result.scalars().all()

    # Get following status for current user
    following_result = await db.execute(
        select(DeveloperFollow.following_id).where(DeveloperFollow.follower_id == current_user.id)
    )
    following_ids = set(row[0] for row in following_result.all())

    # Build feed items
    feed_items = []
    for profile in profiles:
        user = profile.user

        # Get recent projects for this developer
        projects_result = await db.execute(
            select(Project)
            .where(Project.owner_id == user.id)
            .order_by(Project.updated_at.desc())
            .limit(3)
        )
        recent_projects = projects_result.scalars().all()

        user_info = DeveloperUserInfo(
            id=user.id,
            username=user.username,
            full_name=user.full_name,
            profile_image=user.profile_image,
            github_username=user.github_username,
        )

        profile_response = DeveloperProfileResponse.model_validate(profile)
        profile_response.skills = parse_json_list(profile.skills)
        profile_response.expertise_areas = parse_json_list(profile.expertise_areas)

        feed_item = DeveloperFeedItem(
            user=user_info,
            profile=profile_response,
            recent_projects=[
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "github_url": p.github_url,
                }
                for p in recent_projects
            ] if profile.show_projects else [],
            is_following=user.id in following_ids,
        )
        feed_items.append(feed_item)

    return DeveloperFeedList(developers=feed_items, total=total)


@router.get("/{user_id}", response_model=DeveloperFeedItem)
async def get_developer_profile(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific developer's public profile."""
    result = await db.execute(
        select(DeveloperProfile)
        .options(selectinload(DeveloperProfile.user))
        .where(DeveloperProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Developer profile not found"
        )

    # Check if public or own profile
    if not profile.is_public and profile.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This profile is private"
        )

    user = profile.user

    # Get recent projects
    projects_result = await db.execute(
        select(Project)
        .where(Project.owner_id == user.id)
        .order_by(Project.updated_at.desc())
        .limit(5)
    )
    recent_projects = projects_result.scalars().all()

    # Check if following
    follow_result = await db.execute(
        select(DeveloperFollow).where(
            DeveloperFollow.follower_id == current_user.id,
            DeveloperFollow.following_id == user.id
        )
    )
    is_following = follow_result.scalar_one_or_none() is not None

    user_info = DeveloperUserInfo(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        profile_image=user.profile_image,
        github_username=user.github_username,
    )

    profile_response = DeveloperProfileResponse.model_validate(profile)
    profile_response.skills = parse_json_list(profile.skills)
    profile_response.expertise_areas = parse_json_list(profile.expertise_areas)

    return DeveloperFeedItem(
        user=user_info,
        profile=profile_response,
        recent_projects=[
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "github_url": p.github_url,
            }
            for p in recent_projects
        ] if profile.show_projects else [],
        is_following=is_following,
    )


# ============== FOLLOW ENDPOINTS ==============

@router.post("/{user_id}/follow", response_model=FollowResponse, status_code=status.HTTP_201_CREATED)
async def follow_developer(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Follow a developer."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot follow yourself"
        )

    # Check if user exists
    user_result = await db.execute(select(User).where(User.id == user_id))
    if not user_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Check if already following
    existing = await db.execute(
        select(DeveloperFollow).where(
            DeveloperFollow.follower_id == current_user.id,
            DeveloperFollow.following_id == user_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already following this developer"
        )

    follow = DeveloperFollow(
        follower_id=current_user.id,
        following_id=user_id,
    )
    db.add(follow)

    # Update follower counts
    await _update_follow_counts(db, current_user.id, user_id)

    await db.commit()
    await db.refresh(follow)
    return follow


@router.delete("/{user_id}/follow", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow_developer(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Unfollow a developer."""
    result = await db.execute(
        select(DeveloperFollow).where(
            DeveloperFollow.follower_id == current_user.id,
            DeveloperFollow.following_id == user_id
        )
    )
    follow = result.scalar_one_or_none()

    if not follow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not following this developer"
        )

    await db.delete(follow)

    # Update follower counts
    await _update_follow_counts(db, current_user.id, user_id, unfollow=True)

    await db.commit()
    return None


@router.get("/{user_id}/follow-stats", response_model=FollowStats)
async def get_follow_stats(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get follow statistics for a user."""
    # Followers count
    followers_result = await db.execute(
        select(func.count(DeveloperFollow.id)).where(DeveloperFollow.following_id == user_id)
    )
    followers_count = followers_result.scalar() or 0

    # Following count
    following_result = await db.execute(
        select(func.count(DeveloperFollow.id)).where(DeveloperFollow.follower_id == user_id)
    )
    following_count = following_result.scalar() or 0

    # Check if current user is following
    is_following_result = await db.execute(
        select(DeveloperFollow).where(
            DeveloperFollow.follower_id == current_user.id,
            DeveloperFollow.following_id == user_id
        )
    )
    is_following = is_following_result.scalar_one_or_none() is not None

    # Check if target user is following current user
    is_followed_by_result = await db.execute(
        select(DeveloperFollow).where(
            DeveloperFollow.follower_id == user_id,
            DeveloperFollow.following_id == current_user.id
        )
    )
    is_followed_by = is_followed_by_result.scalar_one_or_none() is not None

    return FollowStats(
        followers_count=followers_count,
        following_count=following_count,
        is_following=is_following,
        is_followed_by=is_followed_by,
    )


async def _update_follow_counts(
    db: AsyncSession,
    follower_id: int,
    following_id: int,
    unfollow: bool = False
):
    """Update the cached follower/following counts on profiles."""
    delta = -1 if unfollow else 1

    # Update follower's following_count
    follower_profile = await db.execute(
        select(DeveloperProfile).where(DeveloperProfile.user_id == follower_id)
    )
    fp = follower_profile.scalar_one_or_none()
    if fp:
        fp.following_count = max(0, fp.following_count + delta)

    # Update following's followers_count
    following_profile = await db.execute(
        select(DeveloperProfile).where(DeveloperProfile.user_id == following_id)
    )
    fg = following_profile.scalar_one_or_none()
    if fg:
        fg.followers_count = max(0, fg.followers_count + delta)
