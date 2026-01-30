#!/usr/bin/env python3
"""
MCP Server for Code Live OS Community API

This MCP server exposes the Community API to AI agents, allowing them to:
- Manage projects and issues
- Create and interact with posts
- Send messages between users
- Manage notifications
- Manage blogs with full CRUD operations
- GitHub integration (repos, issues, PRs)
- API key management

AI Agent Capabilities:
- Execute natural language instructions via Agent Gateway
- Store and retrieve memories with semantic search
- Manage contact preferences and communication history
- Make AI-powered phone calls and send SMS
- Property management with contacts, notes, and contracts
"""

import os
import json
import httpx
from typing import Optional, Any
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import TransportSecuritySettings

# Initialize MCP server with transport security settings for cloud deployment
transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=False,  # Disable for cloud deployment
    allowed_hosts=["*"],
    allowed_origins=["*"],
)
mcp = FastMCP("community-api", transport_security=transport_security)

# Configuration
API_BASE_URL = os.getenv("COMMUNITY_API_URL", "http://127.0.0.1:8000/api/v1")
API_TOKEN = os.getenv("COMMUNITY_API_TOKEN", "")  # JWT token
API_KEY = os.getenv("COMMUNITY_API_KEY", "")  # API key (starts with clak_)


def get_headers() -> dict:
    """Get headers for API requests. Prefers API key over JWT token."""
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    elif API_TOKEN:
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
    excerpt: str = "",
    status: str = "draft",
    category: Optional[str] = None,
    tags: Optional[str] = None,
    cover_image: Optional[str] = None,
    is_featured: bool = False,
    project_id: Optional[int] = None
) -> str:
    """
    Create a new blog post.

    Args:
        title: Title of the blog post
        content: Full content of the blog (markdown supported)
        excerpt: Short summary/excerpt
        status: Blog status - 'draft', 'published', or 'archived'
        category: Blog category
        tags: Comma-separated tags (e.g., "python,api,tutorial")
        cover_image: URL for cover image
        is_featured: Whether to feature this blog
        project_id: Optional project to associate with

    Returns:
        Created blog details
    """
    data = {
        "title": title,
        "content": content,
        "excerpt": excerpt,
        "status": status,
        "is_featured": is_featured
    }
    if category:
        data["category"] = category
    if tags:
        data["tags"] = tags
    if cover_image:
        data["cover_image"] = cover_image
    if project_id:
        data["project_id"] = project_id

    result = await api_request("POST", "/blogs", data)
    return json.dumps(result, indent=2)


@mcp.tool()
async def update_blog(
    blog_id: int,
    title: Optional[str] = None,
    content: Optional[str] = None,
    excerpt: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[str] = None,
    cover_image: Optional[str] = None,
    is_featured: Optional[bool] = None
) -> str:
    """
    Update an existing blog post.

    Args:
        blog_id: ID of the blog to update
        title: New title
        content: New content
        excerpt: New excerpt
        status: New status - 'draft', 'published', or 'archived'
        category: New category
        tags: New comma-separated tags
        cover_image: New cover image URL
        is_featured: Whether to feature this blog

    Returns:
        Updated blog details
    """
    data = {}
    if title:
        data["title"] = title
    if content:
        data["content"] = content
    if excerpt:
        data["excerpt"] = excerpt
    if status:
        data["status"] = status
    if category:
        data["category"] = category
    if tags:
        data["tags"] = tags
    if cover_image:
        data["cover_image"] = cover_image
    if is_featured is not None:
        data["is_featured"] = is_featured

    result = await api_request("PATCH", f"/blogs/{blog_id}", data)
    return json.dumps(result, indent=2)


@mcp.tool()
async def publish_blog(blog_id: int) -> str:
    """
    Publish a draft blog post.

    Args:
        blog_id: ID of the blog to publish

    Returns:
        Updated blog with published status
    """
    result = await api_request("PATCH", f"/blogs/{blog_id}", {"status": "published"})
    return json.dumps(result, indent=2)


