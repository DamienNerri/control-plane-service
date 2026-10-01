"""Sondes de santé pour l'orchestrateur, sans authentification."""

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.infrastructure.db.session import get_session

router = APIRouter(tags=["santé"])

READINESS_TIMEOUT_SECONDS = 2.0

logger = logging.getLogger(__name__)


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Vivacité : le processus répond. Ne touche jamais la base."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    """Disponibilité : la base répond en moins de 2 secondes."""
    try:
        async with asyncio.timeout(READINESS_TIMEOUT_SECONDS):
            await session.execute(text("SELECT 1"))
    except SQLAlchemyError, OSError:
        logger.warning("readyz : base de données indisponible", exc_info=True)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}
    return {"status": "ok"}
