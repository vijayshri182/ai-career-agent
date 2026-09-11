"""add job discovery foundation

Revision ID: 5e5f4c256726
Revises: 005485fe2c1f
Create Date: 2026-09-11 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5e5f4c256726'
down_revision: Union[str, Sequence[str], None] = '005485fe2c1f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'companies',
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('website_domain', sa.String(length=255), nullable=True),
        sa.Column('careers_url', sa.String(length=1024), nullable=True),
        sa.Column('verification_status', sa.Enum('UNVERIFIED', 'VERIFIED', 'REJECTED', name='companyverificationstatus'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_companies_website_domain', 'companies', ['website_domain'], unique=False)
    op.create_index(
        'uq_companies_domain_verified',
        'companies',
        ['website_domain'],
        unique=True,
        sqlite_where=sa.text("verification_status = 'VERIFIED'"),
        postgresql_where=sa.text("verification_status = 'VERIFIED'"),
    )
    op.create_table(
        'job_sources',
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('candidate_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('source_type', sa.Enum('COMPANY_CAREERS', 'ATS', 'API', 'JOB_BOARD', 'RSS', name='jobsourcetype'), nullable=False),
        sa.Column('base_url', sa.String(length=1024), nullable=False),
        sa.Column('terms_allow_automation', sa.Boolean(), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False),
        sa.Column('crawl_config', sa.JSON(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('candidate_id', 'name', name='uq_job_sources_candidate_name'),
    )
    op.create_index('ix_job_sources_candidate_id', 'job_sources', ['candidate_id'], unique=False)
    op.create_table(
        'jobs',
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('candidate_id', sa.Uuid(), nullable=False),
        sa.Column('company_id', sa.Uuid(), nullable=False),
        sa.Column('source_id', sa.Uuid(), nullable=False),
        sa.Column('external_id', sa.String(length=255), nullable=True),
        sa.Column('url', sa.String(length=2048), nullable=False),
        sa.Column('title', sa.String(length=512), nullable=False),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('status', sa.Enum('DISCOVERED', 'VERIFIED', 'EXPIRED', 'REJECTED', name='jobstatus'), nullable=False),
        sa.Column('posted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closing_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id']),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['source_id'], ['job_sources.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('candidate_id', 'url', name='uq_jobs_candidate_url'),
        sa.UniqueConstraint('candidate_id', 'company_id', 'external_id', name='uq_jobs_candidate_company_external'),
    )
    op.create_index('ix_jobs_candidate_id', 'jobs', ['candidate_id'], unique=False)
    op.create_index('ix_jobs_company_id', 'jobs', ['company_id'], unique=False)
    op.create_index('ix_jobs_source_id', 'jobs', ['source_id'], unique=False)
    op.create_index('ix_jobs_content_hash', 'jobs', ['content_hash'], unique=False)
    op.create_index('ix_jobs_status', 'jobs', ['status'], unique=False)
    op.create_table(
        'raw_job_extractions',
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('candidate_id', sa.Uuid(), nullable=False),
        sa.Column('source_id', sa.Uuid(), nullable=False),
        sa.Column('job_id', sa.Uuid(), nullable=True),
        sa.Column('fetch_url', sa.String(length=2048), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.Enum('PARSED', 'IGNORED', 'ERROR', name='rawextractionstatus'), nullable=False),
        sa.Column('raw_payload', sa.JSON(), nullable=True),
        sa.Column('content_hash', sa.String(length=64), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id']),
        sa.ForeignKeyConstraint(['source_id'], ['job_sources.id']),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_raw_job_extractions_candidate_id', 'raw_job_extractions', ['candidate_id'], unique=False)
    op.create_index('ix_raw_job_extractions_source_id', 'raw_job_extractions', ['source_id'], unique=False)
    op.create_index('ix_raw_job_extractions_job_id', 'raw_job_extractions', ['job_id'], unique=False)
    op.create_index('ix_raw_job_extractions_content_hash', 'raw_job_extractions', ['content_hash'], unique=False)
    op.create_table(
        'agent_tasks',
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('candidate_id', sa.Uuid(), nullable=True),
        sa.Column('task_type', sa.String(length=64), nullable=False),
        sa.Column('entity_type', sa.String(length=64), nullable=True),
        sa.Column('entity_id', sa.Uuid(), nullable=True),
        sa.Column('status', sa.Enum('PENDING', 'RUNNING', 'SUCCESS', 'FAILED', 'AWAITING_APPROVAL', 'CANCELLED', name='agenttaskstatus'), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('max_retries', sa.Integer(), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('result_metadata', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_tasks_candidate_id', 'agent_tasks', ['candidate_id'], unique=False)
    op.create_index('ix_agent_tasks_task_type', 'agent_tasks', ['task_type'], unique=False)
    op.create_index('ix_agent_tasks_entity_id', 'agent_tasks', ['entity_id'], unique=False)
    op.create_index('ix_agent_tasks_status', 'agent_tasks', ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_agent_tasks_status', table_name='agent_tasks')
    op.drop_index('ix_agent_tasks_entity_id', table_name='agent_tasks')
    op.drop_index('ix_agent_tasks_task_type', table_name='agent_tasks')
    op.drop_index('ix_agent_tasks_candidate_id', table_name='agent_tasks')
    op.drop_table('agent_tasks')
    op.drop_index('ix_raw_job_extractions_content_hash', table_name='raw_job_extractions')
    op.drop_index('ix_raw_job_extractions_job_id', table_name='raw_job_extractions')
    op.drop_index('ix_raw_job_extractions_source_id', table_name='raw_job_extractions')
    op.drop_index('ix_raw_job_extractions_candidate_id', table_name='raw_job_extractions')
    op.drop_table('raw_job_extractions')
    op.drop_index('ix_jobs_status', table_name='jobs')
    op.drop_index('ix_jobs_content_hash', table_name='jobs')
    op.drop_index('ix_jobs_source_id', table_name='jobs')
    op.drop_index('ix_jobs_company_id', table_name='jobs')
    op.drop_index('ix_jobs_candidate_id', table_name='jobs')
    op.drop_table('jobs')
    op.drop_index('ix_job_sources_candidate_id', table_name='job_sources')
    op.drop_table('job_sources')
    op.drop_index('uq_companies_domain_verified', table_name='companies',
                   sqlite_where=sa.text("verification_status = 'VERIFIED'"),
                   postgresql_where=sa.text("verification_status = 'VERIFIED'"))
    op.drop_index('ix_companies_website_domain', table_name='companies')
    op.drop_table('companies')
