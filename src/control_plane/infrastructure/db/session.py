from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from control_plane.config import Settings, get_settings


def build_engine(settings: Settings) -> AsyncEngine:
    """Crée le moteur et son pool de connexions à partir de la configuration."""
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Moteur unique pour tout le processus."""
    return build_engine(get_settings())


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Fabrique de sessions liée au moteur unique."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Fournit une session par requête et la referme toujours à la fin."""
    async with get_session_factory()() as session:
        yield session
