"""Tests unitaires des maillons, avec le dépôt en mémoire (aucune base de données)."""

from datetime import UTC, datetime, timedelta

import pytest

from control_plane.domain.evaluation import EvaluationContext, Reason
from control_plane.domain.ports import OverrideEffect
from control_plane.evaluation.handlers import (
    GlobalOwnerHandler,
    GroupHandler,
    Handler,
    OverrideHandler,
    ProjectAdminHandler,
)
from control_plane.infrastructure.repositories.memory import InMemoryRightsReader

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


def make_reader() -> InMemoryRightsReader:
    return InMemoryRightsReader(
        global_owners={"usr_owner"},
        project_admins={("usr_dana", "portfolio_dev")},
        memberships={
            ("usr_alice", "portfolio_dev"): "group_visitor",
            ("usr_bob", "portfolio_dev"): "group_dev",
        },
        groups={
            ("portfolio_dev", "group_visitor"): frozenset({"contact:send"}),
            ("portfolio_dev", "group_dev"): frozenset({"contact:send", "invoice:create"}),
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


# --- GlobalOwnerHandler ----------------------------------------------------------


async def test_le_global_owner_est_autorise_partout() -> None:
    decision = await GlobalOwnerHandler().handle(
        ask("usr_owner", "project:delete"), make_reader(), NOW
    )
    assert decision is not None
    assert decision.reason is Reason.ALLOW_GLOBAL_OWNER


async def test_un_non_owner_passe_la_main() -> None:
    assert (
        await GlobalOwnerHandler().handle(ask("usr_alice", "contact:send"), make_reader(), NOW)
        is None
    )


# --- ProjectAdminHandler ---------------------------------------------------------


async def test_l_admin_est_autorise_sur_son_projet() -> None:
    decision = await ProjectAdminHandler().handle(
        ask("usr_dana", "invoice:create"), make_reader(), NOW
    )
    assert decision is not None
    assert decision.reason is Reason.ALLOW_PROJECT_ADMIN


async def test_l_admin_passe_la_main_sur_un_autre_projet() -> None:
    context = ask("usr_dana", "contact:send", project_id="blog_dev")
    assert await ProjectAdminHandler().handle(context, make_reader(), NOW) is None


# --- OverrideHandler -------------------------------------------------------------


async def test_un_deny_actif_refuse() -> None:
    decision = await OverrideHandler().handle(ask("usr_bob", "invoice:create"), make_reader(), NOW)
    assert decision is not None
    assert decision.reason is Reason.DENY_OVERRIDE
    assert not decision.allowed


async def test_un_allow_actif_autorise() -> None:
    reader = make_reader()
    reader.overrides[("usr_alice", "portfolio_dev", "invoice:read")] = (OverrideEffect.ALLOW, None)
    decision = await OverrideHandler().handle(ask("usr_alice", "invoice:read"), reader, NOW)
    assert decision is not None
    assert decision.reason is Reason.ALLOW_OVERRIDE


async def test_un_override_expire_passe_la_main() -> None:
    assert (
        await OverrideHandler().handle(ask("usr_alice", "invoice:read"), make_reader(), NOW) is None
    )


async def test_sans_override_on_passe_la_main() -> None:
    assert (
        await OverrideHandler().handle(ask("usr_alice", "contact:send"), make_reader(), NOW) is None
    )


# --- GroupHandler ----------------------------------------------------------------


async def test_le_groupe_autorise_ses_permissions() -> None:
    decision = await GroupHandler().handle(ask("usr_alice", "contact:send"), make_reader(), NOW)
    assert decision is not None
    assert decision.reason is Reason.ALLOW_GROUP


async def test_une_permission_hors_du_groupe_passe_la_main() -> None:
    assert (
        await GroupHandler().handle(ask("usr_alice", "invoice:create"), make_reader(), NOW) is None
    )


# --- Propriétés communes à tous les maillons -------------------------------------

ALL_HANDLERS: list[Handler] = [
    GlobalOwnerHandler(),
    ProjectAdminHandler(),
    OverrideHandler(),
    GroupHandler(),
]


@pytest.mark.parametrize("handler", ALL_HANDLERS, ids=lambda h: type(h).__name__)
async def test_un_inconnu_fait_passer_la_main_a_chaque_maillon(handler: Handler) -> None:
    # RG-08 : jamais d'erreur, jamais de décision pour un sujet inconnu
    context = ask("usr_inconnu", "contact:send", project_id="projet_inconnu")
    assert await handler.handle(context, make_reader(), NOW) is None


async def test_une_decision_porte_la_question_et_l_instant_de_l_evaluation() -> None:
    context = ask("usr_owner", "project:delete")
    decision = await GlobalOwnerHandler().handle(context, make_reader(), NOW)
    assert decision is not None
    assert decision.context is context
    assert decision.evaluated_at == NOW
