"""Données de test fictives pour le développement local, jamais en production.

Couvre les 10 scénarios d'acceptation du cahier des charges v1.1.
Idempotent : peut être relancé sans créer de doublons.
"""

import asyncio
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config import get_settings
from control_plane.infrastructure.db.base import Base
from control_plane.infrastructure.db.models import (
    Group,
    GroupPermission,
    Permission,
    Project,
    ProjectAdmin,
    ProjectMembership,
    User,
    UserProjectOverride,
)
from control_plane.infrastructure.db.session import get_engine, get_session_factory

# Créées avec chaque projet (RG-13). AdminService les créera lui-même au ticket CP-22.
ADMIN_PERMISSIONS = {
    "admin:permission_manage": "Déclarer ou supprimer une permission du projet",
    "admin:group_manage": "Créer, modifier ou supprimer un groupe",
    "admin:member_assign": "Ajouter ou retirer un membre, changer son groupe",
    "admin:override_manage": "Poser ou retirer un override",
    "admin:audit_read": "Consulter le journal d'audit du projet",
}


@dataclass(frozen=True)
class ProjectSeed:
    name: str
    # permission métier -> description
    permissions: dict[str, str]
    # groupe -> (nom affiché, permissions du groupe)
    groups: dict[str, tuple[str, list[str]]] = field(default_factory=dict)


PROJECTS = {
    "portfolio_dev": ProjectSeed(
        name="Portfolio (dev)",
        permissions={
            "project:delete": "Supprimer un projet",
            "contact:send": "Envoyer le formulaire de contact",
            "invoice:create": "Créer une facture",
            "invoice:read": "Consulter les factures",
        },
        groups={
            "group_visitor": ("Visiteur", ["contact:send"]),
            "group_dev": ("Développeur", ["contact:send", "invoice:create", "invoice:read"]),
            # Manager : peut ajouter des membres, mais n'a que contact:send (scénarios 8 à 10)
            "group_manager": ("Manager", ["admin:member_assign", "contact:send"]),
        },
    ),
    "blog_dev": ProjectSeed(
        name="Blog (dev)",
        permissions={
            "contact:send": "Envoyer le formulaire de contact",
            "post:publish": "Publier un article",
        },
        groups={
            "group_visitor": ("Visiteur", ["contact:send"]),
        },
    ),
}

# sub fictif -> Global Owner ?
USERS = {
    "usr_owner": True,
    "usr_alice": False,
    "usr_bob": False,
    "usr_dana": False,
    "usr_eric": False,
}

# (sub, projet) : admins de projet, nommés par usr_owner
PROJECT_ADMINS = [("usr_dana", "portfolio_dev")]

# (sub, projet, groupe)
MEMBERSHIPS = [
    ("usr_alice", "portfolio_dev", "group_visitor"),
    ("usr_bob", "portfolio_dev", "group_dev"),
    ("usr_eric", "portfolio_dev", "group_manager"),
]


async def _insert_ignore(
    session: AsyncSession, model: type[Base], rows: list[dict[str, Any]]
) -> None:
    """INSERT ... ON CONFLICT DO NOTHING : les lignes déjà présentes sont gardées."""
    if rows:
        await session.execute(insert(model).values(rows).on_conflict_do_nothing())


async def _user_ids(session: AsyncSession) -> dict[str, uuid.UUID]:
    result = await session.execute(select(User.subject, User.id).where(User.subject.in_(USERS)))
    return {subject: user_id for subject, user_id in result.all()}


async def seed(session: AsyncSession) -> None:
    await _insert_ignore(
        session,
        Project,
        [{"id": project_id, "name": p.name} for project_id, p in PROJECTS.items()],
    )
    await _insert_ignore(
        session,
        Permission,
        [
            {"project_id": project_id, "id": perm, "description": desc}
            for project_id, p in PROJECTS.items()
            for perm, desc in {**ADMIN_PERMISSIONS, **p.permissions}.items()
        ],
    )
    await _insert_ignore(
        session,
        Group,
        [
            {"project_id": project_id, "id": group, "name": name}
            for project_id, p in PROJECTS.items()
            for group, (name, _) in p.groups.items()
        ],
    )
    await _insert_ignore(
        session,
        GroupPermission,
        [
            {"project_id": project_id, "group_id": group, "permission_id": perm}
            for project_id, p in PROJECTS.items()
            for group, (_, perms) in p.groups.items()
            for perm in perms
        ],
    )
    await _insert_ignore(
        session,
        User,
        [{"subject": subject, "is_global_owner": owner} for subject, owner in USERS.items()],
    )

    ids = await _user_ids(session)

    await _insert_ignore(
        session,
        ProjectAdmin,
        [
            {"user_id": ids[subject], "project_id": project_id, "created_by": ids["usr_owner"]}
            for subject, project_id in PROJECT_ADMINS
        ],
    )
    await _insert_ignore(
        session,
        ProjectMembership,
        [
            {"user_id": ids[subject], "project_id": project_id, "group_id": group}
            for subject, project_id, group in MEMBERSHIPS
        ],
    )
    await _insert_ignore(
        session,
        UserProjectOverride,
        [
            {
                # Scénario 3 : le DENY individuel bat le groupe
                "user_id": ids["usr_bob"],
                "project_id": "portfolio_dev",
                "permission_id": "invoice:create",
                "effect": "DENY",
                "reason": "Scénario d'acceptation : refus individuel",
                "expires_at": None,
                "created_by": ids["usr_owner"],
            },
            {
                # RG-04 : un override expiré est ignoré
                "user_id": ids["usr_alice"],
                "project_id": "portfolio_dev",
                "permission_id": "invoice:read",
                "effect": "ALLOW",
                "reason": "Accès temporaire terminé (test d'expiration)",
                "expires_at": datetime.now(UTC) - timedelta(days=1),
                "created_by": ids["usr_owner"],
            },
        ],
    )


async def main() -> int:
    settings = get_settings()
    if settings.env != "dev":
        print(
            f"Refusé : ENV={settings.env}. Ce script ne s'exécute qu'avec ENV=dev.",
            file=sys.stderr,
        )
        return 1

    try:
        async with get_session_factory()() as session, session.begin():
            await seed(session)
    finally:
        await get_engine().dispose()

    print(
        f"Données de test présentes : {len(PROJECTS)} projets, {len(USERS)} utilisateurs, "
        f"{len(PROJECT_ADMINS)} admin de projet, {len(MEMBERSHIPS)} appartenances."
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
