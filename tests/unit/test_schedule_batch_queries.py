from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.database.models.enums import ClosingStatus, OpeningStatus, StoreStatus, UserRole, UserStatus
from app.database.models.daily_summary import DailySummaryMessage
from app.database.models.enums import SummaryType
from app.repositories.daily_summary import DailySummaryRepository
from app.repositories.binding import BindingRepository
from app.repositories.closing import ClosingRepository
from app.repositories.opening import OpeningRepository
from app.repositories.schedule import ScheduleRepository
from app.services.group_service import GroupService
from app.services.closing_service import ClosingService
from app.services.bush_service import BushService
from app.services.binding_service import BindingService
from app.services.cluster_service import ClusterService
from app.services.store_service import StoreService
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



@pytest.mark.asyncio
@pytest.mark.parametrize("store_count", [50, 85])
async def test_opening_summary_data_for_all_bushes_uses_one_query(
    store_count: int,
) -> None:
    rows = []
    for store_id in range(1, store_count + 1):
        bush_id = (store_id % 6) + 1
        if store_id % 5 == 0:
            status = OpeningStatus.MISSED_CONTROL_DEADLINE
            lateness = 0
        elif store_id % 4 == 0:
            status = OpeningStatus.OPENED_LATE
            lateness = 12
        elif store_id % 3 == 0:
            status = OpeningStatus.WAITING
            lateness = 0
        else:
            status = OpeningStatus.OPENED_ON_TIME
            lateness = 0
        rows.append((
            SimpleNamespace(
                id=store_id,
                store_id=store_id,
                status=status,
                lateness_minutes=lateness,
                actual_open_time=(
                    None if status == OpeningStatus.WAITING else object()
                ),
            ),
            bush_id,
        ))

    session = SimpleNamespace(
        execute=AsyncMock(return_value=FakeRows(rows))
    )
    repository = object.__new__(OpeningRepository)
    repository.session = session

    result = await repository.get_summary_data_by_bush(
        business_date=date(2026, 11, 23),
        bush_ids={1, 2, 3, 4, 5, 6},
    )

    assert set(result) == {1, 2, 3, 4, 5, 6}
    assert sum(
        data["statistics"]["expected_count"]
        for data in result.values()
    ) == store_count
    assert sum(
        data["statistics"]["missed_count"]
        for data in result.values()
    ) == sum(1 for row in rows if row[0].status == OpeningStatus.MISSED_CONTROL_DEADLINE)
    assert sum(
        len(data["waiting_checkins"])
        for data in result.values()
    ) == sum(1 for row in rows if row[0].status == OpeningStatus.WAITING)
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("store_count", [50, 85])
async def test_closing_summary_data_for_all_bushes_uses_one_query(
    store_count: int,
) -> None:
    from decimal import Decimal

    rows = []
    for store_id in range(1, store_count + 1):
        bush_id = (store_id % 6) + 1
        if store_id % 5 == 0:
            status = ClosingStatus.MISSED_DEADLINE
            cash = None
            submitted_at = None
        elif store_id % 4 == 0:
            status = ClosingStatus.SUBMITTED_LATE
            cash = Decimal("120.50")
            submitted_at = object()
        elif store_id % 3 == 0:
            status = ClosingStatus.WAITING
            cash = None
            submitted_at = None
        else:
            status = ClosingStatus.SUBMITTED_ON_TIME
            cash = Decimal("100.00")
            submitted_at = object()
        rows.append((
            SimpleNamespace(
                id=store_id,
                store_id=store_id,
                status=status,
                cash_amount=cash,
                actual_submitted_at=submitted_at,
            ),
            bush_id,
        ))

    session = SimpleNamespace(
        execute=AsyncMock(return_value=FakeRows(rows))
    )
    repository = object.__new__(ClosingRepository)
    repository.session = session

    result = await repository.get_summary_data_by_bush(
        business_date=date(2026, 11, 23),
        bush_ids={1, 2, 3, 4, 5, 6},
    )

    assert set(result) == {1, 2, 3, 4, 5, 6}
    assert sum(
        data["statistics"]["expected_count"]
        for data in result.values()
    ) == store_count
    assert sum(
        data["statistics"]["missed_count"]
        for data in result.values()
    ) == sum(1 for row in rows if row[0].status == ClosingStatus.MISSED_DEADLINE)
    assert sum(
        len(data["waiting_reports"])
        for data in result.values()
    ) == sum(1 for row in rows if row[0].status == ClosingStatus.WAITING)
    assert sum(
        data["statistics"]["total_cash"]
        for data in result.values()
    ) == sum(
        (row[0].cash_amount or Decimal("0"))
        for row in rows
    )
    session.execute.assert_awaited_once()