@mcp.tool()
async def list_blogs(limit: int = 10, status: Optional[str] = None) -> str:
    """
    Get a list of blog posts.

    Args:
        limit: Maximum number of blogs to retrieve
        status: Filter by status - 'draft', 'published', or 'archived'

    Returns:
        List of blog posts with author info
    """
    params = {"limit": limit}
    if status:
        params["status"] = status
    result = await api_request("GET", "/blogs", params=params)
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_blog(blog_id: int) -> str:
    """
    Get a specific blog post.

    Args:
        blog_id: ID of the blog to retrieve

    Returns:
        Full blog details including status, tags, and stats
    """
    result = await api_request("GET", f"/blogs/{blog_id}")
    return json.dumps(result, indent=2)


@mcp.tool()
async def delete_blog(blog_id: int) -> str:
    """
    Delete a blog post.

    Args:
        blog_id: ID of the blog to delete

    Returns:
        Confirmation of deletion
    """
    result = await api_request("DELETE", f"/blogs/{blog_id}")
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


# ============== GitHub Tools ==============

@mcp.tool()
async def list_github_repos() -> str:
    """
    List GitHub repositories for the authenticated user.

    Returns:
        List of GitHub repos with names and URLs
    """
    result = await api_request("GET", "/github/repos")
    return json.dumps(result, indent=2)


@mcp.tool()
async def create_github_repo(
    name: str,
    description: str = "",
    private: bool = False,
    auto_init: bool = True,
    gitignore_template: Optional[str] = None,
    license_template: Optional[str] = None,
    project_id: Optional[int] = None
) -> str:
    """
    Create a new GitHub repository.

    Args:
        name: Name for the new repository
        description: Optional description of the repository
        private: Whether the repo should be private (default: False)
        auto_init: Initialize with a README (default: True)
        gitignore_template: Optional gitignore template (e.g., 'Python', 'Node', 'Go')
        license_template: Optional license template (e.g., 'mit', 'apache-2.0', 'gpl-3.0')
        project_id: Optional project ID to link the new repo to

    Returns:
        Created repository details
    """
    data = {
        "name": name,
        "description": description,
        "private": private,
        "auto_init": auto_init,
    }
    if gitignore_template:
        data["gitignore_template"] = gitignore_template
    if license_template:
        data["license_template"] = license_template
    if project_id:
        data["project_id"] = project_id

    result = await api_request("POST", "/github/repos", data)
    return json.dumps(result, indent=2)


@mcp.tool()
async def link_github_repo(project_id: int, repo_full_name: str) -> str:
    """
    Link a GitHub repository to a project.

    Args:
        project_id: ID of the project to link
        repo_full_name: Full name of the repo (e.g., 'owner/repo')

    Returns:
        Updated project with GitHub repo linked
    """
    result = await api_request("POST", f"/projects/{project_id}/link-repo", {
        "repo_full_name": repo_full_name
    })
    return json.dumps(result, indent=2)


@mcp.tool()
async def sync_github_issues(project_id: int) -> str:
    """
    Sync issues from the linked GitHub repository to the project.

    Args:
        project_id: ID of the project with a linked GitHub repo

    Returns:
        Sync results with created/updated issues
    """
    result = await api_request("POST", f"/projects/{project_id}/sync-issues")
    return json.dumps(result, indent=2)


@mcp.tool()
async def sync_github_pull_requests(project_id: int) -> str:
    """
    Sync pull requests from the linked GitHub repository to the project.

    Args:
        project_id: ID of the project with a linked GitHub repo

    Returns:
        Sync results with created/updated pull requests
    """
    result = await api_request("POST", f"/projects/{project_id}/sync-pull-requests")
    return json.dumps(result, indent=2)


# ============== API Key Tools ==============

@mcp.tool()
async def create_api_key(name: str) -> str:
    """
    Create a new API key for programmatic access.

    The full key is only shown once - save it securely!
    Keys provide full access as the authenticated user.

    Args:
        name: A friendly name to identify this API key

    Returns:
        Created API key details including the full key (save this!)
    """
    result = await api_request("POST", "/api-keys", {"name": name})
    return json.dumps(result, indent=2)


@mcp.tool()
async def list_api_keys() -> str:
    """
    List all API keys for the current user.

    Note: Full keys are not shown, only prefixes for identification.

    Returns:
        List of API keys with names, prefixes, and last used times
    """
    result = await api_request("GET", "/api-keys")
    return json.dumps(result, indent=2)


