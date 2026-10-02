"""Ports du domaine : ce dont l'évaluation a besoin pour lire les droits.

Le domaine décrit le besoin ; l'infrastructure fournit l'implémentation
(SQLAlchemy en production, mémoire dans les tests).
"""

from datetime import datetime
from enum import StrEnum
from typing import Protocol


class OverrideEffect(StrEnum):
    """Effet d'une exception individuelle."""

    ALLOW = "ALLOW"
    DENY = "DENY"


class RightsReader(Protocol):
    """Lecture des droits, une méthode par maillon de la chaîne d'évaluation.

    `at` est l'instant de l'évaluation : un override dont `expires_at <= at` est
    expiré. Le recevoir en paramètre, plutôt que lire l'horloge, rend les tests
    déterministes.

    Un sujet, un projet ou une permission inconnus ne lèvent jamais d'erreur :
    les méthodes répondent simplement « non » ou « rien » (RG-08).
    """

    async def is_global_owner(self, subject: str) -> bool:
        """Maillon 1 : le sujet est-il Global Owner ?"""
        ...

    async def is_project_admin(self, subject: str, project_id: str) -> bool:
        """Maillon 2 : le sujet est-il admin de ce projet ?"""
        ...

    async def active_override(
        self, subject: str, project_id: str, permission: str, at: datetime
    ) -> OverrideEffect | None:
        """Maillons 3 et 4 : effet de l'override non expiré, ou None s'il n'y en a pas."""
        ...

    async def group_grants(self, subject: str, project_id: str, permission: str) -> bool:
        """Maillon 5 : le groupe du sujet dans ce projet contient-il la permission ?"""
        ...

    async def effective_permissions(
        self, subject: str, project_id: str, at: datetime
    ) -> frozenset[str]:
        """Droits d'un membre : son groupe, plus ses ALLOW actifs, moins ses DENY actifs.

        Ne tient pas compte des statuts Global Owner et admin de projet :
        l'appelant les traite à part.
        """
        ...
