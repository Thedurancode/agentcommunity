from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.user import User
from app.models.issue import Issue, IssueState
from app.models.team_member import TeamRole
from app.schemas.issue import (
    IssueCreate,
    IssueResponse,
    IssueUpdate,
    IssueWithDetails,
    IssueList,
)
from app.api.deps import get_current_user
from app.api.routes.projects import check_project_access
from app.services.recap import get_recap_service


router = APIRouter(prefix="/projects/{project_id}/issues", tags=["issues"])


@router.post("", response_model=IssueResponse, status_code=status.HTTP_201_CREATED)
async def create_issue(
    project_id: int,
    issue_data: IssueCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await check_project_access(project_id, current_user, db)

    issue = Issue(
        title=issue_data.title,
        body=issue_data.body,
        project_id=project_id,
        created_by_id=current_user.id,
        assignee_id=issue_data.assignee_id,
    )
    db.add(issue)
    await db.commit()
    await db.refresh(issue)

    # Update recap
    recap_service = get_recap_service(db)
    await recap_service.update_recent_issues(project_id)

    return issue


@router.get("", response_model=IssueList)
async def list_issues(
    project_id: int,
    state: Optional[IssueState] = Query(None),
    assignee_id: Optional[int] = Query(None),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await check_project_access(project_id, current_user, db)

    query = select(Issue).where(Issue.project_id == project_id)

    if state:
        query = query.where(Issue.state == state)
    if assignee_id:
        query = query.where(Issue.assignee_id == assignee_id)

    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    issues = result.scalars().all()

    # Get total count
    count_query = select(Issue).where(Issue.project_id == project_id)
    if state:
        count_query = count_query.where(Issue.state == state)
    if assignee_id:
        count_query = count_query.where(Issue.assignee_id == assignee_id)
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    return IssueList(issues=issues, total=total)


@router.get("/{issue_id}", response_model=IssueWithDetails)
async def get_issue(
    project_id: int,
    issue_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await check_project_access(project_id, current_user, db)

    result = await db.execute(
        select(Issue)
        .options(selectinload(Issue.assignee), selectinload(Issue.created_by))
        .where(Issue.id == issue_id, Issue.project_id == project_id)
    )
    issue = result.scalar_one_or_none()

    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found",
        )

    return issue


@router.patch("/{issue_id}", response_model=IssueResponse)
async def update_issue(
    project_id: int,
    issue_id: int,
    issue_data: IssueUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await check_project_access(project_id, current_user, db)

    result = await db.execute(
        select(Issue).where(Issue.id == issue_id, Issue.project_id == project_id)
    )
    issue = result.scalar_one_or_none()

    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found",
        )

    update_data = issue_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(issue, field, value)

    await db.commit()
    await db.refresh(issue)

    # Update recap
    recap_service = get_recap_service(db)
    await recap_service.update_recent_issues(project_id)

    return issue


@router.delete("/{issue_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_issue(
    project_id: int,
    issue_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER, TeamRole.DEVELOPER]
    )

    result = await db.execute(
        select(Issue).where(Issue.id == issue_id, Issue.project_id == project_id)
    )
    issue = result.scalar_one_or_none()

    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found",
        )

    await db.delete(issue)
    await db.commit()

    # Update recap
    recap_service = get_recap_service(db)
    await recap_service.update_recent_issues(project_id)

    return None
