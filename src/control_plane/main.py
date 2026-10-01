"""Fabrique de l'application FastAPI et point d'entrée du serveur."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from control_plane.api import health
from control_plane.config import Settings, get_settings
from control_plane.infrastructure.db.session import get_engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Au démarrage : rien. À l'arrêt : fermer proprement le pool de connexions."""
    yield
    await get_engine().dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Assemble l'application (pattern Factory)."""
    settings = settings or get_settings()
    docs_enabled = not settings.is_prod

    app = FastAPI(
        title="Control Plane IAM",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.include_router(health.router)
    return app


def run() -> None:
    """Commande `uv run control-plane` : serveur local de développement."""
    uvicorn.run(
        "control_plane.main:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        reload=get_settings().env == "dev",
    )