@mcp.tool()
async def revoke_api_key(key_id: int) -> str:
    """
    Revoke an API key (deactivate without deleting).

    The key will no longer work for authentication.

    Args:
        key_id: ID of the API key to revoke

    Returns:
        Updated API key details showing inactive status
    """
    result = await api_request("PATCH", f"/api-keys/{key_id}/revoke")
    return json.dumps(result, indent=2)


@mcp.tool()
async def delete_api_key(key_id: int) -> str:
    """
    Permanently delete an API key.

    Args:
        key_id: ID of the API key to delete

    Returns:
        Confirmation of deletion
    """
    result = await api_request("DELETE", f"/api-keys/{key_id}")
    return json.dumps(result, indent=2)


@mcp.tool()
async def set_api_key(api_key: str) -> str:
    """
    Set the API key for subsequent requests in this session.

    This allows you to authenticate using an API key instead of
    username/password login. The key should start with 'clak_'.

    Args:
        api_key: The full API key (e.g., clak_abc123...)

    Returns:
        Confirmation that the API key has been set
    """
    global API_KEY
    if not api_key.startswith("clak_"):
        return "Error: API key should start with 'clak_'"
    API_KEY = api_key
    return "API key set successfully for this session."


# ============== AI Agent Tools ==============

@mcp.tool()
async def agent_execute(
    instruction: str,
    property_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    auto_execute: bool = True
) -> str:
    """
    Execute an AI agent task from natural language instruction.

    This is the main entry point for AI agents. The system will:
    1. Parse your instruction to understand the intent
    2. Automatically gather relevant context (memories, preferences, history)
    3. Execute the action (call, SMS, etc.) with context injected
    4. Extract and store memories from the result

    Args:
        instruction: Natural language instruction (e.g., "Call John to follow up on the property viewing")
        property_id: Optional property ID for context
        contact_id: Optional contact ID for context
        auto_execute: Whether to execute immediately (True) or just return the plan (False)

    Returns:
        Task execution result with status, context used, and any outputs
    """
    data = {
        "instruction": instruction,
        "auto_execute": auto_execute
    }
    if property_id:
        data["property_id"] = property_id
    if contact_id:
        data["contact_id"] = contact_id

    result = await api_request("POST", "/agent/execute", data)
    return json.dumps(result, indent=2)


@mcp.tool()
async def agent_preview_context(
    property_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    purpose: Optional[str] = None
) -> str:
    """
    Preview the context that would be gathered for an agent action.

    Use this to see what memories, preferences, and history the AI would
    have access to before executing an action.

    Args:
        property_id: Property ID to gather context for
        contact_id: Contact ID to gather context for
        purpose: Optional purpose for semantic memory search

    Returns:
        Full context including memories, preferences, recent conversations, and commitments
    """
    data = {}
    if property_id:
        data["property_id"] = property_id
    if contact_id:
        data["contact_id"] = contact_id
    if purpose:
        data["purpose"] = purpose

    result = await api_request("POST", "/agent/context/preview", data)
    return json.dumps(result, indent=2)


@mcp.tool()
async def agent_parse_instruction(instruction: str) -> str:
    """
    Parse a natural language instruction into structured intent.

    Use this to understand how the system interprets your instructions
    without actually executing them.

    Args:
        instruction: Natural language instruction to parse

    Returns:
        Parsed intent including task_type, action, target, and purpose
    """
    result = await api_request("POST", "/agent/parse", {"instruction": instruction})
    return json.dumps(result, indent=2)


@mcp.tool()
async def agent_list_tasks(
    status: Optional[str] = None,
    property_id: Optional[int] = None,
    limit: int = 20
) -> str:
    """
    List agent tasks with optional filtering.

    Args:
        status: Filter by status - 'pending', 'in_progress', 'completed', 'failed'
        property_id: Filter by property ID
        limit: Maximum number of tasks to return

    Returns:
        List of agent tasks with their status and results
    """
    params = {"limit": limit}
    if status:
        params["status"] = status
    if property_id:
        params["property_id"] = property_id

    result = await api_request("GET", "/agent/tasks", params=params)
    return json.dumps(result, indent=2)


@mcp.tool()
async def agent_get_tools() -> str:
    """
    Get available agent tools in function-calling format.

    Returns the list of actions the AI agent can perform,
    formatted for use with function calling.

    Returns:
        List of tool definitions with names, descriptions, and parameters
    """
    result = await api_request("GET", "/agent/tools")
    return json.dumps(result, indent=2)


