from typing import Optional, List, Dict, Any

import httpx

from app.core.config import settings


class GitHubService:
    BASE_URL = "https://api.github.com"

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        if access_token:
            self.headers["Authorization"] = f"token {access_token}"

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                f"{self.BASE_URL}{endpoint}",
                headers=self.headers,
                params=params,
                json=json,
            )
            response.raise_for_status()
            return response.json()

    async def get_user(self) -> Dict[str, Any]:
        """Get authenticated user info."""
        return await self._request("GET", "/user")

    async def get_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        """Get repository info."""
        return await self._request("GET", f"/repos/{owner}/{repo}")

    async def list_user_repos(
        self,
        per_page: int = 30,
        page: int = 1,
        sort: str = "updated"
    ) -> List[Dict[str, Any]]:
        """List repositories for authenticated user."""
        return await self._request(
            "GET",
            "/user/repos",
            params={"per_page": per_page, "page": page, "sort": sort}
        )

    async def list_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        per_page: int = 30,
        page: int = 1
    ) -> List[Dict[str, Any]]:
        """List issues for a repository."""
        return await self._request(
            "GET",
            f"/repos/{owner}/{repo}/issues",
            params={"state": state, "per_page": per_page, "page": page}
        )

    async def get_issue(self, owner: str, repo: str, issue_number: int) -> Dict[str, Any]:
        """Get a specific issue."""
        return await self._request("GET", f"/repos/{owner}/{repo}/issues/{issue_number}")

    async def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: Optional[str] = None,
        assignees: Optional[List[str]] = None,
        labels: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create an issue."""
        data = {"title": title}
        if body:
            data["body"] = body
        if assignees:
            data["assignees"] = assignees
        if labels:
            data["labels"] = labels

        return await self._request("POST", f"/repos/{owner}/{repo}/issues", json=data)

    async def update_issue(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        state: Optional[str] = None,
        assignees: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Update an issue."""
        data = {}
        if title:
            data["title"] = title
        if body is not None:
            data["body"] = body
        if state:
            data["state"] = state
        if assignees is not None:
            data["assignees"] = assignees

        return await self._request(
            "PATCH",
            f"/repos/{owner}/{repo}/issues/{issue_number}",
            json=data
        )

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        per_page: int = 30,
        page: int = 1
    ) -> List[Dict[str, Any]]:
        """List pull requests for a repository."""
        return await self._request(
            "GET",
            f"/repos/{owner}/{repo}/pulls",
            params={"state": state, "per_page": per_page, "page": page}
        )

    async def get_pull_request(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        """Get a specific pull request."""
        return await self._request("GET", f"/repos/{owner}/{repo}/pulls/{pr_number}")

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str,
        body: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a pull request."""
        data = {
            "title": title,
            "head": head,
            "base": base,
        }
        if body:
            data["body"] = body

        return await self._request("POST", f"/repos/{owner}/{repo}/pulls", json=data)

    async def merge_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_title: Optional[str] = None,
        commit_message: Optional[str] = None,
        merge_method: str = "merge"
    ) -> Dict[str, Any]:
        """Merge a pull request."""
        data = {"merge_method": merge_method}
        if commit_title:
            data["commit_title"] = commit_title
        if commit_message:
            data["commit_message"] = commit_message

        return await self._request(
            "PUT",
            f"/repos/{owner}/{repo}/pulls/{pr_number}/merge",
            json=data
        )

    # Collaborator management
    async def list_collaborators(
        self,
        owner: str,
        repo: str,
        per_page: int = 30,
        page: int = 1
    ) -> List[Dict[str, Any]]:
        """List repository collaborators."""
        return await self._request(
            "GET",
            f"/repos/{owner}/{repo}/collaborators",
            params={"per_page": per_page, "page": page}
        )

    async def check_collaborator(
        self,
        owner: str,
        repo: str,
        username: str
    ) -> bool:
        """Check if a user is a collaborator on the repository."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    "GET",
                    f"{self.BASE_URL}/repos/{owner}/{repo}/collaborators/{username}",
                    headers=self.headers,
                )
                return response.status_code == 204
        except httpx.HTTPStatusError:
            return False

    async def add_collaborator(
        self,
        owner: str,
        repo: str,
        username: str,
        permission: str = "push"  # pull, push, admin, maintain, triage
    ) -> Dict[str, Any]:
        """
        Add a collaborator to a repository or update their permission.
        Returns invitation details if user needs to accept invitation.
        """
        async with httpx.AsyncClient() as client:
            response = await client.request(
                "PUT",
                f"{self.BASE_URL}/repos/{owner}/{repo}/collaborators/{username}",
                headers=self.headers,
                json={"permission": permission}
            )
            # 201 = invitation created, 204 = already a collaborator (permission updated)
            if response.status_code == 204:
                return {"status": "already_collaborator", "username": username}
            elif response.status_code == 201:
                return response.json()
            else:
                response.raise_for_status()

    async def remove_collaborator(
        self,
        owner: str,
        repo: str,
        username: str
    ) -> bool:
        """Remove a collaborator from a repository."""
        async with httpx.AsyncClient() as client:
            response = await client.request(
                "DELETE",
                f"{self.BASE_URL}/repos/{owner}/{repo}/collaborators/{username}",
                headers=self.headers,
            )
            return response.status_code == 204

    async def list_invitations(
        self,
        owner: str,
        repo: str,
        per_page: int = 30,
        page: int = 1
    ) -> List[Dict[str, Any]]:
        """List pending repository invitations."""
        return await self._request(
            "GET",
            f"/repos/{owner}/{repo}/invitations",
            params={"per_page": per_page, "page": page}
        )

    async def cancel_invitation(
        self,
        owner: str,
        repo: str,
        invitation_id: int
    ) -> bool:
        """Cancel a pending repository invitation."""
        async with httpx.AsyncClient() as client:
            response = await client.request(
                "DELETE",
                f"{self.BASE_URL}/repos/{owner}/{repo}/invitations/{invitation_id}",
                headers=self.headers,
            )
            return response.status_code == 204

    def map_team_role_to_github_permission(self, team_role: str) -> str:
        """Map our team role to GitHub permission level."""
        role_mapping = {
            "owner": "admin",
            "maintainer": "maintain",
            "developer": "push",
            "viewer": "pull",
        }
        return role_mapping.get(team_role, "pull")


def get_github_service(access_token: Optional[str] = None) -> GitHubService:
    return GitHubService(access_token)
