from alembic import op
from app.db import AuthToken
revision='0002'
down_revision='0001'
branch_labels=None
depends_on=None
def upgrade():AuthToken.__table__.create(op.get_bind(),checkfirst=True)
def downgrade():AuthToken.__table__.drop(op.get_bind())
