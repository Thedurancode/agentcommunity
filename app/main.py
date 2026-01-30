from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import init_db
from app.api.routes import auth, projects, team_members, issues, pull_requests, github, brands, notes, recap, videos, classes, support_tickets, feed, episodes, voice_notes, developers, blogs, notifications, messages, properties, webhooks, api_keys, voice_streaming, sentiment, memory, agent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    # Ensure uploads directory exists
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    yield
    # Shutdown


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(projects.router, prefix=settings.API_V1_PREFIX)
app.include_router(team_members.router, prefix=settings.API_V1_PREFIX)
app.include_router(issues.router, prefix=settings.API_V1_PREFIX)
app.include_router(pull_requests.router, prefix=settings.API_V1_PREFIX)
app.include_router(github.router, prefix=settings.API_V1_PREFIX)
app.include_router(brands.router, prefix=settings.API_V1_PREFIX)
app.include_router(notes.router, prefix=settings.API_V1_PREFIX)
app.include_router(recap.router, prefix=settings.API_V1_PREFIX)
app.include_router(videos.router, prefix=settings.API_V1_PREFIX)
app.include_router(classes.router, prefix=settings.API_V1_PREFIX)
app.include_router(classes.history_router, prefix=settings.API_V1_PREFIX)
app.include_router(support_tickets.router, prefix=settings.API_V1_PREFIX)
app.include_router(feed.router, prefix=settings.API_V1_PREFIX)
app.include_router(episodes.router, prefix=settings.API_V1_PREFIX)
app.include_router(voice_notes.router, prefix=settings.API_V1_PREFIX)
app.include_router(developers.router, prefix=settings.API_V1_PREFIX)
app.include_router(blogs.router, prefix=settings.API_V1_PREFIX)
app.include_router(notifications.router, prefix=settings.API_V1_PREFIX)
app.include_router(messages.router, prefix=settings.API_V1_PREFIX)
app.include_router(properties.router, prefix=settings.API_V1_PREFIX)
app.include_router(webhooks.router, prefix=settings.API_V1_PREFIX)
app.include_router(api_keys.router, prefix=settings.API_V1_PREFIX)
app.include_router(voice_streaming.router, prefix=settings.API_V1_PREFIX)
app.include_router(sentiment.router, prefix=settings.API_V1_PREFIX)
app.include_router(memory.router, prefix=settings.API_V1_PREFIX)
app.include_router(agent.router, prefix=settings.API_V1_PREFIX)

# Serve uploaded files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/")
async def root():
    return {
        "name": settings.PROJECT_NAME,
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
@app.get(f"{settings.API_V1_PREFIX}/health")
async def health_check():
    return {"status": "healthy"}
