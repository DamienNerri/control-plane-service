"""schema multi-projets

Revision ID: f0a7c87fd76a
Revises: 3ea992214751
Create Date: 2026-10-02 15:28:02.133600

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f0a7c87fd76a"
down_revision: str | Sequence[str] | None = "3ea992214751"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RIGHTS_TABLES = (
    "group_permissions, project_memberships, user_project_overrides, groups, permissions"
)

ADMIN_PERMISSIONS = {
    "admin:permission_manage": "Déclarer ou supprimer une permission du projet",
    "admin:group_manage": "Créer, modifier ou supprimer un groupe",
    "admin:member_assign": "Ajouter ou retirer un membre, changer son groupe",
    "admin:override_manage": "Poser ou retirer un override",
    "admin:audit_read": "Consulter le journal d'audit du projet",
}


def upgrade() -> None:
    # 1. Vider les tables de droits (données de dev uniquement)
    op.execute(f"TRUNCATE TABLE {RIGHTS_TABLES}")

    # 2. Retirer tout ce qui s'appuie sur les anciennes clés primaires
    op.drop_constraint(
        "fk_group_permissions_group_id_groups", "group_permissions", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_group_permissions_permission_id_permissions",
        "group_permissions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_project_memberships_group_id_groups", "project_memberships", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_user_project_overrides_permission_id_permissions",
        "user_project_overrides",
        type_="foreignkey",
    )
    op.drop_index("ix_group_permissions_permission_id", table_name="group_permissions")
    op.drop_index("ix_project_memberships_group_id", table_name="project_memberships")
    op.drop_index("ix_project_memberships_project_id", table_name="project_memberships")
    op.drop_index("ix_user_project_overrides_permission_id", table_name="user_project_overrides")
    op.drop_index("ix_user_project_overrides_project_id", table_name="user_project_overrides")
    op.drop_constraint("pk_group_permissions", "group_permissions", type_="primary")
    op.drop_constraint("pk_groups", "groups", type_="primary")
    op.drop_constraint("pk_permissions", "permissions", type_="primary")

    # 3. Rattacher permissions et groupes à un projet
    for table in ("permissions", "groups", "group_permissions"):
        op.add_column(table, sa.Column("project_id", sa.String(64), nullable=False))

    op.create_primary_key("pk_permissions", "permissions", ["project_id", "id"])
    op.create_primary_key("pk_groups", "groups", ["project_id", "id"])
    op.create_primary_key(
        "pk_group_permissions", "group_permissions", ["project_id", "group_id", "permission_id"]
    )
    op.create_foreign_key(
        "fk_permissions_project_id_projects",
        "permissions",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_groups_project_id_projects",
        "groups",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 4. Clés étrangères composites : aucun lien ne peut traverser deux projets (RG-09)
    op.create_foreign_key(
        "fk_group_permissions_project_id_groups",
        "group_permissions",
        "groups",
        ["project_id", "group_id"],
        ["project_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_group_permissions_project_id_permissions",
        "group_permissions",
        "permissions",
        ["project_id", "permission_id"],
        ["project_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_project_memberships_project_id_groups",
        "project_memberships",
        "groups",
        ["project_id", "group_id"],
        ["project_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_user_project_overrides_project_id_permissions",
        "user_project_overrides",
        "permissions",
        ["project_id", "permission_id"],
        ["project_id", "id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_group_permissions_project_permission",
        "group_permissions",
        ["project_id", "permission_id"],
    )
    op.create_index(
        "ix_project_memberships_project_group",
        "project_memberships",
        ["project_id", "group_id"],
    )
    op.create_index(
        "ix_user_project_overrides_project_permission",
        "user_project_overrides",
        ["project_id", "permission_id"],
    )

    # 5. Journal d'audit filtrable par projet (sans clé étrangère : survit au projet)
    op.add_column("audit_events", sa.Column("project_id", sa.String(64), nullable=True))
    op.create_index(
        "ix_audit_events_project_occurred", "audit_events", ["project_id", "occurred_at"]
    )

    # 6. Les 5 permissions d'administration pour chaque projet existant (RG-13)
    permissions = sa.table(
        "permissions",
        sa.column("project_id", sa.String),
        sa.column("id", sa.String),
        sa.column("description", sa.Text),
    )
    project_ids = op.get_bind().execute(sa.text("SELECT id FROM projects")).scalars().all()
    rows = [
        {"project_id": project_id, "id": perm_id, "description": description}
        for project_id in project_ids
        for perm_id, description in ADMIN_PERMISSIONS.items()
    ]
    if rows:
        op.bulk_insert(permissions, rows)


def downgrade() -> None:
    op.drop_index("ix_audit_events_project_occurred", table_name="audit_events")
    op.drop_column("audit_events", "project_id")

    op.execute(f"TRUNCATE TABLE {RIGHTS_TABLES}")

    op.drop_index(
        "ix_user_project_overrides_project_permission", table_name="user_project_overrides"
    )
    op.drop_index("ix_project_memberships_project_group", table_name="project_memberships")
    op.drop_index("ix_group_permissions_project_permission", table_name="group_permissions")
    for name, table in (
        ("fk_user_project_overrides_project_id_permissions", "user_project_overrides"),
        ("fk_project_memberships_project_id_groups", "project_memberships"),
        ("fk_group_permissions_project_id_permissions", "group_permissions"),
        ("fk_group_permissions_project_id_groups", "group_permissions"),
        ("fk_groups_project_id_projects", "groups"),
        ("fk_permissions_project_id_projects", "permissions"),
    ):
        op.drop_constraint(name, table, type_="foreignkey")
    op.drop_constraint("pk_group_permissions", "group_permissions", type_="primary")
    op.drop_constraint("pk_groups", "groups", type_="primary")
    op.drop_constraint("pk_permissions", "permissions", type_="primary")
    for table in ("group_permissions", "groups", "permissions"):
        op.drop_column(table, "project_id")

    op.create_primary_key("pk_permissions", "permissions", ["id"])
    op.create_primary_key("pk_groups", "groups", ["id"])
    op.create_primary_key(
        "pk_group_permissions", "group_permissions", ["group_id", "permission_id"]
    )
    op.create_foreign_key(
        "fk_group_permissions_group_id_groups",
        "group_permissions",
        "groups",
        ["group_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_group_permissions_permission_id_permissions",
        "group_permissions",
        "permissions",
        ["permission_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_project_memberships_group_id_groups",
        "project_memberships",
        "groups",
        ["group_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_user_project_overrides_permission_id_permissions",
        "user_project_overrides",
        "permissions",
        ["permission_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_group_permissions_permission_id", "group_permissions", ["permission_id"])
    op.create_index("ix_project_memberships_group_id", "project_memberships", ["group_id"])
    op.create_index("ix_project_memberships_project_id", "project_memberships", ["project_id"])
    op.create_index(
        "ix_user_project_overrides_permission_id", "user_project_overrides", ["permission_id"]
    )
    op.create_index(
        "ix_user_project_overrides_project_id", "user_project_overrides", ["project_id"]
    )