@mcp.tool()
async def agent_quick_call(
    contact_id: int,
    purpose: str,
    property_id: Optional[int] = None
) -> str:
    """
    Quickly initiate an AI-powered phone call to a contact.

    The system will automatically:
    - Gather all relevant context about the contact
    - Include memories and preferences in the call
    - Extract and store memories after the call

    Args:
        contact_id: ID of the contact to call
        purpose: Purpose of the call (e.g., "follow up on property viewing")
        property_id: Optional property ID for additional context

    Returns:
        Call initiation result with call ID and status
    """
    data = {
        "contact_id": contact_id,
        "purpose": purpose
    }
    if property_id:
        data["property_id"] = property_id

    result = await api_request("POST", "/agent/call", data)
    return json.dumps(result, indent=2)


@mcp.tool()
async def agent_quick_sms(
    contact_id: int,
    message: Optional[str] = None,
    purpose: Optional[str] = None,
    property_id: Optional[int] = None
) -> str:
    """
    Quickly send an SMS to a contact (with optional AI-generated message).

    If no message is provided, the AI will generate an appropriate
    message based on the purpose and contact context.

    Args:
        contact_id: ID of the contact to text
        message: Optional specific message to send
        purpose: Purpose of the SMS (used for AI message generation if no message provided)
        property_id: Optional property ID for additional context

    Returns:
        SMS result with message ID and status
    """
    data = {"contact_id": contact_id}
    if message:
        data["message"] = message
    if purpose:
        data["purpose"] = purpose
    if property_id:
        data["property_id"] = property_id

    result = await api_request("POST", "/agent/sms", data)
    return json.dumps(result, indent=2)


# ============== Memory Tools ==============

@mcp.tool()
async def memory_create(
    content: str,
    memory_type: str = "fact",
    property_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    importance: float = 0.5,
    confidence: float = 1.0
) -> str:
    """
    Create a new memory for the AI agent to remember.

    Memories are stored with vector embeddings for semantic search.

    Args:
        content: The memory content in human-readable form
        memory_type: Type of memory - 'fact', 'preference', 'commitment', 'relationship', 'context', 'summary'
        property_id: Optional property to associate with
        contact_id: Optional contact to associate with
        importance: Importance score 0-1 (default 0.5)
        confidence: Confidence score 0-1 (default 1.0)

    Returns:
        Created memory details with ID
    """
    data = {
        "content": content,
        "memory_type": memory_type,
        "importance": importance,
        "confidence": confidence
    }
    if property_id:
        data["property_id"] = property_id
    if contact_id:
        data["contact_id"] = contact_id

    result = await api_request("POST", "/memory", data)
    return json.dumps(result, indent=2)


@mcp.tool()
async def memory_search(
    query: str,
    property_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    memory_types: Optional[str] = None,
    limit: int = 10,
    min_similarity: float = 0.5
) -> str:
    """
    Search memories using semantic similarity.

    This performs a vector search to find memories related to your query,
    even if they don't contain the exact same words.

    Args:
        query: Search query (semantic search)
        property_id: Filter by property
        contact_id: Filter by contact
        memory_types: Comma-separated types to filter (e.g., "fact,preference")
        limit: Maximum results (default 10)
        min_similarity: Minimum similarity threshold 0-1 (default 0.5)

    Returns:
        List of memories with similarity scores
    """
    data = {
        "query": query,
        "limit": limit,
        "min_similarity": min_similarity
    }
    if property_id:
        data["property_id"] = property_id
    if contact_id:
        data["contact_id"] = contact_id
    if memory_types:
        data["memory_types"] = memory_types.split(",")

    result = await api_request("POST", "/memory/search", data)
    return json.dumps(result, indent=2)


@mcp.tool()
async def memory_list(
    property_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    memory_types: Optional[str] = None,
    limit: int = 50
) -> str:
    """
    List memories with optional filtering.

    Args:
        property_id: Filter by property
        contact_id: Filter by contact
        memory_types: Comma-separated types to filter
        limit: Maximum results

    Returns:
        List of memories ordered by importance and recency
    """
    params = {"limit": limit}
    if property_id:
        params["property_id"] = property_id
    if contact_id:
        params["contact_id"] = contact_id
    if memory_types:
        params["memory_types"] = memory_types

    result = await api_request("GET", "/memory", params=params)
    return json.dumps(result, indent=2)


