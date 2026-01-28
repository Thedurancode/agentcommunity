#!/usr/bin/env python3
"""
MCP Server for Code Live OS Community API

This MCP server exposes the Community API to AI agents, allowing them to:
- Manage projects and issues
- Create and interact with posts
- Send messages between users
- Manage notifications
"""

import os
import json
import httpx
from typing import Optional, Any
from mcp.server.fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("community-api")

# Configuration
API_BASE_URL = os.getenv("COMMUNITY_API_URL", "http://127.0.0.1:8000/api/v1")
API_TOKEN = os.getenv("COMMUNITY_API_TOKEN", "")


def get_headers() -> dict:
    """Get headers for API requests."""
    headers = {"Content-Type": "application/json"}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"
    return headers


async def api_request(
    method: str,
    endpoint: str,
    data: Optional[dict] = None,
    params: Optional[dict] = None,
) -> dict:
    """Make an API request to the Community API."""
    async with httpx.AsyncClient() as client:
        url = f"{API_BASE_URL}{endpoint}"
        response = await client.request(
            method=method,
            url=url,
            headers=get_headers(),
            json=data,
            params=params,
            follow_redirects=True,
        )

        if response.status_code >= 400:
            return {"error": response.text, "status_code": response.status_code}

        try:
            return response.json()
        except:
            return {"message": response.text}


# ============== Authentication Tools ==============

@mcp.tool()
async def login(username: str, password: str) -> str:
    """
    Login to the Community API and get an access token.

    Args:
        username: The username to login with
        password: The password for the account

    Returns:
        Access token and token type, or error message
    """
    result = await api_request("POST", "/auth/login", {"username": username, "password": password})

    if "access_token" in result:
        global API_TOKEN
        API_TOKEN = result["access_token"]
        return f"Login successful! Token stored for subsequent requests."

    return json.dumps(result, indent=2)


@mcp.tool()
async def register_user(
    email: str,
    username: str,
    password: str,
    full_name: str,
    phone: str
) -> str:
    """
    Register a new user account.

    Args:
        email: User's email address
        username: Desired username
        password: Password for the account
        full_name: User's full name
        phone: Phone number

    Returns:
        Created user details or error message
    """
    result = await api_request("POST", "/auth/register", {
        "email": email,
        "username": username,
        "password": password,
        "full_name": full_name,
        "phone": phone
    })
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_current_user() -> str:
    """
    Get the currently authenticated user's profile.

    Returns:
        Current user's profile details
    """
    result = await api_request("GET", "/auth/me")
    return json.dumps(result, indent=2)


# ============== Project Tools ==============

@mcp.tool()
async def create_project(name: str, description: str = "") -> str:
    """
    Create a new project.

    Args:
        name: Name of the project
        description: Optional description of the project

    Returns:
        Created project details
    """
    result = await api_request("POST", "/projects", {
        "name": name,
        "description": description
    })
    return json.dumps(result, indent=2)


@mcp.tool()
async def list_projects() -> str:
    """
    List all projects the current user has access to.

    Returns:
        List of projects with their details
    """
    result = await api_request("GET", "/projects")
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_project(project_id: int) -> str:
    """
    Get details of a specific project.

    Args:
        project_id: ID of the project to retrieve

    Returns:
        Project details including owner information
    """
    result = await api_request("GET", f"/projects/{project_id}")
    return json.dumps(result, indent=2)


@mcp.tool()
async def update_project(
    project_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    status_note: Optional[str] = None
) -> str:
    """
    Update a project's details.

    Args:
        project_id: ID of the project to update
        name: New name for the project (optional)
        description: New description (optional)
        status: New status - one of: in_talks, now_coding, needs_review, complete (optional)
        status_note: Note about the current status (optional)

    Returns:
        Updated project details
    """
    data = {}
    if name:
        data["name"] = name
    if description:
        data["description"] = description
    if status:
        data["status"] = status
    if status_note:
        data["status_note"] = status_note

    result = await api_request("PATCH", f"/projects/{project_id}", data)
    return json.dumps(result, indent=2)


# ============== Issue Tools ==============

