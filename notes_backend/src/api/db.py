import os
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def _to_async_driver_url(url: str) -> str:
    """
    Convert a sync postgres URL to asyncpg driver URL if needed.

    Examples:
      postgresql://user:pass@host:port/db -> postgresql+asyncpg://...
      postgres://... -> postgresql+asyncpg://...
      postgresql+asyncpg://... -> unchanged
    """
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


def get_database_url() -> str:
    """
    Resolve the database URL from environment variables.

    We intentionally use a single connection string env var to align with typical
    deployment patterns and the provided db_connection.txt example.

    Env vars supported:
      - DATABASE_URL (preferred)
      - POSTGRES_URL (fallback)

    Returns:
      Async driver URL suitable for SQLAlchemy async engine.
    """
    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not url:
        raise RuntimeError(
            "Database connection is not configured. Please set DATABASE_URL (preferred) "
            "or POSTGRES_URL env var. Example: postgresql://user:pass@host:port/db"
        )
    return _to_async_driver_url(url)


_ENGINE: Optional[AsyncEngine] = None
_SessionMaker: Optional[async_sessionmaker[AsyncSession]] = None


def init_engine() -> AsyncEngine:
    """
    Initialize (or return existing) SQLAlchemy async engine and sessionmaker.
    """
    global _ENGINE, _SessionMaker

    if _ENGINE is None:
        db_url = get_database_url()
        _ENGINE = create_async_engine(
            db_url,
            future=True,
            pool_pre_ping=True,
        )
        _SessionMaker = async_sessionmaker(bind=_ENGINE, expire_on_commit=False)
    return _ENGINE


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides an AsyncSession.
    """
    if _SessionMaker is None:
        init_engine()

    assert _SessionMaker is not None
    async with _SessionMaker() as session:
        yield session
