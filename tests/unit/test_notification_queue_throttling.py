from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.repositories.notification import NotificationRepository
from app.scheduler import locks
from app.services.notification_service import NotificationService


def make_notification_service() -> NotificationService:
    service = object.__new__(NotificationService)
    service._chat_send_locks = {}
    service._last_chat_send_at = {}
    service._chat_blocked_until = {}
    return service


@pytest.mark.asyncio
async def test_group_rate_limit_applies_across_topics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_notification_service()
    clock = [100.0]
    sleeps: list[float] = []

    monkeypatch.setattr(
        "app.services.notification_service.time.monotonic",
        lambda: clock[0],
    )

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        clock[0] += delay

    monkeypatch.setattr(
        "app.services.notification_service.asyncio.sleep",
        fake_sleep,
    )

    await service.wait_for_chat_rate_limit(-100)
    await service.wait_for_chat_rate_limit(-100)

    assert sleeps == pytest.approx([3.1])


@pytest.mark.asyncio
async def test_private_chat_uses_one_message_per_second_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_notification_service()
    clock = [100.0]
    sleeps: list[float] = []

    monkeypatch.setattr(
        "app.services.notification_service.time.monotonic",
        lambda: clock[0],
    )

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        clock[0] += delay

    monkeypatch.setattr(
        "app.services.notification_service.asyncio.sleep",
        fake_sleep,
    )

    await service.wait_for_chat_rate_limit(12345)
    await service.wait_for_chat_rate_limit(12345)

    assert sleeps == pytest.approx([1.05])


@pytest.mark.asyncio
async def test_retry_after_blocks_following_messages_to_same_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_notification_service()
    clock = [100.0]
    sleeps: list[float] = []

    monkeypatch.setattr(
        "app.services.notification_service.time.monotonic",
        lambda: clock[0],
    )

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        clock[0] += delay

    monkeypatch.setattr(
        "app.services.notification_service.asyncio.sleep",
        fake_sleep,
    )

    service._chat_blocked_until[-100] = 160.0
    await service.wait_for_chat_rate_limit(-100)

    assert sleeps == pytest.approx([60.0])
    assert -100 not in service._chat_blocked_until


@pytest.mark.asyncio
async def test_reserve_by_id_uses_one_locked_lookup() -> None:
    repository = object.__new__(NotificationRepository)
    notification = SimpleNamespace(dedupe_key="closing:store:1")
    expected = object()

    repository.get_by_id_or_raise = AsyncMock(
        return_value=notification,
    )
    repository._reserve_locked_notification = AsyncMock(
        return_value=expected,
    )

    attempted_at = datetime.now(UTC)
    result = await repository.reserve_by_id(
        notification_id=42,
        attempted_at=attempted_at,
    )

    assert result is expected
    repository.get_by_id_or_raise.assert_awaited_once_with(
        42,
        for_update=True,
    )
    repository._reserve_locked_notification.assert_awaited_once_with(
        notification=notification,
        attempted_at=attempted_at,
        max_attempts=5,
    )


class FakeLockResult:
    def __init__(self, acquired: bool) -> None:
        self.acquired = acquired

    def scalar_one(self) -> bool:
        return self.acquired


class FakeLockConnection:
    def __init__(self, acquired: bool) -> None:
        self.acquired = acquired
        self.transaction_open = False
        self.rollback_count = 0
        self.closed = False

    async def __aenter__(self) -> FakeLockConnection:
        return self

    async def __aexit__(self, *_args: object) -> None:
        self.closed = True

    async def execute(self, *_args: object, **_kwargs: object) -> FakeLockResult:
        self.transaction_open = True
        return FakeLockResult(self.acquired)

    def in_transaction(self) -> bool:
        return self.transaction_open

    async def rollback(self) -> None:
        self.transaction_open = False
        self.rollback_count += 1


class FakeLockEngine:
    def __init__(self, connection: FakeLockConnection) -> None:
        self.connection = connection

    def connect(self) -> FakeLockConnection:
        return self.connection


@pytest.mark.asyncio
async def test_scheduler_lock_is_held_until_guard_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeLockConnection(acquired=True)
    monkeypatch.setattr(
        locks,
        "settings",
        SimpleNamespace(
            enable_scheduler_lock=True,
            scheduler_lock_id=123,
        ),
    )
    monkeypatch.setattr(
        locks,
        "engine",
        FakeLockEngine(connection),
    )

    async with locks.scheduler_lock_guard(lock_id=456) as acquired:
        assert acquired is True
        assert connection.transaction_open is True
        assert connection.rollback_count == 0

    assert connection.rollback_count == 1
    assert connection.closed is True


@pytest.mark.asyncio
async def test_scheduler_lock_guard_skips_when_another_worker_holds_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeLockConnection(acquired=False)
    monkeypatch.setattr(
        locks,
        "settings",
        SimpleNamespace(
            enable_scheduler_lock=True,
            scheduler_lock_id=123,
        ),
    )
    monkeypatch.setattr(
        locks,
        "engine",
        FakeLockEngine(connection),
    )

    async with locks.scheduler_lock_guard(lock_id=456) as acquired:
        assert acquired is False
        assert connection.rollback_count == 0

    assert connection.rollback_count == 1
