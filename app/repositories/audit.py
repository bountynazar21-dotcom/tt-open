from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    String,
    cast,
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect as sqlalchemy_inspect
from sqlalchemy.orm import InstrumentedAttribute

from app.database.models.audit_log import AuditLog
from app.database.models.enums import (
    AuditAction,
    EntityType,
)
from app.repositories.base import BaseRepository


@dataclass(slots=True, frozen=True)
class AuditContext:
    """
    Додатковий контекст адміністративної дії.
    """

    actor_user_id: int | None = None
    business_date: date | None = None

    reason: str | None = None
    description: str | None = None

    telegram_chat_id: int | None = None
    telegram_message_id: int | None = None

    request_id: str | None = None
    source: str = "telegram_bot"


@dataclass(slots=True, frozen=True)
class AuditChangeSet:
    """
    Значення до та після зміни.
    """

    old_values: dict[str, Any]
    new_values: dict[str, Any]

    @property
    def has_changes(self) -> bool:
        return bool(
            self.old_values or self.new_values
        )

    @property
    def changed_fields(self) -> list[str]:
        return sorted(
            set(self.old_values)
            | set(self.new_values)
        )


class AuditRepository(
    BaseRepository[AuditLog]
):
    """
    Репозиторій журналу адміністративних дій.

    AuditLog не редагується і не видаляється
    після створення.

    Це дозволяє відновити:

    - хто виконав дію;
    - над яким об’єктом;
    - коли це сталося;
    - що було змінено;
    - з якої причини.
    """

    model = AuditLog

    SENSITIVE_FIELDS: frozenset[str] = frozenset(
        {
            "password",
            "password_hash",
            "token",
            "bot_token",
            "secret",
            "api_key",
            "invite_token",
            "raw_token",
            "token_hash",
            "salt",
        }
    )

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        super().__init__(session)

    # ==========================================
    # СТВОРЕННЯ ЗАПИСУ
    # ==========================================

    async def create_entry(
        self,
        *,
        action: AuditAction,
        entity_type: EntityType,
        entity_id: int | None = None,
        context: AuditContext | None = None,
        old_values: Mapping[str, Any] | None = None,
        new_values: Mapping[str, Any] | None = None,
        details: Mapping[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> AuditLog:
        """
        Створює незмінний запис журналу.
        """

        audit_context = (
            context or AuditContext()
        )

        if entity_id is not None:
            self.validate_positive_id(
                entity_id,
                field_name="ID об’єкта",
            )

        if (
            audit_context.actor_user_id
            is not None
        ):
            self.validate_positive_id(
                audit_context.actor_user_id,
                field_name="ID користувача",
            )

        if occurred_at is not None:
            self.validate_aware_datetime(
                occurred_at,
                field_name="occurred_at",
            )

        normalized_old_values = (
            self.prepare_mapping(old_values)
        )

        normalized_new_values = (
            self.prepare_mapping(new_values)
        )

        normalized_details = (
            self.prepare_mapping(details)
        )

        payload: dict[str, Any] = {}

        self.put_payload_value(
            payload,
            names=("action",),
            value=action,
            required=True,
        )

        self.put_payload_value(
            payload,
            names=(
                "entity_type",
                "target_type",
            ),
            value=entity_type,
            required=True,
        )

        self.put_payload_value(
            payload,
            names=(
                "entity_id",
                "target_id",
            ),
            value=entity_id,
        )

        self.put_payload_value(
            payload,
            names=(
                "actor_user_id",
                "actor_id",
                "user_id",
            ),
            value=audit_context.actor_user_id,
        )

        self.put_payload_value(
            payload,
            names=("business_date",),
            value=audit_context.business_date,
        )

        self.put_payload_value(
            payload,
            names=(
                "reason",
                "action_reason",
            ),
            value=self.normalize_optional_text(
                audit_context.reason
            ),
        )

        self.put_payload_value(
            payload,
            names=(
                "description",
                "message",
            ),
            value=self.normalize_optional_text(
                audit_context.description
            ),
        )

        self.put_payload_value(
            payload,
            names=(
                "old_values_json",
                "old_values",
                "before_json",
            ),
            value=(
                normalized_old_values or None
            ),
        )

        self.put_payload_value(
            payload,
            names=(
                "new_values_json",
                "new_values",
                "after_json",
            ),
            value=(
                normalized_new_values or None
            ),
        )

        self.put_payload_value(
            payload,
            names=(
                "details_json",
                "metadata_json",
                "payload_json",
            ),
            value=(
                normalized_details or None
            ),
        )

        self.put_payload_value(
            payload,
            names=("telegram_chat_id",),
            value=audit_context.telegram_chat_id,
        )

        self.put_payload_value(
            payload,
            names=("telegram_message_id",),
            value=(
                audit_context.telegram_message_id
            ),
        )

        self.put_payload_value(
            payload,
            names=(
                "request_id",
                "correlation_id",
            ),
            value=self.normalize_optional_text(
                audit_context.request_id
            ),
        )

        self.put_payload_value(
            payload,
            names=(
                "source",
                "action_source",
            ),
            value=self.normalize_optional_text(
                audit_context.source
            ),
        )

        if occurred_at is not None:
            self.put_payload_value(
                payload,
                names=(
                    "occurred_at",
                    "event_at",
                    "performed_at",
                ),
                value=occurred_at,
            )

        entry = AuditLog(**payload)

        self.session.add(entry)
        await self.session.flush()

        return entry

    # ==========================================
    # СТВОРЕННЯ ОБ’ЄКТА
    # ==========================================

    async def log_create(
        self,
        *,
        entity_type: EntityType,
        entity_id: int,
        new_values: Mapping[str, Any],
        context: AuditContext | None = None,
        action: AuditAction | None = None,
        details: Mapping[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> AuditLog:
        """Фіксує створення нового об’єкта."""

        resolved_action = (
            action
            or self.resolve_action("create")
        )

        return await self.create_entry(
            action=resolved_action,
            entity_type=entity_type,
            entity_id=entity_id,
            context=context,
            new_values=new_values,
            details=details,
            occurred_at=occurred_at,
        )

    # ==========================================
    # ОНОВЛЕННЯ ОБ’ЄКТА
    # ==========================================

    async def log_update(
        self,
        *,
        entity_type: EntityType,
        entity_id: int,
        old_values: Mapping[str, Any],
        new_values: Mapping[str, Any],
        context: AuditContext | None = None,
        action: AuditAction | None = None,
        details: Mapping[str, Any] | None = None,
        occurred_at: datetime | None = None,
        skip_if_unchanged: bool = True,
    ) -> AuditLog | None:
        """
        Фіксує лише реально змінені поля.
        """

        changes = self.build_change_set(
            old_values=old_values,
            new_values=new_values,
        )

        if (
            skip_if_unchanged
            and not changes.has_changes
        ):
            return None

        final_details = dict(
            self.prepare_mapping(details)
        )

        final_details["changed_fields"] = (
            changes.changed_fields
        )

        resolved_action = (
            action
            or self.resolve_action("update")
        )

        return await self.create_entry(
            action=resolved_action,
            entity_type=entity_type,
            entity_id=entity_id,
            context=context,
            old_values=changes.old_values,
            new_values=changes.new_values,
            details=final_details,
            occurred_at=occurred_at,
        )

    # ==========================================
    # ВИДАЛЕННЯ АБО ДЕАКТИВАЦІЯ
    # ==========================================

    async def log_delete(
        self,
        *,
        entity_type: EntityType,
        entity_id: int,
        old_values: Mapping[str, Any],
        context: AuditContext | None = None,
        action: AuditAction | None = None,
        details: Mapping[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> AuditLog:
        """Фіксує видалення або деактивацію."""

        resolved_action = (
            action
            or self.resolve_action("delete")
        )

        return await self.create_entry(
            action=resolved_action,
            entity_type=entity_type,
            entity_id=entity_id,
            context=context,
            old_values=old_values,
            details=details,
            occurred_at=occurred_at,
        )

    # ==========================================
    # ДОВІЛЬНА АДМІНІСТРАТИВНА ДІЯ
    # ==========================================

    async def log_action(
        self,
        *,
        action: AuditAction,
        entity_type: EntityType,
        entity_id: int | None = None,
        context: AuditContext | None = None,
        details: Mapping[str, Any] | None = None,
        old_values: Mapping[str, Any] | None = None,
        new_values: Mapping[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> AuditLog:
        """Фіксує довільну адміністративну дію."""

        return await self.create_entry(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            context=context,
            old_values=old_values,
            new_values=new_values,
            details=details,
            occurred_at=occurred_at,
        )

    # ==========================================
    # ЗАПИС ЗІ SQLALCHEMY-МОДЕЛІ
    # ==========================================

    async def log_model_create(
        self,
        *,
        instance: Any,
        entity_type: EntityType,
        context: AuditContext | None = None,
        action: AuditAction | None = None,
        exclude_fields: set[str] | None = None,
    ) -> AuditLog:
        """Фіксує створення SQLAlchemy-об’єкта."""

        entity_id = self.get_instance_id(
            instance
        )

        snapshot = self.snapshot_model(
            instance,
            exclude_fields=exclude_fields,
        )

        return await self.log_create(
            entity_type=entity_type,
            entity_id=entity_id,
            new_values=snapshot,
            context=context,
            action=action,
        )

    async def log_model_update(
        self,
        *,
        instance: Any,
        entity_type: EntityType,
        old_values: Mapping[str, Any],
        context: AuditContext | None = None,
        action: AuditAction | None = None,
        exclude_fields: set[str] | None = None,
    ) -> AuditLog | None:
        """Фіксує зміну SQLAlchemy-об’єкта."""

        entity_id = self.get_instance_id(
            instance
        )

        new_values = self.snapshot_model(
            instance,
            exclude_fields=exclude_fields,
        )

        return await self.log_update(
            entity_type=entity_type,
            entity_id=entity_id,
            old_values=old_values,
            new_values=new_values,
            context=context,
            action=action,
        )

    # ==========================================
    # ПОШУК ЗАПИСУ
    # ==========================================

    async def get_entry_by_id(
        self,
        audit_id: int,
    ) -> AuditLog | None:
        """Повертає запис журналу за ID."""

        self.validate_positive_id(
            audit_id,
            field_name="ID запису",
        )

        statement = (
            select(AuditLog)
            .where(AuditLog.id == audit_id)
            .limit(1)
        )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_entry_by_id_or_raise(
        self,
        audit_id: int,
    ) -> AuditLog:
        """Повертає запис або викликає помилку."""

        entry = await self.get_entry_by_id(
            audit_id
        )

        if entry is None:
            raise ValueError(
                "Запис журналу дій не знайдено."
            )

        return entry

    # ==========================================
    # ІСТОРІЯ ОБ’ЄКТА
    # ==========================================

    async def get_for_entity(
        self,
        *,
        entity_type: EntityType,
        entity_id: int,
        actions: set[AuditAction] | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[AuditLog]:
        """Повертає повну історію об’єкта."""

        self.validate_pagination(
            limit=limit,
            offset=offset,
        )

        entity_type_field = (
            self.require_model_attribute(
                "entity_type",
                "target_type",
            )
        )

        entity_id_field = (
            self.require_model_attribute(
                "entity_id",
                "target_id",
            )
        )

        conditions = [
            entity_type_field == entity_type,
            entity_id_field == entity_id,
        ]

        if actions:
            action_field = (
                self.require_model_attribute(
                    "action"
                )
            )

            conditions.append(
                action_field.in_(actions)
            )

        statement = (
            select(AuditLog)
            .where(*conditions)
            .order_by(
                self.get_ordering_field().desc(),
                AuditLog.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    # ==========================================
    # ІСТОРІЯ КОРИСТУВАЧА
    # ==========================================

    async def get_by_actor(
        self,
        *,
        actor_user_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        actions: set[AuditAction] | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[AuditLog]:
        """Повертає дії конкретного користувача."""

        self.validate_positive_id(
            actor_user_id,
            field_name="ID користувача",
        )

        self.validate_pagination(
            limit=limit,
            offset=offset,
        )

        actor_field = (
            self.require_model_attribute(
                "actor_user_id",
                "actor_id",
                "user_id",
            )
        )

        conditions = [
            actor_field == actor_user_id,
        ]

        if actions:
            action_field = (
                self.require_model_attribute(
                    "action"
                )
            )

            conditions.append(
                action_field.in_(actions)
            )

        conditions.extend(
            self.build_date_conditions(
                date_from=date_from,
                date_to=date_to,
            )
        )

        statement = (
            select(AuditLog)
            .where(*conditions)
            .order_by(
                self.get_ordering_field().desc(),
                AuditLog.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    # ==========================================
    # ЖУРНАЛ ЗА ДАТУ
    # ==========================================

    async def get_for_business_date(
        self,
        *,
        business_date: date,
        actions: set[AuditAction] | None = None,
        entity_types: set[EntityType] | None = None,
        limit: int = 1000,
    ) -> list[AuditLog]:
        """Повертає записи за бізнес-дату."""

        self.validate_limit(
            limit,
            maximum=10_000,
        )

        business_date_field = (
            self.get_model_attribute(
                "business_date"
            )
        )

        if business_date_field is not None:
            conditions = [
                business_date_field
                == business_date
            ]
        else:
            created_at_field = (
                self.require_model_attribute(
                    "created_at",
                    "occurred_at",
                    "event_at",
                )
            )

            conditions = [
                func.date(created_at_field)
                == business_date
            ]

        if actions:
            action_field = (
                self.require_model_attribute(
                    "action"
                )
            )

            conditions.append(
                action_field.in_(actions)
            )

        if entity_types:
            entity_type_field = (
                self.require_model_attribute(
                    "entity_type",
                    "target_type",
                )
            )

            conditions.append(
                entity_type_field.in_(
                    entity_types
                )
            )

        statement = (
            select(AuditLog)
            .where(*conditions)
            .order_by(
                self.get_ordering_field().desc(),
                AuditLog.id.desc(),
            )
            .limit(limit)
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_between_dates(
        self,
        *,
        date_from: date,
        date_to: date,
        actor_user_id: int | None = None,
        entity_type: EntityType | None = None,
        action: AuditAction | None = None,
        limit: int = 5000,
    ) -> list[AuditLog]:
        """Повертає журнал за діапазон дат."""

        self.validate_date_range(
            date_from=date_from,
            date_to=date_to,
        )

        self.validate_limit(
            limit,
            maximum=20_000,
        )

        conditions = self.build_date_conditions(
            date_from=date_from,
            date_to=date_to,
        )

        if actor_user_id is not None:
            actor_field = (
                self.require_model_attribute(
                    "actor_user_id",
                    "actor_id",
                    "user_id",
                )
            )

            conditions.append(
                actor_field == actor_user_id
            )

        if entity_type is not None:
            entity_type_field = (
                self.require_model_attribute(
                    "entity_type",
                    "target_type",
                )
            )

            conditions.append(
                entity_type_field
                == entity_type
            )

        if action is not None:
            action_field = (
                self.require_model_attribute(
                    "action"
                )
            )

            conditions.append(
                action_field == action
            )

        statement = (
            select(AuditLog)
            .where(*conditions)
            .order_by(
                self.get_ordering_field().desc(),
                AuditLog.id.desc(),
            )
            .limit(limit)
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    # ==========================================
    # ПОШУК У ЖУРНАЛІ
    # ==========================================

    async def search(
        self,
        query: str,
        *,
        actor_user_id: int | None = None,
        action: AuditAction | None = None,
        entity_type: EntityType | None = None,
        limit: int = 200,
    ) -> list[AuditLog]:
        """
        Шукає за:

        - ID об’єкта;
        - причиною;
        - описом;
        - request_id;
        - типом дії;
        - типом об’єкта.
        """

        normalized_query = query.strip()

        if not normalized_query:
            return []

        self.validate_limit(
            limit,
            maximum=1000,
        )

        search_pattern = (
            f"%{normalized_query}%"
        )

        search_conditions = []

        for field_names in (
            ("entity_id", "target_id"),
            ("reason", "action_reason"),
            ("description", "message"),
            ("request_id", "correlation_id"),
            ("source", "action_source"),
            ("action",),
            ("entity_type", "target_type"),
        ):
            field = self.get_model_attribute(
                *field_names
            )

            if field is not None:
                search_conditions.append(
                    cast(field, String).ilike(
                        search_pattern
                    )
                )

        if not search_conditions:
            return []

        conditions = [
            or_(*search_conditions)
        ]

        if actor_user_id is not None:
            actor_field = (
                self.require_model_attribute(
                    "actor_user_id",
                    "actor_id",
                    "user_id",
                )
            )

            conditions.append(
                actor_field == actor_user_id
            )

        if action is not None:
            action_field = (
                self.require_model_attribute(
                    "action"
                )
            )

            conditions.append(
                action_field == action
            )

        if entity_type is not None:
            entity_type_field = (
                self.require_model_attribute(
                    "entity_type",
                    "target_type",
                )
            )

            conditions.append(
                entity_type_field
                == entity_type
            )

        statement = (
            select(AuditLog)
            .where(*conditions)
            .order_by(
                self.get_ordering_field().desc(),
                AuditLog.id.desc(),
            )
            .limit(limit)
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    # ==========================================
    # СТАТИСТИКА
    # ==========================================

    async def count_by_action(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[AuditAction, int]:
        """Підраховує записи за типом дії."""

        action_field = (
            self.require_model_attribute(
                "action"
            )
        )

        statement = (
            select(
                action_field,
                func.count(AuditLog.id),
            )
            .where(
                *self.build_date_conditions(
                    date_from=date_from,
                    date_to=date_to,
                )
            )
            .group_by(action_field)
        )

        result = await self.session.execute(
            statement
        )

        counts = {
            action: 0
            for action in AuditAction
        }

        for action, count in result.all():
            counts[action] = int(count)

        return counts

    async def count_by_entity_type(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[EntityType, int]:
        """Підраховує записи за типом об’єкта."""

        entity_type_field = (
            self.require_model_attribute(
                "entity_type",
                "target_type",
            )
        )

        statement = (
            select(
                entity_type_field,
                func.count(AuditLog.id),
            )
            .where(
                *self.build_date_conditions(
                    date_from=date_from,
                    date_to=date_to,
                )
            )
            .group_by(entity_type_field)
        )

        result = await self.session.execute(
            statement
        )

        counts = {
            entity_type: 0
            for entity_type in EntityType
        }

        for entity_type, count in result.all():
            counts[entity_type] = int(count)

        return counts

    async def get_actor_ranking(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 100,
    ) -> list[dict[str, int]]:
        """Повертає кількість дій кожного користувача."""

        self.validate_limit(
            limit,
            maximum=1000,
        )

        actor_field = (
            self.require_model_attribute(
                "actor_user_id",
                "actor_id",
                "user_id",
            )
        )

        statement = (
            select(
                actor_field.label(
                    "actor_user_id"
                ),
                func.count(AuditLog.id).label(
                    "actions_count"
                ),
            )
            .where(
                actor_field.is_not(None),
                *self.build_date_conditions(
                    date_from=date_from,
                    date_to=date_to,
                ),
            )
            .group_by(actor_field)
            .order_by(
                func.count(AuditLog.id).desc()
            )
            .limit(limit)
        )

        result = await self.session.execute(
            statement
        )

        return [
            {
                "actor_user_id": int(
                    row.actor_user_id
                ),
                "actions_count": int(
                    row.actions_count
                ),
            }
            for row in result.all()
        ]

    # ==========================================
    # РІЗНИЦЯ МІЖ ЗНАЧЕННЯМИ
    # ==========================================

    @classmethod
    def build_change_set(
        cls,
        *,
        old_values: Mapping[str, Any],
        new_values: Mapping[str, Any],
    ) -> AuditChangeSet:
        """Залишає лише поля, що реально змінилися."""

        prepared_old = cls.prepare_mapping(
            old_values
        )

        prepared_new = cls.prepare_mapping(
            new_values
        )

        changed_old: dict[str, Any] = {}
        changed_new: dict[str, Any] = {}

        all_keys = (
            set(prepared_old)
            | set(prepared_new)
        )

        for key in all_keys:
            old_value = prepared_old.get(key)
            new_value = prepared_new.get(key)

            if old_value == new_value:
                continue

            changed_old[key] = old_value
            changed_new[key] = new_value

        return AuditChangeSet(
            old_values=changed_old,
            new_values=changed_new,
        )

    # ==========================================
    # ЗНІМОК SQLALCHEMY-МОДЕЛІ
    # ==========================================

    @classmethod
    def snapshot_model(
        cls,
        instance: Any,
        *,
        exclude_fields: set[str] | None = None,
    ) -> dict[str, Any]:
        """Створює безпечний знімок полів моделі."""

        excluded = {
            field.lower()
            for field in (
                exclude_fields or set()
            )
        }

        excluded.update(
            cls.SENSITIVE_FIELDS
        )

        inspection = sqlalchemy_inspect(
            instance
        )

        snapshot: dict[str, Any] = {}

        for attribute in (
            inspection.mapper.column_attrs
        ):
            field_name = attribute.key

            if field_name.lower() in excluded:
                continue

            value = getattr(
                instance,
                field_name,
                None,
            )

            snapshot[field_name] = (
                cls.serialize_value(value)
            )

        return snapshot

    @staticmethod
    def get_instance_id(
        instance: Any,
    ) -> int:
        """Повертає ID SQLAlchemy-об’єкта."""

        entity_id = getattr(
            instance,
            "id",
            None,
        )

        if (
            not isinstance(entity_id, int)
            or entity_id <= 0
        ):
            raise ValueError(
                "Об’єкт повинен бути збережений "
                "у базі перед створенням AuditLog."
            )

        return entity_id

    # ==========================================
    # ПІДГОТОВКА JSON
    # ==========================================

    @classmethod
    def prepare_mapping(
        cls,
        values: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        """Готує словник для JSONB-поля."""

        if values is None:
            return {}

        result: dict[str, Any] = {}

        for key, value in values.items():
            normalized_key = str(key)

            if (
                normalized_key.lower()
                in cls.SENSITIVE_FIELDS
            ):
                result[normalized_key] = (
                    "***"
                )

                continue

            result[normalized_key] = (
                cls.serialize_value(value)
            )

        return result

    @classmethod
    def serialize_value(
        cls,
        value: Any,
    ) -> Any:
        """Перетворює значення у JSON-сумісний формат."""

        if value is None:
            return None

        if isinstance(
            value,
            (
                str,
                int,
                float,
                bool,
            ),
        ):
            return value

        if isinstance(value, Decimal):
            return str(value)

        if isinstance(
            value,
            (date, datetime),
        ):
            return value.isoformat()

        if isinstance(value, UUID):
            return str(value)

        if isinstance(value, Enum):
            return value.value

        if isinstance(value, Mapping):
            return {
                str(key): cls.serialize_value(
                    nested_value
                )
                for key, nested_value
                in value.items()
            }

        if isinstance(
            value,
            (set, frozenset),
        ):
            return sorted(
                cls.serialize_value(item)
                for item in value
            )

        if isinstance(value, Sequence):
            return [
                cls.serialize_value(item)
                for item in value
            ]

        return str(value)

    # ==========================================
    # РОБОТА З ENUM
    # ==========================================

    @staticmethod
    def resolve_action(
        requested_action: str,
    ) -> AuditAction:
        """
        Знаходить AuditAction за назвою
        або значенням enum.
        """

        normalized_action = (
            requested_action.strip().lower()
        )

        aliases = {
            "create": {
                "create",
                "created",
                "add",
                "added",
            },
            "update": {
                "update",
                "updated",
                "edit",
                "edited",
                "change",
                "changed",
            },
            "delete": {
                "delete",
                "deleted",
                "remove",
                "removed",
                "deactivate",
                "deactivated",
            },
        }

        accepted_values = aliases.get(
            normalized_action,
            {normalized_action},
        )

        for action in AuditAction:
            if (
                action.name.lower()
                in accepted_values
                or str(action.value).lower()
                in accepted_values
            ):
                return action

        raise ValueError(
            "У AuditAction відсутня дія "
            f"«{requested_action}»."
        )

    @staticmethod
    def resolve_entity_type(
        requested_type: str,
    ) -> EntityType:
        """Знаходить EntityType за назвою."""

        normalized_type = (
            requested_type.strip().lower()
        )

        for entity_type in EntityType:
            if (
                entity_type.name.lower()
                == normalized_type
                or str(
                    entity_type.value
                ).lower()
                == normalized_type
            ):
                return entity_type

        raise ValueError(
            "У EntityType відсутній тип "
            f"«{requested_type}»."
        )

    # ==========================================
    # ДИНАМІЧНІ ПОЛЯ МОДЕЛІ
    # ==========================================

    @staticmethod
    def mapped_field_names() -> set[str]:
        """Повертає всі поля AuditLog."""

        mapper = sqlalchemy_inspect(
            AuditLog
        )

        return {
            attribute.key
            for attribute in mapper.attrs
        }

    @classmethod
    def put_payload_value(
        cls,
        payload: dict[str, Any],
        *,
        names: tuple[str, ...],
        value: Any,
        required: bool = False,
    ) -> bool:
        """Записує значення у перше доступне поле."""

        available_fields = (
            cls.mapped_field_names()
        )

        for field_name in names:
            if field_name not in available_fields:
                continue

            payload[field_name] = value
            return True

        if required:
            raise RuntimeError(
                "У моделі AuditLog відсутнє "
                f"обов’язкове поле: {names}."
            )

        return False

    @staticmethod
    def get_model_attribute(
        *names: str,
    ) -> InstrumentedAttribute[Any] | None:
        """Повертає перше доступне SQLAlchemy-поле."""

        for field_name in names:
            attribute = getattr(
                AuditLog,
                field_name,
                None,
            )

            if isinstance(
                attribute,
                InstrumentedAttribute,
            ):
                return attribute

        return None

    @classmethod
    def require_model_attribute(
        cls,
        *names: str,
    ) -> InstrumentedAttribute[Any]:
        """Повертає поле або викликає помилку."""

        attribute = cls.get_model_attribute(
            *names
        )

        if attribute is None:
            raise RuntimeError(
                "У моделі AuditLog відсутнє поле: "
                f"{names}."
            )

        return attribute

    @classmethod
    def get_ordering_field(
        cls,
    ) -> InstrumentedAttribute[Any]:
        """Повертає поле часу для сортування."""

        return cls.require_model_attribute(
            "occurred_at",
            "event_at",
            "performed_at",
            "created_at",
        )

    # ==========================================
    # УМОВИ ДАТИ
    # ==========================================

    @classmethod
    def build_date_conditions(
        cls,
        *,
        date_from: date | None,
        date_to: date | None,
    ) -> list[Any]:
        """Створює SQL-умови діапазону дат."""

        if (
            date_from is not None
            and date_to is not None
        ):
            cls.validate_date_range(
                date_from=date_from,
                date_to=date_to,
            )

        if (
            date_from is None
            and date_to is None
        ):
            return []

        business_date_field = (
            cls.get_model_attribute(
                "business_date"
            )
        )

        conditions = []

        if business_date_field is not None:
            if date_from is not None:
                conditions.append(
                    business_date_field
                    >= date_from
                )

            if date_to is not None:
                conditions.append(
                    business_date_field
                    <= date_to
                )

            return conditions

        time_field = cls.get_ordering_field()

        if date_from is not None:
            conditions.append(
                func.date(time_field)
                >= date_from
            )

        if date_to is not None:
            conditions.append(
                func.date(time_field)
                <= date_to
            )

        return conditions

    # ==========================================
    # ВАЛІДАЦІЯ
    # ==========================================

    @staticmethod
    def normalize_optional_text(
        value: str | None,
    ) -> str | None:
        """Нормалізує необов’язковий текст."""

        if value is None:
            return None

        normalized_value = " ".join(
            value.strip().split()
        )

        return normalized_value or None

    @staticmethod
    def validate_positive_id(
        value: int,
        *,
        field_name: str,
    ) -> None:
        """Перевіряє внутрішній ID."""

        if value <= 0:
            raise ValueError(
                f"{field_name} повинен бути "
                "більшим за нуль."
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
    def validate_limit(
        limit: int,
        *,
        maximum: int,
    ) -> None:
        """Перевіряє обмеження вибірки."""

        if limit <= 0 or limit > maximum:
            raise ValueError(
                f"Limit повинен бути від 1 до {maximum}."
            )

    @classmethod
    def validate_pagination(
        cls,
        *,
        limit: int,
        offset: int,
    ) -> None:
        """Перевіряє пагінацію."""

        cls.validate_limit(
            limit,
            maximum=10_000,
        )

        if offset < 0:
            raise ValueError(
                "Offset не може бути від’ємним."
            )

    @staticmethod
    def validate_date_range(
        *,
        date_from: date,
        date_to: date,
    ) -> None:
        """Перевіряє діапазон дат."""

        if date_to < date_from:
            raise ValueError(
                "Кінцева дата не може бути "
                "раніше початкової."
            )