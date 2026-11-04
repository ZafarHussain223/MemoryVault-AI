"""Persistent in-app reminders and privacy-controlled document visit history."""
from alembic import op
from app.db import Reminder, DocumentVisit
revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    Reminder.__table__.create(op.get_bind(), checkfirst=True)
    DocumentVisit.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    op.drop_table('document_visits')
    op.drop_table('reminders')
