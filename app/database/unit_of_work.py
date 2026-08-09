from __future__ import annotations

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from app.database.session import (
    async_session_factory,
)
from app.repositories import Repositories


class UnitOfWork:
    """
    Unit of Work для однієї транзакції PostgreSQL.

    Один UnitOfWork:
    - створює одну AsyncSession;
    - створює один контейнер Repositories;
    - commit при успішному завершенні;
    - rollback при помилці;
    - закриває session після завершення.

    Приклад:

        async with UnitOfWork() as uow:
            user = await uow.repositories.users.get_by_id(1)

            ...

        # після виходу без помилки буде commit

    Або ручне керування:

        async with UnitOfWork(auto_commit=False) as uow:
            ...
            await uow.commit()
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] = (
            async_session_factory
        ),
        *,
        auto_commit: bool = True,
    ) -> None:
        self.session_factory = (
            session_factory
        )

        self.auto_commit = (
            auto_commit
        )

        self.session: AsyncSession | None = None
        self.repositories: Repositories | None = None

        self._finished = False


    # =====================================================
    # CONTEXT MANAGER
    # =====================================================

    async def __aenter__(
        self,
    ) -> Self:
        if self.session is not None:
            raise RuntimeError(
                "UnitOfWork уже запущений."
            )

        self.session = (
            self.session_factory()
        )

        self.repositories = Repositories(
            self.session
        )

        self._finished = False

        return self


    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        try:
            if exc_type is not None:
                await self.rollback()

            elif (
                self.auto_commit
                and not self._finished
            ):
                await self.commit()

        finally:
            await self.close()

        # False = не приховувати exception.
        return False


    # =====================================================
    # ACCESS
    # =====================================================

    @property
    def repos(
        self,
    ) -> Repositories:
        """
        Короткий alias для repositories.
        """

        if self.repositories is None:
            raise RuntimeError(
                "UnitOfWork ще не запущений. "
                "Використайте 'async with UnitOfWork()'."
            )

        return self.repositories


    @property
    def db(
        self,
    ) -> AsyncSession:
        """
        Повертає активну AsyncSession.
        """

        if self.session is None:
            raise RuntimeError(
                "UnitOfWork ще не запущений."
            )

        return self.session


    # =====================================================
    # TRANSACTION
    # =====================================================

    async def flush(
        self,
    ) -> None:
        """
        Відправляє зміни в PostgreSQL
        без завершення транзакції.
        """

        if self.session is None:
            raise RuntimeError(
                "UnitOfWork ще не запущений."
            )

        await self.session.flush()


    async def commit(
        self,
    ) -> None:
        """
        Підтверджує транзакцію.
        """

        if self.session is None:
            raise RuntimeError(
                "UnitOfWork ще не запущений."
            )

        if self._finished:
            return

        await self.session.commit()

        self._finished = True


    async def rollback(
        self,
    ) -> None:
        """
        Відкочує транзакцію.
        """

        if self.session is None:
            return

        if self._finished:
            return

        await self.session.rollback()

        self._finished = True


    async def refresh(
        self,
        instance: object,
    ) -> None:
        """
        Повторно завантажує модель із PostgreSQL.
        """

        if self.session is None:
            raise RuntimeError(
                "UnitOfWork ще не запущений."
            )

        await self.session.refresh(
            instance
        )


    # =====================================================
    # CLOSE
    # =====================================================

    async def close(
        self,
    ) -> None:
        """
        Закриває session і очищає
        внутрішні посилання.
        """

        if self.session is not None:
            await self.session.close()

        self.session = None
        self.repositories = None


# =========================================================
# FACTORY
# =========================================================


def create_unit_of_work(
    *,
    auto_commit: bool = True,
    session_factory: async_sessionmaker[AsyncSession] = (
        async_session_factory
    ),
) -> UnitOfWork:
    """
    Factory для UnitOfWork.
    """

    return UnitOfWork(
        session_factory=session_factory,
        auto_commit=auto_commit,
    )


# =========================================================
# ALIASES
# =========================================================


UoW = UnitOfWork


__all__ = [
    "UnitOfWork",
    "UoW",
    "create_unit_of_work",
]