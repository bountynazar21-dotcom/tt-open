from __future__ import annotations

from functools import cached_property

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.audit import (
    AuditChangeSet,
    AuditContext,
    AuditRepository,
)
from app.repositories.base import (
    BaseRepository,
)
from app.repositories.binding import (
    BindingRepository,
)
from app.repositories.bush import (
    BushRepository,
)
from app.repositories.closing import (
    ClosingPlan,
    ClosingRepository,
)
from app.repositories.cluster import (
    ClusterRepository,
)
from app.repositories.daily_summary import (
    DailySummaryRepository,
    SummaryScope,
    SummaryUpdateDecision,
)
from app.repositories.invite import (
    CreatedInvite,
    InviteActivationResult,
    InviteRepository,
)
from app.repositories.notification import (
    NotificationRepository,
    NotificationReservation,
)
from app.repositories.opening import (
    OpeningPlan,
    OpeningRepository,
)
from app.repositories.schedule import (
    EffectiveSchedule,
    ScheduleRepository,
)
from app.repositories.store import (
    StoreRepository,
)
from app.repositories.system_setting import (
    SettingDefinition,
    SettingUpdateResult,
    SystemSettingRepository,
)
from app.repositories.user import (
    UserRepository,
)


class Repositories:
    """
    Єдиний контейнер усіх репозиторіїв.

    Кожен репозиторій використовує одну й ту саму
    SQLAlchemy AsyncSession.

    Репозиторії створюються ліниво — лише тоді,
    коли до них звертаються вперше.
    """

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

    # ==========================================
    # КОРИСТУВАЧІ ТА ДОСТУП
    # ==========================================

    @cached_property
    def users(self) -> UserRepository:
        """Репозиторій користувачів."""

        return UserRepository(self.session)

    @cached_property
    def bindings(self) -> BindingRepository:
        """Репозиторій прив’язок до ТТ і кущів."""

        return BindingRepository(self.session)

    @cached_property
    def invites(self) -> InviteRepository:
        """Репозиторій запрошень."""

        return InviteRepository(self.session)

    # ==========================================
    # СТРУКТУРА МЕРЕЖІ
    # ==========================================

    @cached_property
    def stores(self) -> StoreRepository:
        """Репозиторій торгових точок."""

        return StoreRepository(self.session)

    @cached_property
    def bushes(self) -> BushRepository:
        """Репозиторій кущів."""

        return BushRepository(self.session)

    @cached_property
    def clusters(self) -> ClusterRepository:
        """Репозиторій часових кластерів."""

        return ClusterRepository(self.session)

    @cached_property
    def schedules(self) -> ScheduleRepository:
        """Репозиторій графіків роботи."""

        return ScheduleRepository(self.session)

    # ==========================================
    # ВІДКРИТТЯ ТА ЗАКРИТТЯ
    # ==========================================

    @cached_property
    def openings(self) -> OpeningRepository:
        """Репозиторій ранкових відкриттів."""

        return OpeningRepository(self.session)

    @cached_property
    def closings(self) -> ClosingRepository:
        """Репозиторій вечірніх звітів."""

        return ClosingRepository(self.session)

    # ==========================================
    # TELEGRAM-ПОВІДОМЛЕННЯ
    # ==========================================

    @cached_property
    def notifications(
        self,
    ) -> NotificationRepository:
        """Репозиторій Telegram-повідомлень."""

        return NotificationRepository(
            self.session
        )

    @cached_property
    def daily_summaries(
        self,
    ) -> DailySummaryRepository:
        """Репозиторій живих підсумків."""

        return DailySummaryRepository(
            self.session
        )

    # ==========================================
    # СИСТЕМА
    # ==========================================

    @cached_property
    def audit(self) -> AuditRepository:
        """Репозиторій журналу дій."""

        return AuditRepository(self.session)

    @cached_property
    def settings(
        self,
    ) -> SystemSettingRepository:
        """Репозиторій системних налаштувань."""

        return SystemSettingRepository(
            self.session
        )

    # ==========================================
    # ДОПОМІЖНІ МЕТОДИ
    # ==========================================

    async def flush(self) -> None:
        """Застосовує зміни в межах транзакції."""

        await self.session.flush()

    async def commit(self) -> None:
        """Підтверджує поточну транзакцію."""

        await self.session.commit()

    async def rollback(self) -> None:
        """Відкочує поточну транзакцію."""

        await self.session.rollback()

    async def refresh(
        self,
        instance: object,
    ) -> None:
        """Оновлює об’єкт даними з бази."""

        await self.session.refresh(instance)

    async def close(self) -> None:
        """Закриває поточну сесію."""

        await self.session.close()


def create_repositories(
    session: AsyncSession,
) -> Repositories:
    """Створює контейнер репозиторіїв."""

    return Repositories(session)


RepositoryContainer = Repositories


__all__ = [
    # Контейнер
    "Repositories",
    "RepositoryContainer",
    "create_repositories",

    # Базовий репозиторій
    "BaseRepository",

    # Репозиторії
    "UserRepository",
    "StoreRepository",
    "BushRepository",
    "ClusterRepository",
    "BindingRepository",
    "ScheduleRepository",
    "OpeningRepository",
    "ClosingRepository",
    "InviteRepository",
    "NotificationRepository",
    "DailySummaryRepository",
    "AuditRepository",
    "SystemSettingRepository",

    # Графік
    "EffectiveSchedule",

    # Відкриття та закриття
    "OpeningPlan",
    "ClosingPlan",

    # Запрошення
    "CreatedInvite",
    "InviteActivationResult",

    # Повідомлення
    "NotificationReservation",

    # Живі підсумки
    "SummaryScope",
    "SummaryUpdateDecision",

    # Журнал дій
    "AuditContext",
    "AuditChangeSet",

    # Налаштування
    "SettingDefinition",
    "SettingUpdateResult",
]