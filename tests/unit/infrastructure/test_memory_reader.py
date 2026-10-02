"""Tests de InMemoryRightsReader : il doit suivre les mêmes règles que la base."""

from datetime import UTC, datetime, timedelta

from control_plane.domain.ports import OverrideEffect
from control_plane.infrastructure.repositories.memory import InMemoryRightsReader

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


def make_reader() -> InMemoryRightsReader:
    """Reprend les données de scripts/seed_dev.py."""
    return InMemoryRightsReader(
        global_owners={"usr_owner"},
        project_admins={("usr_dana", "portfolio_dev")},
        memberships={
            ("usr_alice", "portfolio_dev"): "group_visitor",
            ("usr_bob", "portfolio_dev"): "group_dev",
        },
        groups={
            ("portfolio_dev", "group_visitor"): frozenset({"contact:send"}),
            ("portfolio_dev", "group_dev"): frozenset(
                {"contact:send", "invoice:create", "invoice:read"}
            ),
            ("blog_dev", "group_visitor"): frozenset({"post:publish"}),
        },
        overrides={
            ("usr_bob", "portfolio_dev", "invoice:create"): (OverrideEffect.DENY, None),
            ("usr_alice", "portfolio_dev", "invoice:read"): (
                OverrideEffect.ALLOW,
                NOW - timedelta(days=1),
            ),
        },
    )


async def test_global_owner() -> None:
    reader = make_reader()
    assert await reader.is_global_owner("usr_owner")
    assert not await reader.is_global_owner("usr_alice")


async def test_un_admin_de_projet_ne_l_est_que_sur_son_projet() -> None:
    reader = make_reader()
    assert await reader.is_project_admin("usr_dana", "portfolio_dev")
    assert not await reader.is_project_admin("usr_dana", "blog_dev")


async def test_un_override_permanent_est_actif() -> None:
    reader = make_reader()
    effect = await reader.active_override("usr_bob", "portfolio_dev", "invoice:create", NOW)
    assert effect is OverrideEffect.DENY


async def test_un_override_expire_est_ignore() -> None:
    reader = make_reader()
    assert await reader.active_override("usr_alice", "portfolio_dev", "invoice:read", NOW) is None


async def test_un_override_qui_expire_a_l_instant_exact_est_expire() -> None:
    reader = make_reader()
    reader.overrides[("usr_alice", "portfolio_dev", "contact:send")] = (OverrideEffect.DENY, NOW)
    assert await reader.active_override("usr_alice", "portfolio_dev", "contact:send", NOW) is None


async def test_un_override_qui_expire_plus_tard_est_actif() -> None:
    reader = make_reader()
    reader.overrides[("usr_alice", "portfolio_dev", "contact:send")] = (
        OverrideEffect.DENY,
        NOW + timedelta(seconds=1),
    )
    effect = await reader.active_override("usr_alice", "portfolio_dev", "contact:send", NOW)
    assert effect is OverrideEffect.DENY


async def test_le_groupe_donne_ses_permissions() -> None:
    reader = make_reader()
    assert await reader.group_grants("usr_alice", "portfolio_dev", "contact:send")
    assert not await reader.group_grants("usr_alice", "portfolio_dev", "invoice:create")


async def test_un_groupe_homonyme_d_un_autre_projet_ne_donne_rien() -> None:
    # group_visitor de blog_dev contient post:publish, mais Alice est dans celui de portfolio_dev
    reader = make_reader()
    assert not await reader.group_grants("usr_alice", "portfolio_dev", "post:publish")
    assert not await reader.group_grants("usr_alice", "blog_dev", "post:publish")


async def test_un_inconnu_n_a_rien_et_ne_provoque_aucune_erreur() -> None:
    reader = make_reader()
    assert not await reader.is_global_owner("usr_inconnu")
    assert not await reader.is_project_admin("usr_inconnu", "projet_inconnu")
    assert await reader.active_override("usr_inconnu", "portfolio_dev", "x:y", NOW) is None
    assert not await reader.group_grants("usr_inconnu", "portfolio_dev", "contact:send")
    assert await reader.effective_permissions("usr_inconnu", "portfolio_dev", NOW) == frozenset()


async def test_droits_effectifs_le_deny_retire_une_permission_du_groupe() -> None:
    reader = make_reader()
    permissions = await reader.effective_permissions("usr_bob", "portfolio_dev", NOW)
    assert permissions == {"contact:send", "invoice:read"}


async def test_droits_effectifs_un_allow_expire_n_ajoute_rien() -> None:
    reader = make_reader()
    permissions = await reader.effective_permissions("usr_alice", "portfolio_dev", NOW)
    assert permissions == {"contact:send"}


async def test_droits_effectifs_un_allow_actif_ajoute_la_permission() -> None:
    reader = make_reader()
    reader.overrides[("usr_alice", "portfolio_dev", "invoice:read")] = (OverrideEffect.ALLOW, None)
    permissions = await reader.effective_permissions("usr_alice", "portfolio_dev", NOW)
    assert permissions == {"contact:send", "invoice:read"}
