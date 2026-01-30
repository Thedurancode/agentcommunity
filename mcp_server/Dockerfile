# MCP Server Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code
COPY server.py .

# Create non-root user
RUN adduser --disabled-password --gecos '' mcpuser
USER mcpuser

# Expose port for SSE mode
EXPOSE 8080

# Run server (MCP_TRANSPORT env var controls stdio vs sse mode)
CMD ["python", "server.py"]
