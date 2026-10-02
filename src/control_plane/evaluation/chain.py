"""Assemblage de la chaîne d'évaluation et refus par défaut."""

from collections.abc import Sequence
from datetime import UTC, datetime

from control_plane.domain.evaluation import Decision, EvaluationContext, Reason
from control_plane.domain.ports import RightsReader
from control_plane.evaluation.handlers import (
    GlobalOwnerHandler,
    GroupHandler,
    Handler,
    OverrideHandler,
    ProjectAdminHandler,
)


class EvaluationChain:
    """Interroge les maillons dans l'ordre : le premier qui tranche gagne, sinon refus.

    Sans état : une seule instance sert toutes les requêtes. Le dépôt, lié à la
    session de la requête en cours, est fourni à chaque évaluation.
    """

    __slots__ = ("_handlers",)

    def __init__(self, handlers: Sequence[Handler]) -> None:
        self._handlers = tuple(handlers)

    @property
    def handlers(self) -> tuple[Handler, ...]:
        return self._handlers

    async def evaluate(
        self,
        context: EvaluationContext,
        reader: RightsReader,
        at: datetime | None = None,
    ) -> Decision:
        moment = at if at is not None else datetime.now(UTC)
        for handler in self._handlers:
            decision = await handler.handle(context, reader, moment)
            if decision is not None:
                return decision
        # Refus par défaut : garanti par la structure, impossible à oublier
        return Decision(context=context, reason=Reason.DENY_DEFAULT, evaluated_at=moment)


def build_chain() -> EvaluationChain:
    """Fabrique de la chaîne officielle : l'ordre des maillons est la règle BF-03."""
    return EvaluationChain(
        [
            GlobalOwnerHandler(),
            ProjectAdminHandler(),
            OverrideHandler(),
            GroupHandler(),
        ]
    )
