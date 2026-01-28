# Community API MCP Server

An MCP (Model Context Protocol) server that exposes the Code Live OS Community API to AI agents.

## Features

This MCP server provides 25+ tools for AI agents to:

- **Authentication**: Login, register, get user profile
- **Projects**: Create, list, update projects
- **Issues**: Create, list, update issues with filtering
- **Feed/Posts**: Create posts, like, comment, view feed
- **Messaging**: Start conversations, send messages
- **Notifications**: Get and manage notifications
- **Blogs**: Create and list blog posts
- **Teams**: Add/list team members

## Installation

1. Install dependencies:
```bash
cd mcp_server
pip install -r requirements.txt
```

2. Copy the environment file:
```bash
cp .env.example .env
```

3. Edit `.env` with your API URL (default: `http://127.0.0.1:8000/api/v1`)

## Usage with Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "community-api": {
      "command": "python",
      "args": ["/path/to/agentcommunity/mcp_server/server.py"],
      "env": {
        "COMMUNITY_API_URL": "http://127.0.0.1:8000/api/v1"
      }
    }
  }
}
```

## Usage with Claude Code

Add to your Claude Code MCP settings:

```json
{
  "mcpServers": {
    "community-api": {
      "command": "python",
      "args": ["mcp_server/server.py"],
      "env": {
        "COMMUNITY_API_URL": "http://127.0.0.1:8000/api/v1"
      }
    }
  }
}
```

## Available Tools

### Authentication
| Tool | Description |
|------|-------------|
| `login` | Login and store access token |
| `register_user` | Create a new user account |
| `get_current_user` | Get authenticated user's profile |

### Projects
| Tool | Description |
|------|-------------|
| `create_project` | Create a new project |
| `list_projects` | List user's projects |
| `get_project` | Get project details |
| `update_project` | Update project name/status |

### Issues
| Tool | Description |
|------|-------------|
| `create_issue` | Create issue in a project |
| `list_issues` | List issues with filtering |
| `update_issue` | Update issue details/state |

### Feed & Posts
| Tool | Description |
|------|-------------|
| `create_post` | Create a new post |
| `get_feed` | Get the post feed |
| `get_post` | Get post details |
| `like_post` | Like a post |
| `comment_on_post` | Comment on a post |
| `get_post_comments` | Get post comments |

### Messaging
| Tool | Description |
|------|-------------|
| `start_conversation` | Start a new conversation |
| `send_message` | Send a message |
| `list_conversations` | List all conversations |
| `get_conversation_messages` | Get conversation messages |

### Notifications
| Tool | Description |
|------|-------------|
| `get_notifications` | Get user notifications |
| `mark_notification_read` | Mark notification as read |

### Blogs
| Tool | Description |
|------|-------------|
| `create_blog` | Create a blog post |
| `list_blogs` | List blog posts |
| `get_blog` | Get blog details |

### Teams
| Tool | Description |
|------|-------------|
| `add_team_member` | Add member to project |
| `list_team_members` | List project members |
| `list_users` | List all users (admin) |

## Example Workflow

```
1. AI: login("myuser", "mypassword")
2. AI: create_project("New App", "Building a new application")
3. AI: create_issue(project_id=1, title="Setup CI/CD", description="Configure GitHub Actions")
4. AI: create_post("Just started a new project!", visibility="public")
5. AI: start_conversation(recipient_id=2, initial_message="Hey, want to collaborate?")
```

## Running the Server Directly

```bash
python server.py
```

The server communicates via stdio using the MCP protocol.
