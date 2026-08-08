from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from enum import Enum
from html import escape
from typing import Any, TypeVar

from sqlalchemy import delete, func, or_, select

from app.database.models.audit_log import AuditLog
from app.database.models.enums import (
    AuditAction,
    EntityType,
)
from app.database.models.store import Store
from app.database.models.user import User
from app.repositories import Repositories
from app.services.access import (
    AccessDeniedError,
    AccessService,
)


EnumType = TypeVar(
    "EnumType",
    bound=Enum,
)


@dataclass(slots=True, frozen=True)
class AuditFilter:
    """
    Фільтри журналу дій.
    """

    action: AuditAction | str | None = None
    entity_type: EntityType | str | None = None
    entity_id: int | None = None

    actor_user_id: int | None = None

    store_id: int | None = None
    bush_id: int | None = None

    business_date_from: date | None = None
    business_date_to: date | None = None

    created_from: datetime | None = None
    created_to: datetime | None = None

    source: str | None = None
    search_text: str | None = None


@dataclass(slots=True, frozen=True)
class AuditEntryView:
    """
    Підготовлений запис журналу.
    """

    id: int

    action: str
    action_text: str

    entity_type: str
    entity_type_text: str
    entity_id: int | None

    actor_user_id: int | None
    actor_name: str

    store_id: int | None
    bush_id: int | None

    business_date: date | None
    created_at: datetime | None

    description: str | None
    reason: str | None
    source: str | None

    old_values: dict[str, Any]
    new_values: dict[str, Any]
    details: dict[str, Any]

    raw_log: AuditLog


@dataclass(slots=True, frozen=True)
class AuditPage:
    """
    Сторінка журналу дій.
    """

    page: int
    page_size: int

    total_count: int
    has_previous: bool
    has_next: bool

    items: tuple[
        AuditEntryView,
        ...,
    ]

    truncated: bool = False


@dataclass(slots=True, frozen=True)
class AuditExportRow:
    """
    Один рядок майбутнього Excel-звіту.
    """

    record_id: int
    created_at: datetime | None
    business_date: date | None

    action: str
    entity_type: str
    entity_id: int | None

    actor_user_id: int | None
    actor_name: str

    store_id: int | None
    bush_id: int | None

    description: str | None
    reason: str | None
    source: str | None

    old_values: str
    new_values: str
    details: str


@dataclass(slots=True, frozen=True)
class AuditStatistics:
    """
    Статистика журналу.
    """

    total_count: int
    system_actions_count: int
    user_actions_count: int

    actions: dict[str, int]
    entity_types: dict[str, int]
    sources: dict[str, int]


