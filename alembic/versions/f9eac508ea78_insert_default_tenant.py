"""insert_default_tenant

Revision ID: f9eac508ea78
Revises: 
Create Date: 2026-06-24 23:52:00.634066

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9eac508ea78'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            slug VARCHAR UNIQUE NOT NULL,
            plan VARCHAR DEFAULT 'free',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    op.execute("""
        INSERT INTO tenants (id, name, slug, plan, is_active)
        VALUES ('default', 'Default Organization', 'default', 'free', TRUE)
        ON CONFLICT (id) DO NOTHING;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM tenants WHERE id = 'default';")

