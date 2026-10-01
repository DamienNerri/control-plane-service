"""schema initial

Revision ID: 82c8f49834f3
Revises:
Create Date: 2026-10-01 23:49:04.478470

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "82c8f49834f3"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "groups",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.CheckConstraint("id ~ '^[a-z0-9_-]{2,64}$'", name=op.f("ck_groups_id_slug")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_groups")),
    )
    op.create_table(
        "permissions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "id ~ '^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$'", name=op.f("ck_permissions_id_format")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permissions")),
    )
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("id ~ '^[a-z0-9_-]{2,64}$'", name=op.f("ck_projects_id_slug")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("is_global_owner", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("subject", name=op.f("uq_users_subject")),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=255), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_audit_events_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(op.f("ix_audit_events_actor_id"), "audit_events", ["actor_id"], unique=False)
    op.create_index(
        op.f("ix_audit_events_occurred_at"), "audit_events", ["occurred_at"], unique=False
    )
    op.create_index(
        "ix_audit_events_target", "audit_events", ["target_type", "target_id"], unique=False
    )
    op.create_table(
        "group_permissions",
        sa.Column("group_id", sa.String(length=64), nullable=False),
        sa.Column("permission_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name=op.f("fk_group_permissions_group_id_groups"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name=op.f("fk_group_permissions_permission_id_permissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("group_id", "permission_id", name=op.f("pk_group_permissions")),
    )
    op.create_index(
        op.f("ix_group_permissions_permission_id"),
        "group_permissions",
        ["permission_id"],
        unique=False,
    )
    op.create_table(
        "project_memberships",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("group_id", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name=op.f("fk_project_memberships_group_id_groups"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_memberships_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_project_memberships_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "project_id", name=op.f("pk_project_memberships")),
    )
    op.create_index(
        op.f("ix_project_memberships_group_id"), "project_memberships", ["group_id"], unique=False
    )
    op.create_index(
        op.f("ix_project_memberships_project_id"),
        "project_memberships",
        ["project_id"],
        unique=False,
    )
    op.create_table(
        "user_project_overrides",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("permission_id", sa.String(length=64), nullable=False),
        sa.Column("effect", sa.Enum("ALLOW", "DENY", name="override_effect"), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(reason)) > 0", name=op.f("ck_user_project_overrides_reason_not_blank")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_user_project_overrides_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name=op.f("fk_user_project_overrides_permission_id_permissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_user_project_overrides_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_project_overrides_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "project_id", "permission_id", name=op.f("pk_user_project_overrides")
        ),
    )
    op.create_index(
        op.f("ix_user_project_overrides_permission_id"),
        "user_project_overrides",
        ["permission_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_project_overrides_project_id"),
        "user_project_overrides",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_user_project_overrides_project_id"), table_name="user_project_overrides")
    op.drop_index(
        op.f("ix_user_project_overrides_permission_id"), table_name="user_project_overrides"
    )
    op.drop_table("user_project_overrides")
    sa.Enum(name="override_effect").drop(op.get_bind(), checkfirst=True)
    op.drop_index(op.f("ix_project_memberships_project_id"), table_name="project_memberships")
    op.drop_index(op.f("ix_project_memberships_group_id"), table_name="project_memberships")
    op.drop_table("project_memberships")
    op.drop_index(op.f("ix_group_permissions_permission_id"), table_name="group_permissions")
    op.drop_table("group_permissions")
    op.drop_index("ix_audit_events_target", table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_occurred_at"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_actor_id"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("users")
    op.drop_table("projects")
    op.drop_table("permissions")
    op.drop_table("groups")
