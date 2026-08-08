from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import (
    UTC,
    date,
    datetime,
    time,
    timedelta,
)
from enum import Enum
from html import escape
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.database.models.cluster import Cluster
from app.database.models.enums import (
    AuditAction,
    EntityType,
)
from app.database.models.store import Store
from app.database.models.user import User
from app.repositories import (
    AuditContext,
    Repositories,
)
from app.services.access import (
    AccessService,
)


EnumType = TypeVar(
    "EnumType",
    bound=Enum,
)


@dataclass(slots=True, frozen=True)
class ClusterView:
    """
    Представлення кластера відкриття.
    """

    id: int

    name: str
    code: str | None

    opening_time: time

    control_deadline_minutes: int

    is_active: bool

    active_store_count: int
    total_store_count: int

    created_at: datetime | None
    updated_at: datetime | None

    raw_cluster: Cluster

    @property
    def opening_hour(self) -> int:
        return self.opening_time.hour

    @property
    def opening_time_text(self) -> str:
        return self.opening_time.strftime(
            "%H:%M"
        )

    @property
    def control_deadline_text(self) -> str:
        dummy_date = date(
            2000,
            1,
            1,
        )

        deadline = (
            datetime.combine(
                dummy_date,
                self.opening_time,
            )
            + timedelta(
                minutes=(
                    self.control_deadline_minutes
                )
            )
        )

        return deadline.strftime(
            "%H:%M"
        )


@dataclass(slots=True, frozen=True)
class ClusterCreateData:
    """
    Дані нового кластера.
    """

    opening_time: time

    name: str | None = None
    code: str | None = None

    control_deadline_minutes: int = 10

    is_active: bool = True


@dataclass(slots=True, frozen=True)
class ClusterChangeResult:
    """
    Результат створення або зміни кластера.
    """

    cluster: Cluster
    view: ClusterView

    was_created: bool
    was_changed: bool

    previous_values: dict[str, Any]
    current_values: dict[str, Any]

    audit_created: bool


@dataclass(slots=True, frozen=True)
class ClusterStatusChangeResult:
    """
    Результат активації або деактивації.
    """

    cluster: Cluster

    previous_active: bool
    current_active: bool

    was_changed: bool

    stores_detached: int

    changed_at: datetime
    changed_by_id: int

    reason: str


@dataclass(slots=True, frozen=True)
class ClusterStoreAssignmentResult:
    """
    Результат призначення ТТ у кластер.
    """

    store: Store

    previous_cluster_id: int | None
    current_cluster_id: int | None

    was_changed: bool

    changed_at: datetime
    changed_by_id: int

    reason: str


@dataclass(slots=True, frozen=True)
class BulkClusterAssignmentItem:
    """
    Результат призначення однієї ТТ.
    """

    store_id: int

    success: bool
    was_changed: bool

    previous_cluster_id: int | None
    current_cluster_id: int | None

    error: str | None


@dataclass(slots=True, frozen=True)
class BulkClusterAssignmentResult:
    """
    Результат масового призначення.
    """

    cluster_id: int | None

    total_count: int
    success_count: int
    failed_count: int
    changed_count: int
    unchanged_count: int

    items: tuple[
        BulkClusterAssignmentItem,
        ...,
    ]


@dataclass(slots=True, frozen=True)
class ClusterControlTimes:
    """
    Розраховані часові межі для ТТ.
    """

    business_date: date

    opening_at: datetime
    control_deadline_at: datetime

    late_from: datetime

    timezone_name: str

    @property
    def opening_time(self) -> time:
        return self.opening_at.timetz()

    @property
    def control_deadline_time(
        self,
    ) -> time:
        return (
            self.control_deadline_at
            .timetz()
        )


@dataclass(slots=True, frozen=True)
class ClusterLatenessResult:
    """
    Результат перевірки запізнення.
    """

    is_late: bool
    lateness_minutes: int

    actual_at: datetime
    opening_at: datetime
    control_deadline_at: datetime

    control_deadline_missed: bool


@dataclass(slots=True, frozen=True)
class DefaultClustersResult:
    """
    Результат створення базових кластерів.
    """

    created_count: int
    existing_count: int
    updated_count: int

    clusters: tuple[
        ClusterView,
        ...,
    ]


