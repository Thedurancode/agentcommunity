from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.recap import Recap
from app.models.team_member import TeamRole
from app.schemas.recap import RecapResponse, RecapUpdate, RecapRefreshResponse, AISummaryResponse
from app.api.deps import get_current_user
from app.api.routes.projects import check_project_access
from app.services.recap import get_recap_service
from app.services.ai import get_ai_service


router = APIRouter(prefix="/projects/{project_id}/recap", tags=["recap"])


@router.get("", response_model=RecapResponse)
async def get_recap(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get the recap for a project with recent commits, issues, and notes."""
    await check_project_access(project_id, current_user, db)

    recap_service = get_recap_service(db)
    recap = await recap_service.get_or_create_recap(project_id)

    return recap


@router.post("/refresh", response_model=RecapRefreshResponse)
async def refresh_recap(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Refresh the recap by fetching latest data.

    - Fetches last 5 commits from GitHub (if linked)
    - Updates last 5 issues from database
    - Updates last 5 notes from database
    """
    await check_project_access(project_id, current_user, db)

    recap_service = get_recap_service(db)
    result = await recap_service.refresh_all(
        project_id,
        github_access_token=current_user.github_access_token
    )

    return RecapRefreshResponse(
        message="Recap refreshed successfully",
        **result
    )


@router.post("/refresh/commits", response_model=RecapRefreshResponse)
async def refresh_commits(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Refresh only the recent commits from GitHub."""
    await check_project_access(project_id, current_user, db)

    if not current_user.github_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub account not connected",
        )

    recap_service = get_recap_service(db)
    commits_count = await recap_service.update_recent_commits(
        project_id,
        current_user.github_access_token
    )

    return RecapRefreshResponse(
        message="Commits refreshed successfully",
        commits_updated=commits_count,
        issues_updated=0,
        notes_updated=0,
    )


@router.post("/refresh/issues", response_model=RecapRefreshResponse)
async def refresh_issues(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Refresh only the recent issues."""
    await check_project_access(project_id, current_user, db)

    recap_service = get_recap_service(db)
    issues_count = await recap_service.update_recent_issues(project_id)

    return RecapRefreshResponse(
        message="Issues refreshed successfully",
        commits_updated=0,
        issues_updated=issues_count,
        notes_updated=0,
    )


@router.post("/refresh/notes", response_model=RecapRefreshResponse)
async def refresh_notes(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Refresh only the recent notes."""
    await check_project_access(project_id, current_user, db)

    recap_service = get_recap_service(db)
    notes_count = await recap_service.update_recent_notes(project_id)

    return RecapRefreshResponse(
        message="Notes refreshed successfully",
        commits_updated=0,
        issues_updated=0,
        notes_updated=notes_count,
    )


@router.patch("", response_model=RecapResponse)
async def update_recap_summary(
    project_id: int,
    recap_data: RecapUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update the recap summary text."""
    await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    if recap_data.summary is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Summary is required",
        )

    recap_service = get_recap_service(db)
    recap = await recap_service.update_summary(project_id, recap_data.summary)

    return recap


@router.post("/ai/generate-summary", response_model=AISummaryResponse)
async def generate_ai_summary(
    project_id: int,
    auto_save: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate an AI-powered summary of recent project activity.

    Uses Claude to analyze recent commits, issues, and notes to create
    a concise summary of what's happening in the project.

    - **auto_save**: If true, automatically saves the summary to the recap
    """
    await check_project_access(project_id, current_user, db)

    ai_service = get_ai_service()
    if not ai_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured. Set ANTHROPIC_API_KEY in environment.",
        )

    # Get project name
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Get current recap data
    recap_service = get_recap_service(db)
    recap = await recap_service.get_or_create_recap(project_id)

    try:
        summary = await ai_service.generate_recap_summary(
            project_name=project.name,
            recent_commits=recap.recent_commits or [],
            recent_issues=recap.recent_issues or [],
            recent_notes=recap.recent_notes or [],
        )

        # Auto-save if requested
        if auto_save:
            recap = await recap_service.update_summary(project_id, summary)

        return AISummaryResponse(
            summary=summary,
            saved=auto_save,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate AI summary: {str(e)}",
        )


@router.post("/ai/suggest-next-steps", response_model=AISummaryResponse)
async def suggest_next_steps(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get AI-suggested next steps for the project.

    Analyzes recent activity and suggests concrete actions the team should consider.
    """
    await check_project_access(project_id, current_user, db)

    ai_service = get_ai_service()
    if not ai_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured. Set ANTHROPIC_API_KEY in environment.",
        )

    # Get project name
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Get current recap data
    recap_service = get_recap_service(db)
    recap = await recap_service.get_or_create_recap(project_id)

    try:
        suggestions = await ai_service.suggest_next_steps(
            project_name=project.name,
            recent_commits=recap.recent_commits or [],
            recent_issues=recap.recent_issues or [],
            recent_notes=recap.recent_notes or [],
        )

        return AISummaryResponse(
            summary=suggestions,
            saved=False,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate suggestions: {str(e)}",
        )
