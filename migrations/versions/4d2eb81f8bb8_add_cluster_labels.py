"""initial schema

Revision ID: 4d2eb81f8bb8
Revises: f1e1aa2cddf4
Create Date: 2025-11-01 17:06:04.483540

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d2eb81f8bb8'
down_revision: Union[str, Sequence[str], None] = 'f1e1aa2cddf4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade():
    # 1. Add the column as nullable
    op.add_column('cluster_labels', sa.Column('board_id', sa.Integer(), nullable=True))
    
    # 2. OPTIONAL: Update existing rows with a valid default (e.g. delete them or assign)
    # op.execute("DELETE FROM cluster_labels")  # safest for dev, but remove if keeping data
    
    # 3. Or if you know a default board id:
    # op.execute("UPDATE cluster_labels SET board_id = 1 WHERE board_id IS NULL")
    
    # 4. Set it to non-nullable after backfilling
    op.alter_column('cluster_labels', 'board_id', nullable=False)

    # 5. Add foreign key constraint (if required)
    op.create_foreign_key(
        'fk_cluster_labels_board_id_boards',
        'cluster_labels',
        'boards',
        ['board_id'],
        ['id']
    )

def downgrade():
    op.drop_constraint('fk_cluster_labels_board_id_boards', 'cluster_labels', type_='foreignkey')
    op.drop_column('cluster_labels', 'board_id')
