"""Persist source metadata, AI insights, quizzes and reviewable conflicts."""
from alembic import op
from sqlalchemy import Column, String, Integer, inspect
from app.db import Insight, Quiz, QuizAttempt, Contradiction
revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # Initial installations used metadata.create_all. Check columns so this
    # migration also supports both empty databases and existing installations.
    document_columns = {c['name'] for c in inspect(bind).get_columns('documents')}
    for name, length in [('source_url', 2048), ('source_type', 30)]:
        if name not in document_columns:
            op.add_column('documents', Column(name, String(length), server_default='', nullable=True))
    if 'revision' not in {c['name'] for c in inspect(bind).get_columns('conversations')}:
        op.add_column('conversations', Column('revision', Integer(), server_default='1', nullable=True))
    for model in [Insight, Quiz, QuizAttempt, Contradiction]:
        model.__table__.create(bind, checkfirst=True)


def downgrade():
    for name in ['contradictions', 'quiz_attempts', 'quizzes', 'document_insights']:
        op.drop_table(name)
    op.drop_column('conversations', 'revision')
    op.drop_column('documents', 'source_type')
    op.drop_column('documents', 'source_url')