@mcp.tool()
async def memory_get_context(
    property_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    query: Optional[str] = None,
    include_memories: bool = True,
    include_conversations: bool = True,
    include_preferences: bool = True
) -> str:
    """
    Get full agent context for a property/contact.

    This retrieves everything the AI knows about a property and/or contact:
    - Property details
    - Contact details
    - Relevant memories
    - Recent conversations
    - Contact preferences
    - Open commitments

    Args:
        property_id: Property to get context for
        contact_id: Contact to get context for
        query: Optional query for semantic memory filtering
        include_memories: Include memories (default True)
        include_conversations: Include recent conversations (default True)
        include_preferences: Include contact preferences (default True)

    Returns:
        Full context package for AI agent use
    """
    data = {
        "include_memories": include_memories,
        "include_conversations": include_conversations,
        "include_preferences": include_preferences
    }
    if property_id:
        data["property_id"] = property_id
    if contact_id:
        data["contact_id"] = contact_id
    if query:
        data["query"] = query

    result = await api_request("POST", "/memory/context", data)
    return json.dumps(result, indent=2)


@mcp.tool()
async def memory_update_preferences(
    contact_id: int,
    preferred_channel: Optional[str] = None,
    preferred_time: Optional[str] = None,
    do_not_call: Optional[bool] = None,
    do_not_text: Optional[bool] = None,
    formality_level: Optional[str] = None,
    language: Optional[str] = None,
    notes: Optional[str] = None
) -> str:
    """
    Update contact communication preferences.

    These preferences are automatically used by the AI agent when
    deciding how and when to contact someone.

    Args:
        contact_id: Contact to update preferences for
        preferred_channel: Preferred contact method ('phone', 'sms', 'email')
        preferred_time: Preferred time to contact (e.g., "mornings", "after 5pm")
        do_not_call: Set to True to prevent phone calls
        do_not_text: Set to True to prevent text messages
        formality_level: Communication style ('formal', 'casual', 'professional')
        language: Preferred language code (e.g., 'en', 'es')
        notes: Additional notes about preferences

    Returns:
        Updated preferences
    """
    data = {}
    if preferred_channel:
        data["preferred_channel"] = preferred_channel
    if preferred_time:
        data["preferred_time"] = preferred_time
    if do_not_call is not None:
        data["do_not_call"] = do_not_call
    if do_not_text is not None:
        data["do_not_text"] = do_not_text
    if formality_level:
        data["formality_level"] = formality_level
    if language:
        data["language"] = language
    if notes:
        data["notes"] = notes

    result = await api_request("PUT", f"/memory/contacts/{contact_id}/preferences", data)
    return json.dumps(result, indent=2)


# ============== Property Tools ==============

@mcp.tool()
async def property_create(
    name: str,
    address: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    zip_code: Optional[str] = None,
    property_type: Optional[str] = None,
    description: Optional[str] = None
) -> str:
    """
    Create a new property.

    Args:
        name: Property name
        address: Street address
        city: City
        state: State
        zip_code: ZIP code
        property_type: Type (e.g., 'residential', 'commercial', 'land')
        description: Property description

    Returns:
        Created property details
    """
    data = {"name": name}
    if address:
        data["address"] = address
    if city:
        data["city"] = city
    if state:
        data["state"] = state
    if zip_code:
        data["zip_code"] = zip_code
    if property_type:
        data["property_type"] = property_type
    if description:
        data["description"] = description

    result = await api_request("POST", "/properties", data)
    return json.dumps(result, indent=2)


@mcp.tool()
async def property_list(
    status: Optional[str] = None,
    limit: int = 50
) -> str:
    """
    List properties with optional filtering.

    Args:
        status: Filter by status ('active', 'pending', 'closed', 'archived')
        limit: Maximum results

    Returns:
        List of properties
    """
    params = {"limit": limit}
    if status:
        params["status"] = status

    result = await api_request("GET", "/properties", params=params)
    return json.dumps(result, indent=2)


