"""admins de projet

Revision ID: 83e90ceafe05
Revises: f0a7c87fd76a
Create Date: 2026-10-02 15:32:34.932350

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "83e90ceafe05"
down_revision: str | Sequence[str] | None = "f0a7c87fd76a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_admins",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", "project_id", name="pk_project_admins"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_project_admins_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_admins_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_project_admins_created_by_users",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_project_admins_project_id", "project_admins", ["project_id"])

    # Le service nomme et retire des admins, il ne modifie jamais une ligne existante
    op.execute("GRANT SELECT, INSERT, DELETE ON project_admins TO cp_app")


def downgrade() -> None:
    op.drop_index("ix_project_admins_project_id", table_name="project_admins")
    op.drop_table("project_admins")