class ClusterService:
    """
    Сервіс кластерів відкриття магазинів.

    Базові кластери:

        07:00
        08:00
        09:00
        10:00

    Ключове правило:

    Магазин вважається запізненим одразу
    після часу відкриття.

    Приклад:

        кластер: 08:00

        08:00 -> вчасно
        08:01 -> 1 хв запізнення
        08:05 -> 5 хв запізнення

    Окремо існує контрольний дедлайн.

    Наприклад:

        відкриття: 08:00
        дедлайн контролю: 08:10

    Тобто магазин уже запізнився з 08:01,
    але після 08:10 система може піднімати
    додаткову тривогу адміністраторам.
    """

    DEFAULT_CONTROL_DEADLINE_MINUTES = 10

    DEFAULT_TIMEZONE = "Europe/Kyiv"

    DEFAULT_CLUSTER_TIMES = (
        time(7, 0),
        time(8, 0),
        time(9, 0),
        time(10, 0),
    )

    MAX_BULK_ASSIGNMENT = 1000

    def __init__(
        self,
        repositories: Repositories,
        *,
        access_service: AccessService | None = None,
    ) -> None:
        self.repositories = repositories
        self.session = repositories.session

        self.access = (
            access_service
            or AccessService(repositories)
        )

    # ==========================================
    # ОТРИМАННЯ ОДНОГО КЛАСТЕРА
    # ==========================================

    async def get_cluster(
        self,
        *,
        user: User,
        cluster_id: int,
        include_inactive: bool = False,
    ) -> ClusterView:
        """
        Повертає один кластер.
        """

        self.access.ensure_active_user(
            user
        )

        cluster = (
            await self.get_cluster_or_raise(
                cluster_id,
                include_inactive=(
                    include_inactive
                ),
            )
        )

        return await self.build_cluster_view(
            cluster
        )

    # ==========================================
    # СПИСОК КЛАСТЕРІВ
    # ==========================================

    async def get_clusters(
        self,
        *,
        user: User,
        active_only: bool = True,
    ) -> list[ClusterView]:
        """
        Повертає всі кластери.
        """

        self.access.ensure_active_user(
            user
        )

        conditions: list[Any] = []

        if (
            active_only
            and hasattr(
                Cluster,
                "is_active",
            )
        ):
            conditions.append(
                Cluster.is_active.is_(
                    True
                )
            )

        statement = (
            select(Cluster)
            .where(*conditions)
            .order_by(
                *self.cluster_order_columns()
            )
        )

        result = await self.session.scalars(
            statement
        )

        clusters = list(
            result.unique().all()
        )

        return [
            await self.build_cluster_view(
                cluster
            )
            for cluster in clusters
        ]

    # ==========================================
    # СТВОРЕННЯ КЛАСТЕРА
    # ==========================================

    async def create_cluster(
        self,
        *,
        actor: User,
        opening_time: time,
        name: str | None = None,
        code: str | None = None,
        control_deadline_minutes: int = (
            DEFAULT_CONTROL_DEADLINE_MINUTES
        ),
        is_active: bool = True,
        reason: str | None = None,
        created_at: datetime | None = None,
    ) -> ClusterChangeResult:
        """
        Створює новий кластер.
        """

        self.access.require_network_management(
            actor
        )

        now = created_at or datetime.now(
            UTC
        )

        self.validate_aware_datetime(
            now,
            field_name="created_at",
        )

        normalized_time = (
            self.normalize_opening_time(
                opening_time
            )
        )

        self.validate_control_deadline_minutes(
            control_deadline_minutes
        )

        normalized_name = (
            self.normalize_optional_text(
                name,
                max_length=100,
            )
            or self.default_cluster_name(
                normalized_time
            )
        )

        normalized_code = (
            self.normalize_optional_code(
                code
            )
            or self.default_cluster_code(
                normalized_time
            )
        )

        await self.ensure_unique_cluster(
            opening_time=normalized_time,
            code=normalized_code,
        )

        payload = {
            "name": normalized_name,
            "title": normalized_name,

            "code": normalized_code,
            "slug": normalized_code,

            "opening_time": normalized_time,
            "start_time": normalized_time,

            "hour": normalized_time.hour,
            "opening_hour": (
                normalized_time.hour
            ),

            "control_deadline_minutes": (
                control_deadline_minutes
            ),
            "deadline_minutes": (
                control_deadline_minutes
            ),
            "grace_minutes": (
                control_deadline_minutes
            ),

            "is_active": bool(
                is_active
            ),

            "created_by_id": actor.id,
            "updated_by_id": actor.id,

            "created_at": now,
            "updated_at": now,
        }

        repository_result = (
            await self.try_repository_create(
                payload
            )
        )

        if repository_result is not None:
            cluster = self.extract_cluster(
                repository_result
            )

        else:
            cluster = Cluster(
                **self.filter_model_payload(
                    payload
                )
            )

            self.session.add(
                cluster
            )

            await self.session.flush()

        if cluster is None:
            raise RuntimeError(
                "Не вдалося створити "
                "кластер."
            )

        current_values = (
            self.cluster_snapshot(
                cluster
            )
        )

        await self.log_cluster_change(
            actor=actor,
            cluster=cluster,
            description=(
                "Створено кластер відкриття"
            ),
            reason=reason,
            previous_values={},
            current_values=current_values,
            was_created=True,
        )

        return ClusterChangeResult(
            cluster=cluster,
            view=(
                await self.build_cluster_view(
                    cluster
                )
            ),
            was_created=True,
            was_changed=True,
            previous_values={},
            current_values=current_values,
            audit_created=True,
        )

    # ==========================================
    # РЕДАГУВАННЯ
    # ==========================================

    async def update_cluster(
        self,
        *,
        actor: User,
        cluster_id: int,
        opening_time: time | None = None,
        name: str | None = None,
        code: str | None = None,
        control_deadline_minutes: int | None = None,
        reason: str,
        updated_at: datetime | None = None,
    ) -> ClusterChangeResult:
        """
        Редагує кластер.
        """

        self.access.require_network_management(
            actor
        )

        now = updated_at or datetime.now(
            UTC
        )

        self.validate_aware_datetime(
            now,
            field_name="updated_at",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
                max_length=2000,
            )
        )

        cluster = (
            await self.get_cluster_or_raise(
                cluster_id,
                include_inactive=True,
                for_update=True,
            )
        )

        previous_values = (
            self.cluster_snapshot(
                cluster
            )
        )

        if opening_time is not None:
            normalized_time = (
                self.normalize_opening_time(
                    opening_time
                )
            )

            await self.ensure_unique_cluster(
                opening_time=(
                    normalized_time
                ),
                exclude_cluster_id=(
                    cluster.id
                ),
            )

            self.set_first_existing_attribute(
                cluster,
                normalized_time,
                "opening_time",
                "start_time",
            )

            self.set_first_existing_attribute(
                cluster,
                normalized_time.hour,
                "hour",
                "opening_hour",
            )

        if name is not None:
            normalized_name = (
                self.normalize_required_text(
                    name,
                    field_name=(
                        "Назва кластера"
                    ),
                    max_length=100,
                )
            )

            self.set_first_existing_attribute(
                cluster,
                normalized_name,
                "name",
                "title",
            )

        if code is not None:
            normalized_code = (
                self.normalize_optional_code(
                    code
                )
            )

            if normalized_code is None:
                raise ValueError(
                    "Код кластера "
                    "не може бути порожнім."
                )

            await self.ensure_unique_cluster(
                code=normalized_code,
                exclude_cluster_id=(
                    cluster.id
                ),
            )

            self.set_first_existing_attribute(
                cluster,
                normalized_code,
                "code",
                "slug",
            )

        if (
            control_deadline_minutes
            is not None
        ):
            self.validate_control_deadline_minutes(
                control_deadline_minutes
            )

            self.set_first_existing_attribute(
                cluster,
                control_deadline_minutes,
                "control_deadline_minutes",
                "deadline_minutes",
                "grace_minutes",
            )

        self.set_first_existing_attribute(
            cluster,
            actor.id,
            "updated_by_id",
            "modified_by_id",
        )

        self.set_first_existing_attribute(
            cluster,
            now,
            "updated_at",
            "modified_at",
        )

        self.session.add(
            cluster
        )

        await self.session.flush()

        current_values = (
            self.cluster_snapshot(
                cluster
            )
        )

        was_changed = (
            previous_values
            != current_values
        )

        if was_changed:
            await self.log_cluster_change(
                actor=actor,
                cluster=cluster,
                description=(
                    "Змінено кластер відкриття"
                ),
                reason=normalized_reason,
                previous_values=(
                    previous_values
                ),
                current_values=(
                    current_values
                ),
                was_created=False,
            )

        return ClusterChangeResult(
            cluster=cluster,
            view=(
                await self.build_cluster_view(
                    cluster
                )
            ),
            was_created=False,
            was_changed=was_changed,
            previous_values=previous_values,
            current_values=current_values,
            audit_created=was_changed,
        )

    # ==========================================
    # БАЗОВІ 07 / 08 / 09 / 10
    # ==========================================

    async def ensure_default_clusters(
        self,
        *,
        actor: User,
        control_deadline_minutes: int = (
            DEFAULT_CONTROL_DEADLINE_MINUTES
        ),
        update_existing: bool = True,
    ) -> DefaultClustersResult:
        """
        Створює базові кластери:

            07:00
            08:00
            09:00
            10:00
        """

        self.access.require_network_management(
            actor
        )

        self.validate_control_deadline_minutes(
            control_deadline_minutes
        )

        created_count = 0
        existing_count = 0
        updated_count = 0

        cluster_views: list[
            ClusterView
        ] = []

        for opening_time in (
            self.DEFAULT_CLUSTER_TIMES
        ):
            existing = (
                await self.find_cluster_by_time(
                    opening_time
                )
            )

            if existing is None:
                result = (
                    await self.create_cluster(
                        actor=actor,
                        opening_time=(
                            opening_time
                        ),
                        name=(
                            self
                            .default_cluster_name(
                                opening_time
                            )
                        ),
                        code=(
                            self
                            .default_cluster_code(
                                opening_time
                            )
                        ),
                        control_deadline_minutes=(
                            control_deadline_minutes
                        ),
                        is_active=True,
                        reason=(
                            "Початкова "
                            "конфігурація "
                            "кластерів"
                        ),
                    )
                )

                created_count += 1

                cluster_views.append(
                    result.view
                )

                continue

            existing_count += 1

            if update_existing:
                current_deadline = (
                    self.cluster_deadline_minutes(
                        existing
                    )
                )

                is_active = bool(
                    getattr(
                        existing,
                        "is_active",
                        True,
                    )
                )

                needs_update = (
                    current_deadline
                    != control_deadline_minutes
                    or not is_active
                )

                if needs_update:
                    self.set_first_existing_attribute(
                        existing,
                        control_deadline_minutes,
                        "control_deadline_minutes",
                        "deadline_minutes",
                        "grace_minutes",
                    )

                    self.set_first_existing_attribute(
                        existing,
                        True,
                        "is_active",
                        "active",
                    )

                    self.session.add(
                        existing
                    )

                    await self.session.flush()

                    updated_count += 1

            cluster_views.append(
                await self.build_cluster_view(
                    existing
                )
            )

        return DefaultClustersResult(
            created_count=created_count,
            existing_count=existing_count,
            updated_count=updated_count,
            clusters=tuple(
                cluster_views
            ),
        )

    # ==========================================
    # ПРИЗНАЧЕННЯ ТТ У КЛАСТЕР
    # ==========================================

    async def assign_store(
        self,
        *,
        actor: User,
        store_id: int,
        cluster_id: int | None,
        reason: str,
        changed_at: datetime | None = None,
    ) -> ClusterStoreAssignmentResult:
        """
        Призначає ТТ у кластер.

        cluster_id=None:
        прибирає кластер у магазину.
        """

        now = changed_at or datetime.now(
            UTC
        )

        self.validate_aware_datetime(
            now,
            field_name="changed_at",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
                max_length=2000,
            )
        )

        store = (
            await self.get_store_or_raise(
                store_id,
                for_update=True,
            )
        )

        decision = (
            await self.access.can_manage_store(
                actor,
                store.id,
            )
        )

        decision.raise_if_denied()

        if cluster_id is not None:
            await self.get_cluster_or_raise(
                cluster_id
            )

        previous_cluster_id = getattr(
            store,
            "cluster_id",
            None,
        )

        if (
            previous_cluster_id
            == cluster_id
        ):
            return (
                ClusterStoreAssignmentResult(
                    store=store,
                    previous_cluster_id=(
                        previous_cluster_id
                    ),
                    current_cluster_id=(
                        cluster_id
                    ),
                    was_changed=False,
                    changed_at=now,
                    changed_by_id=actor.id,
                    reason=normalized_reason,
                )
            )

        store.cluster_id = cluster_id

        self.set_first_existing_attribute(
            store,
            actor.id,
            "updated_by_id",
            "modified_by_id",
        )

        self.set_first_existing_attribute(
            store,
            now,
            "updated_at",
            "modified_at",
        )

        self.session.add(
            store
        )

        await self.session.flush()

        await self.log_store_cluster_change(
            actor=actor,
            store=store,
            reason=normalized_reason,
            previous_cluster_id=(
                previous_cluster_id
            ),
            current_cluster_id=(
                cluster_id
            ),
        )

        return ClusterStoreAssignmentResult(
            store=store,
            previous_cluster_id=(
                previous_cluster_id
            ),
            current_cluster_id=(
                cluster_id
            ),
            was_changed=True,
            changed_at=now,
            changed_by_id=actor.id,
            reason=normalized_reason,
        )

    # ==========================================
    # МАСОВЕ ПРИЗНАЧЕННЯ
    # ==========================================

    async def bulk_assign_stores(
        self,
        *,
        actor: User,
        store_ids: list[int] | set[int],
        cluster_id: int | None,
        reason: str,
        changed_at: datetime | None = None,
    ) -> BulkClusterAssignmentResult:
        """
        Масово призначає ТТ у кластер.
        """

        normalized_ids = self.normalize_ids(
            store_ids
        )

        if (
            len(normalized_ids)
            > self.MAX_BULK_ASSIGNMENT
        ):
            raise ValueError(
                "За один раз можна "
                "перепризначити не більше "
                f"{self.MAX_BULK_ASSIGNMENT} ТТ."
            )

        if cluster_id is not None:
            await self.get_cluster_or_raise(
                cluster_id
            )

        now = changed_at or datetime.now(
            UTC
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
                max_length=2000,
            )
        )

        items: list[
            BulkClusterAssignmentItem
        ] = []

        for store_id in normalized_ids:
            try:
                result = await self.assign_store(
                    actor=actor,
                    store_id=store_id,
                    cluster_id=cluster_id,
                    reason=normalized_reason,
                    changed_at=now,
                )

                items.append(
                    BulkClusterAssignmentItem(
                        store_id=store_id,
                        success=True,
                        was_changed=(
                            result.was_changed
                        ),
                        previous_cluster_id=(
                            result
                            .previous_cluster_id
                        ),
                        current_cluster_id=(
                            result
                            .current_cluster_id
                        ),
                        error=None,
                    )
                )

            except Exception as error:
                items.append(
                    BulkClusterAssignmentItem(
                        store_id=store_id,
                        success=False,
                        was_changed=False,
                        previous_cluster_id=None,
                        current_cluster_id=(
                            cluster_id
                        ),
                        error=str(error),
                    )
                )

        return BulkClusterAssignmentResult(
            cluster_id=cluster_id,

            total_count=len(items),

            success_count=sum(
                item.success
                for item in items
            ),

            failed_count=sum(
                not item.success
                for item in items
            ),

            changed_count=sum(
                (
                    item.success
                    and item.was_changed
                )
                for item in items
            ),

            unchanged_count=sum(
                (
                    item.success
                    and not item.was_changed
                )
                for item in items
            ),

            items=tuple(items),
        )

    # ==========================================
    # ТТ КЛАСТЕРА
    # ==========================================

    async def get_cluster_stores(
        self,
        *,
        user: User,
        cluster_id: int,
        active_only: bool = True,
    ) -> list[Store]:
        """
        Повертає ТТ конкретного кластера.
        """

        self.access.ensure_active_user(
            user
        )

        await self.get_cluster_or_raise(
            cluster_id,
            include_inactive=True,
        )

        conditions: list[Any] = [
            Store.cluster_id
            == cluster_id
        ]

        if (
            active_only
            and hasattr(
                Store,
                "is_active",
            )
        ):
            conditions.append(
                Store.is_active.is_(
                    True
                )
            )

        statement = (
            select(Store)
            .where(*conditions)
            .order_by(
                *self.store_order_columns()
            )
        )

        result = await self.session.scalars(
            statement
        )

        stores = list(
            result.unique().all()
        )

        visible: list[Store] = []

        for store in stores:
            try:
                await self.access.require_store_view(
                    user,
                    store.id,
                )

                visible.append(
                    store
                )

            except Exception:
                continue

        return visible

    # ==========================================
    # ЧАС КОНТРОЛЮ
    # ==========================================

    def calculate_control_times(
        self,
        *,
        cluster: Cluster | ClusterView,
        business_date: date,
        timezone_name: str = (
            DEFAULT_TIMEZONE
        ),
    ) -> ClusterControlTimes:
        """
        Розраховує час відкриття і дедлайн.

        Запізнення починається одразу після
        планового часу відкриття.
        """

        timezone = ZoneInfo(
            timezone_name
        )

        if isinstance(
            cluster,
            ClusterView,
        ):
            opening_time = (
                cluster.opening_time
            )

            deadline_minutes = (
                cluster
                .control_deadline_minutes
            )

        else:
            opening_time = (
                self.cluster_opening_time(
                    cluster
                )
            )

            deadline_minutes = (
                self.cluster_deadline_minutes(
                    cluster
                )
            )

        opening_at = datetime.combine(
            business_date,
            opening_time,
            tzinfo=timezone,
        )

        control_deadline_at = (
            opening_at
            + timedelta(
                minutes=deadline_minutes
            )
        )

        return ClusterControlTimes(
            business_date=business_date,
            opening_at=opening_at,
            control_deadline_at=(
                control_deadline_at
            ),
            late_from=opening_at,
            timezone_name=timezone_name,
        )

    # ==========================================
    # РОЗРАХУНОК ЗАПІЗНЕННЯ
    # ==========================================

    def calculate_lateness(
        self,
        *,
        actual_at: datetime,
        cluster: Cluster | ClusterView,
        business_date: date,
        timezone_name: str = (
            DEFAULT_TIMEZONE
        ),
    ) -> ClusterLatenessResult:
        """
        Рахує хвилини запізнення.

        Приклад:

            план: 08:00
            факт: 08:00 -> 0 хв
            факт: 08:01 -> 1 хв
            факт: 08:13 -> 13 хв
        """

        self.validate_aware_datetime(
            actual_at,
            field_name="actual_at",
        )

        control = (
            self.calculate_control_times(
                cluster=cluster,
                business_date=(
                    business_date
                ),
                timezone_name=(
                    timezone_name
                ),
            )
        )

        timezone = ZoneInfo(
            timezone_name
        )

        local_actual = (
            actual_at.astimezone(
                timezone
            )
        )

        difference_seconds = (
            local_actual
            - control.opening_at
        ).total_seconds()

        if difference_seconds <= 0:
            lateness_minutes = 0

        else:
            # 08:00:01 ще належить першій
            # хвилині запізнення.
            lateness_minutes = int(
                (
                    difference_seconds
                    + 59
                )
                // 60
            )

        is_late = (
            lateness_minutes > 0
        )

        deadline_missed = (
            local_actual
            > control.control_deadline_at
        )

        return ClusterLatenessResult(
            is_late=is_late,
            lateness_minutes=(
                lateness_minutes
            ),
            actual_at=local_actual,
            opening_at=(
                control.opening_at
            ),
            control_deadline_at=(
                control
                .control_deadline_at
            ),
            control_deadline_missed=(
                deadline_missed
            ),
        )

    # ==========================================
    # ДЕАКТИВАЦІЯ
    # ==========================================

    async def deactivate_cluster(
        self,
        *,
        actor: User,
        cluster_id: int,
        reason: str,
        detach_stores: bool = False,
        changed_at: datetime | None = None,
    ) -> ClusterStatusChangeResult:
        """
        Деактивує кластер.
        """

        return await self.set_active_state(
            actor=actor,
            cluster_id=cluster_id,
            is_active=False,
            reason=reason,
            detach_stores=(
                detach_stores
            ),
            changed_at=changed_at,
        )

    async def reactivate_cluster(
        self,
        *,
        actor: User,
        cluster_id: int,
        reason: str,
        changed_at: datetime | None = None,
    ) -> ClusterStatusChangeResult:
        """
        Повторно активує кластер.
        """

        return await self.set_active_state(
            actor=actor,
            cluster_id=cluster_id,
            is_active=True,
            reason=reason,
            detach_stores=False,
            changed_at=changed_at,
        )

    async def set_active_state(
        self,
        *,
        actor: User,
        cluster_id: int,
        is_active: bool,
        reason: str,
        detach_stores: bool,
        changed_at: datetime | None,
    ) -> ClusterStatusChangeResult:
        """
        Змінює активність кластера.
        """

        self.access.require_network_management(
            actor
        )

        now = changed_at or datetime.now(
            UTC
        )

        self.validate_aware_datetime(
            now,
            field_name="changed_at",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
                max_length=2000,
            )
        )

        cluster = (
            await self.get_cluster_or_raise(
                cluster_id,
                include_inactive=True,
                for_update=True,
            )
        )

        previous_active = bool(
            getattr(
                cluster,
                "is_active",
                True,
            )
        )

        if previous_active == is_active:
            return (
                ClusterStatusChangeResult(
                    cluster=cluster,
                    previous_active=(
                        previous_active
                    ),
                    current_active=(
                        is_active
                    ),
                    was_changed=False,
                    stores_detached=0,
                    changed_at=now,
                    changed_by_id=actor.id,
                    reason=normalized_reason,
                )
            )

        self.set_first_existing_attribute(
            cluster,
            is_active,
            "is_active",
            "active",
        )

        if is_active:
            self.set_first_existing_attribute(
                cluster,
                None,
                "deactivated_at",
            )

            self.set_first_existing_attribute(
                cluster,
                None,
                "deactivated_by_id",
            )

        else:
            self.set_first_existing_attribute(
                cluster,
                now,
                "deactivated_at",
            )

            self.set_first_existing_attribute(
                cluster,
                actor.id,
                "deactivated_by_id",
            )

        self.set_first_existing_attribute(
            cluster,
            normalized_reason,
            "deactivation_reason",
            "status_reason",
        )

        self.set_first_existing_attribute(
            cluster,
            actor.id,
            "updated_by_id",
            "modified_by_id",
        )

        self.set_first_existing_attribute(
            cluster,
            now,
            "updated_at",
            "modified_at",
        )

        self.session.add(
            cluster
        )

        await self.session.flush()

        stores_detached = 0

        if (
            not is_active
            and detach_stores
        ):
            stores_detached = (
                await self.detach_all_stores(
                    cluster_id=cluster.id,
                    actor=actor,
                    changed_at=now,
                )
            )

        await self.log_cluster_change(
            actor=actor,
            cluster=cluster,
            description=(
                "Кластер активовано"
                if is_active
                else "Кластер деактивовано"
            ),
            reason=normalized_reason,
            previous_values={
                "is_active": (
                    previous_active
                ),
            },
            current_values={
                "is_active": is_active,
                "stores_detached": (
                    stores_detached
                ),
            },
            was_created=False,
        )

        return ClusterStatusChangeResult(
            cluster=cluster,
            previous_active=(
                previous_active
            ),
            current_active=is_active,
            was_changed=True,
            stores_detached=(
                stores_detached
            ),
            changed_at=now,
            changed_by_id=actor.id,
            reason=normalized_reason,
        )

    # ==========================================
    # ВІД’ЄДНАННЯ ТТ
    # ==========================================

    async def detach_all_stores(
        self,
        *,
        cluster_id: int,
        actor: User,
        changed_at: datetime,
    ) -> int:
        """
        Прибирає кластер у всіх ТТ.
        """

        statement = (
            select(Store)
            .where(
                Store.cluster_id
                == cluster_id
            )
            .with_for_update()
        )

        result = await self.session.scalars(
            statement
        )

        stores = list(
            result.unique().all()
        )

        for store in stores:
            store.cluster_id = None

            self.set_first_existing_attribute(
                store,
                actor.id,
                "updated_by_id",
                "modified_by_id",
            )

            self.set_first_existing_attribute(
                store,
                changed_at,
                "updated_at",
                "modified_at",
            )

            self.session.add(
                store
            )

        if stores:
            await self.session.flush()

        return len(stores)

    # ==========================================
    # ПОШУК ПО ЧАСУ
    # ==========================================

    async def find_cluster_by_time(
        self,
        opening_time: time,
    ) -> Cluster | None:
        """
        Шукає кластер за часом відкриття.
        """

        normalized = (
            self.normalize_opening_time(
                opening_time
            )
        )

        opening_column = (
            self.model_column(
                "opening_time",
                "start_time",
            )
        )

        if opening_column is not None:
            statement = (
                select(Cluster)
                .where(
                    opening_column
                    == normalized
                )
                .limit(1)
            )

            result = (
                await self.session.scalar(
                    statement
                )
            )

            if result is not None:
                return result

        hour_column = self.model_column(
            "hour",
            "opening_hour",
        )

        if hour_column is not None:
            statement = (
                select(Cluster)
                .where(
                    hour_column
                    == normalized.hour
                )
                .limit(1)
            )

            return await self.session.scalar(
                statement
            )

        return None

    # ==========================================
    # УНІКАЛЬНІСТЬ
    # ==========================================

    async def ensure_unique_cluster(
        self,
        *,
        opening_time: time | None = None,
        code: str | None = None,
        exclude_cluster_id: int | None = None,
    ) -> None:
        """
        Перевіряє унікальність кластера.
        """

        if opening_time is not None:
            existing = (
                await self.find_cluster_by_time(
                    opening_time
                )
            )

            if (
                existing is not None
                and existing.id
                != exclude_cluster_id
            ):
                raise ValueError(
                    "Кластер із таким часом "
                    "відкриття вже існує."
                )

        if code is not None:
            code_column = (
                self.model_column(
                    "code",
                    "slug",
                )
            )

            if code_column is not None:
                statement = (
                    select(Cluster)
                    .where(
                        func.lower(
                            code_column
                        )
                        == code.lower()
                    )
                    .limit(1)
                )

                existing = (
                    await self.session.scalar(
                        statement
                    )
                )

                if (
                    existing is not None
                    and existing.id
                    != exclude_cluster_id
                ):
                    raise ValueError(
                        "Кластер із таким "
                        "кодом уже існує."
                    )

    # ==========================================
    # VIEW
    # ==========================================

    async def build_cluster_view(
        self,
        cluster: Cluster,
    ) -> ClusterView:
        """
        Формує ClusterView.
        """

        store_statement = (
            select(Store)
            .where(
                Store.cluster_id
                == cluster.id
            )
        )

        store_result = (
            await self.session.scalars(
                store_statement
            )
        )

        stores = list(
            store_result.unique().all()
        )

        active_count = sum(
            bool(
                getattr(
                    store,
                    "is_active",
                    True,
                )
            )
            for store in stores
        )

        return ClusterView(
            id=cluster.id,

            name=self.cluster_name(
                cluster
            ),

            code=self.get_text_attribute(
                cluster,
                "code",
                "slug",
            ),

            opening_time=(
                self.cluster_opening_time(
                    cluster
                )
            ),

            control_deadline_minutes=(
                self.cluster_deadline_minutes(
                    cluster
                )
            ),

            is_active=bool(
                getattr(
                    cluster,
                    "is_active",
                    True,
                )
            ),

            active_store_count=(
                active_count
            ),

            total_store_count=len(
                stores
            ),

            created_at=getattr(
                cluster,
                "created_at",
                None,
            ),

            updated_at=getattr(
                cluster,
                "updated_at",
                None,
            ),

            raw_cluster=cluster,
        )

    # ==========================================
    # SNAPSHOT
    # ==========================================

    def cluster_snapshot(
        self,
        cluster: Cluster,
    ) -> dict[str, Any]:
        """
        Формує знімок кластера.
        """

        opening_time = (
            self.cluster_opening_time(
                cluster
            )
        )

        return {
            "id": cluster.id,

            "name": self.cluster_name(
                cluster
            ),

            "code": self.get_text_attribute(
                cluster,
                "code",
                "slug",
            ),

            "opening_time": (
                opening_time.strftime(
                    "%H:%M"
                )
            ),

            "opening_hour": (
                opening_time.hour
            ),

            "control_deadline_minutes": (
                self.cluster_deadline_minutes(
                    cluster
                )
            ),

            "is_active": bool(
                getattr(
                    cluster,
                    "is_active",
                    True,
                )
            ),
        }

    # ==========================================
    # AUDIT
    # ==========================================

    async def log_cluster_change(
        self,
        *,
        actor: User,
        cluster: Cluster,
        description: str,
        reason: str | None,
        previous_values: dict[str, Any],
        current_values: dict[str, Any],
        was_created: bool,
    ) -> None:
        """
        Записує зміну кластера.
        """

        action = (
            self.resolve_audit_action(
                (
                    "create"
                    if was_created
                    else "update"
                ),
                (
                    "created"
                    if was_created
                    else "changed"
                ),
            )
        )

        entity_type = (
            self.resolve_entity_type(
                "cluster",
                "schedule",
                "system",
            )
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=cluster.id,

            context=AuditContext(
                actor_user_id=actor.id,

                reason=(
                    self
                    .normalize_optional_text(
                        reason,
                        max_length=2000,
                    )
                ),

                description=description,

                source="telegram_bot",
            ),

            old_values=(
                previous_values
            ),

            new_values={
                **current_values,
                "cluster_id": cluster.id,
            },
        )

    async def log_store_cluster_change(
        self,
        *,
        actor: User,
        store: Store,
        reason: str,
        previous_cluster_id: int | None,
        current_cluster_id: int | None,
    ) -> None:
        """
        Записує зміну кластера ТТ.
        """

        action = (
            self.resolve_audit_action(
                "update",
                "changed",
            )
        )

        entity_type = (
            self.resolve_entity_type(
                "store",
                "shop",
            )
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=store.id,

            context=AuditContext(
                actor_user_id=actor.id,
                reason=reason,
                description=(
                    "Змінено кластер "
                    "торгової точки"
                ),
                source="telegram_bot",
            ),

            old_values={
                "store_id": store.id,
                "cluster_id": (
                    previous_cluster_id
                ),
            },

            new_values={
                "store_id": store.id,
                "cluster_id": (
                    current_cluster_id
                ),
            },
        )

    # ==========================================
    # МОДЕЛІ
    # ==========================================

    async def get_cluster_or_raise(
        self,
        cluster_id: int,
        *,
        include_inactive: bool = False,
        for_update: bool = False,
    ) -> Cluster:
        """
        Повертає кластер за ID.
        """

        if cluster_id <= 0:
            raise ValueError(
                "ID кластера повинен бути "
                "більшим за нуль."
            )

        statement = (
            select(Cluster)
            .where(
                Cluster.id
                == cluster_id
            )
        )

        if for_update:
            statement = (
                statement.with_for_update()
            )

        cluster = (
            await self.session.scalar(
                statement
            )
        )

        if cluster is None:
            raise ValueError(
                "Кластер не знайдено."
            )

        if (
            not include_inactive
            and not bool(
                getattr(
                    cluster,
                    "is_active",
                    True,
                )
            )
        ):
            raise ValueError(
                "Кластер неактивний."
            )

        return cluster

    async def get_store_or_raise(
        self,
        store_id: int,
        *,
        for_update: bool = False,
    ) -> Store:
        """
        Повертає ТТ.
        """

        if store_id <= 0:
            raise ValueError(
                "ID ТТ повинен бути "
                "більшим за нуль."
            )

        statement = (
            select(Store)
            .where(
                Store.id == store_id
            )
        )

        if for_update:
            statement = (
                statement.with_for_update()
            )

        store = (
            await self.session.scalar(
                statement
            )
        )

        if store is None:
            raise ValueError(
                "Торгову точку не знайдено."
            )

        return store

    # ==========================================
    # REPOSITORY CREATE
    # ==========================================

    async def try_repository_create(
        self,
        payload: dict[str, Any],
    ) -> Any | None:
        """
        Пробує створити кластер
        через ClusterRepository.
        """

        repository = getattr(
            self.repositories,
            "clusters",
            None,
        )

        if repository is None:
            return None

        for method_name in (
            "create_cluster",
            "create",
            "add_cluster",
        ):
            method = getattr(
                repository,
                method_name,
                None,
            )

            if not callable(
                method
            ):
                continue

            result = method(
                **self.filter_method_kwargs(
                    method,
                    payload,
                )
            )

            if inspect.isawaitable(
                result
            ):
                result = await result

            return result

        return None

    # ==========================================
    # MODEL HELPERS
    # ==========================================

    @staticmethod
    def model_column(
        *names: str,
    ) -> Any | None:
        """
        Повертає першу колонку Cluster.
        """

        for name in names:
            column = getattr(
                Cluster,
                name,
                None,
            )

            if column is not None:
                return column

        return None

    @staticmethod
    def filter_model_payload(
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Залишає реальні поля Cluster.
        """

        columns = {
            column.key
            for column
            in Cluster.__mapper__.columns
        }

        return {
            key: value
            for key, value
            in payload.items()
            if key in columns
        }

    @staticmethod
    def filter_method_kwargs(
        method: Any,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Фільтрує kwargs за сигнатурою.
        """

        signature = inspect.signature(
            method
        )

        accepts_kwargs = any(
            parameter.kind
            == inspect.Parameter.VAR_KEYWORD
            for parameter
            in signature.parameters.values()
        )

        if accepts_kwargs:
            return dict(
                payload
            )

        return {
            key: value
            for key, value
            in payload.items()
            if key in signature.parameters
        }

    @staticmethod
    def extract_cluster(
        result: Any,
    ) -> Cluster | None:
        """
        Витягує Cluster із результату.
        """

        if isinstance(
            result,
            Cluster,
        ):
            return result

        if isinstance(
            result,
            tuple,
        ):
            for item in result:
                if isinstance(
                    item,
                    Cluster,
                ):
                    return item

        for field_name in (
            "cluster",
            "entity",
            "model",
            "result",
        ):
            value = getattr(
                result,
                field_name,
                None,
            )

            if isinstance(
                value,
                Cluster,
            ):
                return value

        return None

    # ==========================================
    # OPENING TIME
    # ==========================================

    @staticmethod
    def cluster_opening_time(
        cluster: Cluster,
    ) -> time:
        """
        Повертає час відкриття.
        """

        for field_name in (
            "opening_time",
            "start_time",
        ):
            value = getattr(
                cluster,
                field_name,
                None,
            )

            if isinstance(
                value,
                time,
            ):
                return (
                    ClusterService
                    .normalize_opening_time(
                        value
                    )
                )

        for field_name in (
            "hour",
            "opening_hour",
        ):
            value = getattr(
                cluster,
                field_name,
                None,
            )

            if value is None:
                continue

            try:
                hour = int(value)

            except (
                TypeError,
                ValueError,
            ):
                continue

            if 0 <= hour <= 23:
                return time(
                    hour,
                    0,
                )

        raise ValueError(
            "У кластері не задано "
            "час відкриття."
        )

    @classmethod
    def cluster_deadline_minutes(
        cls,
        cluster: Cluster,
    ) -> int:
        """
        Повертає хвилини до
        контрольного дедлайну.
        """

        for field_name in (
            "control_deadline_minutes",
            "deadline_minutes",
            "grace_minutes",
        ):
            value = getattr(
                cluster,
                field_name,
                None,
            )

            if value is None:
                continue

            try:
                minutes = int(
                    value
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

            if 0 <= minutes <= 180:
                return minutes

        return (
            cls
            .DEFAULT_CONTROL_DEADLINE_MINUTES
        )

    # ==========================================
    # ENUM
    # ==========================================

    @classmethod
    def resolve_audit_action(
        cls,
        *names: str,
    ) -> AuditAction:
        """
        Повертає AuditAction.
        """

        result = (
            cls.resolve_enum_member(
                AuditAction,
                *names,
                default=None,
            )
        )

        if result is not None:
            return result

        result = (
            cls.resolve_enum_member(
                AuditAction,
                "update",
                "changed",
                default=None,
            )
        )

        if result is None:
            raise ValueError(
                "Не знайдено AuditAction."
            )

        return result

    @classmethod
    def resolve_entity_type(
        cls,
        *names: str,
    ) -> EntityType:
        """
        Повертає EntityType.
        """

        result = (
            cls.resolve_enum_member(
                EntityType,
                *names,
                default=None,
            )
        )

        if result is not None:
            return result

        result = (
            cls.resolve_enum_member(
                EntityType,
                "system",
                default=None,
            )
        )

        if result is None:
            raise ValueError(
                "Не знайдено EntityType."
            )

        return result

    @staticmethod
    def resolve_enum_member(
        enum_class: type[EnumType],
        *names: str,
        default: EnumType | None = None,
    ) -> EnumType | None:
        """
        Шукає enum за name/value.
        """

        normalized = {
            name.strip().lower()
            for name in names
            if name.strip()
        }

        for item in enum_class:
            candidates = {
                item.name.lower(),
                str(
                    item.value
                ).lower(),
            }

            if candidates.intersection(
                normalized
            ):
                return item

        return default

    # ==========================================
    # SORT
    # ==========================================

    @staticmethod
    def cluster_order_columns(
    ) -> tuple[Any, ...]:
        """
        Сортування кластерів за часом.
        """

        opening_column = (
            ClusterService.model_column(
                "opening_time",
                "start_time",
            )
        )

        if opening_column is not None:
            return (
                opening_column.asc(),
                Cluster.id.asc(),
            )

        hour_column = (
            ClusterService.model_column(
                "hour",
                "opening_hour",
            )
        )

        if hour_column is not None:
            return (
                hour_column.asc(),
                Cluster.id.asc(),
            )

        return (
            Cluster.id.asc(),
        )

    @staticmethod
    def store_order_columns(
    ) -> tuple[Any, ...]:
        """
        Сортування ТТ.
        """

        number_column = getattr(
            Store,
            "store_number",
            None,
        )

        if number_column is not None:
            return (
                number_column.asc(),
                Store.id.asc(),
            )

        return (
            Store.id.asc(),
        )

    # ==========================================
    # ATTRIBUTES
    # ==========================================

    @staticmethod
    def set_first_existing_attribute(
        target: Any,
        value: Any,
        *names: str,
    ) -> bool:
        """
        Записує перший існуючий атрибут.
        """

        for name in names:
            if hasattr(
                target,
                name,
            ):
                setattr(
                    target,
                    name,
                    value,
                )

                return True

        return False

    @staticmethod
    def get_text_attribute(
        target: Any,
        *names: str,
    ) -> str | None:
        """
        Читає текстове поле.
        """

        if target is None:
            return None

        for name in names:
            value = getattr(
                target,
                name,
                None,
            )

            if value is None:
                continue

            normalized = str(
                value
            ).strip()

            if normalized:
                return normalized

        return None

    @classmethod
    def cluster_name(
        cls,
        cluster: Cluster,
    ) -> str:
        """
        Повертає назву кластера.
        """

        for field_name in (
            "name",
            "title",
        ):
            value = getattr(
                cluster,
                field_name,
                None,
            )

            if value:
                return str(
                    value
                )

        opening_time = (
            cls.cluster_opening_time(
                cluster
            )
        )

        return cls.default_cluster_name(
            opening_time
        )

    # ==========================================
    # DEFAULT NAME / CODE
    # ==========================================

    @staticmethod
    def default_cluster_name(
        opening_time: time,
    ) -> str:
        """
        Наприклад:
        Кластер 08:00
        """

        return (
            "Кластер "
            f"{opening_time.strftime('%H:%M')}"
        )

    @staticmethod
    def default_cluster_code(
        opening_time: time,
    ) -> str:
        """
        Наприклад:
        CLUSTER_08
        """

        return (
            "CLUSTER_"
            f"{opening_time.hour:02d}"
        )

    # ==========================================
    # VALIDATION
    # ==========================================

    @staticmethod
    def normalize_opening_time(
        value: time,
    ) -> time:
        """
        Нормалізує час до HH:MM:00.
        """

        if not isinstance(
            value,
            time,
        ):
            raise ValueError(
                "Час відкриття має бути "
                "datetime.time."
            )

        return time(
            value.hour,
            value.minute,
        )

    @staticmethod
    def validate_control_deadline_minutes(
        value: int,
    ) -> None:
        """
        Перевіряє дедлайн контролю.
        """

        if isinstance(
            value,
            bool,
        ):
            raise ValueError(
                "Дедлайн повинен бути "
                "числом хвилин."
            )

        if value < 0 or value > 180:
            raise ValueError(
                "Контрольний дедлайн "
                "повинен бути від 0 "
                "до 180 хвилин."
            )

    @staticmethod
    def normalize_optional_code(
        value: str | None,
    ) -> str | None:
        """
        Нормалізує код кластера.
        """

        if value is None:
            return None

        normalized = (
            value.strip()
            .upper()
            .replace(
                " ",
                "_",
            )
        )

        if not normalized:
            return None

        if len(normalized) > 50:
            raise ValueError(
                "Код кластера "
                "занадто довгий."
            )

        return normalized

    @staticmethod
    def normalize_required_text(
        value: str,
        *,
        field_name: str,
        max_length: int,
    ) -> str:
        """
        Нормалізує обов’язковий текст.
        """

        normalized = " ".join(
            value.strip().split()
        )

        if not normalized:
            raise ValueError(
                f"{field_name} "
                "не може бути порожнім."
            )

        if len(normalized) > max_length:
            raise ValueError(
                f"{field_name} "
                "занадто довгий."
            )

        return normalized

    @staticmethod
    def normalize_optional_text(
        value: str | None,
        *,
        max_length: int = 2000,
    ) -> str | None:
        """
        Нормалізує необов’язковий текст.
        """

        if value is None:
            return None

        normalized = " ".join(
            value.strip().split()
        )

        if not normalized:
            return None

        if len(normalized) > max_length:
            raise ValueError(
                "Текст занадто довгий."
            )

        return normalized

    @staticmethod
    def validate_aware_datetime(
        value: datetime,
        *,
        field_name: str,
    ) -> None:
        """
        Перевіряє timezone.
        """

        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                f"{field_name} повинен "
                "містити часовий пояс."
            )

    @staticmethod
    def normalize_ids(
        values: list[int] | set[int],
    ) -> list[int]:
        """
        Нормалізує список ID ТТ.
        """

        result: set[int] = set()

        for value in values:
            try:
                store_id = int(
                    value
                )

            except (
                TypeError,
                ValueError,
            ) as error:
                raise ValueError(
                    "Некоректний ID ТТ."
                ) from error

            if store_id <= 0:
                raise ValueError(
                    "ID ТТ повинен бути "
                    "більшим за нуль."
                )

            result.add(
                store_id
            )

        if not result:
            raise ValueError(
                "Список ТТ порожній."
            )

        return sorted(
            result
        )

    # ==========================================
    # TELEGRAM FORMAT
    # ==========================================

    @staticmethod
    def format_cluster(
        cluster: ClusterView,
    ) -> str:
        """
        Картка кластера для Telegram.
        """

        status = (
            "активний ✅"
            if cluster.is_active
            else "неактивний ❌"
        )

        return "\n".join(
            [
                (
                    "⏰ <b>"
                    f"{escape(cluster.name)}"
                    "</b>"
                ),
                "",
                (
                    "Час відкриття: "
                    "<b>"
                    f"{cluster.opening_time_text}"
                    "</b>"
                ),
                (
                    "Запізнення рахується: "
                    "<b>з першої хвилини</b>"
                ),
                (
                    "Контрольний дедлайн: "
                    "<b>"
                    f"{cluster.control_deadline_text}"
                    "</b>"
                ),
                (
                    "Статус: "
                    f"<b>{status}</b>"
                ),
                "",
                (
                    "🏪 Активних ТТ: "
                    "<b>"
                    f"{cluster.active_store_count}"
                    "</b>"
                ),
                (
                    "📦 Усього ТТ: "
                    "<b>"
                    f"{cluster.total_store_count}"
                    "</b>"
                ),
            ]
        )

    @staticmethod
    def format_lateness(
        result: ClusterLatenessResult,
    ) -> str:
        """
        Форматує результат запізнення.
        """

        if not result.is_late:
            return (
                "✅ Магазин відкрито вчасно."
            )

        lines = [
            (
                "⚠️ <b>Зафіксовано "
                "запізнення</b>"
            ),
            "",
            (
                "План: "
                "<b>"
                f"{result.opening_at.strftime('%H:%M')}"
                "</b>"
            ),
            (
                "Факт: "
                "<b>"
                f"{result.actual_at.strftime('%H:%M')}"
                "</b>"
            ),
            (
                "Запізнення: "
                "<b>"
                f"{result.lateness_minutes} хв"
                "</b>"
            ),
        ]

        if result.control_deadline_missed:
            lines.append(
                "🚨 Контрольний дедлайн "
                "<b>пропущено</b>"
            )

        return "\n".join(
            lines
        )