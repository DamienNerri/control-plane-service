"""Données de test fictives pour le développement local, jamais en production.

Reprend les scénarios d'acceptation du cahier des charges.
Idempotent : peut être relancé sans créer de doublons.
"""

import asyncio
import sys
import uuid
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
    ProjectMembership,
    User,
    UserProjectOverride,
)
from control_plane.infrastructure.db.session import get_engine, get_session_factory

PROJECT_ID = "portfolio_dev"

PERMISSIONS = {
    "project:delete": "Supprimer un projet",
    "contact:send": "Envoyer le formulaire de contact",
    "invoice:create": "Créer une facture",
    "invoice:read": "Consulter les factures",
}

# groupe -> (nom affiché, permissions du groupe)
GROUPS = {
    "group_visitor": ("Visiteur", ["contact:send"]),
    "group_dev": ("Développeur", ["contact:send", "invoice:create", "invoice:read"]),
}

# sub fictif -> Global Owner ?
USERS = {
    "usr_owner": True,
    "usr_alice": False,
    "usr_bob": False,
}

# sub -> groupe dans portfolio_dev
MEMBERSHIPS = {
    "usr_alice": "group_visitor",
    "usr_bob": "group_dev",
}


async def _insert_ignore(
    session: AsyncSession, model: type[Base], rows: list[dict[str, Any]]
) -> None:
    """INSERT ... ON CONFLICT DO NOTHING : les lignes déjà présentes sont gardées."""
    await session.execute(insert(model).values(rows).on_conflict_do_nothing())


async def _user_ids(session: AsyncSession) -> dict[str, uuid.UUID]:
    result = await session.execute(select(User.subject, User.id).where(User.subject.in_(USERS)))
    return {subject: user_id for subject, user_id in result.all()}


async def seed(session: AsyncSession) -> None:
    await _insert_ignore(
        session,
        Permission,
        [{"id": perm, "description": desc} for perm, desc in PERMISSIONS.items()],
    )
    await _insert_ignore(
        session,
        Group,
        [{"id": group, "name": name} for group, (name, _) in GROUPS.items()],
    )
    await _insert_ignore(
        session,
        GroupPermission,
        [
            {"group_id": group, "permission_id": perm}
            for group, (_, perms) in GROUPS.items()
            for perm in perms
        ],
    )
    await _insert_ignore(session, Project, [{"id": PROJECT_ID, "name": "Portfolio (dev)"}])
    await _insert_ignore(
        session,
        User,
        [{"subject": subject, "is_global_owner": owner} for subject, owner in USERS.items()],
    )

    ids = await _user_ids(session)

    await _insert_ignore(
        session,
        ProjectMembership,
        [
            {"user_id": ids[subject], "project_id": PROJECT_ID, "group_id": group}
            for subject, group in MEMBERSHIPS.items()
        ],
    )
    await _insert_ignore(
        session,
        UserProjectOverride,
        [
            {
                # Scénario d'acceptation : le DENY individuel bat le groupe
                "user_id": ids["usr_bob"],
                "project_id": PROJECT_ID,
                "permission_id": "invoice:create",
                "effect": "DENY",
                "reason": "Scénario d'acceptation : refus individuel",
                "expires_at": None,
                "created_by": ids["usr_owner"],
            },
            {
                # RG-04 : un override expiré est ignoré
                "user_id": ids["usr_alice"],
                "project_id": PROJECT_ID,
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

    print(f"Données de test présentes dans {PROJECT_ID} (3 utilisateurs, 2 overrides).")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
