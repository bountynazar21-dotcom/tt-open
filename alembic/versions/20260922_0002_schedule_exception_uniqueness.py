"""Add schedule exception uniqueness constraints.

Revision ID: 20260922_0002
Revises: 20260808_0001
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260922_0002"
down_revision = "20260808_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fail explicitly if production already contains
    # ambiguous duplicate schedule exceptions.
    connection = op.get_bind()

    duplicate_store = connection.execute(
        sa.text(
            """
            SELECT
                store_id,
                exception_date,
                COUNT(*) AS row_count
            FROM schedule_exceptions
            WHERE store_id IS NOT NULL
              AND bush_id IS NULL
            GROUP BY store_id, exception_date
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()

    if duplicate_store is not None:
        raise RuntimeError(
            "Cannot add schedule exception uniqueness: "
            "duplicate store/date exceptions exist."
        )

    duplicate_bush = connection.execute(
        sa.text(
            """
            SELECT
                bush_id,
                exception_date,
                COUNT(*) AS row_count
            FROM schedule_exceptions
            WHERE bush_id IS NOT NULL
              AND store_id IS NULL
            GROUP BY bush_id, exception_date
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()

    if duplicate_bush is not None:
        raise RuntimeError(
            "Cannot add schedule exception uniqueness: "
            "duplicate bush/date exceptions exist."
        )

    duplicate_network = connection.execute(
        sa.text(
            """
            SELECT
                exception_date,
                COUNT(*) AS row_count
            FROM schedule_exceptions
            WHERE store_id IS NULL
              AND bush_id IS NULL
            GROUP BY exception_date
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()

    if duplicate_network is not None:
        raise RuntimeError(
            "Cannot add schedule exception uniqueness: "
            "duplicate network/date exceptions exist."
        )

    op.create_index(
        "uq_schedule_exceptions_store_date",
        "schedule_exceptions",
        [
            "store_id",
            "exception_date",
        ],
        unique=True,
        postgresql_where=sa.text(
            "store_id IS NOT NULL "
            "AND bush_id IS NULL"
        ),
    )

    op.create_index(
        "uq_schedule_exceptions_bush_date",
        "schedule_exceptions",
        [
            "bush_id",
            "exception_date",
        ],
        unique=True,
        postgresql_where=sa.text(
            "bush_id IS NOT NULL "
            "AND store_id IS NULL"
        ),
    )

    op.create_index(
        "uq_schedule_exceptions_network_date",
        "schedule_exceptions",
        [
            "exception_date",
        ],
        unique=True,
        postgresql_where=sa.text(
            "store_id IS NULL "
            "AND bush_id IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_schedule_exceptions_network_date",
        table_name="schedule_exceptions",
    )

    op.drop_index(
        "uq_schedule_exceptions_bush_date",
        table_name="schedule_exceptions",
    )

    op.drop_index(
        "uq_schedule_exceptions_store_date",
        table_name="schedule_exceptions",
    )