@mcp.tool()
async def property_get(property_id: int) -> str:
    """
    Get detailed information about a property.

    Includes all related data: contacts, contracts, phases, notes,
    phone calls, SMS messages, and enrichment data.

    Args:
        property_id: ID of the property

    Returns:
        Full property details with all relationships
    """
    result = await api_request("GET", f"/properties/{property_id}")
    return json.dumps(result, indent=2)


@mcp.tool()
async def property_add_contact(
    property_id: int,
    name: str,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    company: Optional[str] = None,
    contact_type: str = "other",
    notes: Optional[str] = None
) -> str:
    """
    Add a contact to a property.

    Args:
        property_id: ID of the property
        name: Contact name
        phone: Phone number
        email: Email address
        company: Company name
        contact_type: Type - 'owner', 'seller', 'buyer', 'agent', 'attorney', 'other'
        notes: Additional notes

    Returns:
        Created contact details
    """
    data = {
        "name": name,
        "contact_type": contact_type
    }
    if phone:
        data["phone"] = phone
    if email:
        data["email"] = email
    if company:
        data["company"] = company
    if notes:
        data["notes"] = notes

    result = await api_request("POST", f"/properties/{property_id}/contacts", data)
    return json.dumps(result, indent=2)


@mcp.tool()
async def property_list_contacts(property_id: int) -> str:
    """
    List all contacts for a property.

    Args:
        property_id: ID of the property

    Returns:
        List of contacts with their details
    """
    result = await api_request("GET", f"/properties/{property_id}/contacts")
    return json.dumps(result, indent=2)


@mcp.tool()
async def property_add_note(
    property_id: int,
    content: str,
    note_type: str = "general"
) -> str:
    """
    Add a note to a property.

    Args:
        property_id: ID of the property
        content: Note content
        note_type: Type of note ('general', 'call_summary', 'meeting', 'todo')

    Returns:
        Created note details
    """
    result = await api_request("POST", f"/properties/{property_id}/notes", {
        "content": content,
        "note_type": note_type
    })
    return json.dumps(result, indent=2)


@mcp.tool()
async def property_get_calls(property_id: int, limit: int = 20) -> str:
    """
    Get phone call history for a property.

    Args:
        property_id: ID of the property
        limit: Maximum calls to return

    Returns:
        List of calls with transcripts and summaries
    """
    result = await api_request("GET", f"/properties/{property_id}/calls", params={"limit": limit})
    return json.dumps(result, indent=2)


@mcp.tool()
async def property_get_sms(property_id: int, limit: int = 50) -> str:
    """
    Get SMS message history for a property.

    Args:
        property_id: ID of the property
        limit: Maximum messages to return

    Returns:
        List of SMS messages
    """
    result = await api_request("GET", f"/properties/{property_id}/sms", params={"limit": limit})
    return json.dumps(result, indent=2)


@mcp.tool()
async def property_update_status(
    property_id: int,
    status: str,
    status_note: Optional[str] = None
) -> str:
    """
    Update a property's status.

    Args:
        property_id: ID of the property
        status: New status - 'active', 'pending', 'closed', 'archived'
        status_note: Optional note about the status change

    Returns:
        Updated property details
    """
    data = {"status": status}
    if status_note:
        data["status_note"] = status_note

    result = await api_request("PATCH", f"/properties/{property_id}", data)
    return json.dumps(result, indent=2)


# ============== Address Autocomplete Tools ==============

@mcp.tool()
async def address_autocomplete(query: str, session_token: Optional[str] = None) -> str:
    """
    Get address autocomplete suggestions as user types.

    Use this when a user starts typing an address to get Google suggestions.
    Returns place_ids that can be used with address_details or property_create_from_place.

    Args:
        query: The partial address text (min 3 characters)
        session_token: Optional token for Google billing optimization

    Returns:
        List of address predictions with place_id and description
    """
    params = {"query": query}
    if session_token:
        params["session_token"] = session_token

    result = await api_request("GET", "/properties/address/autocomplete", params=params)
    return json.dumps(result, indent=2)


@mcp.tool()
async def address_details(place_id: str, session_token: Optional[str] = None) -> str:
    """
    Get full address details from a Google place_id.

    Use this after address_autocomplete to get the structured address
    (street, city, state, zip, coordinates).

    Args:
        place_id: The Google place_id from autocomplete
        session_token: Optional token (should match autocomplete call)

    Returns:
        Full structured address with components and lat/lng
    """
    params = {}
    if session_token:
        params["session_token"] = session_token

    result = await api_request("GET", f"/properties/address/details/{place_id}", params=params)
    return json.dumps(result, indent=2)


