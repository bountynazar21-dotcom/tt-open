from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, lazyload

from app.database.models.daily_summary import (
    DailySummaryMessage,
)
from app.database.models.enums import SummaryType
from app.repositories.base import BaseRepository


@dataclass(slots=True, frozen=True)
class SummaryScope:
    """
    Унікальна область живого підсумку.

    Один підсумок визначається комбінацією:

    - тип підсумку;
    - бізнес-дата;
    - Telegram-чат;
    - Telegram-тема;
    - кущ або вся мережа.
    """

    summary_type: SummaryType
    business_date: date
    chat_id: int

    bush_id: int | None = None
    topic_id: int | None = None


@dataclass(slots=True, frozen=True)
class SummaryUpdateDecision:
    """
    Рішення щодо Telegram-повідомлення.
    """

    summary: DailySummaryMessage

    should_send: bool
    should_edit: bool
    content_changed: bool

    reason: str

    @property
    def telegram_message_exists(self) -> bool:
        return self.summary.message_id is not None


class DailySummaryRepository(
    BaseRepository[DailySummaryMessage]
):
    """
    Репозиторій живих щоденних підсумків.

    Принцип роботи:

    1. Для куща або мережі створюється один запис.
    2. Після першого надсилання зберігається message_id.
    3. Після нового відкриття або закриття
       текст Telegram-повідомлення редагується.
    4. Якщо текст не змінився — Telegram API
       повторно не викликається.
    """

    model = DailySummaryMessage

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        super().__init__(session)

    # ==========================================
    # ПОШУК ЗА ID
    # ==========================================

    async def get_by_id(
        self,
        summary_id: int,
        *,
        for_update: bool = False,
    ) -> DailySummaryMessage | None:
        """Повертає підсумок за внутрішнім ID."""

        self.validate_positive_id(
            summary_id,
            field_name="ID підсумку",
        )

        statement = (
            select(DailySummaryMessage)
            .where(
                DailySummaryMessage.id == summary_id
            )
            .limit(1)
        )

        if for_update:
            statement = (
                statement
                .options(
                    lazyload(
                        DailySummaryMessage.bush
                    )
                )
                .with_for_update(
                    of=DailySummaryMessage
                )
            )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_by_id_or_raise(
        self,
        summary_id: int,
        *,
        for_update: bool = False,
    ) -> DailySummaryMessage:
        """Повертає підсумок або викликає помилку."""

        summary = await self.get_by_id(
            summary_id,
            for_update=for_update,
        )

        if summary is None:
            raise ValueError(
                "Щоденний підсумок не знайдено."
            )

        return summary

    # ==========================================
    # ПОШУК ЗА ОБЛАСТЮ
    # ==========================================

    async def get_by_scope(
        self,
        *,
        summary_type: SummaryType,
        business_date: date,
        chat_id: int,
        bush_id: int | None = None,
        topic_id: int | None = None,
        for_update: bool = False,
    ) -> DailySummaryMessage | None:
        """
        Повертає унікальний підсумок для:

        - конкретного куща;
        - або всієї мережі.
        """

        self.validate_scope(
            summary_type=summary_type,
            bush_id=bush_id,
        )

        conditions = [
            DailySummaryMessage.summary_type
            == summary_type,
            DailySummaryMessage.business_date
            == business_date,
            DailySummaryMessage.chat_id
            == chat_id,
        ]

        if bush_id is None:
            conditions.append(
                DailySummaryMessage.bush_id.is_(None)
            )
        else:
            conditions.append(
                DailySummaryMessage.bush_id
                == bush_id
            )

        if topic_id is None:
            conditions.append(
                DailySummaryMessage.topic_id.is_(None)
            )
        else:
            conditions.append(
                DailySummaryMessage.topic_id
                == topic_id
            )

        statement = (
            select(DailySummaryMessage)
            .where(*conditions)
            .limit(1)
        )

        if for_update:
            statement = (
                statement
                .options(
                    lazyload(
                        DailySummaryMessage.bush
                    )
                )
                .with_for_update(
                    of=DailySummaryMessage
                )
            )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_by_scope_object(
        self,
        scope: SummaryScope,
        *,
        for_update: bool = False,
    ) -> DailySummaryMessage | None:
        """Повертає підсумок за SummaryScope."""

        return await self.get_by_scope(
            summary_type=scope.summary_type,
            business_date=scope.business_date,
            chat_id=scope.chat_id,
            bush_id=scope.bush_id,
            topic_id=scope.topic_id,
            for_update=for_update,
        )

    async def get_by_scope_or_raise(
        self,
        *,
        summary_type: SummaryType,
        business_date: date,
        chat_id: int,
        bush_id: int | None = None,
        topic_id: int | None = None,
        for_update: bool = False,
    ) -> DailySummaryMessage:
        """Повертає підсумок за областю або помилку."""

        summary = await self.get_by_scope(
            summary_type=summary_type,
            business_date=business_date,
            chat_id=chat_id,
            bush_id=bush_id,
            topic_id=topic_id,
            for_update=for_update,
        )

        if summary is None:
            raise ValueError(
                "Живий підсумок для вибраної області "
                "ще не створено."
            )

        return summary

    # ==========================================
    # СТВОРЕННЯ
    # ==========================================

    async def get_or_create(
        self,
        *,
        summary_type: SummaryType,
        business_date: date,
        chat_id: int,
        bush_id: int | None = None,
        topic_id: int | None = None,
        initial_text: str | None = None,
        snapshot_json: dict[str, Any] | None = None,
    ) -> tuple[DailySummaryMessage, bool]:
        """
        Повертає існуючий або створює новий підсумок.

        Результат:
        - DailySummaryMessage;
        - True, якщо запис створено;
        - False, якщо запис уже існував.
        """

        self.validate_scope(
            summary_type=summary_type,
            bush_id=bush_id,
        )

        self.validate_topic_id(topic_id)

        existing = await self.get_by_scope(
            summary_type=summary_type,
            business_date=business_date,
            chat_id=chat_id,
            bush_id=bush_id,
            topic_id=topic_id,
        )

        if existing is not None:
            return existing, False

        normalized_text = self.normalize_optional_text(
            initial_text
        )

        summary = DailySummaryMessage(
            summary_type=summary_type,
            business_date=business_date,
            bush_id=bush_id,
            chat_id=chat_id,
            topic_id=topic_id,
            message_id=None,
        )

        content_hash = (
            self.build_content_hash(
                normalized_text
            )
            if normalized_text is not None
            else None
        )

        self.set_first_available_value(
            summary,
            names=(
                "message_text",
                "last_message_text",
                "last_text",
                "rendered_text",
            ),
            value=normalized_text,
        )

        self.set_first_available_value(
            summary,
            names=(
                "content_hash",
                "last_content_hash",
                "message_hash",
                "text_hash",
            ),
            value=content_hash,
        )

        self.set_first_available_value(
            summary,
            names=(
                "snapshot_json",
                "statistics_json",
                "stats_json",
                "payload_json",
            ),
            value=snapshot_json,
        )

        try:
            async with self.session.begin_nested():
                self.session.add(summary)
                await self.session.flush()

            return summary, True

        except IntegrityError:
            existing = await self.get_by_scope(
                summary_type=summary_type,
                business_date=business_date,
                chat_id=chat_id,
                bush_id=bush_id,
                topic_id=topic_id,
            )

            if existing is None:
                raise

            return existing, False

    async def get_or_create_from_scope(
        self,
        scope: SummaryScope,
        *,
        initial_text: str | None = None,
        snapshot_json: dict[str, Any] | None = None,
    ) -> tuple[DailySummaryMessage, bool]:
        """Створює підсумок із SummaryScope."""

        return await self.get_or_create(
            summary_type=scope.summary_type,
            business_date=scope.business_date,
            chat_id=scope.chat_id,
            bush_id=scope.bush_id,
            topic_id=scope.topic_id,
            initial_text=initial_text,
            snapshot_json=snapshot_json,
        )

    # ==========================================
    # ПЕРЕВІРКА ОНОВЛЕННЯ
    # ==========================================

    async def prepare_update(
        self,
        *,
        summary_type: SummaryType,
        business_date: date,
        chat_id: int,
        message_text: str,
        bush_id: int | None = None,
        topic_id: int | None = None,
        snapshot_json: dict[str, Any] | None = None,
    ) -> SummaryUpdateDecision:
        """
        Визначає, що потрібно зробити:

        - надіслати нове повідомлення;
        - відредагувати існуюче;
        - нічого не робити.
        """

        normalized_text = self.normalize_required_text(
            message_text,
            field_name="Текст підсумку",
        )

        summary, _ = await self.get_or_create(
            summary_type=summary_type,
            business_date=business_date,
            chat_id=chat_id,
            bush_id=bush_id,
            topic_id=topic_id,
            initial_text=None,
            snapshot_json=None,
        )

        summary = await self.get_by_id_or_raise(
            summary.id,
            for_update=True,
        )

        new_hash = self.build_content_hash(
            normalized_text
        )

        old_hash = self.get_first_available_value(
            summary,
            names=(
                "content_hash",
                "last_content_hash",
                "message_hash",
                "text_hash",
            ),
        )

        if old_hash is None:
            old_text = self.get_first_available_value(
                summary,
                names=(
                    "message_text",
                    "last_message_text",
                    "last_text",
                    "rendered_text",
                ),
            )

            if isinstance(old_text, str):
                old_hash = self.build_content_hash(
                    old_text
                )

        content_changed = old_hash != new_hash

        if summary.message_id is None:
            should_send = True
            should_edit = False
            reason = "telegram_message_missing"

        elif content_changed:
            should_send = False
            should_edit = True
            reason = "content_changed"

        else:
            should_send = False
            should_edit = False
            reason = "content_unchanged"

        self.set_first_available_value(
            summary,
            names=(
                "pending_message_text",
                "next_message_text",
            ),
            value=normalized_text,
        )

        self.set_first_available_value(
            summary,
            names=(
                "pending_snapshot_json",
                "next_snapshot_json",
            ),
            value=snapshot_json,
        )

        self.session.add(summary)
        await self.session.flush()

        return SummaryUpdateDecision(
            summary=summary,
            should_send=should_send,
            should_edit=should_edit,
            content_changed=content_changed,
            reason=reason,
        )

    async def needs_update(
        self,
        summary: DailySummaryMessage,
        *,
        message_text: str,
    ) -> bool:
        """Перевіряє, чи змінився текст підсумку."""

        normalized_text = self.normalize_required_text(
            message_text,
            field_name="Текст підсумку",
        )

        new_hash = self.build_content_hash(
            normalized_text
        )

        current_hash = self.get_first_available_value(
            summary,
            names=(
                "content_hash",
                "last_content_hash",
                "message_hash",
                "text_hash",
            ),
        )

        if current_hash is not None:
            return current_hash != new_hash

        current_text = self.get_first_available_value(
            summary,
            names=(
                "message_text",
                "last_message_text",
                "last_text",
                "rendered_text",
            ),
        )

        return current_text != normalized_text

    # ==========================================
    # ПЕРШЕ НАДСИЛАННЯ
    # ==========================================

    async def mark_sent(
        self,
        summary: DailySummaryMessage,
        *,
        message_id: int,
        message_text: str,
        sent_at: datetime,
        snapshot_json: dict[str, Any] | None = None,
        chat_id: int | None = None,
        topic_id: int | None = None,
    ) -> DailySummaryMessage:
        """Фіксує перше надсилання підсумку."""

        self.validate_positive_id(
            message_id,
            field_name="Telegram message_id",
        )

        self.validate_aware_datetime(
            sent_at,
            field_name="sent_at",
        )

        normalized_text = self.normalize_required_text(
            message_text,
            field_name="Текст підсумку",
        )

        if chat_id is not None:
            summary.chat_id = chat_id

        if topic_id is not None:
            self.validate_topic_id(topic_id)
            summary.topic_id = topic_id

        summary.message_id = message_id

        self.save_successful_content(
            summary,
            message_text=normalized_text,
            snapshot_json=snapshot_json,
            processed_at=sent_at,
            action="sent",
        )

        self.session.add(summary)
        await self.session.flush()

        return summary

    async def mark_sent_by_id(
        self,
        *,
        summary_id: int,
        message_id: int,
        message_text: str,
        sent_at: datetime,
        snapshot_json: dict[str, Any] | None = None,
    ) -> DailySummaryMessage:
        """Фіксує перше надсилання за ID."""

        summary = await self.get_by_id_or_raise(
            summary_id,
            for_update=True,
        )

        return await self.mark_sent(
            summary,
            message_id=message_id,
            message_text=message_text,
            sent_at=sent_at,
            snapshot_json=snapshot_json,
        )

    # ==========================================
    # РЕДАГУВАННЯ
    # ==========================================

    async def mark_edited(
        self,
        summary: DailySummaryMessage,
        *,
        message_text: str,
        edited_at: datetime,
        snapshot_json: dict[str, Any] | None = None,
    ) -> DailySummaryMessage:
        """Фіксує успішне редагування Telegram-повідомлення."""

        self.validate_aware_datetime(
            edited_at,
            field_name="edited_at",
        )

        if summary.message_id is None:
            raise ValueError(
                "Неможливо позначити підсумок "
                "відредагованим без message_id."
            )

        normalized_text = self.normalize_required_text(
            message_text,
            field_name="Текст підсумку",
        )

        self.save_successful_content(
            summary,
            message_text=normalized_text,
            snapshot_json=snapshot_json,
            processed_at=edited_at,
            action="edited",
        )

        self.session.add(summary)
        await self.session.flush()

        return summary

    async def mark_edited_by_id(
        self,
        *,
        summary_id: int,
        message_text: str,
        edited_at: datetime,
        snapshot_json: dict[str, Any] | None = None,
    ) -> DailySummaryMessage:
        """Фіксує редагування підсумку за ID."""

        summary = await self.get_by_id_or_raise(
            summary_id,
            for_update=True,
        )

        return await self.mark_edited(
            summary,
            message_text=message_text,
            edited_at=edited_at,
            snapshot_json=snapshot_json,
        )

    # ==========================================
    # ПОМИЛКИ СИНХРОНІЗАЦІЇ
    # ==========================================

    async def mark_sync_failed(
        self,
        summary: DailySummaryMessage,
        *,
        failed_at: datetime,
        error_text: str,
    ) -> DailySummaryMessage:
        """Зберігає помилку Telegram API."""

        self.validate_aware_datetime(
            failed_at,
            field_name="failed_at",
        )

        normalized_error = self.normalize_required_text(
            error_text,
            field_name="Текст помилки",
        )

        self.set_first_available_value(
            summary,
            names=(
                "last_error",
                "last_error_text",
                "error_text",
            ),
            value=normalized_error,
        )

        self.set_first_available_value(
            summary,
            names=(
                "last_error_at",
                "failed_at",
            ),
            value=failed_at,
        )

        self.increment_first_available_value(
            summary,
            names=(
                "error_count",
                "failure_count",
                "failed_attempts",
            ),
        )

        self.session.add(summary)
        await self.session.flush()

        return summary

    async def clear_sync_error(
        self,
        summary: DailySummaryMessage,
    ) -> DailySummaryMessage:
        """Очищає останню помилку синхронізації."""

        self.set_all_available_values(
            summary,
            names=(
                "last_error",
                "last_error_text",
                "error_text",
                "last_error_at",
                "failed_at",
            ),
            value=None,
        )

        self.session.add(summary)
        await self.session.flush()

        return summary

    # ==========================================
    # ПОВІДОМЛЕННЯ ВИДАЛЕНЕ З TELEGRAM
    # ==========================================

    async def detach_telegram_message(
        self,
        summary: DailySummaryMessage,
        *,
        detached_at: datetime,
        reason: str | None = None,
    ) -> DailySummaryMessage:
        """
        Очищає message_id.

        Під час наступного оновлення бот створить
        нове Telegram-повідомлення.
        """

        self.validate_aware_datetime(
            detached_at,
            field_name="detached_at",
        )

        summary.message_id = None

        self.set_first_available_value(
            summary,
            names=(
                "detached_at",
                "message_deleted_at",
            ),
            value=detached_at,
        )

        self.set_first_available_value(
            summary,
            names=(
                "detach_reason",
                "message_deleted_reason",
            ),
            value=self.normalize_optional_text(
                reason
            ),
        )

        self.session.add(summary)
        await self.session.flush()

        return summary

    async def change_destination(
        self,
        summary: DailySummaryMessage,
        *,
        chat_id: int,
        topic_id: int | None,
        reset_message_id: bool = True,
    ) -> DailySummaryMessage:
        """
        Переносить підсумок в інший чат або тему.

        За замовчуванням старий message_id очищається.
        """

        self.validate_topic_id(topic_id)

        destination_changed = (
            summary.chat_id != chat_id
            or summary.topic_id != topic_id
        )

        summary.chat_id = chat_id
        summary.topic_id = topic_id

        if destination_changed and reset_message_id:
            summary.message_id = None

        self.session.add(summary)
        await self.session.flush()

        return summary

    # ==========================================
    # СПИСКИ ПІДСУМКІВ
    # ==========================================

    async def get_for_date(
        self,
        *,
        business_date: date,
        summary_types: set[SummaryType] | None = None,
        bush_id: int | None = None,
        chat_id: int | None = None,
        with_message_only: bool | None = None,
    ) -> list[DailySummaryMessage]:
        """Повертає підсумки за дату."""

        conditions = [
            DailySummaryMessage.business_date
            == business_date,
        ]

        if summary_types:
            conditions.append(
                DailySummaryMessage.summary_type.in_(
                    summary_types
                )
            )

        if bush_id is not None:
            conditions.append(
                DailySummaryMessage.bush_id
                == bush_id
            )

        if chat_id is not None:
            conditions.append(
                DailySummaryMessage.chat_id
                == chat_id
            )

        if with_message_only is True:
            conditions.append(
                DailySummaryMessage.message_id
                .is_not(None)
            )

        elif with_message_only is False:
            conditions.append(
                DailySummaryMessage.message_id
                .is_(None)
            )

        statement = (
            select(DailySummaryMessage)
            .where(*conditions)
            .order_by(
                DailySummaryMessage.summary_type.asc(),
                DailySummaryMessage.bush_id.asc().nullsfirst(),
                DailySummaryMessage.id.asc(),
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_for_bush(
        self,
        *,
        bush_id: int,
        business_date: date | None = None,
    ) -> list[DailySummaryMessage]:
        """Повертає підсумки конкретного куща."""

        conditions = [
            DailySummaryMessage.bush_id == bush_id,
        ]

        if business_date is not None:
            conditions.append(
                DailySummaryMessage.business_date
                == business_date
            )

        statement = (
            select(DailySummaryMessage)
            .where(*conditions)
            .order_by(
                DailySummaryMessage.business_date.desc(),
                DailySummaryMessage.summary_type.asc(),
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_network_summaries(
        self,
        *,
        business_date: date,
    ) -> list[DailySummaryMessage]:
        """Повертає загальні підсумки мережі."""

        statement = (
            select(DailySummaryMessage)
            .where(
                DailySummaryMessage.business_date
                == business_date,
                DailySummaryMessage.bush_id.is_(None),
            )
            .order_by(
                DailySummaryMessage.summary_type.asc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_unsent_for_date(
        self,
        *,
        business_date: date,
        summary_types: set[SummaryType] | None = None,
    ) -> list[DailySummaryMessage]:
        """Повертає підсумки без Telegram message_id."""

        return await self.get_for_date(
            business_date=business_date,
            summary_types=summary_types,
            with_message_only=False,
        )

    async def get_sent_for_date(
        self,
        *,
        business_date: date,
        summary_types: set[SummaryType] | None = None,
    ) -> list[DailySummaryMessage]:
        """Повертає вже створені Telegram-підсумки."""

        return await self.get_for_date(
            business_date=business_date,
            summary_types=summary_types,
            with_message_only=True,
        )

    async def get_history(
        self,
        *,
        date_from: date,
        date_to: date,
        summary_type: SummaryType | None = None,
        bush_id: int | None = None,
        limit: int = 5000,
    ) -> list[DailySummaryMessage]:
        """Повертає історію живих підсумків."""

        self.validate_date_range(
            date_from=date_from,
            date_to=date_to,
        )

        self.validate_limit(
            limit,
            maximum=10_000,
        )

        conditions = [
            DailySummaryMessage.business_date
            >= date_from,
            DailySummaryMessage.business_date
            <= date_to,
        ]

        if summary_type is not None:
            conditions.append(
                DailySummaryMessage.summary_type
                == summary_type
            )

        if bush_id is not None:
            conditions.append(
                DailySummaryMessage.bush_id
                == bush_id
            )

        statement = (
            select(DailySummaryMessage)
            .where(*conditions)
            .order_by(
                DailySummaryMessage.business_date.desc(),
                DailySummaryMessage.summary_type.asc(),
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

    async def count_by_type(
        self,
        *,
        business_date: date | None = None,
    ) -> dict[SummaryType, int]:
        """Підраховує підсумки за типами."""

        statement = select(
            DailySummaryMessage.summary_type,
            func.count(
                DailySummaryMessage.id
            ),
        )

        if business_date is not None:
            statement = statement.where(
                DailySummaryMessage.business_date
                == business_date
            )

        statement = statement.group_by(
            DailySummaryMessage.summary_type
        )

        result = await self.session.execute(
            statement
        )

        counts = {
            summary_type: 0
            for summary_type in SummaryType
        }

        for summary_type, count in result.all():
            counts[summary_type] = int(count)

        return counts

    async def get_statistics(
        self,
        *,
        business_date: date,
    ) -> dict[str, int]:
        """Формує статистику Telegram-підсумків."""

        total_statement = select(
            func.count(
                DailySummaryMessage.id
            )
        ).where(
            DailySummaryMessage.business_date
            == business_date
        )

        sent_statement = select(
            func.count(
                DailySummaryMessage.id
            )
        ).where(
            DailySummaryMessage.business_date
            == business_date,
            DailySummaryMessage.message_id
            .is_not(None),
        )

        network_statement = select(
            func.count(
                DailySummaryMessage.id
            )
        ).where(
            DailySummaryMessage.business_date
            == business_date,
            DailySummaryMessage.bush_id.is_(None),
        )

        total_count = int(
            await self.session.scalar(
                total_statement
            )
            or 0
        )

        sent_count = int(
            await self.session.scalar(
                sent_statement
            )
            or 0
        )

        network_count = int(
            await self.session.scalar(
                network_statement
            )
            or 0
        )

        return {
            "total_count": total_count,
            "sent_count": sent_count,
            "unsent_count": (
                total_count - sent_count
            ),
            "network_count": network_count,
            "bush_count": (
                total_count - network_count
            ),
        }

    # ==========================================
    # ЗБЕРЕЖЕННЯ УСПІШНОГО ВМІСТУ
    # ==========================================

    def save_successful_content(
        self,
        summary: DailySummaryMessage,
        *,
        message_text: str,
        snapshot_json: dict[str, Any] | None,
        processed_at: datetime,
        action: str,
    ) -> None:
        """Зберігає останній успішний стан."""

        content_hash = self.build_content_hash(
            message_text
        )

        self.set_first_available_value(
            summary,
            names=(
                "message_text",
                "last_message_text",
                "last_text",
                "rendered_text",
            ),
            value=message_text,
        )

        self.set_first_available_value(
            summary,
            names=(
                "content_hash",
                "last_content_hash",
                "message_hash",
                "text_hash",
            ),
            value=content_hash,
        )

        self.set_first_available_value(
            summary,
            names=(
                "snapshot_json",
                "statistics_json",
                "stats_json",
                "payload_json",
            ),
            value=snapshot_json,
        )

        self.set_all_available_values(
            summary,
            names=(
                "pending_message_text",
                "next_message_text",
                "pending_snapshot_json",
                "next_snapshot_json",
            ),
            value=None,
        )

        if action == "sent":
            self.set_first_available_value(
                summary,
                names=(
                    "sent_at",
                    "first_sent_at",
                ),
                value=processed_at,
            )

        elif action == "edited":
            self.set_first_available_value(
                summary,
                names=(
                    "edited_at",
                    "last_edited_at",
                ),
                value=processed_at,
            )

        self.set_first_available_value(
            summary,
            names=(
                "last_synced_at",
                "last_updated_at",
                "last_rendered_at",
            ),
            value=processed_at,
        )

        self.increment_first_available_value(
            summary,
            names=(
                "revision",
                "revision_number",
                "edit_count",
                "update_count",
            ),
        )

        self.set_all_available_values(
            summary,
            names=(
                "last_error",
                "last_error_text",
                "error_text",
                "last_error_at",
                "failed_at",
            ),
            value=None,
        )

    # ==========================================
    # ХЕШУВАННЯ ТЕКСТУ
    # ==========================================

    @staticmethod
    def build_content_hash(
        message_text: str,
    ) -> str:
        """
        Створює SHA-256 хеш тексту.

        Telegram API не викликатиметься,
        якщо новий хеш збігається зі старим.
        """

        normalized_text = (
            DailySummaryRepository
            .normalize_required_text(
                message_text,
                field_name="Текст підсумку",
            )
        )

        return hashlib.sha256(
            normalized_text.encode("utf-8")
        ).hexdigest()

    # ==========================================
    # ПЕРЕВІРКА ОБЛАСТІ
    # ==========================================

    @staticmethod
    def validate_scope(
        *,
        summary_type: SummaryType,
        bush_id: int | None,
    ) -> None:
        """
        Перевіряє відповідність типу підсумку
        області куща або всієї мережі.
        """

        type_names = {
            summary_type.name.lower(),
            str(summary_type.value).lower(),
        }

        is_bush_summary = any(
            word in value
            for value in type_names
            for word in (
                "bush",
                "cluster",
                "кущ",
            )
        )

        is_network_summary = any(
            word in value
            for value in type_names
            for word in (
                "network",
                "global",
                "all",
                "мереж",
            )
        )

        if (
            is_bush_summary
            and bush_id is None
        ):
            raise ValueError(
                "Для підсумку куща потрібно "
                "вказати bush_id."
            )

        if (
            is_network_summary
            and bush_id is not None
        ):
            raise ValueError(
                "Загальний підсумок мережі "
                "не повинен містити bush_id."
            )

        if bush_id is not None and bush_id <= 0:
            raise ValueError(
                "ID куща повинен бути більшим за нуль."
            )

    # ==========================================
    # СУМІСНІСТЬ ІЗ МОДЕЛЛЮ
    # ==========================================

    @staticmethod
    def mapped_field_names() -> set[str]:
        """Повертає всі поля моделі."""

        mapper = inspect(
            DailySummaryMessage
        )

        return {
            attribute.key
            for attribute in mapper.attrs
        }

    @classmethod
    def set_first_available_value(
        cls,
        summary: DailySummaryMessage,
        *,
        names: tuple[str, ...],
        value: Any,
    ) -> bool:
        """Встановлює перше доступне поле."""

        available_fields = (
            cls.mapped_field_names()
        )

        for field_name in names:
            if field_name not in available_fields:
                continue

            setattr(
                summary,
                field_name,
                value,
            )

            return True

        return False

    @classmethod
    def set_all_available_values(
        cls,
        summary: DailySummaryMessage,
        *,
        names: tuple[str, ...],
        value: Any,
    ) -> bool:
        """Встановлює всі знайдені поля."""

        available_fields = (
            cls.mapped_field_names()
        )

        changed = False

        for field_name in names:
            if field_name not in available_fields:
                continue

            setattr(
                summary,
                field_name,
                value,
            )

            changed = True

        return changed

    @classmethod
    def get_first_available_value(
        cls,
        summary: DailySummaryMessage,
        *,
        names: tuple[str, ...],
    ) -> Any:
        """Читає значення першого доступного поля."""

        available_fields = (
            cls.mapped_field_names()
        )

        for field_name in names:
            if field_name not in available_fields:
                continue

            return getattr(
                summary,
                field_name,
                None,
            )

        return None

    @classmethod
    def increment_first_available_value(
        cls,
        summary: DailySummaryMessage,
        *,
        names: tuple[str, ...],
    ) -> bool:
        """Збільшує перше знайдене числове поле."""

        available_fields = (
            cls.mapped_field_names()
        )

        for field_name in names:
            if field_name not in available_fields:
                continue

            current_value = getattr(
                summary,
                field_name,
                0,
            )

            setattr(
                summary,
                field_name,
                int(current_value or 0) + 1,
            )

            return True

        return False

    @staticmethod
    def get_model_attribute(
        field_name: str,
    ) -> InstrumentedAttribute[Any] | None:
        """Повертає SQLAlchemy-поле моделі."""

        attribute = getattr(
            DailySummaryMessage,
            field_name,
            None,
        )

        if isinstance(
            attribute,
            InstrumentedAttribute,
        ):
            return attribute

        return None

    # ==========================================
    # ВАЛІДАЦІЯ
    # ==========================================

    @staticmethod
    def normalize_required_text(
        value: str,
        *,
        field_name: str,
    ) -> str:
        """Нормалізує обов’язковий текст."""

        normalized_value = value.strip()

        if not normalized_value:
            raise ValueError(
                f"{field_name} не може бути порожнім."
            )

        return normalized_value

    @staticmethod
    def normalize_optional_text(
        value: str | None,
    ) -> str | None:
        """Нормалізує необов’язковий текст."""

        if value is None:
            return None

        normalized_value = value.strip()

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
    def validate_topic_id(
        topic_id: int | None,
    ) -> None:
        """Перевіряє ID Telegram-теми."""

        if topic_id is not None and topic_id <= 0:
            raise ValueError(
                "Telegram topic_id повинен бути "
                "більшим за нуль."
            )

    @staticmethod
    def validate_aware_datetime(
        value: datetime,
        *,
        field_name: str,
    ) -> None:
        """Перевіряє наявність часового поясу."""

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