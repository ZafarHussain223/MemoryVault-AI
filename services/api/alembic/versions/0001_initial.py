from alembic import op
from app.db import Base
revision='0001'
down_revision=None
branch_labels=None
depends_on=None
def upgrade():
    bind=op.get_bind()
    if bind.dialect.name=='postgresql':op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    Base.metadata.create_all(bind)
    if bind.dialect.name=='postgresql':op.execute('CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)')
def downgrade():Base.metadata.drop_all(op.get_bind())
