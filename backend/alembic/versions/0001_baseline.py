"""Baseline schema revision.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-08

This revision documents the existing database as the Alembic starting point.
ORM tables have historically been created via SQLAlchemy metadata +
db.constraints.ensure_db_constraints (views/triggers). Future DDL must land
here as explicit upgrade()/downgrade() steps — do not rely on create_all
for durable changes.

On a fresh environment:
  1. alembic upgrade head
  2. Optionally set TLH_AUTO_CREATE_SCHEMA=1 once to create ORM tables/views
     until those objects are fully expressed in Alembic revisions.
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create PostgreSQL schemas used by models. Tables/views remain owned by
    # ensure_db_constraints / create_all until subsequent migrations fold them in.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(text("CREATE SCHEMA IF NOT EXISTS vault_ingest"))
        op.execute(text("CREATE SCHEMA IF NOT EXISTS expenses"))
        op.execute(text("CREATE SCHEMA IF NOT EXISTS taxes"))


def downgrade() -> None:
    # Schemas may still contain objects; leave them in place on downgrade.
    pass
