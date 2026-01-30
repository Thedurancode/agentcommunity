from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.core.config import settings


# Configure engine with SSL disabled for Fly.io internal postgres connections
connect_args = {}
if "postgresql+asyncpg" in settings.DATABASE_URL and ".flycast" in settings.DATABASE_URL:
    # Fly.io internal network doesn't need SSL
    connect_args["ssl"] = False

engine = create_async_engine(settings.DATABASE_URL, echo=True, connect_args=connect_args)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    # Import all models to register them with SQLAlchemy
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        # Enable pgvector extension if using PostgreSQL
        if "postgresql" in settings.DATABASE_URL:
            try:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            except Exception:
                # Extension might already exist or not be available
                pass

        await conn.run_sync(Base.metadata.create_all)
