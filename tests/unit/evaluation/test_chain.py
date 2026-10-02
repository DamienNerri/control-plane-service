"""Tests de la chaîne complète : scénarios, priorités, court-circuit et refus par défaut."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from control_plane.domain.evaluation import EvaluationContext, Reason
from control_plane.domain.ports import OverrideEffect
from control_plane.evaluation.chain import EvaluationChain, build_chain
from control_plane.evaluation.handlers import (
    GlobalOwnerHandler,
    GroupHandler,
    OverrideHandler,
    ProjectAdminHandler,
)
from control_plane.infrastructure.repositories.memory import InMemoryRightsReader

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


def make_reader() -> InMemoryRightsReader:
    """Mêmes données que scripts/seed_dev.py."""
    return InMemoryRightsReader(
        global_owners={"usr_owner"},
        project_admins={("usr_dana", "portfolio_dev")},
        memberships={
            ("usr_alice", "portfolio_dev"): "group_visitor",
            ("usr_bob", "portfolio_dev"): "group_dev",
            ("usr_eric", "portfolio_dev"): "group_manager",
        },
        groups={
            ("portfolio_dev", "group_visitor"): frozenset({"contact:send"}),
            ("portfolio_dev", "group_dev"): frozenset(
                {"contact:send", "invoice:create", "invoice:read"}
            ),
            ("portfolio_dev", "group_manager"): frozenset({"admin:member_assign", "contact:send"}),
            ("blog_dev", "group_visitor"): frozenset({"contact:send"}),
        },
        overrides={
            ("usr_bob", "portfolio_dev", "invoice:create"): (OverrideEffect.DENY, None),
            ("usr_alice", "portfolio_dev", "invoice:read"): (
                OverrideEffect.ALLOW,
                NOW - timedelta(days=1),
            ),
        },
    )


def ask(subject: str, permission: str, project_id: str = "portfolio_dev") -> EvaluationContext:
    return EvaluationContext(subject=subject, project_id=project_id, permission=permission)


# --- Scénarios d'acceptation (cahier des charges v1.1) ---------------------------


@pytest.mark.parametrize(
    ("subject", "project_id", "permission", "expected"),
    [
        ("usr_owner", "portfolio_dev", "project:delete", Reason.ALLOW_GLOBAL_OWNER),  # 1
        ("usr_alice", "portfolio_dev", "contact:send", Reason.ALLOW_GROUP),  # 2
        ("usr_bob", "portfolio_dev", "invoice:create", Reason.DENY_OVERRIDE),  # 3
        ("usr_inconnu", "portfolio_dev", "contact:send", Reason.DENY_DEFAULT),  # 4
        ("usr_dana", "portfolio_dev", "invoice:create", Reason.ALLOW_PROJECT_ADMIN),  # 6
        ("usr_dana", "blog_dev", "contact:send", Reason.DENY_DEFAULT),  # 7
        ("usr_alice", "portfolio_dev", "invoice:read", Reason.DENY_DEFAULT),  # ALLOW expiré
        ("usr_eric", "portfolio_dev", "admin:member_assign", Reason.ALLOW_GROUP),
        ("usr_eric", "portfolio_dev", "invoice:create", Reason.DENY_DEFAULT),
        ("usr_alice", "projet_inconnu", "x:y", Reason.DENY_DEFAULT),  # RG-08
    ],
)
async def test_scenarios(subject: str, project_id: str, permission: str, expected: Reason) -> None:
    decision = await build_chain().evaluate(
        ask(subject, permission, project_id), make_reader(), NOW
    )
    assert decision.reason is expected
    assert decision.allowed is expected.allowed


# --- Priorités entre les règles ---------------------------------------------------


async def test_un_deny_individuel_ne_s_applique_pas_au_global_owner() -> None:
    reader = make_reader()
    reader.overrides[("usr_owner", "portfolio_dev", "project:delete")] = (OverrideEffect.DENY, None)
    decision = await build_chain().evaluate(ask("usr_owner", "project:delete"), reader, NOW)
    assert decision.reason is Reason.ALLOW_GLOBAL_OWNER


async def test_un_deny_individuel_ne_s_applique_pas_a_l_admin_du_projet() -> None:
    reader = make_reader()
    reader.overrides[("usr_dana", "portfolio_dev", "invoice:create")] = (OverrideEffect.DENY, None)
    decision = await build_chain().evaluate(ask("usr_dana", "invoice:create"), reader, NOW)
    assert decision.reason is Reason.ALLOW_PROJECT_ADMIN


async def test_un_allow_individuel_donne_une_permission_absente_du_groupe() -> None:
    reader = make_reader()
    reader.overrides[("usr_alice", "portfolio_dev", "invoice:create")] = (
        OverrideEffect.ALLOW,
        None,
    )
    decision = await build_chain().evaluate(ask("usr_alice", "invoice:create"), reader, NOW)
    assert decision.reason is Reason.ALLOW_OVERRIDE


# --- Court-circuit : on s'arrête au premier maillon qui tranche -----------------


@dataclass
class SpyReader:
    """Enveloppe un dépôt et note chaque question posée."""

    inner: InMemoryRightsReader
    calls: list[str] = field(default_factory=list)

    async def is_global_owner(self, subject: str) -> bool:
        self.calls.append("is_global_owner")
        return await self.inner.is_global_owner(subject)

    async def is_project_admin(self, subject: str, project_id: str) -> bool:
        self.calls.append("is_project_admin")
        return await self.inner.is_project_admin(subject, project_id)

    async def active_override(
        self, subject: str, project_id: str, permission: str, at: datetime
    ) -> OverrideEffect | None:
        self.calls.append("active_override")
        return await self.inner.active_override(subject, project_id, permission, at)

    async def group_grants(self, subject: str, project_id: str, permission: str) -> bool:
        self.calls.append("group_grants")
        return await self.inner.group_grants(subject, project_id, permission)

    async def effective_permissions(
        self, subject: str, project_id: str, at: datetime
    ) -> frozenset[str]:
        self.calls.append("effective_permissions")
        return await self.inner.effective_permissions(subject, project_id, at)


ALL_STEPS = ["is_global_owner", "is_project_admin", "active_override", "group_grants"]


@pytest.mark.parametrize(
    ("subject", "permission", "expected_calls"),
    [
        ("usr_owner", "project:delete", ALL_STEPS[:1]),
        ("usr_dana", "invoice:create", ALL_STEPS[:2]),
        ("usr_bob", "invoice:create", ALL_STEPS[:3]),
        ("usr_alice", "contact:send", ALL_STEPS),
        ("usr_inconnu", "contact:send", ALL_STEPS),
    ],
)
async def test_la_chaine_s_arrete_au_premier_maillon_qui_tranche(
    subject: str, permission: str, expected_calls: list[str]
) -> None:
    spy = SpyReader(make_reader())
    await build_chain().evaluate(ask(subject, permission), spy, NOW)
    assert spy.calls == expected_calls


# --- Refus par défaut, horodatage et erreurs -------------------------------------


async def test_une_chaine_vide_refuse_tout() -> None:
    decision = await EvaluationChain([]).evaluate(ask("usr_owner", "project:delete"), make_reader())
    assert decision.reason is Reason.DENY_DEFAULT


async def test_sans_instant_fourni_la_decision_est_horodatee_maintenant() -> None:
    before = datetime.now(UTC)
    decision = await build_chain().evaluate(ask("usr_alice", "contact:send"), make_reader())
    assert before <= decision.evaluated_at <= datetime.now(UTC)


async def test_une_panne_du_depot_remonte_au_lieu_de_devenir_un_refus() -> None:
    # Une panne n'est pas une décision : l'API répondra 503, le SDK refusera (fail-closed)
    class BrokenReader(InMemoryRightsReader):
        async def is_global_owner(self, subject: str) -> bool:
            raise ConnectionError("base injoignable")

    with pytest.raises(ConnectionError):
        await build_chain().evaluate(ask("usr_alice", "contact:send"), BrokenReader(), NOW)


def test_l_ordre_officiel_des_maillons() -> None:
    # Verrouille la règle BF-03 : changer cet ordre doit être une décision consciente
    assert [type(h) for h in build_chain().handlers] == [
        GlobalOwnerHandler,
        ProjectAdminHandler,
        OverrideHandler,
        GroupHandler,
    ]
