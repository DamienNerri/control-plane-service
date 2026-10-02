"""Maillons de la chaîne d'évaluation (Chain of Responsibility + Strategy).

Chaque maillon répond à une seule question : il tranche en renvoyant une
Decision, ou passe la main en renvoyant None. Il ne connaît ni ses voisins
ni l'ordre de la chaîne, qui est assemblée par build_chain (CP-16).
"""

from datetime import datetime
from typing import Protocol

from control_plane.domain.evaluation import Decision, EvaluationContext, Reason
from control_plane.domain.ports import OverrideEffect, RightsReader


class Handler(Protocol):
    """Interface commune à tous les maillons."""

    async def handle(
        self, context: EvaluationContext, reader: RightsReader, at: datetime
    ) -> Decision | None:
        """Renvoie une Decision si ce maillon tranche, sinon None."""
        ...


class GlobalOwnerHandler:
    """Maillon 1 : le Global Owner a tous les droits, sur tous les projets."""

    async def handle(
        self, context: EvaluationContext, reader: RightsReader, at: datetime
    ) -> Decision | None:
        if await reader.is_global_owner(context.subject):
            return Decision(context=context, reason=Reason.ALLOW_GLOBAL_OWNER, evaluated_at=at)
        return None


class ProjectAdminHandler:
    """Maillon 2 : l'admin d'un projet a tous les droits sur ce projet, et lui seul."""

    async def handle(
        self, context: EvaluationContext, reader: RightsReader, at: datetime
    ) -> Decision | None:
        if await reader.is_project_admin(context.subject, context.project_id):
            return Decision(context=context, reason=Reason.ALLOW_PROJECT_ADMIN, evaluated_at=at)
        return None


_OVERRIDE_REASONS = {
    OverrideEffect.DENY: Reason.DENY_OVERRIDE,
    OverrideEffect.ALLOW: Reason.ALLOW_OVERRIDE,
}


class OverrideHandler:
    """Maillons 3 et 4 : une exception individuelle non expirée tranche, dans un sens ou l'autre.

    La clé primaire (utilisateur, projet, permission) garantit qu'il existe au plus
    un override : une seule requête suffit pour les deux effets.
    """

    async def handle(
        self, context: EvaluationContext, reader: RightsReader, at: datetime
    ) -> Decision | None:
        effect = await reader.active_override(
            context.subject, context.project_id, context.permission, at
        )
        if effect is None:
            return None
        return Decision(context=context, reason=_OVERRIDE_REASONS[effect], evaluated_at=at)


class GroupHandler:
    """Maillon 5 : le groupe de l'utilisateur dans ce projet contient la permission."""

    async def handle(
        self, context: EvaluationContext, reader: RightsReader, at: datetime
    ) -> Decision | None:
        if await reader.group_grants(context.subject, context.project_id, context.permission):
            return Decision(context=context, reason=Reason.ALLOW_GROUP, evaluated_at=at)
        return None
