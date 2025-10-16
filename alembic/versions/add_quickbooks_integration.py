"""add_quickbooks_integration

Revision ID: add_quickbooks_integration
Revises: c5ec7cb25cd5
Create Date: 2025-10-16 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_quickbooks_integration'
down_revision: Union[str, Sequence[str], None] = 'c5ec7cb25cd5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to add QuickBooks integration tables and fields."""
    
    # Create quickbooks_connections table
    op.create_table('quickbooks_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('realm_id', sa.String(), nullable=False),
        sa.Column('company_name', sa.String(), nullable=True),
        sa.Column('access_token', sa.Text(), nullable=False),
        sa.Column('refresh_token', sa.Text(), nullable=False),
        sa.Column('token_expires_at', sa.DateTime(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(), nullable=True),
        sa.Column('sync_status', sa.String(), nullable=True),
        sa.Column('sync_error', sa.Text(), nullable=True),
        sa.Column('auto_sync_enabled', sa.Boolean(), nullable=True),
        sa.Column('sync_frequency_hours', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_quickbooks_connections_realm_id'), 'quickbooks_connections', ['realm_id'], unique=True)
    
    # Create quickbooks_sync_logs table
    op.create_table('quickbooks_sync_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('connection_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sync_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('transactions_fetched', sa.Integer(), nullable=True),
        sa.Column('transactions_created', sa.Integer(), nullable=True),
        sa.Column('transactions_updated', sa.Integer(), nullable=True),
        sa.Column('transactions_skipped', sa.Integer(), nullable=True),
        sa.Column('vendors_synced', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('sync_params', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['connection_id'], ['quickbooks_connections.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_quickbooks_sync_logs_connection_id'), 'quickbooks_sync_logs', ['connection_id'], unique=False)
    op.create_index(op.f('ix_quickbooks_sync_logs_status'), 'quickbooks_sync_logs', ['status'], unique=False)
    
    # Add QuickBooks fields to transactions table
    op.add_column('transactions', sa.Column('source_type', sa.String(), nullable=True))
    op.add_column('transactions', sa.Column('quickbooks_id', sa.String(), nullable=True))
    op.add_column('transactions', sa.Column('quickbooks_connection_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('transactions', sa.Column('quickbooks_sync_version', sa.String(), nullable=True))
    
    # Create indexes on new transaction fields
    op.create_index(op.f('ix_transactions_source_type'), 'transactions', ['source_type'], unique=False)
    op.create_index(op.f('ix_transactions_quickbooks_id'), 'transactions', ['quickbooks_id'], unique=False)
    op.create_index(op.f('ix_transactions_quickbooks_connection_id'), 'transactions', ['quickbooks_connection_id'], unique=False)
    
    # Add foreign key constraint
    op.create_foreign_key('fk_transactions_quickbooks_connection', 'transactions', 'quickbooks_connections', ['quickbooks_connection_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema to remove QuickBooks integration."""
    
    # Remove foreign key and indexes from transactions
    op.drop_constraint('fk_transactions_quickbooks_connection', 'transactions', type_='foreignkey')
    op.drop_index(op.f('ix_transactions_quickbooks_connection_id'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_quickbooks_id'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_source_type'), table_name='transactions')
    
    # Remove columns from transactions
    op.drop_column('transactions', 'quickbooks_sync_version')
    op.drop_column('transactions', 'quickbooks_connection_id')
    op.drop_column('transactions', 'quickbooks_id')
    op.drop_column('transactions', 'source_type')
    
    # Drop quickbooks_sync_logs table
    op.drop_index(op.f('ix_quickbooks_sync_logs_status'), table_name='quickbooks_sync_logs')
    op.drop_index(op.f('ix_quickbooks_sync_logs_connection_id'), table_name='quickbooks_sync_logs')
    op.drop_table('quickbooks_sync_logs')
    
    # Drop quickbooks_connections table
    op.drop_index(op.f('ix_quickbooks_connections_realm_id'), table_name='quickbooks_connections')
    op.drop_table('quickbooks_connections')