class AuditService:
    """
    Сервіс журналу дій.

    Доступ:

    ROOT_ADMIN і DIRECTOR:
        бачать журнал усієї мережі.

    BUSH_ADMIN:
        бачить журнал лише своїх кущів.

    LION і STORE_USER:
        не мають доступу до журналу.

    Сервіс підтримує:

    - перегляд журналу;
    - фільтрацію за датами;
    - фільтрацію за ТТ і кущем;
    - пошук за текстом;
    - історію конкретного об’єкта;
    - історію користувача;
    - статистику;
    - підготовку рядків для Excel;
    - очищення старих записів ROOT_ADMIN.
    """

    MAX_PAGE_SIZE = 200
    MAX_EXPORT_ROWS = 50_000
    POST_FILTER_LIMIT = 5_000

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
    # ОДИН ЗАПИС
    # ==========================================

    async def get_entry(
        self,
        *,
        user: User,
        audit_id: int,
    ) -> AuditEntryView:
        """Повертає один доступний запис."""

        if audit_id <= 0:
            raise ValueError(
                "ID запису повинен бути "
                "більшим за нуль."
            )

        log = await self.session.get(
            AuditLog,
            audit_id,
        )

        if log is None:
            raise ValueError(
                "Запис журналу не знайдено."
            )

        await self.authorize_log(
            user=user,
            log=log,
        )

        actor_map = await self.load_actor_map(
            [log]
        )

        return self.build_entry_view(
            log,
            actor_map=actor_map,
        )

    # ==========================================
    # СПИСОК ЖУРНАЛУ
    # ==========================================

    async def get_page(
        self,
        *,
        user: User,
        filters: AuditFilter | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AuditPage:
        """Повертає сторінку журналу."""

        self.validate_pagination(
            page=page,
            page_size=page_size,
        )

        resolved_filters = (
            filters or AuditFilter()
        )

        await self.authorize_filters(
            user=user,
            filters=resolved_filters,
        )

        conditions = self.build_conditions(
            resolved_filters
        )

        requires_post_filter = (
            self.requires_post_scope_filter(
                resolved_filters
            )
        )

        order_columns = self.get_order_columns()

        if requires_post_filter:
            statement = (
                select(AuditLog)
                .where(*conditions)
                .order_by(*order_columns)
                .limit(self.POST_FILTER_LIMIT)
            )

            result = await self.session.scalars(
                statement
            )

            logs = list(
                result.unique().all()
            )

            logs = [
                log
                for log in logs
                if self.matches_scope_filter(
                    log,
                    store_id=(
                        resolved_filters.store_id
                    ),
                    bush_id=(
                        resolved_filters.bush_id
                    ),
                )
            ]

            total_count = len(logs)

            offset = (
                page - 1
            ) * page_size

            page_logs = logs[
                offset:
                offset + page_size
            ]

            truncated = (
                len(logs)
                >= self.POST_FILTER_LIMIT
            )

        else:
            count_statement = (
                select(
                    func.count(AuditLog.id)
                )
                .where(*conditions)
            )

            total_count = int(
                await self.session.scalar(
                    count_statement
                )
                or 0
            )

            offset = (
                page - 1
            ) * page_size

            statement = (
                select(AuditLog)
                .where(*conditions)
                .order_by(*order_columns)
                .offset(offset)
                .limit(page_size)
            )

            result = await self.session.scalars(
                statement
            )

            page_logs = list(
                result.unique().all()
            )

            truncated = False

        actor_map = await self.load_actor_map(
            page_logs
        )

        items = tuple(
            self.build_entry_view(
                log,
                actor_map=actor_map,
            )
            for log in page_logs
        )

        return AuditPage(
            page=page,
            page_size=page_size,
            total_count=total_count,
            has_previous=page > 1,
            has_next=(
                page * page_size
                < total_count
            ),
            items=items,
            truncated=truncated,
        )

    # ==========================================
    # ІСТОРІЯ ТОРГОВОЇ ТОЧКИ
    # ==========================================

    async def get_store_history(
        self,
        *,
        user: User,
        store_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AuditPage:
        """Повертає історію конкретної ТТ."""

        await self.require_store_audit_access(
            user=user,
            store_id=store_id,
        )

        return await self.get_page(
            user=user,
            filters=AuditFilter(
                store_id=store_id,
                business_date_from=date_from,
                business_date_to=date_to,
            ),
            page=page,
            page_size=page_size,
        )

    # ==========================================
    # ІСТОРІЯ КУЩА
    # ==========================================

    async def get_bush_history(
        self,
        *,
        user: User,
        bush_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AuditPage:
        """Повертає історію куща."""

        decision = await self.access.can_view_audit(
            user,
            bush_id=bush_id,
        )

        decision.raise_if_denied()

        return await self.get_page(
            user=user,
            filters=AuditFilter(
                bush_id=bush_id,
                business_date_from=date_from,
                business_date_to=date_to,
            ),
            page=page,
            page_size=page_size,
        )

    # ==========================================
    # ІСТОРІЯ КОРИСТУВАЧА
    # ==========================================

    async def get_user_history(
        self,
        *,
        user: User,
        actor_user_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        bush_id: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AuditPage:
        """Повертає дії конкретного користувача."""

        if actor_user_id <= 0:
            raise ValueError(
                "ID користувача повинен бути "
                "більшим за нуль."
            )

        if bush_id is None:
            decision = await self.access.can_view_audit(
                user
            )

        else:
            decision = await self.access.can_view_audit(
                user,
                bush_id=bush_id,
            )

        decision.raise_if_denied()

        return await self.get_page(
            user=user,
            filters=AuditFilter(
                actor_user_id=actor_user_id,
                bush_id=bush_id,
                business_date_from=date_from,
                business_date_to=date_to,
            ),
            page=page,
            page_size=page_size,
        )

    # ==========================================
    # ІСТОРІЯ ОБ’ЄКТА
    # ==========================================

    async def get_entity_history(
        self,
        *,
        user: User,
        entity_type: EntityType | str,
        entity_id: int,
        store_id: int | None = None,
        bush_id: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AuditPage:
        """Повертає історію одного об’єкта."""

        if entity_id <= 0:
            raise ValueError(
                "ID об’єкта повинен бути "
                "більшим за нуль."
            )

        return await self.get_page(
            user=user,
            filters=AuditFilter(
                entity_type=entity_type,
                entity_id=entity_id,
                store_id=store_id,
                bush_id=bush_id,
            ),
            page=page,
            page_size=page_size,
        )

    # ==========================================
    # СТАТИСТИКА
    # ==========================================

    async def get_statistics(
        self,
        *,
        user: User,
        filters: AuditFilter | None = None,
    ) -> AuditStatistics:
        """Повертає статистику журналу."""

        resolved_filters = (
            filters or AuditFilter()
        )

        await self.authorize_filters(
            user=user,
            filters=resolved_filters,
        )

        page = await self.get_page(
            user=user,
            filters=resolved_filters,
            page=1,
            page_size=self.MAX_PAGE_SIZE,
        )

        if (
            page.total_count
            > self.MAX_PAGE_SIZE
        ):
            logs = await self.get_logs_for_export(
                user=user,
                filters=resolved_filters,
                limit=min(
                    page.total_count,
                    self.MAX_EXPORT_ROWS,
                ),
            )

            actor_map = await self.load_actor_map(
                logs
            )

            entries = [
                self.build_entry_view(
                    log,
                    actor_map=actor_map,
                )
                for log in logs
            ]

        else:
            entries = list(page.items)

        actions: dict[str, int] = {}
        entity_types: dict[str, int] = {}
        sources: dict[str, int] = {}

        system_actions_count = 0
        user_actions_count = 0

        for entry in entries:
            actions[entry.action] = (
                actions.get(entry.action, 0)
                + 1
            )

            entity_types[entry.entity_type] = (
                entity_types.get(
                    entry.entity_type,
                    0,
                )
                + 1
            )

            source_key = (
                entry.source or "unknown"
            )

            sources[source_key] = (
                sources.get(source_key, 0)
                + 1
            )

            if entry.actor_user_id is None:
                system_actions_count += 1
            else:
                user_actions_count += 1

        return AuditStatistics(
            total_count=len(entries),
            system_actions_count=(
                system_actions_count
            ),
            user_actions_count=(
                user_actions_count
            ),
            actions=actions,
            entity_types=entity_types,
            sources=sources,
        )

    # ==========================================
    # ДАНІ ДЛЯ EXCEL
    # ==========================================

    async def prepare_export_rows(
        self,
        *,
        user: User,
        filters: AuditFilter | None = None,
        limit: int = MAX_EXPORT_ROWS,
    ) -> list[AuditExportRow]:
        """Готує рядки для Excel-звіту."""

        if limit < 1:
            raise ValueError(
                "Ліміт повинен бути "
                "більшим за нуль."
            )

        if limit > self.MAX_EXPORT_ROWS:
            raise ValueError(
                "За один раз можна експортувати "
                f"не більше {self.MAX_EXPORT_ROWS} записів."
            )

        logs = await self.get_logs_for_export(
            user=user,
            filters=filters or AuditFilter(),
            limit=limit,
        )

        actor_map = await self.load_actor_map(
            logs
        )

        rows: list[AuditExportRow] = []

        for log in logs:
            entry = self.build_entry_view(
                log,
                actor_map=actor_map,
            )

            rows.append(
                AuditExportRow(
                    record_id=entry.id,
                    created_at=entry.created_at,
                    business_date=(
                        entry.business_date
                    ),
                    action=entry.action_text,
                    entity_type=(
                        entry.entity_type_text
                    ),
                    entity_id=entry.entity_id,
                    actor_user_id=(
                        entry.actor_user_id
                    ),
                    actor_name=entry.actor_name,
                    store_id=entry.store_id,
                    bush_id=entry.bush_id,
                    description=(
                        entry.description
                    ),
                    reason=entry.reason,
                    source=entry.source,
                    old_values=self.json_text(
                        entry.old_values
                    ),
                    new_values=self.json_text(
                        entry.new_values
                    ),
                    details=self.json_text(
                        entry.details
                    ),
                )
            )

        return rows

    async def get_logs_for_export(
        self,
        *,
        user: User,
        filters: AuditFilter,
        limit: int,
    ) -> list[AuditLog]:
        """Завантажує доступні записи для експорту."""

        await self.authorize_filters(
            user=user,
            filters=filters,
        )

        conditions = self.build_conditions(
            filters
        )

        statement = (
            select(AuditLog)
            .where(*conditions)
            .order_by(
                *self.get_order_columns()
            )
            .limit(
                max(
                    limit,
                    self.POST_FILTER_LIMIT,
                )
                if self.requires_post_scope_filter(
                    filters
                )
                else limit
            )
        )

        result = await self.session.scalars(
            statement
        )

        logs = list(
            result.unique().all()
        )

        if self.requires_post_scope_filter(
            filters
        ):
            logs = [
                log
                for log in logs
                if self.matches_scope_filter(
                    log,
                    store_id=filters.store_id,
                    bush_id=filters.bush_id,
                )
            ]

        return logs[:limit]

    # ==========================================
    # ФОРМАТУВАННЯ ДЛЯ TELEGRAM
    # ==========================================

    @classmethod
    def format_entry(
        cls,
        entry: AuditEntryView,
    ) -> str:
        """Формує один запис для Telegram."""

        created_at_text = (
            entry.created_at
            .astimezone(UTC)
            .strftime("%d.%m.%Y %H:%M UTC")
            if entry.created_at is not None
            else "не вказано"
        )

        lines = [
            (
                f"🧾 <b>Запис #{entry.id}</b>"
            ),
            (
                "🕘 Час: "
                f"<b>{created_at_text}</b>"
            ),
            (
                "⚙️ Дія: "
                f"<b>{escape(entry.action_text)}</b>"
            ),
            (
                "📦 Об’єкт: "
                f"<b>{escape(entry.entity_type_text)}</b>"
                + (
                    f" #{entry.entity_id}"
                    if entry.entity_id is not None
                    else ""
                )
            ),
            (
                "👤 Виконавець: "
                f"<b>{escape(entry.actor_name)}</b>"
            ),
        ]

        if entry.store_id is not None:
            lines.append(
                "🏪 ТТ: "
                f"<b>#{entry.store_id}</b>"
            )

        if entry.bush_id is not None:
            lines.append(
                "🌿 Кущ: "
                f"<b>#{entry.bush_id}</b>"
            )

        if entry.description:
            lines.extend(
                [
                    "",
                    (
                        "📝 "
                        f"{escape(entry.description)}"
                    ),
                ]
            )

        if entry.reason:
            lines.append(
                "💬 Причина: "
                f"{escape(entry.reason)}"
            )

        if entry.source:
            lines.append(
                "🔗 Джерело: "
                f"<code>{escape(entry.source)}</code>"
            )

        return "\n".join(lines)

    @classmethod
    def format_page(
        cls,
        page: AuditPage,
    ) -> str:
        """Формує короткий список журналу."""

        if not page.items:
            return (
                "🧾 <b>Журнал дій</b>\n\n"
                "За вказаними фільтрами "
                "записів не знайдено."
            )

        lines = [
            "🧾 <b>Журнал дій</b>",
            (
                f"Сторінка: <b>{page.page}</b>"
            ),
            (
                "Усього записів: "
                f"<b>{page.total_count}</b>"
            ),
            "",
        ]

        for entry in page.items:
            created_text = (
                entry.created_at
                .strftime("%d.%m %H:%M")
                if entry.created_at is not None
                else "без дати"
            )

            lines.append(
                (
                    f"• <b>#{entry.id}</b> "
                    f"{created_text} — "
                    f"{escape(entry.action_text)}, "
                    f"{escape(entry.entity_type_text)}"
                )
            )

        if page.truncated:
            lines.extend(
                [
                    "",
                    (
                        "⚠️ Показано лише частину "
                        "знайдених записів."
                    ),
                ]
            )

        return "\n".join(lines)

    # ==========================================
    # ОЧИЩЕННЯ СТАРИХ ЗАПИСІВ
    # ==========================================

    async def delete_old_entries(
        self,
        *,
        actor: User,
        before: datetime,
        reason: str,
    ) -> int:
        """
        Видаляє старі записи журналу.

        Доступно лише ROOT_ADMIN.
        """

        self.access.ensure_root_admin(actor)

        self.validate_aware_datetime(
            before,
            field_name="before",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
            )
        )

        created_column = self.model_column(
            "created_at"
        )

        if created_column is None:
            raise RuntimeError(
                "У моделі AuditLog відсутнє "
                "поле created_at."
            )

        count_statement = (
            select(
                func.count(AuditLog.id)
            )
            .where(
                created_column < before
            )
        )

        deleted_count = int(
            await self.session.scalar(
                count_statement
            )
            or 0
        )

        if deleted_count == 0:
            return 0

        await self.session.execute(
            delete(AuditLog).where(
                created_column < before
            )
        )

        # Сам запис про очищення створюється
        # після видалення старої історії.
        action = self.resolve_enum_member(
            AuditAction,
            "delete",
            "removed",
            "update",
        )

        entity_type = self.resolve_enum_member(
            EntityType,
            "audit_log",
            "audit",
            "system",
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=None,
            context=self.build_cleanup_context(
                actor=actor,
                reason=normalized_reason,
            ),
            old_values={
                "records_before": (
                    before.isoformat()
                ),
                "records_count": deleted_count,
            },
            new_values={
                "records_count": 0,
            },
        )

        return deleted_count

    @staticmethod
    def build_cleanup_context(
        *,
        actor: User,
        reason: str,
    ) -> Any:
        """Створює AuditContext без циклічного імпорту."""

        from app.repositories import (
            AuditContext,
        )

        return AuditContext(
            actor_user_id=actor.id,
            reason=reason,
            description=(
                "Очищено старі записи "
                "журналу дій"
            ),
            source="telegram_bot",
        )

    # ==========================================
    # ПРАВА ДОСТУПУ
    # ==========================================

    async def authorize_filters(
        self,
        *,
        user: User,
        filters: AuditFilter,
    ) -> None:
        """Перевіряє доступ до фільтрів."""

        if filters.store_id is not None:
            await self.require_store_audit_access(
                user=user,
                store_id=filters.store_id,
            )
            return

        if filters.bush_id is not None:
            decision = await self.access.can_view_audit(
                user,
                bush_id=filters.bush_id,
            )

            decision.raise_if_denied()
            return

        decision = await self.access.can_view_audit(
            user
        )

        decision.raise_if_denied()

    async def require_store_audit_access(
        self,
        *,
        user: User,
        store_id: int,
    ) -> Store:
        """Перевіряє доступ до журналу ТТ."""

        store = await self.access.get_store_or_raise(
            store_id
        )

        if self.access.is_global_manager(user):
            return store

        if store.bush_id is None:
            raise AccessDeniedError(
                "Торгова точка не належить до куща, "
                "тому журнал доступний лише директору "
                "або ROOT_ADMIN."
            )

        decision = await self.access.can_view_audit(
            user,
            bush_id=store.bush_id,
        )

        decision.raise_if_denied()

        return store

    async def authorize_log(
        self,
        *,
        user: User,
        log: AuditLog,
    ) -> None:
        """Перевіряє доступ до одного запису."""

        if self.access.is_global_manager(user):
            self.access.ensure_active_user(user)
            return

        store_id, bush_id = (
            self.extract_scope_ids(log)
        )

        if bush_id is not None:
            decision = await self.access.can_view_audit(
                user,
                bush_id=bush_id,
            )

            decision.raise_if_denied()
            return

        if store_id is not None:
            await self.require_store_audit_access(
                user=user,
                store_id=store_id,
            )
            return

        raise AccessDeniedError(
            "Цей запис не прив’язаний до доступного "
            "користувачу куща."
        )

    # ==========================================
    # SQL-ФІЛЬТРИ
    # ==========================================

    def build_conditions(
        self,
        filters: AuditFilter,
    ) -> list[Any]:
        """Формує SQL-умови."""

        conditions: list[Any] = []

        action = self.normalize_enum_value(
            AuditAction,
            filters.action,
        )

        entity_type = self.normalize_enum_value(
            EntityType,
            filters.entity_type,
        )

        if action is not None:
            column = self.model_column("action")

            if column is not None:
                conditions.append(
                    column == action
                )

        if entity_type is not None:
            column = self.model_column(
                "entity_type"
            )

            if column is not None:
                conditions.append(
                    column == entity_type
                )

        if filters.entity_id is not None:
            column = self.model_column(
                "entity_id"
            )

            if column is not None:
                conditions.append(
                    column == filters.entity_id
                )

        if filters.actor_user_id is not None:
            column = self.model_column(
                "actor_user_id",
                "user_id",
            )

            if column is not None:
                conditions.append(
                    column
                    == filters.actor_user_id
                )

        store_column = self.model_column(
            "store_id"
        )

        if (
            filters.store_id is not None
            and store_column is not None
        ):
            conditions.append(
                store_column
                == filters.store_id
            )

        bush_column = self.model_column(
            "bush_id"
        )

        if (
            filters.bush_id is not None
            and bush_column is not None
        ):
            conditions.append(
                bush_column
                == filters.bush_id
            )

        business_date_column = self.model_column(
            "business_date"
        )

        if (
            filters.business_date_from
            is not None
            and business_date_column
            is not None
        ):
            conditions.append(
                business_date_column
                >= filters.business_date_from
            )

        if (
            filters.business_date_to
            is not None
            and business_date_column
            is not None
        ):
            conditions.append(
                business_date_column
                <= filters.business_date_to
            )

        created_column = self.model_column(
            "created_at"
        )

        if (
            filters.created_from is not None
            and created_column is not None
        ):
            self.validate_aware_datetime(
                filters.created_from,
                field_name="created_from",
            )

            conditions.append(
                created_column
                >= filters.created_from
            )

        if (
            filters.created_to is not None
            and created_column is not None
        ):
            self.validate_aware_datetime(
                filters.created_to,
                field_name="created_to",
            )

            conditions.append(
                created_column
                <= filters.created_to
            )

        source_column = self.model_column(
            "source"
        )

        if (
            filters.source
            and source_column is not None
        ):
            conditions.append(
                source_column
                == filters.source.strip()
            )

        if filters.search_text:
            search_value = (
                f"%{filters.search_text.strip()}%"
            )

            searchable_columns = [
                self.model_column(
                    "description"
                ),
                self.model_column(
                    "reason"
                ),
                self.model_column(
                    "source"
                ),
            ]

            searchable_columns = [
                column
                for column in searchable_columns
                if column is not None
            ]

            if searchable_columns:
                conditions.append(
                    or_(
                        *[
                            column.ilike(
                                search_value
                            )
                            for column
                            in searchable_columns
                        ]
                    )
                )

        return conditions

    def get_order_columns(
        self,
    ) -> tuple[Any, ...]:
        """Повертає сортування журналу."""

        created_column = self.model_column(
            "created_at"
        )

        if created_column is not None:
            return (
                created_column.desc(),
                AuditLog.id.desc(),
            )

        return (
            AuditLog.id.desc(),
        )

    # ==========================================
    # POST-ФІЛЬТРАЦІЯ ОБЛАСТІ
    # ==========================================

    def requires_post_scope_filter(
        self,
        filters: AuditFilter,
    ) -> bool:
        """Чи потрібно фільтрувати JSON у Python."""

        if (
            filters.store_id is not None
            and self.model_column(
                "store_id"
            )
            is None
        ):
            return True

        if (
            filters.bush_id is not None
            and self.model_column(
                "bush_id"
            )
            is None
        ):
            return True

        return False

    def matches_scope_filter(
        self,
        log: AuditLog,
        *,
        store_id: int | None,
        bush_id: int | None,
    ) -> bool:
        """Перевіряє ТТ або кущ усередині JSON."""

        extracted_store_id, extracted_bush_id = (
            self.extract_scope_ids(log)
        )

        if (
            store_id is not None
            and extracted_store_id
            != store_id
        ):
            return False

        if (
            bush_id is not None
            and extracted_bush_id
            != bush_id
        ):
            return False

        return True

    # ==========================================
    # ПЕРЕТВОРЕННЯ ЗАПИСУ
    # ==========================================

    def build_entry_view(
        self,
        log: AuditLog,
        *,
        actor_map: dict[int, User],
    ) -> AuditEntryView:
        """Перетворює модель у безпечний view."""

        action = self.enum_text_value(
            self.read_attribute(
                log,
                "action",
                default="unknown",
            )
        )

        entity_type = self.enum_text_value(
            self.read_attribute(
                log,
                "entity_type",
                default="unknown",
            )
        )

        actor_user_id = self.read_int_attribute(
            log,
            "actor_user_id",
            "user_id",
        )

        actor = (
            actor_map.get(actor_user_id)
            if actor_user_id is not None
            else None
        )

        store_id, bush_id = (
            self.extract_scope_ids(log)
        )

        return AuditEntryView(
            id=int(log.id),
            action=action,
            action_text=self.action_text(action),
            entity_type=entity_type,
            entity_type_text=(
                self.entity_type_text(
                    entity_type
                )
            ),
            entity_id=self.read_int_attribute(
                log,
                "entity_id",
            ),
            actor_user_id=actor_user_id,
            actor_name=self.user_display_name(
                actor,
                actor_user_id=actor_user_id,
            ),
            store_id=store_id,
            bush_id=bush_id,
            business_date=self.read_attribute(
                log,
                "business_date",
                default=None,
            ),
            created_at=self.read_attribute(
                log,
                "created_at",
                default=None,
            ),
            description=self.read_text_attribute(
                log,
                "description",
            ),
            reason=self.read_text_attribute(
                log,
                "reason",
            ),
            source=self.read_text_attribute(
                log,
                "source",
            ),
            old_values=self.read_dict_attribute(
                log,
                "old_values",
                "old_values_json",
                "previous_values",
            ),
            new_values=self.read_dict_attribute(
                log,
                "new_values",
                "new_values_json",
                "current_values",
            ),
            details=self.read_dict_attribute(
                log,
                "details",
                "details_json",
                "metadata_json",
                "payload_json",
            ),
            raw_log=log,
        )

    # ==========================================
    # ОБЛАСТЬ ЗАПИСУ
    # ==========================================

    def extract_scope_ids(
        self,
        log: AuditLog,
    ) -> tuple[int | None, int | None]:
        """Витягує store_id і bush_id."""

        store_id = self.read_int_attribute(
            log,
            "store_id",
        )

        bush_id = self.read_int_attribute(
            log,
            "bush_id",
        )

        dictionaries = [
            self.read_dict_attribute(
                log,
                "old_values",
                "old_values_json",
            ),
            self.read_dict_attribute(
                log,
                "new_values",
                "new_values_json",
            ),
            self.read_dict_attribute(
                log,
                "details",
                "details_json",
                "metadata_json",
                "payload_json",
            ),
        ]

        if store_id is None:
            store_id = self.find_integer_in_data(
                dictionaries,
                keys={
                    "store_id",
                    "target_store_id",
                    "shop_id",
                },
            )

        if bush_id is None:
            bush_id = self.find_integer_in_data(
                dictionaries,
                keys={
                    "bush_id",
                    "target_bush_id",
                },
            )

        return store_id, bush_id

    @classmethod
    def find_integer_in_data(
        cls,
        value: Any,
        *,
        keys: set[str],
    ) -> int | None:
        """Рекурсивно шукає ID у JSON."""

        if isinstance(value, dict):
            for key, item in value.items():
                if key in keys:
                    try:
                        return int(item)
                    except (
                        TypeError,
                        ValueError,
                    ):
                        pass

                nested = cls.find_integer_in_data(
                    item,
                    keys=keys,
                )

                if nested is not None:
                    return nested

        elif isinstance(value, list):
            for item in value:
                nested = cls.find_integer_in_data(
                    item,
                    keys=keys,
                )

                if nested is not None:
                    return nested

        return None

    # ==========================================
    # КОРИСТУВАЧІ
    # ==========================================

    async def load_actor_map(
        self,
        logs: list[AuditLog],
    ) -> dict[int, User]:
        """Завантажує авторів одним запитом."""

        actor_ids = {
            actor_id
            for log in logs
            if (
                actor_id
                := self.read_int_attribute(
                    log,
                    "actor_user_id",
                    "user_id",
                )
            )
            is not None
        }

        if not actor_ids:
            return {}

        statement = (
            select(User)
            .where(
                User.id.in_(actor_ids)
            )
        )

        result = await self.session.scalars(
            statement
        )

        return {
            user.id: user
            for user in result.unique().all()
        }

    @staticmethod
    def user_display_name(
        user: User | None,
        *,
        actor_user_id: int | None,
    ) -> str:
        """Формує ім’я автора дії."""

        if user is None:
            if actor_user_id is None:
                return "Система"

            return (
                f"Користувач #{actor_user_id}"
            )

        full_name = " ".join(
            part
            for part in (
                getattr(
                    user,
                    "first_name",
                    None,
                ),
                getattr(
                    user,
                    "last_name",
                    None,
                ),
            )
            if part
        ).strip()

        if full_name:
            return full_name

        username = getattr(
            user,
            "telegram_username",
            None,
        ) or getattr(
            user,
            "username",
            None,
        )

        if username:
            return f"@{str(username).lstrip('@')}"

        return f"Користувач #{user.id}"

    # ==========================================
    # НАЗВИ ДІЙ
    # ==========================================

    @staticmethod
    def action_text(
        action: str,
    ) -> str:
        """Перекладає дію."""

        translations = {
            "create": "створення",
            "created": "створення",
            "update": "зміна",
            "updated": "зміна",
            "change": "зміна",
            "changed": "зміна",
            "delete": "видалення",
            "deleted": "видалення",
            "activate": "активація",
            "activated": "активація",
            "deactivate": "деактивація",
            "login": "вхід",
            "confirm": "підтвердження",
            "approve": "підтвердження",
            "reject": "відхилення",
            "revoke": "відкликання",
            "export": "експорт",
        }

        return translations.get(
            action.lower(),
            action,
        )

    @staticmethod
    def entity_type_text(
        entity_type: str,
    ) -> str:
        """Перекладає тип об’єкта."""

        translations = {
            "user": "користувач",
            "store": "торгова точка",
            "bush": "кущ",
            "cluster": "кластер",
            "binding": "прив’язка",
            "store_schedule": "графік ТТ",
            "schedule": "графік",
            "schedule_exception": (
                "виняток графіка"
            ),
            "opening_checkin": (
                "відкриття ТТ"
            ),
            "opening": "відкриття ТТ",
            "closing_report": (
                "вечірній звіт"
            ),
            "closing": "вечірній звіт",
            "invite": "запрошення",
            "notification": "повідомлення",
            "daily_summary": "живий підсумок",
            "system_setting": (
                "системне налаштування"
            ),
            "audit_log": "журнал дій",
            "system": "система",
        }

        return translations.get(
            entity_type.lower(),
            entity_type,
        )

    # ==========================================
    # МОДЕЛЬНІ ПОЛЯ
    # ==========================================

    @staticmethod
    def model_column(
        *names: str,
    ) -> Any | None:
        """Повертає першу наявну колонку моделі."""

        for name in names:
            column = getattr(
                AuditLog,
                name,
                None,
            )

            if column is not None:
                return column

        return None

    @staticmethod
    def read_attribute(
        source: Any,
        *names: str,
        default: Any = None,
    ) -> Any:
        """Читає перший наявний атрибут."""

        for name in names:
            if hasattr(source, name):
                return getattr(source, name)

        return default

    @classmethod
    def read_text_attribute(
        cls,
        source: Any,
        *names: str,
    ) -> str | None:
        """Читає текстовий атрибут."""

        value = cls.read_attribute(
            source,
            *names,
            default=None,
        )

        if value is None:
            return None

        text_value = str(value).strip()

        return text_value or None

    @classmethod
    def read_int_attribute(
        cls,
        source: Any,
        *names: str,
    ) -> int | None:
        """Читає цілий атрибут."""

        value = cls.read_attribute(
            source,
            *names,
            default=None,
        )

        if value is None:
            return None

        try:
            return int(value)

        except (TypeError, ValueError):
            return None

    @classmethod
    def read_dict_attribute(
        cls,
        source: Any,
        *names: str,
    ) -> dict[str, Any]:
        """Читає JSON-словник."""

        value = cls.read_attribute(
            source,
            *names,
            default=None,
        )

        if isinstance(value, dict):
            return dict(value)

        return {}

    # ==========================================
    # ENUM
    # ==========================================

    @classmethod
    def normalize_enum_value(
        cls,
        enum_class: type[EnumType],
        value: EnumType | str | None,
    ) -> EnumType | None:
        """Нормалізує enum-фільтр."""

        if value is None:
            return None

        if isinstance(value, enum_class):
            return value

        return cls.resolve_enum_member(
            enum_class,
            str(value),
        )

    @staticmethod
    def resolve_enum_member(
        enum_class: type[EnumType],
        *names: str,
    ) -> EnumType:
        """Шукає enum за назвою або значенням."""

        normalized_names = {
            name.strip().lower()
            for name in names
            if name.strip()
        }

        for enum_item in enum_class:
            candidates = {
                enum_item.name.lower(),
                str(enum_item.value).lower(),
            }

            if candidates.intersection(
                normalized_names
            ):
                return enum_item

        raise ValueError(
            f"У {enum_class.__name__} відсутнє "
            f"значення: {sorted(normalized_names)}."
        )

    @staticmethod
    def enum_text_value(
        value: Any,
    ) -> str:
        """Повертає текст enum."""

        if isinstance(value, Enum):
            return str(value.value)

        return str(value)

    # ==========================================
    # JSON
    # ==========================================

    @staticmethod
    def json_text(
        value: dict[str, Any],
    ) -> str:
        """Форматує JSON для Excel."""

        if not value:
            return ""

        return json.dumps(
            value,
            ensure_ascii=False,
            default=str,
            sort_keys=True,
        )

    # ==========================================
    # ВАЛІДАЦІЯ
    # ==========================================

    @classmethod
    def validate_pagination(
        cls,
        *,
        page: int,
        page_size: int,
    ) -> None:
        """Перевіряє пагінацію."""

        if page < 1:
            raise ValueError(
                "Номер сторінки повинен бути "
                "більшим за нуль."
            )

        if (
            page_size < 1
            or page_size > cls.MAX_PAGE_SIZE
        ):
            raise ValueError(
                "Розмір сторінки повинен бути "
                f"від 1 до {cls.MAX_PAGE_SIZE}."
            )

    @staticmethod
    def validate_aware_datetime(
        value: datetime,
        *,
        field_name: str,
    ) -> None:
        """Перевіряє часовий пояс."""

        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                f"{field_name} повинен містити "
                "часовий пояс."
            )

    @staticmethod
    def normalize_required_text(
        value: str,
        *,
        field_name: str,
    ) -> str:
        """Нормалізує обов’язковий текст."""

        normalized_value = " ".join(
            value.strip().split()
        )

        if not normalized_value:
            raise ValueError(
                f"{field_name} не може бути порожнім."
            )

        if len(normalized_value) > 2000:
            raise ValueError(
                f"{field_name} занадто довгий."
            )

        return normalized_value