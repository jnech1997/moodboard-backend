"""allow content to be null in items

Revision ID: 2713169914a2
Revises: a3f2a0dde25a
Create Date: 2025-10-30 19:17:31.898234

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2713169914a2'
down_revision: Union[str, Sequence[str], None] = 'a3f2a0dde25a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.alter_column(
        "items",
        "content",
        existing_type=sa.VARCHAR(),
        nullable=True
    )

def downgrade():
    op.alter_column(
        "items",
        "content",
        existing_type=sa.VARCHAR(),
        nullable=False
    )
