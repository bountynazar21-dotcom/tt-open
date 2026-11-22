from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.database.models.enums import ClosingStatus, StoreStatus, UserRole, UserStatus
from app.repositories.closing import ClosingRepository
from app.repositories.schedule import ScheduleRepository
from app.services.group_service import GroupService
from app.services.closing_service import ClosingService
from app.services.opening_service import OpeningService


class FakeScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def unique(self) -> FakeScalarResult:
        return self

    def all(self) -> list[object]:
        return self.rows

    def first(self) -> object | None:
        return self.rows[0] if self.rows else None


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


class FakeRows:
    def __init__(self, rows: list[tuple[int, object]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[int, object]]:
        return self.rows


@pytest.mark.asyncio
@pytest.mark.parametrize("store_count", [50, 85])
@pytest.mark.parametrize("service_class", [OpeningService, ClosingService])
async def test_alert_recipients_are_loaded_in_two_queries_for_store_batch(
    store_count: int,
    service_class: type[OpeningService] | type[ClosingService],
) -> None:
    stores = [
        SimpleNamespace(
            id=store_id,
            bush_id=(store_id % 6) + 1,
        )
        for store_id in range(1, store_count + 1)
    ]
    bush_users = [
        SimpleNamespace(
            id=100 + bush_id,
            role=UserRole.LION,
            status=UserStatus.ACTIVE,
            is_blocked=False,
        )
        for bush_id in range(1, 7)
    ]
    root_admin = SimpleNamespace(
        id=1,
        role=UserRole.ROOT_ADMIN,
        status=UserStatus.ACTIVE,
        is_blocked=False,
    )

    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=FakeRows([
                (user.id - 100, user)
                for user in bush_users
            ])
        ),
        scalars=AsyncMock(
            return_value=FakeScalarResult([root_admin])
        ),
    )
    service = object.__new__(service_class)
    service.session = session

    result = await service.get_alert_recipients_for_stores(stores)

    assert len(result) == store_count
    assert all(
        {user.id for user in recipients} == {1, (store_id % 6) + 101}
        for store_id, recipients in result.items()
    )
    session.execute.assert_awaited_once()
    session.scalars.assert_awaited_once()


class FakeMappings:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def mappings(self) -> FakeMappings:
        return self

    def all(self) -> list[dict[str, object]]:
        return self.rows


@pytest.mark.asyncio
async def test_closing_statistics_for_all_bushes_use_one_query() -> None:
    row: dict[str, object] = {
        "bush_id": 3,
        "total_cash": 1250,
        "average_cash": 250,
        "maximum_cash": 500,
        "minimum_cash": 100,
    }
    for status in ClosingStatus:
        row[f"count_{status.name.lower()}"] = 0
    row["count_waiting"] = 2
    row["count_submitted_on_time"] = 3
    row["count_submitted_late"] = 1
    row["count_missed_deadline"] = 1

    session = SimpleNamespace(
        execute=AsyncMock(return_value=FakeMappings([row]))
    )
    repository = object.__new__(ClosingRepository)
    repository.session = session

    result = await repository.get_daily_statistics_by_bush(
        business_date=date(2026, 11, 23)
    )

    stats = result[3]
    assert stats["expected_count"] == 7
    assert stats["submitted_count"] == 4
    assert stats["waiting_count"] == 2
    assert stats["missed_count"] == 1
    assert stats["total_cash"] == 1250
    assert stats["average_cash"] == 250
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_group_integer_settings_are_loaded_in_one_query() -> None:
    settings = [
        SimpleNamespace(key="telegram_groups_bush_1_chat_id", value="-1001"),
        SimpleNamespace(key="telegram_groups_bush_1_summaries_thread_id", value="15"),
        SimpleNamespace(key="telegram_groups_bush_2_chat_id", value="not-an-int"),
    ]
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=FakeScalarResult(settings))
    )
    service = object.__new__(GroupService)
    service.session = session

    result = await service.get_int_settings({
        "telegram_groups_bush_1_chat_id",
        "telegram_groups_bush_1_summaries_thread_id",
        "telegram_groups_bush_2_chat_id",
    })

    assert result == {
        "telegram_groups_bush_1_chat_id": -1001,
        "telegram_groups_bush_1_summaries_thread_id": 15,
    }
    session.scalars.assert_awaited_once()
