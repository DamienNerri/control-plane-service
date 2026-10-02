"""Les moteurs « chain » et « sql » doivent donner la même raison à chaque question."""

import itertools
from datetime import UTC, datetime, timedelta

import pytest
from scripts.seed_dev import ADMIN_PERMISSIONS, PROJECTS, USERS
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.evaluation import EvaluationContext, Reason
from control_plane.domain.ports import PermissionEvaluator
from control_plane.evaluation.chain import ChainEvaluator, build_chain
from control_plane.infrastructure.repositories.sql_evaluator import SqlEvaluator
from control_plane.infrastructure.repositories.sqlalchemy_reader import SqlAlchemyRightsReader

pytestmark = pytest.mark.integration

# Toutes les questions possibles sur les données de test, plus des inconnus (RG-08)
SUBJECTS = [*USERS, "usr_inconnu"]
PROJECT_IDS = [*PROJECTS, "projet_inconnu"]
PERMISSIONS = sorted(
    {perm for project in PROJECTS.values() for perm in project.permissions}
    | set(ADMIN_PERMISSIONS)
    | {"x:y"}
)


def engines(session: AsyncSession) -> dict[str, PermissionEvaluator]:
    return {
        "chain": ChainEvaluator(build_chain(), SqlAlchemyRightsReader(session)),
        "sql": SqlEvaluator(session),
    }


@pytest.mark.parametrize(
    "offset",
    [timedelta(0), timedelta(days=-2)],
    ids=["maintenant", "avant-expiration"],
)
async def test_les_deux_moteurs_sont_d_accord_sur_toutes_les_questions(
    seeded_session: AsyncSession, offset: timedelta
) -> None:
    # Il y a deux jours, l'ALLOW temporaire d'Alice était encore actif : on teste les deux cas
    at = datetime.now(UTC) + offset
    chain, sql = engines(seeded_session).values()

    disagreements = []
    for subject, project_id, permission in itertools.product(SUBJECTS, PROJECT_IDS, PERMISSIONS):
        context = EvaluationContext(subject=subject, project_id=project_id, permission=permission)
        by_chain = (await chain.evaluate(context, at)).reason
        by_sql = (await sql.evaluate(context, at)).reason
        if by_chain is not by_sql:
            disagreements.append(f"{subject} {project_id} {permission}: {by_chain} != {by_sql}")

    assert disagreements == []


@pytest.mark.parametrize("engine_name", ["chain", "sql"])
@pytest.mark.parametrize(
    ("subject", "project_id", "permission", "expected"),
    [
        ("usr_owner", "portfolio_dev", "project:delete", Reason.ALLOW_GLOBAL_OWNER),  # 1
        ("usr_alice", "portfolio_dev", "contact:send", Reason.ALLOW_GROUP),  # 2
        ("usr_bob", "portfolio_dev", "invoice:create", Reason.DENY_OVERRIDE),  # 3
        ("usr_inconnu", "portfolio_dev", "contact:send", Reason.DENY_DEFAULT),  # 4
        ("usr_dana", "portfolio_dev", "invoice:create", Reason.ALLOW_PROJECT_ADMIN),  # 6
        ("usr_dana", "blog_dev", "contact:send", Reason.DENY_DEFAULT),  # 7
    ],
)
async def test_scenarios_d_acceptation_sur_un_vrai_postgresql(
    seeded_session: AsyncSession,
    engine_name: str,
    subject: str,
    project_id: str,
    permission: str,
    expected: Reason,
) -> None:
    engine = engines(seeded_session)[engine_name]
    context = EvaluationContext(subject=subject, project_id=project_id, permission=permission)
    assert (await engine.evaluate(context)).reason is expected