@mcp.tool()
async def property_create_from_place(
    place_id: str,
    name: Optional[str] = None,
    property_type: Optional[str] = None,
    description: Optional[str] = None
) -> str:
    """
    Create a property from a Google Place selection (recommended way).

    This is the best way to create properties:
    1. Use address_autocomplete to get suggestions
    2. User selects an address (gives you place_id)
    3. Call this with the place_id

    The property will be created with the full structured address
    and automatically enriched with property data (beds, baths, value, etc.).

    Args:
        place_id: Google place_id from autocomplete
        name: Optional custom name (defaults to formatted address)
        property_type: Type like 'residential', 'commercial', 'land'
        description: Optional property description

    Returns:
        Created property with enrichment data
    """
    data = {"place_id": place_id}
    if name:
        data["name"] = name
    if property_type:
        data["property_type"] = property_type
    if description:
        data["description"] = description

    result = await api_request("POST", "/properties/from-place", data)
    return json.dumps(result, indent=2)


@mcp.tool()
async def property_enrich(property_id: int, force: bool = False) -> str:
    """
    Enrich a property with external data.

    Fetches property details like:
    - Bedrooms, bathrooms, square footage
    - Year built, lot size
    - Zestimate and tax value
    - Photos, price history, schools

    Args:
        property_id: ID of the property to enrich
        force: If True, re-enrich even if data exists

    Returns:
        Enrichment data for the property
    """
    params = {"force": force}
    result = await api_request("POST", f"/properties/{property_id}/enrich", params=params)
    return json.dumps(result, indent=2)


@mcp.tool()
async def property_get_enrichment(property_id: int) -> str:
    """
    Get existing enrichment data for a property.

    Args:
        property_id: ID of the property

    Returns:
        Enrichment data (beds, baths, value, etc.) or error if not enriched
    """
    result = await api_request("GET", f"/properties/{property_id}/enrichment")
    return json.dumps(result, indent=2)


# ============== Property Research Tools ==============

@mcp.tool()
async def property_start_research(
    property_id: int,
    brand_name: str = "Property Intelligence",
    intended_use: str = "BUY/HOLD",
    owner_hypothesis: Optional[str] = None,
    force: bool = False
) -> str:
    """
    Start comprehensive due diligence research for a property.

    This performs deep AI-powered research including:
    - Identity validation (parcel, block/lot, tax IDs)
    - 30-year ownership & title timeline
    - Tax & assessment history
    - Permits, zoning, violations
    - Market comps & valuation
    - Neighborhood intelligence (schools, transit, employers)
    - Environmental & safety data
    - Risk scorecard with recommendations

    Research takes 30-60 seconds. Use property_get_research to check status.

    Args:
        property_id: ID of the property to research
        brand_name: Brand name for white-labeling the report
        intended_use: BUY/HOLD, FLIP, or WHOLESALE
        owner_hypothesis: Known/suspected owner name (helps verify)
        force: If True, re-research even if already completed

    Returns:
        Research status and summary
    """
    data = {
        "brand_name": brand_name,
        "intended_use": intended_use,
        "force": force
    }
    if owner_hypothesis:
        data["owner_hypothesis"] = owner_hypothesis

    result = await api_request("POST", f"/properties/{property_id}/research", data)
    return json.dumps(result, indent=2)


@mcp.tool()
async def property_get_research(property_id: int) -> str:
    """
    Get research status and summary for a property.

    Returns key findings including:
    - Status (pending, in_progress, completed, failed)
    - County, block/lot, current owner
    - Assessed value, zoning
    - Value estimate range
    - Risk scores (title, tax, permit, environmental, market, neighborhood)

    Args:
        property_id: ID of the property

    Returns:
        Research summary with status and key findings
    """
    result = await api_request("GET", f"/properties/{property_id}/research")
    return json.dumps(result, indent=2)


