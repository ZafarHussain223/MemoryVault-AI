"""Persist explicit, owner-scoped knowledge relationships."""
from alembic import op
from app.db import Relationship
revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    # The historical initial migration creates current metadata for empty installs.
    Relationship.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    op.drop_table('relationships')