@pytest.mark.asyncio
async def test_prepare_many_summaries_uses_one_locked_read_for_six_bushes() -> None:
    business_date = date(2026, 11, 23)
    summaries = [
        DailySummaryMessage.create_pending(
            summary_type=SummaryType.BUSH_CLOSING,
            business_date=business_date,
            chat_id=-1000 - bush_id,
            bush_id=bush_id,
            topic_id=20 + bush_id,
        )
        for bush_id in range(1, 7)
    ]
    for index, summary in enumerate(summaries, start=1):
        summary.message_id = 1000 + index
        summary.message_text = "previous"

    session = SimpleNamespace(
        scalars=AsyncMock(return_value=FakeScalarResult(summaries)),
        add=Mock(),
        flush=AsyncMock(),
    )
    repository = object.__new__(DailySummaryRepository)
    repository.session = session

    decisions = await repository.prepare_updates_many(
        summary_type=SummaryType.BUSH_CLOSING,
        business_date=business_date,
        items=[
            {
                "chat_id": -1000 - bush_id,
                "bush_id": bush_id,
                "topic_id": 20 + bush_id,
                "message_text": f"updated summary {bush_id}",
                "snapshot_json": {"bush_id": bush_id},
            }
            for bush_id in range(1, 7)
        ],
    )

    assert len(decisions) == 6
    assert all(decision.should_edit for decision in decisions)
    assert not any(decision.should_send for decision in decisions)
    assert session.scalars.await_count == 1
    assert session.flush.await_count == 1
    assert session.add.call_count == 6



@pytest.mark.asyncio
async def test_bulk_store_lookup_uses_one_query_for_many_codes() -> None:
    stores = [
        SimpleNamespace(id=store_id, code=f"TT-{store_id:03d}")
        for store_id in range(1, 86)
    ]
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=FakeScalarResult(stores))
    )
    service = object.__new__(StoreService)
    service.session = session

    result = await service.find_by_codes({
        f"TT-{store_id:03d}"
        for store_id in range(1, 86)
    })

    assert len(result) == 85
    assert result["tt-001"].id == 1
    assert result["tt-085"].id == 85
    session.scalars.assert_awaited_once()


@pytest.mark.asyncio
async def test_bulk_bush_lookup_uses_one_query_for_names_and_codes() -> None:
    bushes = [
        SimpleNamespace(id=bush_id, name=f"Bush {bush_id}", code=f"B{bush_id}")
        for bush_id in range(1, 7)
    ]
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=FakeScalarResult(bushes))
    )
    service = object.__new__(BushService)
    service.session = session

    result = await service.find_bushes_matching(
        names={f"bush {bush_id}" for bush_id in range(1, 7)},
        codes={f"b{bush_id}" for bush_id in range(1, 7)},
    )

    assert [bush.id for bush in result] == [1, 2, 3, 4, 5, 6]
    session.scalars.assert_awaited_once()



@pytest.mark.asyncio
@pytest.mark.parametrize("store_count", [50, 85])
async def test_bulk_cluster_assignment_locks_all_stores_in_one_query(
    store_count: int,
) -> None:
    stores = [
        SimpleNamespace(
            id=store_id,
            cluster_id=None,
        )
        for store_id in range(1, store_count + 1)
    ]
    assignment_results = [
        SimpleNamespace(
            was_changed=True,
            previous_cluster_id=None,
            current_cluster_id=7,
        )
        for _ in stores
    ]
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=FakeScalarResult(stores))
    )
    service = object.__new__(ClusterService)
    service.session = session
    service.get_cluster_or_raise = AsyncMock(
        return_value=SimpleNamespace(id=7, is_active=True)
    )
    service.assign_store = AsyncMock(side_effect=assignment_results)

    result = await service.bulk_assign_stores(
        actor=SimpleNamespace(id=1),
        store_ids=list(range(1, store_count + 1)),
        cluster_id=7,
        reason="bulk assignment test",
    )

    assert result.total_count == store_count
    assert result.success_count == store_count
    assert result.changed_count == store_count
    assert session.scalars.await_count == 1
    service.get_cluster_or_raise.assert_awaited_once_with(7)
    assert service.assign_store.await_count == store_count
    for call, store in zip(
        service.assign_store.await_args_list,
        stores,
        strict=True,
    ):
        assert call.kwargs["_preloaded_store"] is store
        assert call.kwargs["_cluster_prevalidated"] is True



