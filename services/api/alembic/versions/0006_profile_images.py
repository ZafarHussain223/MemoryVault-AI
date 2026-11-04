"""Private canonical profile images stored with the account."""
from alembic import op
from app.profile import ProfileImage
revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    ProfileImage.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    op.drop_table('profile_images')
