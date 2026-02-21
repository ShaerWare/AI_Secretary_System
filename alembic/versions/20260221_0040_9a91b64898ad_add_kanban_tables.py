"""add_kanban_tables

Revision ID: 9a91b64898ad
Revises: 0004
Create Date: 2026-02-21 00:40:31.422978

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '9a91b64898ad'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('kanban_tasks',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='draft', nullable=False),
    sa.Column('is_private', sa.Boolean(), server_default='1', nullable=False),
    sa.Column('assignee', sa.String(length=100), nullable=True),
    sa.Column('created_by', sa.String(length=100), nullable=False),
    sa.Column('start_date', sa.String(length=10), nullable=True),
    sa.Column('due_date', sa.String(length=10), nullable=True),
    sa.Column('position', sa.Integer(), server_default='0', nullable=False),
    sa.Column('tags', sa.Text(), nullable=True),
    sa.Column('created', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_kanban_tasks_created_by'), 'kanban_tasks', ['created_by'], unique=False)
    op.create_index(op.f('ix_kanban_tasks_status'), 'kanban_tasks', ['status'], unique=False)
    op.create_index(op.f('ix_kanban_tasks_title'), 'kanban_tasks', ['title'], unique=False)
    op.create_table('kanban_checklist_items',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('task_id', sa.Integer(), nullable=False),
    sa.Column('text', sa.String(length=500), nullable=False),
    sa.Column('is_done', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('position', sa.Integer(), server_default='0', nullable=False),
    sa.ForeignKeyConstraint(['task_id'], ['kanban_tasks.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_kanban_checklist_items_task_id'), 'kanban_checklist_items', ['task_id'], unique=False)
    op.create_table('kanban_task_dependencies',
    sa.Column('blocker_id', sa.Integer(), nullable=False),
    sa.Column('dependent_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['blocker_id'], ['kanban_tasks.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['dependent_id'], ['kanban_tasks.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('blocker_id', 'dependent_id')
    )


def downgrade() -> None:
    op.drop_table('kanban_task_dependencies')
    op.drop_index(op.f('ix_kanban_checklist_items_task_id'), table_name='kanban_checklist_items')
    op.drop_table('kanban_checklist_items')
    op.drop_index(op.f('ix_kanban_tasks_title'), table_name='kanban_tasks')
    op.drop_index(op.f('ix_kanban_tasks_status'), table_name='kanban_tasks')
    op.drop_index(op.f('ix_kanban_tasks_created_by'), table_name='kanban_tasks')
    op.drop_table('kanban_tasks')