@pytest.mark.asyncio
async def test_user_bush_access_ids_are_loaded_in_one_query() -> None:
    session = SimpleNamespace(
        scalars=AsyncMock(
            return_value=FakeScalarResult([2, 4, 6, 8])
        )
    )
    repository = object.__new__(BindingRepository)
    repository.session = session

    result = await repository.get_user_bush_ids(
        user_id=99,
        roles={UserRole.BUSH_ADMIN},
    )

    assert result == {2, 4, 6, 8}
    session.scalars.assert_awaited_once()


@pytest.mark.asyncio
async def test_bulk_cluster_assignment_preloads_bush_permissions_once() -> None:
    stores = [
        SimpleNamespace(id=store_id, bush_id=(store_id % 6) + 1, cluster_id=None)
        for store_id in range(1, 86)
    ]
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=FakeScalarResult(stores))
    )
    bindings = SimpleNamespace(
        get_user_bush_ids=AsyncMock(return_value={1, 2, 3, 4, 5, 6})
    )
    service = object.__new__(ClusterService)
    service.session = session
    service.repositories = SimpleNamespace(bindings=bindings)
    service.access = SimpleNamespace(
        is_active_user=Mock(return_value=True),
        is_global_manager=Mock(return_value=False),
    )
    service.get_cluster_or_raise = AsyncMock(
        return_value=SimpleNamespace(id=7, is_active=True)
    )
    service.assign_store = AsyncMock(
        side_effect=[
            SimpleNamespace(
                was_changed=True,
                previous_cluster_id=None,
                current_cluster_id=7,
            )
            for _ in stores
        ]
    )

    await service.bulk_assign_stores(
        actor=SimpleNamespace(id=99, role=UserRole.BUSH_ADMIN),
        store_ids=[store.id for store in stores],
        cluster_id=7,
        reason="bulk assignment test",
    )

    bindings.get_user_bush_ids.assert_awaited_once_with(
        user_id=99,
        roles={UserRole.BUSH_ADMIN},
    )
    assert service.assign_store.await_count == 85
    assert all(
        call.kwargs["_manageable_bush_ids"] == {1, 2, 3, 4, 5, 6}
        for call in service.assign_store.await_args_list
    )



@pytest.mark.asyncio
async def test_store_bindings_for_many_users_use_one_query() -> None:
    bindings = [
        SimpleNamespace(id=user_id, user_id=user_id, store_id=17)
        for user_id in range(1, 86)
    ]
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=FakeScalarResult(bindings))
    )
    repository = object.__new__(BindingRepository)
    repository.session = session

    result = await repository.get_store_bindings_for_users(
        user_ids=set(range(1, 86)),
        store_id=17,
        for_update=True,
    )

    assert len(result) == 85
    assert result[42].store_id == 17
    session.scalars.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("user_count", [50, 85])

@pytest.mark.asyncio
async def test_bush_bindings_for_many_users_use_one_query() -> None:
    bindings = [
        SimpleNamespace(id=user_id, user_id=user_id, bush_id=8, role=UserRole.LION)
        for user_id in range(1, 86)
    ]
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=FakeScalarResult(bindings))
    )
    repository = object.__new__(BindingRepository)
    repository.session = session

    result = await repository.get_bush_bindings_for_users(
        user_ids=set(range(1, 86)),
        bush_id=8,
        role=UserRole.LION,
        for_update=True,
    )

    assert len(result) == 85
    assert result[42].bush_id == 8
    session.scalars.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("user_count", [50, 85])