@mcp.tool()
async def property_get_research_dossier(property_id: int) -> str:
    """
    Get the FULL research dossier for a property.

    Returns the complete due diligence report with all sections:
    - meta: Analysis metadata
    - identity_and_validation: Parcel, block/lot, tax IDs
    - property_facts: Beds, baths, sqft, HOA, utilities
    - ownership_and_title_timeline: 30-year transfer history
    - taxes_and_assessments: Assessment history, delinquency
    - permits_zoning_violations: Zoning, permits, code violations
    - sales_and_listing_history: Price history
    - comps_and_market_snapshot: Comparable sales, value estimate
    - neighborhood_intelligence: Schools, transit, employers
    - news_and_area_narrative: Recent news affecting value
    - risk_scorecard_and_next_steps: Risk scores, questions, documents needed
    - source_log: All sources used

    This JSON can be used to generate PDF reports.

    Args:
        property_id: ID of the property

    Returns:
        Complete research dossier as JSON
    """
    result = await api_request("GET", f"/properties/{property_id}/research/dossier")
    return json.dumps(result, indent=2)


@mcp.tool()
async def property_get_pdf_report(
    property_id: int,
    include_comps: bool = True,
    include_timeline: bool = True
) -> str:
    """
    Generate a professional PDF report for a property.

    Creates a beautifully formatted PDF document with:
    - Property photos and executive summary
    - Value estimates and risk scores
    - Property facts (beds, baths, sqft, year built)
    - Ownership timeline (30-year history)
    - Tax history
    - Zoning and permits
    - Comparable sales
    - Neighborhood intelligence
    - Top questions and next steps

    The property MUST have research completed first.
    Use property_start_research if not yet researched.

    Args:
        property_id: ID of the property (must have completed research)
        include_comps: Include comparable sales section (default True)
        include_timeline: Include ownership timeline section (default True)

    Returns:
        URL to download the generated PDF report
    """
    params = {
        "include_comps": include_comps,
        "include_timeline": include_timeline
    }
    # This endpoint returns binary PDF, but we'll return the URL for download
    result = await api_request("GET", f"/properties/{property_id}/research/pdf", params=params)
    if "error" in result:
        return json.dumps(result, indent=2)
    # If successful, return a download URL
    return json.dumps({
        "status": "success",
        "message": f"PDF report generated for property {property_id}",
        "download_url": f"{API_BASE_URL}/properties/{property_id}/research/pdf",
        "note": "Access this URL to download the PDF file"
    }, indent=2)


@mcp.tool()
async def property_email_report(
    property_id: int,
    to_email: str,
    custom_message: Optional[str] = None
) -> str:
    """
    Email a property report to a recipient.

    Generates a professional PDF report and sends it via email with:
    - Branded email template
    - Property address in subject line
    - Summary of report contents
    - PDF report as attachment

    The property MUST have research completed first.
    Use property_start_research if not yet researched.

    This is the main tool for sending reports to clients, investors,
    or other stakeholders. The AI voice agent should use this when
    someone asks to "send me the report" or "email me the details".

    Args:
        property_id: ID of the property (must have completed research)
        to_email: Recipient email address
        custom_message: Optional personalized message to include in the email

    Returns:
        Email send status with confirmation
    """
    data = {
        "to_email": to_email
    }
    if custom_message:
        data["custom_message"] = custom_message

    result = await api_request("POST", f"/properties/{property_id}/research/email", params=data)
    return json.dumps(result, indent=2)


# ============== Run the server ==============

if __name__ == "__main__":
    import sys

    # Check for SSE mode (for ElevenLabs, web clients, etc.)
    if os.getenv("MCP_TRANSPORT", "stdio") == "sse":
        import uvicorn
        from starlette.applications import Starlette
        from starlette.routing import Mount
        from starlette.middleware import Middleware
        from starlette.middleware.trustedhost import TrustedHostMiddleware
        from starlette.middleware.cors import CORSMiddleware

        port = int(os.getenv("PORT", "8080"))
        # Allow all hosts and CORS for cloud deployment (ElevenLabs, etc.)
        middleware = [
            Middleware(TrustedHostMiddleware, allowed_hosts=["*"]),
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"],
                expose_headers=["Mcp-Session-Id"],
            ),
        ]
        app = Starlette(routes=[Mount('/', app=mcp.sse_app())], middleware=middleware)
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        # Default stdio mode for Claude Desktop
        mcp.run()
