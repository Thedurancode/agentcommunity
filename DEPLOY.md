# Deploying to Fly.io

## Prerequisites

1. Install the Fly CLI:
```bash
brew install flyctl
```

2. Login to Fly.io:
```bash
fly auth login
```

## Deploy the API

### 1. Create the Fly app

```bash
fly apps create agentcommunity-api
```

### 2. Create PostgreSQL database

```bash
fly postgres create --name agentcommunity-db --region ord
```

### 3. Attach database to app

```bash
fly postgres attach agentcommunity-db --app agentcommunity-api
```

This automatically sets the `DATABASE_URL` secret.

### 4. Create uploads volume

```bash
fly volumes create uploads_data --region ord --size 1 --app agentcommunity-api
```

### 5. Set secrets

```bash
# Generate a secure secret key
fly secrets set SECRET_KEY=$(openssl rand -hex 32) --app agentcommunity-api

# Optional: Add API keys
fly secrets set ANTHROPIC_API_KEY=your-key --app agentcommunity-api
fly secrets set GITHUB_CLIENT_ID=your-id --app agentcommunity-api
fly secrets set GITHUB_CLIENT_SECRET=your-secret --app agentcommunity-api
fly secrets set GITHUB_REDIRECT_URI=https://agentcommunity-api.fly.dev/api/v1/github/callback --app agentcommunity-api
```

### 6. Deploy

```bash
fly deploy
```

### 7. Check status

```bash
fly status --app agentcommunity-api
fly logs --app agentcommunity-api
```

## Access the API

- **API**: https://agentcommunity-api.fly.dev
- **Docs**: https://agentcommunity-api.fly.dev/docs
- **Health**: https://agentcommunity-api.fly.dev/api/v1/health

## MCP Server Setup

The MCP server runs locally and connects to your deployed API.

### Configure Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "community-api": {
      "command": "python",
      "args": ["/path/to/agentcommunity/mcp_server/server.py"],
      "env": {
        "COMMUNITY_API_URL": "https://agentcommunity-api.fly.dev/api/v1",
        "COMMUNITY_API_TOKEN": "your-jwt-token"
      }
    }
  }
}
```

### Get an API token

1. Register a user via the API
2. Login to get a JWT token
3. Use that token in the MCP config

## Useful Commands

```bash
# View logs
fly logs --app agentcommunity-api

# SSH into the machine
fly ssh console --app agentcommunity-api

# Connect to database
fly postgres connect --app agentcommunity-db

# Scale up/down
fly scale count 1 --app agentcommunity-api
fly scale memory 1024 --app agentcommunity-api

# View secrets
fly secrets list --app agentcommunity-api
```

## Troubleshooting

### Database connection issues
- Ensure postgres is attached: `fly postgres attach agentcommunity-db --app agentcommunity-api`
- Check DATABASE_URL is set: `fly secrets list --app agentcommunity-api`

### App not starting
- Check logs: `fly logs --app agentcommunity-api`
- Verify health endpoint: `curl https://agentcommunity-api.fly.dev/health`

### Volume issues
- List volumes: `fly volumes list --app agentcommunity-api`
- Ensure volume is in same region as app
