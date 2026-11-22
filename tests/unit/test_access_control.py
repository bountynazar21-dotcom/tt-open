from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.database.models.enums import UserRole, UserStatus
from app.database.models.store import Store
from app.services.access import AccessService


@pytest.mark.asyncio
async def test_require_store_view_reuses_preloaded_store() -> None:
    store = SimpleNamespace(id=42, bush_id=None)
    session = SimpleNamespace(
        get=AsyncMock(return_value=store),
    )
    bindings = SimpleNamespace(
        user_has_store_access=AsyncMock(return_value=True),
    )
    repositories = SimpleNamespace(
        session=session,
        bindings=bindings,
    )
    service = AccessService(repositories)
    user = SimpleNamespace(
        id=7,
        role=UserRole.STORE_USER,
        status=UserStatus.ACTIVE,
        is_blocked=False,
    )

    result = await service.require_store_view(user, store.id)

    assert result is store
    session.get.assert_awaited_once_with(Store, store.id)
    bindings.user_has_store_access.assert_awaited_once_with(
        user_id=user.id,
        store_id=store.id,
    )


@pytest.mark.asyncio
async def test_can_view_store_rejects_mismatched_preloaded_store() -> None:
    repositories = SimpleNamespace(
        session=SimpleNamespace(get=AsyncMock()),
        bindings=SimpleNamespace(
            user_has_store_access=AsyncMock(return_value=True),
        ),
    )
    service = AccessService(repositories)
    user = SimpleNamespace(
        id=7,
        role=UserRole.STORE_USER,
        status=UserStatus.ACTIVE,
        is_blocked=False,
    )
    other_store = SimpleNamespace(id=41, bush_id=None)

    with pytest.raises(
        ValueError,
        match="Передана інша торгова точка",
    ):
        await service.can_view_store(
            user,
            42,
            store=other_store,
        )

    repositories.session.get.assert_not_awaited()
