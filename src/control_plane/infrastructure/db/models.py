"""Modèles ORM des 9 tables, conformes au document « Base de données » v1.1."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    String,
    Text,
    Uuid,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.infrastructure.db.base import Base

SLUG_PATTERN = "^[a-z0-9_-]{2,64}$"
PERMISSION_PATTERN = "^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$"


# --- Référentiel ---------------------------------------------------------------


class User(Base):
    """Utilisateur référencé par le `sub` de l'Identity Provider (aucun email)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    subject: Mapped[str] = mapped_column(String(255), unique=True)
    is_global_owner: Mapped[bool] = mapped_column(Boolean, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (CheckConstraint(f"id ~ '{SLUG_PATTERN}'", name="id_slug"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProjectAdmin(Base):
    """Admin de projet : tous les droits sur un projet, nommé par le Global Owner."""

    __tablename__ = "project_admins"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Permission(Base):
    """Action protégée d'un projet ; les `admin:*` sont créées avec le projet (RG-13)."""

    __tablename__ = "permissions"
    __table_args__ = (CheckConstraint(f"id ~ '{PERMISSION_PATTERN}'", name="id_format"),)

    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str | None] = mapped_column(Text)


class Group(Base):
    """Ensemble de permissions d'un projet, utilisable dans ce projet uniquement."""

    __tablename__ = "groups"
    __table_args__ = (CheckConstraint(f"id ~ '{SLUG_PATTERN}'", name="id_slug"),)

    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)


# --- Tables de liaison (clés composites : aucun lien entre deux projets) ----------


class GroupPermission(Base):
    __tablename__ = "group_permissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "group_id"],
            ["groups.project_id", "groups.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["project_id", "permission_id"],
            ["permissions.project_id", "permissions.id"],
            ondelete="CASCADE",
        ),
        Index("ix_group_permissions_project_permission", "project_id", "permission_id"),
    )

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    group_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    permission_id: Mapped[str] = mapped_column(String(64), primary_key=True)


class ProjectMembership(Base):
    """Appartenance : un seul groupe par utilisateur et par projet (RG-02)."""

    __tablename__ = "project_memberships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "group_id"],
            ["groups.project_id", "groups.id"],
            ondelete="CASCADE",
        ),
        Index("ix_project_memberships_project_group", "project_id", "group_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserProjectOverride(Base):
    """Exception individuelle ALLOW/DENY, avec motif et expiration (RG-04)."""

    __tablename__ = "user_project_overrides"
    __table_args__ = (
        CheckConstraint("length(trim(reason)) > 0", name="reason_not_blank"),
        ForeignKeyConstraint(
            ["project_id", "permission_id"],
            ["permissions.project_id", "permissions.id"],
            ondelete="CASCADE",
        ),
        Index("ix_user_project_overrides_project_permission", "project_id", "permission_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    effect: Mapped[str] = mapped_column(Enum("ALLOW", "DENY", name="override_effect"))
    reason: Mapped[str] = mapped_column(String(500))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Audit -----------------------------------------------------------------------


class AuditEvent(Base):
    """Journal des modifications : l'application n'a que INSERT et SELECT dessus."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_target", "target_type", "target_id"),
        Index("ix_audit_events_project_occurred", "project_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # Sans clé étrangère : l'historique survit à la suppression du projet
    project_id: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[str] = mapped_column(String(255))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    request_id: Mapped[str | None] = mapped_column(String(64))
