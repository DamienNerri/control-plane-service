"""Test de contrat : les implémentations mémoire et SQL de RightsReader se comportent pareil.

Chaque test tourne deux fois, une par implémentation, sur les mêmes données
(celles de scripts/seed_dev.py).
"""

from datetime import UTC, datetime, timedelta

import pytest
from scripts.seed_dev import MEMBERSHIPS, PROJECT_ADMINS, PROJECTS, USERS
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.ports import OverrideEffect, RightsReader
from control_plane.infrastructure.repositories.memory import InMemoryRightsReader
from control_plane.infrastructure.repositories.sqlalchemy_reader import SqlAlchemyRightsReader

pytestmark = pytest.mark.integration


def memory_reader() -> InMemoryRightsReader:
    """Mêmes données que seed_dev.py, mais en mémoire."""
    return InMemoryRightsReader(
        global_owners={subject for subject, owner in USERS.items() if owner},
        project_admins=set(PROJECT_ADMINS),
        memberships={(subject, project): group for subject, project, group in MEMBERSHIPS},
        groups={
            (project_id, group): frozenset(perms)
            for project_id, project in PROJECTS.items()
            for group, (_, perms) in project.groups.items()
        },
        # Recopie des deux overrides écrits dans seed()
        overrides={
            ("usr_bob", "portfolio_dev", "invoice:create"): (OverrideEffect.DENY, None),
            ("usr_alice", "portfolio_dev", "invoice:read"): (
                OverrideEffect.ALLOW,
                datetime.now(UTC) - timedelta(days=1),
            ),
        },
    )


@pytest.fixture(params=["memory", "sql"])
def reader(request: pytest.FixtureRequest, seeded_session: AsyncSession) -> RightsReader:
    if request.param == "memory":
        return memory_reader()
    return SqlAlchemyRightsReader(seeded_session)


def now() -> datetime:
    return datetime.now(UTC)


async def test_global_owner(reader: RightsReader) -> None:
    assert await reader.is_global_owner("usr_owner")
    assert not await reader.is_global_owner("usr_alice")


async def test_un_admin_de_projet_ne_l_est_que_sur_son_projet(reader: RightsReader) -> None:
    assert await reader.is_project_admin("usr_dana", "portfolio_dev")
    assert not await reader.is_project_admin("usr_dana", "blog_dev")
    assert not await reader.is_project_admin("usr_eric", "portfolio_dev")


async def test_le_deny_permanent_de_bob_est_actif(reader: RightsReader) -> None:
    effect = await reader.active_override("usr_bob", "portfolio_dev", "invoice:create", now())
    assert effect is OverrideEffect.DENY


async def test_l_allow_expire_d_alice_est_ignore(reader: RightsReader) -> None:
    assert await reader.active_override("usr_alice", "portfolio_dev", "invoice:read", now()) is None


async def test_le_groupe_donne_ses_permissions(reader: RightsReader) -> None:
    assert await reader.group_grants("usr_alice", "portfolio_dev", "contact:send")
    assert not await reader.group_grants("usr_alice", "portfolio_dev", "invoice:create")
    assert await reader.group_grants("usr_eric", "portfolio_dev", "admin:member_assign")


async def test_un_membre_n_a_rien_sur_un_autre_projet(reader: RightsReader) -> None:
    # blog_dev a aussi un group_visitor avec contact:send, mais Alice n'en est pas membre
    assert not await reader.group_grants("usr_alice", "blog_dev", "contact:send")


async def test_un_inconnu_n_a_rien_et_ne_provoque_aucune_erreur(reader: RightsReader) -> None:
    assert not await reader.is_global_owner("usr_inconnu")
    assert not await reader.is_project_admin("usr_inconnu", "projet_inconnu")
    assert await reader.active_override("usr_inconnu", "portfolio_dev", "x:y", now()) is None
    assert not await reader.group_grants("usr_inconnu", "projet_inconnu", "contact:send")
    assert await reader.effective_permissions("usr_inconnu", "portfolio_dev", now()) == set()


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("usr_bob", {"contact:send", "invoice:read"}),  # le DENY retire invoice:create
        ("usr_alice", {"contact:send"}),  # l'ALLOW expiré n'ajoute rien
        ("usr_eric", {"admin:member_assign", "contact:send"}),
        ("usr_dana", set()),  # le statut d'admin est traité à part par l'appelant
    ],
)
async def test_droits_effectifs(reader: RightsReader, subject: str, expected: set[str]) -> None:
    assert await reader.effective_permissions(subject, "portfolio_dev", now()) == expected