async def test_bulk_bush_assignment_preloads_users_and_bindings(
    user_count: int,
) -> None:
    users = [
        SimpleNamespace(id=user_id)
        for user_id in range(1, user_count + 1)
    ]
    bindings_by_user = {
        user.id: SimpleNamespace(
            id=user.id,
            user_id=user.id,
            bush_id=8,
            role=UserRole.BUSH_ADMIN,
        )
        for user in users
    }
    access = SimpleNamespace(
        can_manage_bush=AsyncMock(
            return_value=SimpleNamespace(
                raise_if_denied=Mock(return_value=None)
            )
        )
    )
    bindings_repo = SimpleNamespace(
        get_bush_bindings_for_users=AsyncMock(
            return_value=bindings_by_user
        )
    )
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=FakeScalarResult(users))
    )
    service = object.__new__(BindingService)
    service.session = session
    service.access = access
    service.repositories = SimpleNamespace(bindings=bindings_repo)
    service.get_bush_or_raise = AsyncMock(
        return_value=SimpleNamespace(id=8)
    )
    service.assign_bush = AsyncMock(
        side_effect=[
            SimpleNamespace(
                was_created=False,
                was_changed=True,
                binding=SimpleNamespace(id=user.id),
            )
            for user in users
        ]
    )

    result = await service.bulk_assign_bush(
        actor=SimpleNamespace(id=99),
        user_ids=[user.id for user in users],
        bush_id=8,
        role=UserRole.BUSH_ADMIN,
        reason="bulk bush assignment test",
    )

    assert result.total_count == user_count
    assert result.success_count == user_count
    access.can_manage_bush.assert_awaited_once_with(
        service.assign_bush.await_args.kwargs["actor"],
        8,
    )
    session.scalars.assert_awaited_once()
    bindings_repo.get_bush_bindings_for_users.assert_awaited_once_with(
        user_ids=set(range(1, user_count + 1)),
        bush_id=8,
        role=UserRole.BUSH_ADMIN,
        for_update=True,
    )
    assert service.assign_bush.await_count == user_count
    for call, user in zip(
        service.assign_bush.await_args_list,
        users,
        strict=True,
    ):
        assert call.kwargs["_preloaded_user"] is user
        assert call.kwargs["_preloaded_binding"] is bindings_by_user[user.id]
        assert call.kwargs["_preloaded_binding_loaded"] is True
        assert call.kwargs["_bush_access_prevalidated"] is True


async def test_bulk_store_assignment_preloads_users_and_bindings(
    user_count: int,
) -> None:
    users = [
        SimpleNamespace(id=user_id)
        for user_id in range(1, user_count + 1)
    ]
    bindings_by_user = {
        user.id: SimpleNamespace(id=user.id, user_id=user.id, store_id=10)
        for user in users
    }
    access = SimpleNamespace(
        can_manage_store=AsyncMock(
            return_value=SimpleNamespace(
                raise_if_denied=Mock(return_value=None)
            )
        )
    )
    bindings_repo = SimpleNamespace(
        get_store_bindings_for_users=AsyncMock(
            return_value=bindings_by_user
        )
    )
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=FakeScalarResult(users))
    )
    service = object.__new__(BindingService)
    service.session = session
    service.access = access
    service.repositories = SimpleNamespace(bindings=bindings_repo)
    service.get_store_or_raise = AsyncMock(
        return_value=SimpleNamespace(id=10)
    )
    service.assign_store = AsyncMock(
        side_effect=[
            SimpleNamespace(
                was_created=False,
                was_changed=True,
                binding=SimpleNamespace(id=user.id),
            )
            for user in users
        ]
    )

    result = await service.bulk_assign_store(
        actor=SimpleNamespace(id=99),
        user_ids=[user.id for user in users],
        store_id=10,
        reason="bulk assignment test",
    )

    assert result.total_count == user_count
    assert result.success_count == user_count
    access.can_manage_store.assert_awaited_once_with(
        service.assign_store.await_args.kwargs["actor"],
        10,
    )
    session.scalars.assert_awaited_once()
    bindings_repo.get_store_bindings_for_users.assert_awaited_once_with(
        user_ids=set(range(1, user_count + 1)),
        store_id=10,
        for_update=True,
    )
    assert service.assign_store.await_count == user_count
    for call, user in zip(
        service.assign_store.await_args_list,
        users,
        strict=True,
    ):
        assert call.kwargs["_preloaded_user"] is user
        assert call.kwargs["_preloaded_binding"] is bindings_by_user[user.id]
        assert call.kwargs["_preloaded_binding_loaded"] is True
        assert call.kwargs["_store_access_prevalidated"] is True
