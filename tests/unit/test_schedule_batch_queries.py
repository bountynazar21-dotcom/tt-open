from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.database.models.enums import StoreStatus
from app.repositories.schedule import ScheduleRepository


class FakeScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def unique(self) -> FakeScalarResult:
        return self

    def all(self) -> list[object]:
        return self.rows


@pytest.mark.asyncio
@pytest.mark.parametrize("store_count", [50, 85])
@pytest.mark.parametrize(
    ("method_name", "required_attribute"),
    [
        ("get_stores_requiring_opening", "requires_opening"),
        ("get_stores_requiring_closing", "requires_closing"),
    ],
)
async def test_deadline_store_queries_do_not_scale_with_store_count(
    store_count: int,
    method_name: str,
    required_attribute: str,
) -> None:
    """The schedule resolver must use a fixed number of queries for 50/85 stores."""
    stores = [
        SimpleNamespace(
            id=store_id,
            store_number=store_id,
            bush_id=(store_id % 6) + 1,
            cluster_id=(store_id % 4) + 1,
            is_active=True,
            status=StoreStatus.ACTIVE,
        )
        for store_id in range(1, store_count + 1)
    ]
    clusters = [
        SimpleNamespace(
            id=cluster_id,
            is_active=True,
            opening_time=time(9, 0),
            opening_control_deadline=time(9, 10),
            default_closing_time=time(21, 0),
            default_closing_control_deadline=time(21, 10),
        )
        for cluster_id in range(1, 5)
    ]

    session = SimpleNamespace(
        scalars=AsyncMock(
            side_effect=[
                FakeScalarResult(stores),   # active stores
                FakeScalarResult([]),       # store exceptions
                FakeScalarResult([]),       # bush exceptions
                FakeScalarResult([]),       # network exception
                FakeScalarResult([]),       # weekday schedules
                FakeScalarResult(clusters), # cluster defaults
            ]
        )
    )
    repository = ScheduleRepository(session)

    method = getattr(repository, method_name)
    result = await method(business_date=date(2026, 11, 23))

    assert len(result) == store_count
    assert all(getattr(schedule, required_attribute) for _, schedule in result)
    assert session.scalars.await_count == 6
