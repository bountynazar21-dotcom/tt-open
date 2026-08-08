from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable

from sqlalchemy import (
    func,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload

from app.database.models.enums import (
    NotificationStatus,
    NotificationType,
)
from app.database.models.notification import NotificationLog
from app.repositories.base import BaseRepository


@dataclass(slots=True)
class NotificationReservation:
    """
    Результат резервування повідомлення.

    Якщо should_send=True, поточна транзакція повинна
    залишатися відкритою до завершення Telegram-запиту
    та виклику mark_sent() або mark_failed().
    """

    notification: NotificationLog
    should_send: bool
    reason: str

    @property
    def is_already_delivered(self) -> bool:
        return self.reason == "already_delivered"

    @property
    def is_not_due(self) -> bool:
        return self.reason == "not_due"

    @property
    def attempts_exhausted(self) -> bool:
        return self.reason == "attempts_exhausted"


class NotificationRepository(
    BaseRepository[NotificationLog]
):
    """
    Репозиторій Telegram-повідомлень.

    Основні правила:

    - кожне логічне повідомлення має dedupe_key;
    - один dedupe_key може існувати лише один раз;
    - повторний запуск scheduler не створює дублікат;
    - повідомлення резервується транзакційним блокуванням;
    - успішні повідомлення не надсилаються повторно;
    - невдалі повідомлення можна повернути у чергу.
    """

    model = NotificationLog

    DELIVERED_STATUSES: frozenset[
        NotificationStatus
    ] = frozenset(
        {
            NotificationStatus.SENT,
            NotificationStatus.EDITED,
        }
    )

    TERMINAL_STATUSES: frozenset[
        NotificationStatus
    ] = frozenset(
        {
            NotificationStatus.SENT,
            NotificationStatus.EDITED,
            NotificationStatus.SKIPPED,
        }
    )

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        super().__init__(session)

    # ==========================================
    # ПОШУК
    # ==========================================

    async def get_by_id(
        self,
        notification_id: int,
        *,
        for_update: bool = False,
    ) -> NotificationLog | None:
        """Повертає повідомлення за внутрішнім ID."""

        self.validate_positive_id(
            notification_id,
            field_name="ID повідомлення",
        )

        statement = (
            select(NotificationLog)
            .where(
                NotificationLog.id
                == notification_id
            )
            .limit(1)
        )

        if for_update:
            statement = (
                statement
                .options(
                    lazyload(
                        NotificationLog.recipient_user
                    ),
                    lazyload(
                        NotificationLog.store
                    ),
                    lazyload(
                        NotificationLog.bush
                    ),
                )
                .with_for_update(
                    of=NotificationLog
                )
            )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_by_id_or_raise(
        self,
        notification_id: int,
        *,
        for_update: bool = False,
    ) -> NotificationLog:
        """Повертає повідомлення або викликає помилку."""

        notification = await self.get_by_id(
            notification_id,
            for_update=for_update,
        )

        if notification is None:
            raise ValueError(
                "Повідомлення не знайдено."
            )

        return notification

    async def get_by_dedupe_key(
        self,
        dedupe_key: str,
        *,
        for_update: bool = False,
    ) -> NotificationLog | None:
        """Повертає повідомлення за унікальним ключем."""

        normalized_key = self.normalize_dedupe_key(
            dedupe_key
        )

        statement = (
            select(NotificationLog)
            .where(
                NotificationLog.dedupe_key
                == normalized_key
            )
            .limit(1)
        )

        if for_update:
            statement = (
                statement
                .options(
                    lazyload(
                        NotificationLog.recipient_user
                    ),
                    lazyload(
                        NotificationLog.store
                    ),
                    lazyload(
                        NotificationLog.bush
                    ),
                )
                .with_for_update(
                    of=NotificationLog
                )
            )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_by_dedupe_key_or_raise(
        self,
        dedupe_key: str,
        *,
        for_update: bool = False,
    ) -> NotificationLog:
        """Повертає повідомлення або викликає помилку."""

        notification = await self.get_by_dedupe_key(
            dedupe_key,
            for_update=for_update,
        )

        if notification is None:
            raise ValueError(
                "Повідомлення з таким ключем "
                "дедуплікації не знайдено."
            )

        return notification

    async def get_by_chat_message(
        self,
        *,
        chat_id: int,
        message_id: int,
    ) -> NotificationLog | None:
        """Шукає запис за Telegram chat_id і message_id."""

        if message_id <= 0:
            return None

        statement = (
            select(NotificationLog)
            .where(
                NotificationLog.chat_id == chat_id,
                NotificationLog.message_id
                == message_id,
            )
            .order_by(
                NotificationLog.id.desc()
            )
            .limit(1)
        )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    # ==========================================
    # СТВОРЕННЯ З DEDUPE_KEY
    # ==========================================

    async def get_or_create_pending(
        self,
        *,
        notification_type: NotificationType,
        dedupe_key: str,
        business_date: date | None = None,
        scheduled_for: datetime | None = None,
        recipient_user_id: int | None = None,
        store_id: int | None = None,
        bush_id: int | None = None,
        chat_id: int | None = None,
        topic_id: int | None = None,
        message_text: str | None = None,
        payload_json: dict[str, Any] | None = None,
        update_existing_pending: bool = False,
    ) -> tuple[NotificationLog, bool]:
        """
        Повертає існуюче або створює нове повідомлення.

        Для PostgreSQL використовується:

        INSERT ... ON CONFLICT DO NOTHING

        Тому навіть два одночасні scheduler-процеси
        не створять два записи з однаковим dedupe_key.

        Результат:
        - NotificationLog;
        - True, якщо запис створено;
        - False, якщо він уже існував.
        """

        normalized_key = self.normalize_dedupe_key(
            dedupe_key
        )

        if scheduled_for is not None:
            self.validate_aware_datetime(
                scheduled_for,
                field_name="scheduled_for",
            )

        pending = NotificationLog.create_pending(
            notification_type=notification_type,
            dedupe_key=normalized_key,
            business_date=business_date,
            scheduled_for=scheduled_for,
            recipient_user_id=recipient_user_id,
            store_id=store_id,
            bush_id=bush_id,
            chat_id=chat_id,
            topic_id=topic_id,
            message_text=message_text,
            payload_json=payload_json,
        )

        statement = (
            pg_insert(NotificationLog)
            .values(
                notification_type=(
                    pending.notification_type
                ),
                status=pending.status,
                dedupe_key=pending.dedupe_key,
                idempotency_hash=(
                    pending.idempotency_hash
                ),
                business_date=(
                    pending.business_date
                ),
                scheduled_for=pending.scheduled_for,
                recipient_user_id=(
                    pending.recipient_user_id
                ),
                store_id=pending.store_id,
                bush_id=pending.bush_id,
                chat_id=pending.chat_id,
                topic_id=pending.topic_id,
                message_text=pending.message_text,
                payload_json=pending.payload_json,
                attempt_count=0,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    NotificationLog.dedupe_key,
                ]
            )
            .returning(
                NotificationLog.id
            )
        )

        inserted_id = await self.session.scalar(
            statement
        )

        if inserted_id is not None:
            notification = await self.get_by_id(
                int(inserted_id)
            )

            if notification is None:
                raise RuntimeError(
                    "Повідомлення створено, але його "
                    "не вдалося повторно завантажити."
                )

            return notification, True

        existing = (
            await self.get_by_dedupe_key_or_raise(
                normalized_key,
                for_update=update_existing_pending,
            )
        )

        if (
            update_existing_pending
            and existing.status
            in {
                NotificationStatus.PENDING,
                NotificationStatus.FAILED,
            }
        ):
            existing.notification_type = (
                notification_type
            )

            existing.business_date = business_date
            existing.scheduled_for = scheduled_for
            existing.recipient_user_id = (
                recipient_user_id
            )

            existing.store_id = store_id
            existing.bush_id = bush_id
            existing.chat_id = chat_id
            existing.topic_id = topic_id

            existing.message_text = message_text
            existing.payload_json = payload_json

            self.session.add(existing)
            await self.session.flush()

        return existing, False

    async def get_or_create_from_parts(
        self,
        *,
        notification_type: NotificationType,
        business_date: date | None = None,
        recipient_user_id: int | None = None,
        store_id: int | None = None,
        bush_id: int | None = None,
        chat_id: int | None = None,
        topic_id: int | None = None,
        suffix: str | None = None,
        scheduled_for: datetime | None = None,
        message_text: str | None = None,
        payload_json: dict[str, Any] | None = None,
        update_existing_pending: bool = False,
    ) -> tuple[NotificationLog, bool]:
        """
        Самостійно формує dedupe_key
        та створює повідомлення.
        """

        dedupe_key = NotificationLog.build_dedupe_key(
            notification_type=notification_type,
            business_date=business_date,
            recipient_user_id=recipient_user_id,
            store_id=store_id,
            bush_id=bush_id,
            chat_id=chat_id,
            suffix=suffix,
        )

        if topic_id is not None:
            dedupe_key = (
                f"{dedupe_key}:topic-{topic_id}"
            )

        return await self.get_or_create_pending(
            notification_type=notification_type,
            dedupe_key=dedupe_key,
            business_date=business_date,
            scheduled_for=scheduled_for,
            recipient_user_id=recipient_user_id,
            store_id=store_id,
            bush_id=bush_id,
            chat_id=chat_id,
            topic_id=topic_id,
            message_text=message_text,
            payload_json=payload_json,
            update_existing_pending=(
                update_existing_pending
            ),
        )

    # ==========================================
    # РЕЗЕРВУВАННЯ ПЕРЕД НАДСИЛАННЯМ
    # ==========================================

    async def reserve_for_sending(
        self,
        *,
        dedupe_key: str,
        attempted_at: datetime,
        max_attempts: int = 5,
    ) -> NotificationReservation:
        """
        Резервує повідомлення перед Telegram-запитом.

        Запис блокується через SELECT FOR UPDATE.

        Важливо:
        Telegram-запит і mark_sent()/mark_failed()
        потрібно виконати до commit поточної транзакції.
        """

        self.validate_aware_datetime(
            attempted_at,
            field_name="attempted_at",
        )

        if max_attempts <= 0:
            raise ValueError(
                "Максимальна кількість спроб "
                "повинна бути більшою за нуль."
            )

        notification = (
            await self.get_by_dedupe_key_or_raise(
                dedupe_key,
                for_update=True,
            )
        )

        if notification.status in self.DELIVERED_STATUSES:
            return NotificationReservation(
                notification=notification,
                should_send=False,
                reason="already_delivered",
            )

        if (
            notification.status
            == NotificationStatus.SKIPPED
        ):
            return NotificationReservation(
                notification=notification,
                should_send=False,
                reason="skipped",
            )

        if (
            notification.scheduled_for is not None
            and notification.scheduled_for
            > attempted_at
        ):
            return NotificationReservation(
                notification=notification,
                should_send=False,
                reason="not_due",
            )

        if notification.attempt_count >= max_attempts:
            return NotificationReservation(
                notification=notification,
                should_send=False,
                reason="attempts_exhausted",
            )

        if (
            notification.status
            == NotificationStatus.FAILED
        ):
            notification.reset_for_retry()

        notification.register_attempt(
            attempted_at=attempted_at
        )

        self.session.add(notification)
        await self.session.flush()

        return NotificationReservation(
            notification=notification,
            should_send=True,
            reason="reserved",
        )

    async def reserve_by_id(
        self,
        *,
        notification_id: int,
        attempted_at: datetime,
        max_attempts: int = 5,
    ) -> NotificationReservation:
        """Резервує повідомлення за ID."""

        self.validate_aware_datetime(
            attempted_at,
            field_name="attempted_at",
        )

        notification = await self.get_by_id_or_raise(
            notification_id,
            for_update=True,
        )

        return await self.reserve_for_sending(
            dedupe_key=notification.dedupe_key,
            attempted_at=attempted_at,
            max_attempts=max_attempts,
        )

    # ==========================================
    # УСПІШНЕ НАДСИЛАННЯ
    # ==========================================

    async def mark_sent(
        self,
        notification: NotificationLog,
        *,
        sent_at: datetime,
        chat_id: int,
        message_id: int,
        topic_id: int | None = None,
        message_text: str | None = None,
    ) -> NotificationLog:
        """Фіксує успішне надсилання повідомлення."""

        self.validate_aware_datetime(
            sent_at,
            field_name="sent_at",
        )

        if message_id <= 0:
            raise ValueError(
                "Telegram message_id повинен бути "
                "більшим за нуль."
            )

        if notification.status in self.DELIVERED_STATUSES:
            return notification

        notification.mark_sent(
            sent_at=sent_at,
            chat_id=chat_id,
            message_id=message_id,
            topic_id=topic_id,
            message_text=message_text,
        )

        self.session.add(notification)
        await self.session.flush()

        return notification

    async def mark_sent_by_dedupe_key(
        self,
        *,
        dedupe_key: str,
        sent_at: datetime,
        chat_id: int,
        message_id: int,
        topic_id: int | None = None,
        message_text: str | None = None,
    ) -> NotificationLog:
        """Фіксує доставку за dedupe_key."""

        notification = (
            await self.get_by_dedupe_key_or_raise(
                dedupe_key,
                for_update=True,
            )
        )

        return await self.mark_sent(
            notification,
            sent_at=sent_at,
            chat_id=chat_id,
            message_id=message_id,
            topic_id=topic_id,
            message_text=message_text,
        )

    # ==========================================
    # РЕДАГУВАННЯ ПОВІДОМЛЕННЯ
    # ==========================================

    async def mark_edited(
        self,
        notification: NotificationLog,
        *,
        edited_at: datetime,
        message_text: str | None = None,
    ) -> NotificationLog:
        """Фіксує успішне редагування повідомлення."""

        self.validate_aware_datetime(
            edited_at,
            field_name="edited_at",
        )

        notification.mark_edited(
            edited_at=edited_at,
            message_text=message_text,
        )

        self.session.add(notification)
        await self.session.flush()

        return notification

    async def mark_edited_by_chat_message(
        self,
        *,
        chat_id: int,
        message_id: int,
        edited_at: datetime,
        message_text: str | None = None,
    ) -> NotificationLog:
        """Фіксує редагування за Telegram message_id."""

        notification = await self.get_by_chat_message(
            chat_id=chat_id,
            message_id=message_id,
        )

        if notification is None:
            raise ValueError(
                "Telegram-повідомлення не знайдено "
                "у журналі."
            )

        locked_notification = (
            await self.get_by_id_or_raise(
                notification.id,
                for_update=True,
            )
        )

        return await self.mark_edited(
            locked_notification,
            edited_at=edited_at,
            message_text=message_text,
        )

    # ==========================================
    # ПОМИЛКА НАДСИЛАННЯ
    # ==========================================

    async def mark_failed(
        self,
        notification: NotificationLog,
        *,
        failed_at: datetime,
        error_text: str,
        telegram_error_code: str | None = None,
    ) -> NotificationLog:
        """Фіксує помилку Telegram API."""

        self.validate_aware_datetime(
            failed_at,
            field_name="failed_at",
        )

        if notification.status in self.DELIVERED_STATUSES:
            raise ValueError(
                "Уже доставлене повідомлення "
                "не можна позначити невдалим."
            )

        notification.mark_failed(
            failed_at=failed_at,
            error_text=error_text,
            telegram_error_code=(
                telegram_error_code
            ),
        )

        self.session.add(notification)
        await self.session.flush()

        return notification

    async def mark_failed_by_dedupe_key(
        self,
        *,
        dedupe_key: str,
        failed_at: datetime,
        error_text: str,
        telegram_error_code: str | None = None,
    ) -> NotificationLog:
        """Фіксує помилку за dedupe_key."""

        notification = (
            await self.get_by_dedupe_key_or_raise(
                dedupe_key,
                for_update=True,
            )
        )

        return await self.mark_failed(
            notification,
            failed_at=failed_at,
            error_text=error_text,
            telegram_error_code=(
                telegram_error_code
            ),
        )

    # ==========================================
    # ПРОПУСК ПОВІДОМЛЕННЯ
    # ==========================================

    async def mark_skipped(
        self,
        notification: NotificationLog,
        *,
        skipped_at: datetime,
        reason: str,
    ) -> NotificationLog:
        """
        Позначає повідомлення пропущеним.

        Наприклад:
        ТТ уже відкрилася до моменту надсилання
        нагадування.
        """

        self.validate_aware_datetime(
            skipped_at,
            field_name="skipped_at",
        )

        if notification.status in self.DELIVERED_STATUSES:
            raise ValueError(
                "Доставлене повідомлення не можна "
                "позначити пропущеним."
            )

        notification.mark_skipped(
            skipped_at=skipped_at,
            reason=reason,
        )

        self.session.add(notification)
        await self.session.flush()

        return notification

    async def mark_skipped_by_dedupe_key(
        self,
        *,
        dedupe_key: str,
        skipped_at: datetime,
        reason: str,
    ) -> NotificationLog:
        """Позначає пропуск за dedupe_key."""

        notification = (
            await self.get_by_dedupe_key_or_raise(
                dedupe_key,
                for_update=True,
            )
        )

        return await self.mark_skipped(
            notification,
            skipped_at=skipped_at,
            reason=reason,
        )

    # ==========================================
    # ПОВТОРНІ СПРОБИ
    # ==========================================

    async def schedule_retry(
        self,
        notification: NotificationLog,
        *,
        retry_at: datetime | None = None,
        reset_error: bool = True,
    ) -> NotificationLog:
        """Повертає невдале повідомлення у чергу."""

        if retry_at is not None:
            self.validate_aware_datetime(
                retry_at,
                field_name="retry_at",
            )

        if notification.status not in {
            NotificationStatus.FAILED,
            NotificationStatus.SKIPPED,
        }:
            raise ValueError(
                "Повторити можна лише невдале "
                "або пропущене повідомлення."
            )

        notification.status = (
            NotificationStatus.PENDING
        )

        notification.scheduled_for = retry_at

        if reset_error:
            notification.error_text = None
            notification.telegram_error_code = None

        self.session.add(notification)
        await self.session.flush()

        return notification

    async def schedule_retry_by_id(
        self,
        *,
        notification_id: int,
        retry_at: datetime | None = None,
    ) -> NotificationLog:
        """Повертає повідомлення у чергу за ID."""

        notification = await self.get_by_id_or_raise(
            notification_id,
            for_update=True,
        )

        return await self.schedule_retry(
            notification,
            retry_at=retry_at,
        )

    async def retry_failed_batch(
        self,
        *,
        retry_at: datetime,
        max_attempts: int = 5,
        limit: int = 100,
    ) -> list[NotificationLog]:
        """
        Повертає групу невдалих повідомлень у чергу.

        skip_locked дозволяє запускати декілька
        worker-процесів без конфлікту.
        """

        self.validate_aware_datetime(
            retry_at,
            field_name="retry_at",
        )

        self.validate_limit(
            limit,
            maximum=1000,
        )

        statement = (
            select(NotificationLog)
            .options(
                lazyload(
                    NotificationLog.recipient_user
                ),
                lazyload(
                    NotificationLog.store
                ),
                lazyload(
                    NotificationLog.bush
                ),
            )
            .where(
                NotificationLog.status
                == NotificationStatus.FAILED,
                NotificationLog.attempt_count
                < max_attempts,
            )
            .order_by(
                NotificationLog
                .last_attempt_at
                .asc()
                .nullsfirst(),
                NotificationLog.id.asc(),
            )
            .with_for_update(
                of=NotificationLog,
                skip_locked=True,
            )
            .limit(limit)
        )

        result = await self.session.scalars(
            statement
        )

        notifications = list(
            result.unique().all()
        )

        for notification in notifications:
            notification.status = (
                NotificationStatus.PENDING
            )

            notification.scheduled_for = retry_at
            notification.error_text = None
            notification.telegram_error_code = None

            self.session.add(notification)

        if notifications:
            await self.session.flush()

        return notifications

    # ==========================================
    # ОНОВЛЕННЯ ВМІСТУ
    # ==========================================

    async def update_pending_content(
        self,
        notification: NotificationLog,
        *,
        message_text: str | None = None,
        payload_json: dict[str, Any] | None = None,
        scheduled_for: datetime | None = None,
        chat_id: int | None = None,
        topic_id: int | None = None,
    ) -> NotificationLog:
        """Оновлює ще не доставлене повідомлення."""

        if notification.status in self.DELIVERED_STATUSES:
            raise ValueError(
                "Доставлене повідомлення потрібно "
                "редагувати через Telegram API."
            )

        if scheduled_for is not None:
            self.validate_aware_datetime(
                scheduled_for,
                field_name="scheduled_for",
            )

        notification.message_text = message_text
        notification.payload_json = payload_json
        notification.scheduled_for = scheduled_for
        notification.chat_id = chat_id
        notification.topic_id = topic_id

        self.session.add(notification)
        await self.session.flush()

        return notification

    # ==========================================
    # ЧЕРГА ПОВІДОМЛЕНЬ
    # ==========================================

    async def get_due_pending(
        self,
        *,
        current_time: datetime,
        notification_types: set[
            NotificationType
        ]
        | None = None,
        business_date: date | None = None,
        recipient_user_id: int | None = None,
        store_id: int | None = None,
        bush_id: int | None = None,
        limit: int = 100,
    ) -> list[NotificationLog]:
        """Повертає повідомлення, готові до надсилання."""

        self.validate_aware_datetime(
            current_time,
            field_name="current_time",
        )

        self.validate_limit(
            limit,
            maximum=1000,
        )

        conditions = [
            NotificationLog.status
            == NotificationStatus.PENDING,
            or_(
                NotificationLog.scheduled_for
                .is_(None),
                NotificationLog.scheduled_for
                <= current_time,
            ),
        ]

        if notification_types:
            conditions.append(
                NotificationLog.notification_type
                .in_(notification_types)
            )

        if business_date is not None:
            conditions.append(
                NotificationLog.business_date
                == business_date
            )

        if recipient_user_id is not None:
            conditions.append(
                NotificationLog.recipient_user_id
                == recipient_user_id
            )

        if store_id is not None:
            conditions.append(
                NotificationLog.store_id
                == store_id
            )

        if bush_id is not None:
            conditions.append(
                NotificationLog.bush_id
                == bush_id
            )

        statement = (
            select(NotificationLog)
            .where(*conditions)
            .order_by(
                NotificationLog
                .scheduled_for
                .asc()
                .nullsfirst(),
                NotificationLog.id.asc(),
            )
            .limit(limit)
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_failed(
        self,
        *,
        max_attempts: int | None = None,
        business_date: date | None = None,
        limit: int = 100,
    ) -> list[NotificationLog]:
        """Повертає невдалі повідомлення."""

        self.validate_limit(
            limit,
            maximum=1000,
        )

        conditions = [
            NotificationLog.status
            == NotificationStatus.FAILED,
        ]

        if max_attempts is not None:
            conditions.append(
                NotificationLog.attempt_count
                < max_attempts
            )

        if business_date is not None:
            conditions.append(
                NotificationLog.business_date
                == business_date
            )

        statement = (
            select(NotificationLog)
            .where(*conditions)
            .order_by(
                NotificationLog
                .last_attempt_at
                .desc()
                .nullslast(),
                NotificationLog.id.desc(),
            )
            .limit(limit)
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_attempts_exhausted(
        self,
        *,
        max_attempts: int = 5,
        limit: int = 100,
    ) -> list[NotificationLog]:
        """Повертає повідомлення з вичерпаними спробами."""

        self.validate_limit(
            limit,
            maximum=1000,
        )

        statement = (
            select(NotificationLog)
            .where(
                NotificationLog.status
                == NotificationStatus.FAILED,
                NotificationLog.attempt_count
                >= max_attempts,
            )
            .order_by(
                NotificationLog
                .last_attempt_at
                .desc()
                .nullslast()
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
    # СПИСКИ ТА ІСТОРІЯ
    # ==========================================

    async def get_for_date(
        self,
        *,
        business_date: date,
        statuses: set[
            NotificationStatus
        ]
        | None = None,
        notification_types: set[
            NotificationType
        ]
        | None = None,
        store_id: int | None = None,
        bush_id: int | None = None,
        recipient_user_id: int | None = None,
        limit: int = 1000,
    ) -> list[NotificationLog]:
        """Повертає журнал повідомлень за день."""

        self.validate_limit(
            limit,
            maximum=10_000,
        )

        conditions = [
            NotificationLog.business_date
            == business_date,
        ]

        if statuses:
            conditions.append(
                NotificationLog.status.in_(
                    statuses
                )
            )

        if notification_types:
            conditions.append(
                NotificationLog.notification_type
                .in_(notification_types)
            )

        if store_id is not None:
            conditions.append(
                NotificationLog.store_id
                == store_id
            )

        if bush_id is not None:
            conditions.append(
                NotificationLog.bush_id
                == bush_id
            )

        if recipient_user_id is not None:
            conditions.append(
                NotificationLog.recipient_user_id
                == recipient_user_id
            )

        statement = (
            select(NotificationLog)
            .where(*conditions)
            .order_by(
                NotificationLog.created_at.desc(),
                NotificationLog.id.desc(),
            )
            .limit(limit)
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_store_history(
        self,
        *,
        store_id: int,
        date_from: date,
        date_to: date,
        limit: int = 5000,
    ) -> list[NotificationLog]:
        """Повертає повідомлення конкретної ТТ."""

        self.validate_date_range(
            date_from=date_from,
            date_to=date_to,
        )

        self.validate_limit(
            limit,
            maximum=10_000,
        )

        statement = (
            select(NotificationLog)
            .where(
                NotificationLog.store_id == store_id,
                NotificationLog.business_date
                >= date_from,
                NotificationLog.business_date
                <= date_to,
            )
            .order_by(
                NotificationLog.business_date.desc(),
                NotificationLog.created_at.desc(),
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
    # ПЕРЕВІРКИ ДОСТАВКИ
    # ==========================================

    async def was_delivered(
        self,
        dedupe_key: str,
    ) -> bool:
        """Чи було логічне повідомлення доставлено."""

        normalized_key = self.normalize_dedupe_key(
            dedupe_key
        )

        statement = select(
            select(NotificationLog.id)
            .where(
                NotificationLog.dedupe_key
                == normalized_key,
                NotificationLog.status.in_(
                    self.DELIVERED_STATUSES
                ),
            )
            .exists()
        )

        result = await self.session.scalar(
            statement
        )

        return bool(result)

    async def exists_by_dedupe_key(
        self,
        dedupe_key: str,
    ) -> bool:
        """Чи існує запис із таким dedupe_key."""

        normalized_key = self.normalize_dedupe_key(
            dedupe_key
        )

        statement = select(
            select(NotificationLog.id)
            .where(
                NotificationLog.dedupe_key
                == normalized_key
            )
            .exists()
        )

        result = await self.session.scalar(
            statement
        )

        return bool(result)

    # ==========================================
    # СТАТИСТИКА
    # ==========================================

    async def count_by_status(
        self,
        *,
        business_date: date | None = None,
    ) -> dict[NotificationStatus, int]:
        """Підраховує повідомлення за статусами."""

        statement = select(
            NotificationLog.status,
            func.count(NotificationLog.id),
        )

        if business_date is not None:
            statement = statement.where(
                NotificationLog.business_date
                == business_date
            )

        statement = statement.group_by(
            NotificationLog.status
        )

        result = await self.session.execute(
            statement
        )

        counts = {
            status: 0
            for status in NotificationStatus
        }

        for status, count in result.all():
            counts[status] = int(count)

        return counts

    async def count_by_type(
        self,
        *,
        business_date: date | None = None,
    ) -> dict[NotificationType, int]:
        """Підраховує повідомлення за типами."""

        statement = select(
            NotificationLog.notification_type,
            func.count(NotificationLog.id),
        )

        if business_date is not None:
            statement = statement.where(
                NotificationLog.business_date
                == business_date
            )

        statement = statement.group_by(
            NotificationLog.notification_type
        )

        result = await self.session.execute(
            statement
        )

        counts = {
            notification_type: 0
            for notification_type in NotificationType
        }

        for notification_type, count in result.all():
            counts[notification_type] = int(count)

        return counts

    async def get_statistics(
        self,
        *,
        business_date: date | None = None,
    ) -> dict[str, int | float]:
        """Формує загальну статистику доставки."""

        counts = await self.count_by_status(
            business_date=business_date
        )

        total_count = sum(counts.values())

        delivered_count = sum(
            counts[status]
            for status in self.DELIVERED_STATUSES
        )

        failed_count = counts[
            NotificationStatus.FAILED
        ]

        pending_count = counts[
            NotificationStatus.PENDING
        ]

        skipped_count = counts[
            NotificationStatus.SKIPPED
        ]

        attempts_statement = select(
            func.coalesce(
                func.sum(
                    NotificationLog.attempt_count
                ),
                0,
            ),
            func.coalesce(
                func.avg(
                    NotificationLog.attempt_count
                ),
                0,
            ),
            func.coalesce(
                func.max(
                    NotificationLog.attempt_count
                ),
                0,
            ),
        )

        if business_date is not None:
            attempts_statement = (
                attempts_statement.where(
                    NotificationLog.business_date
                    == business_date
                )
            )

        attempts_result = (
            await self.session.execute(
                attempts_statement
            )
        )

        total_attempts, average_attempts, maximum_attempts = (
            attempts_result.one()
        )

        delivery_percent = (
            round(
                delivered_count
                / total_count
                * 100,
                2,
            )
            if total_count > 0
            else 0.0
        )

        return {
            "total_count": total_count,
            "pending_count": pending_count,
            "sent_count": counts[
                NotificationStatus.SENT
            ],
            "edited_count": counts[
                NotificationStatus.EDITED
            ],
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "delivered_count": delivered_count,
            "total_attempts": int(
                total_attempts or 0
            ),
            "average_attempts": round(
                float(average_attempts or 0),
                2,
            ),
            "maximum_attempts": int(
                maximum_attempts or 0
            ),
            "delivery_percent": (
                delivery_percent
            ),
        }

    # ==========================================
    # ДОПОМІЖНІ МЕТОДИ
    # ==========================================

    @staticmethod
    def normalize_dedupe_key(
        dedupe_key: str,
    ) -> str:
        """Нормалізує ключ дедуплікації."""

        normalized_key = dedupe_key.strip()

        if not normalized_key:
            raise ValueError(
                "Ключ дедуплікації не може бути "
                "порожнім."
            )

        if len(normalized_key) > 255:
            raise ValueError(
                "Ключ дедуплікації не може бути "
                "довшим за 255 символів."
            )

        return normalized_key

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
        """Перевіряє обмеження кількості записів."""

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