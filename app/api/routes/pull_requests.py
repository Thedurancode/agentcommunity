from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.user import User
from app.models.pull_request import PullRequest, PRState
from app.models.team_member import TeamRole
from app.schemas.pull_request import (
    PullRequestCreate,
    PullRequestResponse,
    PullRequestUpdate,
    PullRequestWithAuthor,
    PullRequestList,
)
from app.api.deps import get_current_user
from app.api.routes.projects import check_project_access


router = APIRouter(prefix="/projects/{project_id}/pull-requests", tags=["pull-requests"])


@router.post("", response_model=PullRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_pull_request(
    project_id: int,
    pr_data: PullRequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await check_project_access(project_id, current_user, db)

    pull_request = PullRequest(
        title=pr_data.title,
        body=pr_data.body,
        head_branch=pr_data.head_branch,
        base_branch=pr_data.base_branch,
        project_id=project_id,
        author_id=current_user.id,
    )
    db.add(pull_request)
    await db.commit()
    await db.refresh(pull_request)
    return pull_request


@router.get("", response_model=PullRequestList)
async def list_pull_requests(
    project_id: int,
    state: Optional[PRState] = Query(None),
    author_id: Optional[int] = Query(None),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await check_project_access(project_id, current_user, db)

    query = select(PullRequest).where(PullRequest.project_id == project_id)

    if state:
        query = query.where(PullRequest.state == state)
    if author_id:
        query = query.where(PullRequest.author_id == author_id)

    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    pull_requests = result.scalars().all()

    # Get total count
    count_query = select(PullRequest).where(PullRequest.project_id == project_id)
    if state:
        count_query = count_query.where(PullRequest.state == state)
    if author_id:
        count_query = count_query.where(PullRequest.author_id == author_id)
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    return PullRequestList(pull_requests=pull_requests, total=total)


@router.get("/{pr_id}", response_model=PullRequestWithAuthor)
async def get_pull_request(
    project_id: int,
    pr_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await check_project_access(project_id, current_user, db)

    result = await db.execute(
        select(PullRequest)
        .options(selectinload(PullRequest.author))
        .where(PullRequest.id == pr_id, PullRequest.project_id == project_id)
    )
    pull_request = result.scalar_one_or_none()

    if not pull_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pull request not found",
        )

    return pull_request


@router.patch("/{pr_id}", response_model=PullRequestResponse)
async def update_pull_request(
    project_id: int,
    pr_id: int,
    pr_data: PullRequestUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await check_project_access(project_id, current_user, db)

    result = await db.execute(
        select(PullRequest).where(PullRequest.id == pr_id, PullRequest.project_id == project_id)
    )
    pull_request = result.scalar_one_or_none()

    if not pull_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pull request not found",
        )

    update_data = pr_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(pull_request, field, value)

    await db.commit()
    await db.refresh(pull_request)
    return pull_request


@router.post("/{pr_id}/merge", response_model=PullRequestResponse)
async def merge_pull_request(
    project_id: int,
    pr_id: int,
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
        select(PullRequest).where(PullRequest.id == pr_id, PullRequest.project_id == project_id)
    )
    pull_request = result.scalar_one_or_none()

    if not pull_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pull request not found",
        )

    if pull_request.state != PRState.OPEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only merge open pull requests",
        )

    from datetime import datetime
    pull_request.state = PRState.MERGED
    pull_request.merged_at = datetime.utcnow()

    await db.commit()
    await db.refresh(pull_request)
    return pull_request


@router.delete("/{pr_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pull_request(
    project_id: int,
    pr_id: int,
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
        select(PullRequest).where(PullRequest.id == pr_id, PullRequest.project_id == project_id)
    )
    pull_request = result.scalar_one_or_none()

    if not pull_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pull request not found",
        )

    await db.delete(pull_request)
    await db.commit()
    return None