@mcp.tool()
async def create_issue(
    project_id: int,
    title: str,
    description: str = "",
    assignee_id: Optional[int] = None
) -> str:
    """
    Create a new issue in a project.

    Args:
        project_id: ID of the project to create the issue in
        title: Title of the issue
        description: Detailed description of the issue
        assignee_id: Optional user ID to assign the issue to

    Returns:
        Created issue details
    """
    data = {"title": title, "description": description}
    if assignee_id:
        data["assignee_id"] = assignee_id

    result = await api_request("POST", f"/projects/{project_id}/issues", data)
    return json.dumps(result, indent=2)


@mcp.tool()
async def list_issues(
    project_id: int,
    state: Optional[str] = None,
    assignee_id: Optional[int] = None
) -> str:
    """
    List issues in a project with optional filtering.

    Args:
        project_id: ID of the project
        state: Filter by state - 'open' or 'closed' (optional)
        assignee_id: Filter by assignee user ID (optional)

    Returns:
        List of issues matching the criteria
    """
    params = {}
    if state:
        params["state"] = state
    if assignee_id:
        params["assignee_id"] = assignee_id

    result = await api_request("GET", f"/projects/{project_id}/issues", params=params)
    return json.dumps(result, indent=2)


@mcp.tool()
async def update_issue(
    project_id: int,
    issue_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    state: Optional[str] = None,
    assignee_id: Optional[int] = None
) -> str:
    """
    Update an existing issue.

    Args:
        project_id: ID of the project
        issue_id: ID of the issue to update
        title: New title (optional)
        description: New description (optional)
        state: New state - 'open' or 'closed' (optional)
        assignee_id: New assignee user ID (optional)

    Returns:
        Updated issue details
    """
    data = {}
    if title:
        data["title"] = title
    if description:
        data["description"] = description
    if state:
        data["state"] = state
    if assignee_id:
        data["assignee_id"] = assignee_id

    result = await api_request("PATCH", f"/projects/{project_id}/issues/{issue_id}", data)
    return json.dumps(result, indent=2)


# ============== Feed/Post Tools ==============

@mcp.tool()
async def create_post(
    content: str,
    visibility: str = "public",
    project_id: Optional[int] = None
) -> str:
    """
    Create a new post in the feed.

    Args:
        content: The post content/text
        visibility: Post visibility - 'public', 'project', or 'private'
        project_id: Optional project ID to associate the post with

    Returns:
        Created post details
    """
    data = {"content": content, "visibility": visibility}
    if project_id:
        data["project_id"] = project_id

    result = await api_request("POST", "/feed/posts", data)
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_feed(limit: int = 10) -> str:
    """
    Get the feed of posts.

    Args:
        limit: Maximum number of posts to retrieve (default 10)

    Returns:
        List of posts with author info, likes, and comments
    """
    result = await api_request("GET", "/feed", params={"limit": limit})
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_post(post_id: int) -> str:
    """
    Get details of a specific post.

    Args:
        post_id: ID of the post to retrieve

    Returns:
        Post details including comments and engagement
    """
    result = await api_request("GET", f"/feed/posts/{post_id}")
    return json.dumps(result, indent=2)


@mcp.tool()
async def like_post(post_id: int) -> str:
    """
    Like a post.

    Args:
        post_id: ID of the post to like

    Returns:
        Like status and count
    """
    result = await api_request("POST", f"/feed/posts/{post_id}/like")
    return json.dumps(result, indent=2)


@mcp.tool()
async def comment_on_post(post_id: int, content: str) -> str:
    """
    Add a comment to a post.

    Args:
        post_id: ID of the post to comment on
        content: The comment text

    Returns:
        Created comment details
    """
    result = await api_request("POST", f"/feed/posts/{post_id}/comments", {"content": content})
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_post_comments(post_id: int) -> str:
    """
    Get all comments on a post.

    Args:
        post_id: ID of the post

    Returns:
        List of comments with author info
    """
    result = await api_request("GET", f"/feed/posts/{post_id}/comments")
    return json.dumps(result, indent=2)


# ============== Messaging Tools ==============

