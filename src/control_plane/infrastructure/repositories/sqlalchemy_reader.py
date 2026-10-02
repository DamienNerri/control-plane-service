"""Implémentation SQLAlchemy de RightsReader : une requête indexée par maillon."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ColumnElement, and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.ports import OverrideEffect
from control_plane.infrastructure.db.models import (
    GroupPermission,
    ProjectAdmin,
    ProjectMembership,
    User,
    UserProjectOverride,
)

if TYPE_CHECKING:
    from control_plane.domain.ports import RightsReader


def _is_active(at: datetime) -> ColumnElement[bool]:
    """Override non expiré à l'instant `at` (même règle que InMemoryRightsReader)."""
    return or_(UserProjectOverride.expires_at.is_(None), UserProjectOverride.expires_at > at)


class SqlAlchemyRightsReader:
    """Lit les droits dans PostgreSQL. Lecture seule : ne valide jamais de transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_global_owner(self, subject: str) -> bool:
        stmt = select(User.is_global_owner).where(User.subject == subject)
        return bool(await self._session.scalar(stmt))

    async def is_project_admin(self, subject: str, project_id: str) -> bool:
        stmt = select(
            exists().where(
                ProjectAdmin.user_id == User.id,
                User.subject == subject,
                ProjectAdmin.project_id == project_id,
            )
        )
        return bool(await self._session.scalar(stmt))

    async def active_override(
        self, subject: str, project_id: str, permission: str, at: datetime
    ) -> OverrideEffect | None:
        stmt = (
            select(UserProjectOverride.effect)
            .join(User, User.id == UserProjectOverride.user_id)
            .where(
                User.subject == subject,
                UserProjectOverride.project_id == project_id,
                UserProjectOverride.permission_id == permission,
                _is_active(at),
            )
        )
        effect = await self._session.scalar(stmt)
        return None if effect is None else OverrideEffect(effect)

    async def group_grants(self, subject: str, project_id: str, permission: str) -> bool:
        stmt = select(
            exists().where(
                ProjectMembership.user_id == User.id,
                User.subject == subject,
                ProjectMembership.project_id == project_id,
                GroupPermission.project_id == ProjectMembership.project_id,
                GroupPermission.group_id == ProjectMembership.group_id,
                GroupPermission.permission_id == permission,
            )
        )
        return bool(await self._session.scalar(stmt))

    async def effective_permissions(
        self, subject: str, project_id: str, at: datetime
    ) -> frozenset[str]:
        group_stmt = (
            select(GroupPermission.permission_id)
            .join(
                ProjectMembership,
                and_(
                    GroupPermission.project_id == ProjectMembership.project_id,
                    GroupPermission.group_id == ProjectMembership.group_id,
                ),
            )
            .join(User, User.id == ProjectMembership.user_id)
            .where(User.subject == subject, ProjectMembership.project_id == project_id)
        )
        override_stmt = (
            select(UserProjectOverride.permission_id, UserProjectOverride.effect)
            .join(User, User.id == UserProjectOverride.user_id)
            .where(
                User.subject == subject,
                UserProjectOverride.project_id == project_id,
                _is_active(at),
            )
        )

        permissions = set((await self._session.scalars(group_stmt)).all())
        for permission, effect in (await self._session.execute(override_stmt)).all():
            if effect == OverrideEffect.ALLOW:
                permissions.add(permission)
            else:
                permissions.discard(permission)
        return frozenset(permissions)


if TYPE_CHECKING:
    # Vérifié par mypy uniquement : la classe respecte bien le port RightsReader
    def _conformance_check(session: AsyncSession) -> RightsReader:
        return SqlAlchemyRightsReader(session)
