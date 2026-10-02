"""Objets du domaine de l'évaluation : la question, la raison, la réponse.

Python pur : aucun import de base de données ni de framework web.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

SUBJECT_MAX_LENGTH = 255
PERMISSION_MAX_LENGTH = 64
PROJECT_ID_PATTERN = re.compile(r"[a-z0-9_-]{2,64}")
PERMISSION_PATTERN = re.compile(r"[a-z][a-z0-9_]*:[a-z][a-z0-9_]*")


class Reason(StrEnum):
    """Règle qui a tranché, dans l'ordre de la chaîne d'évaluation."""

    ALLOW_GLOBAL_OWNER = "ALLOW_GLOBAL_OWNER"
    ALLOW_PROJECT_ADMIN = "ALLOW_PROJECT_ADMIN"
    DENY_OVERRIDE = "DENY_OVERRIDE"
    ALLOW_OVERRIDE = "ALLOW_OVERRIDE"
    ALLOW_GROUP = "ALLOW_GROUP"
    DENY_DEFAULT = "DENY_DEFAULT"

    @property
    def allowed(self) -> bool:
        """Vrai si cette raison autorise l'action."""
        return self in _ALLOWING_REASONS

    @property
    def description(self) -> str:
        """Explication lisible, renvoyée par l'API avec chaque décision."""
        return _DESCRIPTIONS[self]


_ALLOWING_REASONS = frozenset(
    {
        Reason.ALLOW_GLOBAL_OWNER,
        Reason.ALLOW_PROJECT_ADMIN,
        Reason.ALLOW_OVERRIDE,
        Reason.ALLOW_GROUP,
    }
)

_DESCRIPTIONS = {
    Reason.ALLOW_GLOBAL_OWNER: "L'utilisateur est Global Owner",
    Reason.ALLOW_PROJECT_ADMIN: "L'utilisateur est admin de ce projet",
    Reason.DENY_OVERRIDE: "Refus individuel explicite",
    Reason.ALLOW_OVERRIDE: "Autorisation individuelle explicite",
    Reason.ALLOW_GROUP: "Le groupe de l'utilisateur contient la permission",
    Reason.DENY_DEFAULT: "Aucune règle ne s'applique",
}


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    """La question : ce sujet a-t-il cette permission sur ce projet ?

    Un contexte mal formé est refusé dès sa création. Un projet ou une
    permission bien formés mais inconnus restent valides : la chaîne
    répondra DENY_DEFAULT (RG-08).
    """

    subject: str
    project_id: str
    permission: str

    def __post_init__(self) -> None:
        # Les messages ne recopient jamais la valeur reçue : elle pourrait finir dans un log
        if not 0 < len(self.subject) <= SUBJECT_MAX_LENGTH:
            raise ValueError("subject doit contenir entre 1 et 255 caractères")
        if not PROJECT_ID_PATTERN.fullmatch(self.project_id):
            raise ValueError("project_id invalide : slug de 2 à 64 caractères attendu")
        if len(self.permission) > PERMISSION_MAX_LENGTH or not PERMISSION_PATTERN.fullmatch(
            self.permission
        ):
            raise ValueError("permission invalide : format ressource:action attendu")


@dataclass(frozen=True, slots=True)
class Decision:
    """La réponse : autorisé ou non, et la règle qui a tranché.

    `allowed` est déduit de la raison : une décision « ALLOW_GROUP mais refusé »
    est impossible à construire.
    """

    context: EvaluationContext
    reason: Reason
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at doit porter un fuseau horaire")

    @property
    def allowed(self) -> bool:
        return self.reason.allowed

    @property
    def description(self) -> str:
        return self.reason.description
