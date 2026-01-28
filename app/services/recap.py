from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.project import Project
from app.models.recap import Recap
from app.models.issue import Issue
from app.models.note import Note
from app.services.github import get_github_service


class RecapService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_recap(self, project_id: int) -> Recap:
        """Get existing recap or create a new one for the project."""
        result = await self.db.execute(
            select(Recap).where(Recap.project_id == project_id)
        )
        recap = result.scalar_one_or_none()

        if not recap:
            recap = Recap(project_id=project_id)
            self.db.add(recap)
            await self.db.commit()
            await self.db.refresh(recap)

        return recap

    async def update_recent_commits(
        self,
        project_id: int,
        github_access_token: Optional[str] = None
    ) -> int:
        """Fetch and update the last 5 commits from GitHub."""
        result = await self.db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()

        if not project or not project.github_repo_full_name:
            return 0

        if not github_access_token:
            return 0

        recap = await self.get_or_create_recap(project_id)

        try:
            owner, repo = project.github_repo_full_name.split("/")
            github = get_github_service(github_access_token)

            # Fetch commits from GitHub API
            commits_response = await github._request(
                "GET",
                f"/repos/{owner}/{repo}/commits",
                params={"per_page": 5}
            )

            recent_commits = []
            for commit in commits_response:
                commit_data = commit.get("commit", {})
                author_data = commit_data.get("author", {})
                recent_commits.append({
                    "sha": commit.get("sha", "")[:7],
                    "message": commit_data.get("message", "").split("\n")[0][:100],
                    "author": author_data.get("name", "Unknown"),
                    "date": author_data.get("date", datetime.utcnow().isoformat()),
                    "url": commit.get("html_url", ""),
                })

            recap.recent_commits = recent_commits
            await self.db.commit()
            return len(recent_commits)

        except Exception:
            return 0

    async def update_recent_issues(self, project_id: int) -> int:
        """Update the last 5 issues from the database."""
        recap = await self.get_or_create_recap(project_id)

        result = await self.db.execute(
            select(Issue)
            .where(Issue.project_id == project_id)
            .order_by(Issue.updated_at.desc())
            .limit(5)
        )
        issues = result.scalars().all()

        recent_issues = []
        for issue in issues:
            recent_issues.append({
                "id": issue.id,
                "title": issue.title[:100],
                "state": issue.state.value,
                "created_at": issue.created_at.isoformat(),
                "github_issue_number": issue.github_issue_number,
                "github_issue_url": issue.github_issue_url,
            })

        recap.recent_issues = recent_issues
        await self.db.commit()
        return len(recent_issues)

    async def update_recent_notes(self, project_id: int) -> int:
        """Update the last 5 notes from the database."""
        recap = await self.get_or_create_recap(project_id)

        result = await self.db.execute(
            select(Note)
            .options(selectinload(Note.created_by))
            .where(Note.project_id == project_id)
            .order_by(Note.updated_at.desc())
            .limit(5)
        )
        notes = result.scalars().all()

        recent_notes = []
        for note in notes:
            recent_notes.append({
                "id": note.id,
                "title": note.title[:100],
                "created_at": note.created_at.isoformat(),
                "created_by": note.created_by.username if note.created_by else None,
            })

        recap.recent_notes = recent_notes
        await self.db.commit()
        return len(recent_notes)

    async def refresh_all(
        self,
        project_id: int,
        github_access_token: Optional[str] = None
    ) -> Dict[str, int]:
        """Refresh all recap data for a project."""
        commits_count = await self.update_recent_commits(project_id, github_access_token)
        issues_count = await self.update_recent_issues(project_id)
        notes_count = await self.update_recent_notes(project_id)

        return {
            "commits_updated": commits_count,
            "issues_updated": issues_count,
            "notes_updated": notes_count,
        }

    async def update_summary(self, project_id: int, summary: str) -> Recap:
        """Update the recap summary text."""
        recap = await self.get_or_create_recap(project_id)
        recap.summary = summary
        await self.db.commit()
        await self.db.refresh(recap)
        return recap


def get_recap_service(db: AsyncSession) -> RecapService:
    return RecapService(db)
