"""add pgvector extension and document_chunks table

Revision ID: c498a129d10e
Revises: 22159e02220d
Create Date: 2026-08-27 01:25:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from core.config import settings

# revision identifiers, used by Alembic.
revision: str = 'c498a129d10e'
down_revision: Union[str, Sequence[str], None] = '22159e02220d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Create document_chunks table
    op.create_table(
        'document_chunks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('document_id', sa.String(length=36), nullable=False),
        sa.Column('org_id', sa.String(length=36), nullable=False),
        sa.Column('department_id', sa.String(length=36), nullable=True),
        sa.Column('uploader_id', sa.String(length=36), nullable=True),
        sa.Column('access_level', sa.String(length=50), nullable=False, server_default='DEPARTMENT'),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(settings.EMBEDDING_DIMENSION), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['enterprise_documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 3. Create relational and composite indexes
    op.create_index(op.f('ix_document_chunks_document_id'), 'document_chunks', ['document_id'], unique=False)
    op.create_index(op.f('ix_document_chunks_org_id'), 'document_chunks', ['org_id'], unique=False)
    op.create_index(op.f('ix_document_chunks_department_id'), 'document_chunks', ['department_id'], unique=False)
    op.create_index('ix_doc_chunks_org_dept', 'document_chunks', ['org_id', 'department_id'], unique=False)
    op.create_index('ix_doc_chunks_doc_idx', 'document_chunks', ['document_id', 'chunk_index'], unique=False)

    # 4. Create HNSW Vector Index on embeddings (fail-safe if pgvector enabled)
    try:
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_doc_chunks_embedding_hnsw "
            "ON document_chunks USING hnsw (embedding vector_cosine_ops);"
        )
    except Exception:
        pass


def downgrade() -> None:
    op.drop_index('ix_doc_chunks_doc_idx', table_name='document_chunks')
    op.drop_index('ix_doc_chunks_org_dept', table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_department_id'), table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_org_id'), table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_document_id'), table_name='document_chunks')
    try:
        op.execute("DROP INDEX IF EXISTS ix_doc_chunks_embedding_hnsw;")
    except Exception:
        pass
    op.drop_table('document_chunks')