@mcp.tool()
async def start_conversation(recipient_id: int, initial_message: str = "") -> str:
    """
    Start a new conversation with another user.

    Args:
        recipient_id: User ID of the person to message
        initial_message: Optional first message to send

    Returns:
        Created conversation details
    """
    data = {"recipient_id": recipient_id}
    if initial_message:
        data["initial_message"] = initial_message

    result = await api_request("POST", "/messages", data)
    return json.dumps(result, indent=2)


@mcp.tool()
async def send_message(conversation_id: int, content: str) -> str:
    """
    Send a message in a conversation.

    Args:
        conversation_id: ID of the conversation
        content: Message content to send

    Returns:
        Sent message details
    """
    result = await api_request("POST", f"/messages/{conversation_id}/messages", {"content": content})
    return json.dumps(result, indent=2)


@mcp.tool()
async def list_conversations() -> str:
    """
    List all conversations for the current user.

    Returns:
        List of conversations with participants and last message
    """
    result = await api_request("GET", "/messages")
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_conversation_messages(conversation_id: int, limit: int = 50) -> str:
    """
    Get messages in a conversation.

    Args:
        conversation_id: ID of the conversation
        limit: Maximum number of messages to retrieve

    Returns:
        List of messages with sender info
    """
    result = await api_request("GET", f"/messages/{conversation_id}/messages", params={"limit": limit})
    return json.dumps(result, indent=2)


# ============== Notification Tools ==============

@mcp.tool()
async def get_notifications(limit: int = 20) -> str:
    """
    Get notifications for the current user.

    Args:
        limit: Maximum number of notifications to retrieve

    Returns:
        List of notifications with unread count
    """
    result = await api_request("GET", "/notifications", params={"limit": limit})
    return json.dumps(result, indent=2)


@mcp.tool()
async def mark_notification_read(notification_id: int) -> str:
    """
    Mark a notification as read.

    Args:
        notification_id: ID of the notification to mark as read

    Returns:
        Confirmation of the update
    """
    result = await api_request("PATCH", f"/notifications/{notification_id}/read")
    return json.dumps(result, indent=2)


# ============== Blog Tools ==============

@mcp.tool()
async def create_blog(
    title: str,
    content: str,
    summary: str = "",
    project_id: Optional[int] = None
) -> str:
    """
    Create a new blog post.

    Args:
        title: Title of the blog post
        content: Full content of the blog
        summary: Short summary/excerpt
        project_id: Optional project to associate with

    Returns:
        Created blog details
    """
    data = {"title": title, "content": content, "summary": summary}
    if project_id:
        data["project_id"] = project_id

    result = await api_request("POST", "/blogs", data)
    return json.dumps(result, indent=2)


@mcp.tool()
async def list_blogs(limit: int = 10) -> str:
    """
    Get a list of blog posts.

    Args:
        limit: Maximum number of blogs to retrieve

    Returns:
        List of blog posts with author info
    """
    result = await api_request("GET", "/blogs", params={"limit": limit})
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_blog(blog_id: int) -> str:
    """
    Get a specific blog post.

    Args:
        blog_id: ID of the blog to retrieve

    Returns:
        Full blog details
    """
    result = await api_request("GET", f"/blogs/{blog_id}")
    return json.dumps(result, indent=2)


# ============== Team Member Tools ==============

@mcp.tool()
async def add_team_member(
    project_id: int,
    user_id: int,
    role: str = "developer"
) -> str:
    """
    Add a team member to a project.

    Args:
        project_id: ID of the project
        user_id: ID of the user to add
        role: Role for the member - 'owner', 'maintainer', or 'developer'

    Returns:
        Created team member details
    """
    result = await api_request("POST", f"/projects/{project_id}/team", {
        "user_id": user_id,
        "role": role
    })
    return json.dumps(result, indent=2)


@mcp.tool()
async def list_team_members(project_id: int) -> str:
    """
    List all team members of a project.

    Args:
        project_id: ID of the project

    Returns:
        List of team members with their roles
    """
    result = await api_request("GET", f"/projects/{project_id}/team")
    return json.dumps(result, indent=2)


@mcp.tool()
async def list_users() -> str:
    """
    List all users (admin only).

    Returns:
        List of all users in the system
    """
    result = await api_request("GET", "/auth/users")
    return json.dumps(result, indent=2)


# ============== Run the server ==============

if __name__ == "__main__":
    mcp.run()
