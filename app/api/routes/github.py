from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.issue import Issue
from app.models.pull_request import PullRequest
from app.models.team_member import TeamRole
from app.api.deps import get_current_user
from app.api.routes.projects import check_project_access
from app.services.github import get_github_service


router = APIRouter(prefix="/github", tags=["github"])


class CreateRepoRequest(BaseModel):
    name: str
    description: Optional[str] = None
    private: bool = False
    auto_init: bool = True
    gitignore_template: Optional[str] = None
    license_template: Optional[str] = None
    project_id: Optional[int] = None  # Optional: link to existing project


@router.get("/repos")
async def list_github_repos(
    current_user: User = Depends(get_current_user),
):
    """List GitHub repositories for the authenticated user."""
    if not current_user.github_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub account not connected",
        )

    github = get_github_service(current_user.github_access_token)
    return await github.list_user_repos()


@router.post("/repos")
async def create_github_repo(
    repo_data: CreateRepoRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new GitHub repository.

    Optionally link it to an existing project by providing project_id.
    """
    if not current_user.github_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub account not connected. Please connect your GitHub account first.",
        )

    github = get_github_service(current_user.github_access_token)

    # Create the repo on GitHub
    try:
        repo_info = await github.create_repository(
            name=repo_data.name,
            description=repo_data.description,
            private=repo_data.private,
            auto_init=repo_data.auto_init,
            gitignore_template=repo_data.gitignore_template,
            license_template=repo_data.license_template,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create GitHub repository: {str(e)}",
        )

    result = {
        "message": "Repository created successfully",
        "repo": {
            "id": repo_info["id"],
            "name": repo_info["name"],
            "full_name": repo_info["full_name"],
            "url": repo_info["html_url"],
            "private": repo_info["private"],
        }
    }

    # If project_id provided, link the repo to the project
    if repo_data.project_id:
        project = await check_project_access(
            repo_data.project_id,
            current_user,
            db,
            required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
        )

        project.github_repo_id = repo_info["id"]
        project.github_repo_name = repo_info["name"]
        project.github_repo_full_name = repo_info["full_name"]
        project.github_repo_url = repo_info["html_url"]

        await db.commit()
        await db.refresh(project)

        result["project_linked"] = True
        result["project_id"] = project.id

    return result


@router.post("/projects/{project_id}/sync-issues")
async def sync_github_issues(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Sync issues from GitHub repository to local project."""
    project = await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    if not project.github_repo_full_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project is not linked to a GitHub repository",
        )

    if not current_user.github_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub account not connected",
        )

    owner, repo = project.github_repo_full_name.split("/")
    github = get_github_service(current_user.github_access_token)

    try:
        github_issues = await github.list_issues(owner, repo, state="all")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch issues from GitHub: {str(e)}",
        )

    synced_count = 0
    for gh_issue in github_issues:
        # Skip pull requests (GitHub returns them as issues too)
        if "pull_request" in gh_issue:
            continue

        # Check if issue already exists
        result = await db.execute(
            select(Issue).where(
                Issue.project_id == project_id,
                Issue.github_issue_id == gh_issue["id"]
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing issue
            existing.title = gh_issue["title"]
            existing.body = gh_issue.get("body")
            existing.state = "open" if gh_issue["state"] == "open" else "closed"
        else:
            # Create new issue
            issue = Issue(
                title=gh_issue["title"],
                body=gh_issue.get("body"),
                state="open" if gh_issue["state"] == "open" else "closed",
                project_id=project_id,
                github_issue_id=gh_issue["id"],
                github_issue_number=gh_issue["number"],
                github_issue_url=gh_issue["html_url"],
            )
            db.add(issue)
            synced_count += 1

    await db.commit()
    return {"message": f"Synced {synced_count} new issues", "total_processed": len(github_issues)}


@router.post("/projects/{project_id}/sync-pull-requests")
async def sync_github_pull_requests(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Sync pull requests from GitHub repository to local project."""
    project = await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    if not project.github_repo_full_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project is not linked to a GitHub repository",
        )

    if not current_user.github_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub account not connected",
        )

    owner, repo = project.github_repo_full_name.split("/")
    github = get_github_service(current_user.github_access_token)

    try:
        github_prs = await github.list_pull_requests(owner, repo, state="all")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch pull requests from GitHub: {str(e)}",
        )

    synced_count = 0
    for gh_pr in github_prs:
        # Check if PR already exists
        result = await db.execute(
            select(PullRequest).where(
                PullRequest.project_id == project_id,
                PullRequest.github_pr_id == gh_pr["id"]
            )
        )
        existing = result.scalar_one_or_none()

        # Determine state
        if gh_pr.get("merged_at"):
            state = "merged"
        elif gh_pr["state"] == "closed":
            state = "closed"
        else:
            state = "open"

        if existing:
            # Update existing PR
            existing.title = gh_pr["title"]
            existing.body = gh_pr.get("body")
            existing.state = state
            existing.head_branch = gh_pr["head"]["ref"]
            existing.base_branch = gh_pr["base"]["ref"]
        else:
            # Create new PR
            pr = PullRequest(
                title=gh_pr["title"],
                body=gh_pr.get("body"),
                state=state,
                head_branch=gh_pr["head"]["ref"],
                base_branch=gh_pr["base"]["ref"],
                project_id=project_id,
                github_pr_id=gh_pr["id"],
                github_pr_number=gh_pr["number"],
                github_pr_url=gh_pr["html_url"],
            )
            db.add(pr)
            synced_count += 1

    await db.commit()
    return {"message": f"Synced {synced_count} new pull requests", "total_processed": len(github_prs)}


@router.post("/projects/{project_id}/link-repo")
async def link_github_repo(
    project_id: int,
    repo_full_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Link a GitHub repository to a project."""
    project = await check_project_access(
        project_id,
        current_user,
        db,
        required_roles=[TeamRole.OWNER, TeamRole.MAINTAINER]
    )

    if not current_user.github_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub account not connected",
        )

    owner, repo = repo_full_name.split("/")
    github = get_github_service(current_user.github_access_token)

    try:
        repo_info = await github.get_repository(owner, repo)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found or access denied: {str(e)}",
        )

    project.github_repo_id = repo_info["id"]
    project.github_repo_name = repo_info["name"]
    project.github_repo_full_name = repo_info["full_name"]
    project.github_repo_url = repo_info["html_url"]

    await db.commit()
    await db.refresh(project)

    return {
        "message": "Repository linked successfully",
        "project_id": project.id,
        "github_repo": repo_info["full_name"]
    }
