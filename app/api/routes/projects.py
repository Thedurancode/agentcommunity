from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.user import User, UserRole
from app.models.project import Project
from app.models.team_member import TeamMember, TeamRole
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate, ProjectWithOwner, ProjectList
from app.api.deps import get_current_user, get_current_admin


router = APIRouter(prefix="/projects", tags=["projects"])


async def check_project_access(
    project_id: int,
    user: User,
    db: AsyncSession,
    required_roles: List[TeamRole] = None
) -> Project:
    """Check if user has access to a project."""
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.team_members))
        .where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Admins have access to everything
    if user.role == UserRole.ADMIN:
        return project

    # Check if user is owner
    if project.owner_id == user.id:
        return project

    # Check if user is a team member
    membership = next(
        (tm for tm in project.team_members if tm.user_id == user.id),
        None
    )

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this project",
        )

    if required_roles and membership.role not in required_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for this action",
        )

    return project


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    project = Project(
        name=project_data.name,
        description=project_data.description,
        github_repo_full_name=project_data.github_repo_full_name,
        owner_id=current_user.id,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    # Add owner as team member with OWNER role
    team_member = TeamMember(
        user_id=current_user.id,
        project_id=project.id,
        role=TeamRole.OWNER,
    )
    db.add(team_member)
    await db.commit()

    return project


@router.get("", response_model=ProjectList)
async def list_projects(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Admins see all projects
    if current_user.role == UserRole.ADMIN:
        result = await db.execute(select(Project).offset(skip).limit(limit))
        projects = result.scalars().all()
        count_result = await db.execute(select(Project))
        total = len(count_result.scalars().all())
    else:
        # Team members see only their projects
        result = await db.execute(
            select(Project)
            .join(TeamMember)
            .where(TeamMember.user_id == current_user.id)
            .offset(skip)
            .limit(limit)
        )
        projects = result.scalars().all()
        count_result = await db.execute(
            select(Project)
            .join(TeamMember)
            .where(TeamMember.user_id == current_user.id)
        )
        total = len(count_result.scalars().all())

    return ProjectList(projects=projects, total=total)


@router.get("/{project_id}", response_model=ProjectWithOwner)
async def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.owner), selectinload(Project.team_members))
        .where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Check access
    await check_project_access(project_id, current_user, db)

    return project


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    project_data: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    project = await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    update_data = project_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    project = await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER]
    )

    await db.delete(project)
    await db.commit()
    return None
