"""roles et privileges

Revision ID: 3ea992214751
Revises: 82c8f49834f3
Create Date: 2026-10-01 23:54:35.017915

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3ea992214751"
down_revision: str | Sequence[str] | None = "82c8f49834f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crée cp_app et cp_readonly (sans mot de passe) et leur donne le minimum."""
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cp_app') THEN
                CREATE ROLE cp_app LOGIN;
            END IF;
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cp_readonly') THEN
                CREATE ROLE cp_readonly LOGIN;
            END IF;
        END
        $$
        """
    )
    op.execute(
        "DO $$ BEGIN EXECUTE 'GRANT CONNECT ON DATABASE ' "
        "|| quote_ident(current_database()) || ' TO cp_app, cp_readonly'; END $$"
    )
    op.execute("GRANT USAGE ON SCHEMA public TO cp_app, cp_readonly")

    # Service : lecture/écriture sur le référentiel et les droits
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON users, projects, groups, permissions, "
        "group_permissions, project_memberships, user_project_overrides TO cp_app"
    )
    # Journal d'audit : ni modifiable ni effaçable par l'application
    op.execute("GRANT SELECT, INSERT ON audit_events TO cp_app")

    # Lecture seule, y compris sur les tables créées par les futures migrations
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO cp_readonly")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO cp_readonly")


def downgrade() -> None:
    """Retire tous les droits puis supprime les deux rôles."""
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT ON TABLES FROM cp_readonly")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM cp_app, cp_readonly")
    op.execute("REVOKE USAGE ON SCHEMA public FROM cp_app, cp_readonly")
    op.execute(
        "DO $$ BEGIN EXECUTE 'REVOKE CONNECT ON DATABASE ' "
        "|| quote_ident(current_database()) || ' FROM cp_app, cp_readonly'; END $$"
    )
    op.execute("DROP ROLE IF EXISTS cp_app")
    op.execute("DROP ROLE IF EXISTS cp_readonly")
