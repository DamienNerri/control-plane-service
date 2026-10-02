"""Implémentation en mémoire de RightsReader, pour les tests sans base de données."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from control_plane.domain.ports import OverrideEffect

if TYPE_CHECKING:
    from control_plane.domain.ports import RightsReader


def _is_active(expires_at: datetime | None, at: datetime) -> bool:
    return expires_at is None or expires_at > at


@dataclass
class InMemoryRightsReader:
    """Mêmes règles que la base, sans la base : chaque champ imite une table."""

    global_owners: set[str] = field(default_factory=set)
    # (sujet, projet)
    project_admins: set[tuple[str, str]] = field(default_factory=set)
    # (sujet, projet) -> groupe
    memberships: dict[tuple[str, str], str] = field(default_factory=dict)
    # (projet, groupe) -> permissions : un groupe n'existe que dans son projet
    groups: dict[tuple[str, str], frozenset[str]] = field(default_factory=dict)
    # (sujet, projet, permission) -> (effet, expiration ou None)
    overrides: dict[tuple[str, str, str], tuple[OverrideEffect, datetime | None]] = field(
        default_factory=dict
    )

    async def is_global_owner(self, subject: str) -> bool:
        return subject in self.global_owners

    async def is_project_admin(self, subject: str, project_id: str) -> bool:
        return (subject, project_id) in self.project_admins

    async def active_override(
        self, subject: str, project_id: str, permission: str, at: datetime
    ) -> OverrideEffect | None:
        entry = self.overrides.get((subject, project_id, permission))
        if entry is None:
            return None
        effect, expires_at = entry
        return effect if _is_active(expires_at, at) else None

    async def group_grants(self, subject: str, project_id: str, permission: str) -> bool:
        return permission in self._group_permissions(subject, project_id)

    async def effective_permissions(
        self, subject: str, project_id: str, at: datetime
    ) -> frozenset[str]:
        permissions = set(self._group_permissions(subject, project_id))
        for (o_subject, o_project, permission), (effect, expires_at) in self.overrides.items():
            if (o_subject, o_project) != (subject, project_id) or not _is_active(expires_at, at):
                continue
            if effect is OverrideEffect.ALLOW:
                permissions.add(permission)
            else:
                permissions.discard(permission)
        return frozenset(permissions)

    def _group_permissions(self, subject: str, project_id: str) -> frozenset[str]:
        group = self.memberships.get((subject, project_id))
        if group is None:
            return frozenset()
        return self.groups.get((project_id, group), frozenset())


if TYPE_CHECKING:
    # Vérifié par mypy uniquement : la classe respecte bien le port RightsReader
    _conformance_check: RightsReader = InMemoryRightsReader()
