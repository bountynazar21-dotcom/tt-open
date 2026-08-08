"""Initial database schema.

Revision ID: 20260808_0001
Revises:
"""

from __future__ import annotations

from alembic import op

from app.database.base import Base

import app.database.models  # noqa: F401


revision = "20260808_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    Base.metadata.create_all(
        bind=bind,
        checkfirst=True,
    )


def downgrade() -> None:
    bind = op.get_bind()

    Base.metadata.drop_all(
        bind=bind,
        checkfirst=True,
    )
