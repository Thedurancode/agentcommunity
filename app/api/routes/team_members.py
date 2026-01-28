from typing import List, Optional
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.user import User, UserRole
from app.models.project import Project
from app.models.team_member import TeamMember, TeamRole
from app.schemas.team_member import (
    TeamMemberCreate,
    TeamMemberResponse,
    TeamMemberUpdate,
    TeamMemberWithUser,
    TeamMemberList,
)
from app.api.deps import get_current_user
from app.api.routes.projects import check_project_access
from app.services.github import get_github_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/team", tags=["team-members"])


async def invite_to_github_repo(
    project: Project,
    user: User,
    team_role: TeamRole,
    inviter: User,
) -> Optional[dict]:
    """
    Invite a user to the GitHub repo if the project is linked to GitHub.
    Returns invitation details or None if no GitHub integration.
    """
    # Check if project has GitHub repo linked
    if not project.github_repo_full_name:
        return None

    # Check if user has a GitHub username
    if not user.github_username:
        logger.warning(f"User {user.id} has no GitHub username, skipping repo invite")
        return None

    # Check if inviter has GitHub access token
    if not inviter.github_access_token:
        logger.warning(f"Inviter {inviter.id} has no GitHub access token, skipping repo invite")
        return None

    try:
        github = get_github_service(inviter.github_access_token)
        owner, repo = project.github_repo_full_name.split("/")

        # Check if already a collaborator
        is_collaborator = await github.check_collaborator(owner, repo, user.github_username)
        if is_collaborator:
            logger.info(f"User {user.github_username} is already a collaborator on {project.github_repo_full_name}")
            return {"status": "already_collaborator", "username": user.github_username}

        # Map team role to GitHub permission
        permission = github.map_team_role_to_github_permission(team_role.value)

        # Send invitation
        result = await github.add_collaborator(owner, repo, user.github_username, permission)
        logger.info(f"Invited {user.github_username} to {project.github_repo_full_name} with {permission} permission")
        return result

    except Exception as e:
        logger.error(f"Failed to invite {user.github_username} to GitHub repo: {e}")
        # Don't fail the team member addition if GitHub invite fails
        return {"status": "error", "message": str(e)}


async def remove_from_github_repo(
    project: Project,
    user: User,
    remover: User,
) -> bool:
    """
    Remove a user from the GitHub repo collaborators.
    Returns True if successful or no action needed.
    """
    if not project.github_repo_full_name:
        return True

    if not user.github_username:
        return True

    if not remover.github_access_token:
        logger.warning(f"Remover {remover.id} has no GitHub access token, skipping repo removal")
        return False

    try:
        github = get_github_service(remover.github_access_token)
        owner, repo = project.github_repo_full_name.split("/")

        result = await github.remove_collaborator(owner, repo, user.github_username)
        if result:
            logger.info(f"Removed {user.github_username} from {project.github_repo_full_name}")
        return result

    except Exception as e:
        logger.error(f"Failed to remove {user.github_username} from GitHub repo: {e}")
        return False


@router.post("", response_model=TeamMemberResponse, status_code=status.HTTP_201_CREATED)
async def add_team_member(
    project_id: int,
    member_data: TeamMemberCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Add a team member to a project.
    If the project is linked to a GitHub repo and both users have GitHub accounts,
    the new member will automatically be invited to the repository.
    """
    # Check if current user has permission to add members
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    # Get the project
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Check if user exists
    result = await db.execute(select(User).where(User.id == member_data.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check if already a member
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.project_id == project_id,
            TeamMember.user_id == member_data.user_id
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a team member",
        )

    # Cannot add another owner
    if member_data.role == TeamRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot add another owner. Transfer ownership instead.",
        )

    team_member = TeamMember(
        user_id=member_data.user_id,
        project_id=project_id,
        role=member_data.role,
    )
    db.add(team_member)
    await db.commit()
    await db.refresh(team_member)

    # Invite user to GitHub repo if applicable
    github_invite = await invite_to_github_repo(project, user, member_data.role, current_user)
    if github_invite:
        logger.info(f"GitHub invite result for user {user.id}: {github_invite}")

    return team_member


@router.get("", response_model=TeamMemberList)
async def list_team_members(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await check_project_access(project_id, current_user, db)

    result = await db.execute(
        select(TeamMember)
        .options(selectinload(TeamMember.user))
        .where(TeamMember.project_id == project_id)
    )
    team_members = result.scalars().all()

    return TeamMemberList(team_members=team_members, total=len(team_members))


@router.get("/{member_id}", response_model=TeamMemberWithUser)
async def get_team_member(
    project_id: int,
    member_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await check_project_access(project_id, current_user, db)

    result = await db.execute(
        select(TeamMember)
        .options(selectinload(TeamMember.user))
        .where(TeamMember.id == member_id, TeamMember.project_id == project_id)
    )
    team_member = result.scalar_one_or_none()

    if not team_member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team member not found",
        )

    return team_member


@router.patch("/{member_id}", response_model=TeamMemberResponse)
async def update_team_member(
    project_id: int,
    member_id: int,
    member_data: TeamMemberUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    result = await db.execute(
        select(TeamMember).where(TeamMember.id == member_id, TeamMember.project_id == project_id)
    )
    team_member = result.scalar_one_or_none()

    if not team_member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team member not found",
        )

    # Cannot change owner role or set someone else as owner
    if team_member.role == TeamRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify owner's role",
        )

    if member_data.role == TeamRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot set role to owner. Transfer ownership instead.",
        )

    update_data = member_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(team_member, field, value)

    await db.commit()
    await db.refresh(team_member)
    return team_member


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    project_id: int,
    member_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Remove a team member from a project.
    If the project is linked to a GitHub repo, the member will also be removed
    from the repository collaborators.
    """
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    # Get project
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalar_one_or_none()

    result = await db.execute(
        select(TeamMember)
        .options(selectinload(TeamMember.user))
        .where(TeamMember.id == member_id, TeamMember.project_id == project_id)
    )
    team_member = result.scalar_one_or_none()

    if not team_member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team member not found",
        )

    # Cannot remove owner
    if team_member.role == TeamRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove project owner",
        )

    # Remove from GitHub repo if applicable
    if project and team_member.user:
        await remove_from_github_repo(project, team_member.user, current_user)

    await db.delete(team_member)
    await db.commit()
    return None
