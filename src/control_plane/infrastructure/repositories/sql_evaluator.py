"""Moteur « sql » : toute la chaîne d'évaluation en une seule requête PostgreSQL."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.evaluation import Decision, EvaluationContext, Reason

if TYPE_CHECKING:
    from control_plane.domain.ports import PermissionEvaluator

# Même ordre que la chaîne : Owner, admin de projet, override, groupe, refus.
# Requête du document « Base de données » v1.1, avec :at à la place de now()
# pour que les deux moteurs évaluent l'expiration au même instant.
_EVALUATION_SQL = text(
    """
    WITH ctx AS (
        SELECT u.id, u.is_global_owner
        FROM users u
        WHERE u.subject = :subject
    ),
    padm AS (
        SELECT 1
        FROM project_admins pa
        JOIN ctx ON pa.user_id = ctx.id
        WHERE pa.project_id = :project_id
    ),
    ovr AS (
        SELECT o.effect::text AS effect
        FROM user_project_overrides o
        JOIN ctx ON o.user_id = ctx.id
        WHERE o.project_id = :project_id
          AND o.permission_id = :permission
          AND (o.expires_at IS NULL OR o.expires_at > :at)
    ),
    grp AS (
        SELECT 1
        FROM project_memberships pm
        JOIN ctx ON pm.user_id = ctx.id
        JOIN group_permissions gp
          ON gp.project_id = pm.project_id AND gp.group_id = pm.group_id
        WHERE pm.project_id = :project_id
          AND gp.permission_id = :permission
    )
    SELECT CASE
        WHEN (SELECT is_global_owner FROM ctx) THEN 'ALLOW_GLOBAL_OWNER'
        WHEN EXISTS (SELECT 1 FROM padm) THEN 'ALLOW_PROJECT_ADMIN'
        WHEN (SELECT effect FROM ovr) = 'DENY' THEN 'DENY_OVERRIDE'
        WHEN (SELECT effect FROM ovr) = 'ALLOW' THEN 'ALLOW_OVERRIDE'
        WHEN EXISTS (SELECT 1 FROM grp) THEN 'ALLOW_GROUP'
        ELSE 'DENY_DEFAULT'
    END AS reason
    """
)


class SqlEvaluator:
    """Un seul aller-retour avec PostgreSQL par vérification."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def evaluate(self, context: EvaluationContext, at: datetime | None = None) -> Decision:
        moment = at if at is not None else datetime.now(UTC)
        reason = await self._session.scalar(
            _EVALUATION_SQL,
            {
                "subject": context.subject,
                "project_id": context.project_id,
                "permission": context.permission,
                "at": moment,
            },
        )
        return Decision(context=context, reason=Reason(reason), evaluated_at=moment)


if TYPE_CHECKING:
    # Vérifié par mypy uniquement : SqlEvaluator respecte le port PermissionEvaluator
    def _conformance_check(session: AsyncSession) -> PermissionEvaluator:
        return SqlEvaluator(session)
