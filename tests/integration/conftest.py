"""Fixtures des tests d'intégration : un vrai PostgreSQL jetable, migré et rempli."""

from collections.abc import AsyncIterator, Iterator

import pytest
from alembic import command
from alembic.config import Config
from scripts.seed_dev import seed
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from control_plane.config import get_settings


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Démarre PostgreSQL 16 une seule fois pour toute la session, puis applique les migrations."""
    with (
        PostgresContainer("postgres:16-alpine", driver="asyncpg") as postgres,
        pytest.MonkeyPatch.context() as mp,
    ):
        url = postgres.get_connection_url()
        # Les migrations lisent leur URL dans Settings : on les pointe vers le conteneur
        mp.setenv("DATABASE_URL", url)
        mp.setenv("DATABASE_MIGRATION_URL", url)
        get_settings.cache_clear()
        command.upgrade(Config("alembic.ini"), "head")
        yield url
    get_settings.cache_clear()


@pytest.fixture
async def session(database_url: str) -> AsyncIterator[AsyncSession]:
    """Une session par test, dans une transaction annulée à la fin.

    Chaque test part ainsi d'une base propre, sans avoir à la vider.
    """
    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint"
        ) as session:
            yield session
        await transaction.rollback()
    await engine.dispose()


@pytest.fixture
async def seeded_session(session: AsyncSession) -> AsyncSession:
    """Session remplie avec les données de scripts/seed_dev.py (scénarios d'acceptation)."""
    await seed(session)
    return session
