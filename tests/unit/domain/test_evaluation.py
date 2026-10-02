"""Tests des objets du domaine de l'évaluation."""

import dataclasses
from datetime import UTC, datetime

import pytest

from control_plane.domain.evaluation import Decision, EvaluationContext, Reason

ALLOWING = {
    Reason.ALLOW_GLOBAL_OWNER,
    Reason.ALLOW_PROJECT_ADMIN,
    Reason.ALLOW_OVERRIDE,
    Reason.ALLOW_GROUP,
}


def make_context(**overrides: str) -> EvaluationContext:
    values = {
        "subject": "usr_alice",
        "project_id": "portfolio_dev",
        "permission": "contact:send",
    } | overrides
    return EvaluationContext(**values)


# --- Reason ----------------------------------------------------------------------


@pytest.mark.parametrize("reason", list(Reason))
def test_seules_les_raisons_allow_autorisent(reason: Reason) -> None:
    assert reason.allowed is (reason in ALLOWING)


@pytest.mark.parametrize("reason", list(Reason))
def test_chaque_raison_a_une_description(reason: Reason) -> None:
    assert reason.description


def test_une_raison_se_serialise_en_texte() -> None:
    assert Reason.DENY_OVERRIDE == "DENY_OVERRIDE"
    assert f"{Reason.ALLOW_PROJECT_ADMIN}" == "ALLOW_PROJECT_ADMIN"


# --- EvaluationContext -----------------------------------------------------------


def test_un_contexte_valide_est_accepte() -> None:
    context = make_context()
    assert context.permission == "contact:send"


def test_une_permission_admin_est_un_contexte_valide() -> None:
    assert make_context(permission="admin:member_assign").permission == "admin:member_assign"


@pytest.mark.parametrize(
    "permission",
    [
        "",
        "invoice",
        "Invoice:create",
        "invoice:",
        ":create",
        "invoice:create:pdf",
        "invoice:create ",
        "1nvoice:create",
        "a:" + "b" * 70,
    ],
)
def test_une_permission_mal_formee_est_refusee(permission: str) -> None:
    with pytest.raises(ValueError, match="permission"):
        make_context(permission=permission)


@pytest.mark.parametrize("project_id", ["", "p", "Portfolio", "portfolio dev", "x" * 65])
def test_un_projet_mal_forme_est_refuse(project_id: str) -> None:
    with pytest.raises(ValueError, match="project_id"):
        make_context(project_id=project_id)


@pytest.mark.parametrize("subject", ["", "u" * 256])
def test_un_sujet_vide_ou_trop_long_est_refuse(subject: str) -> None:
    with pytest.raises(ValueError, match="subject"):
        make_context(subject=subject)


def test_un_projet_inconnu_bien_forme_reste_valide() -> None:
    # RG-08 : c'est la chaîne qui répondra DENY_DEFAULT, pas une erreur
    assert make_context(project_id="projet_inexistant").project_id == "projet_inexistant"


# --- Decision --------------------------------------------------------------------


@pytest.mark.parametrize("reason", list(Reason))
def test_une_decision_deduit_allowed_de_sa_raison(reason: Reason) -> None:
    decision = Decision(context=make_context(), reason=reason)
    assert decision.allowed is reason.allowed
    assert decision.description == reason.description


def test_une_decision_est_horodatee_en_utc() -> None:
    decision = Decision(context=make_context(), reason=Reason.DENY_DEFAULT)
    assert decision.evaluated_at.tzinfo is UTC


def test_une_decision_sans_fuseau_horaire_est_refusee() -> None:
    with pytest.raises(ValueError, match="fuseau"):
        Decision(
            context=make_context(),
            reason=Reason.DENY_DEFAULT,
            evaluated_at=datetime(2026, 10, 1, 19, 0),
        )


def test_une_decision_est_immuable() -> None:
    decision = Decision(context=make_context(), reason=Reason.DENY_DEFAULT)
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.reason = Reason.ALLOW_GROUP  # type: ignore[misc]
