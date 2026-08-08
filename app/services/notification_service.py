from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Any

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramMigrateToChat,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import Message

from app.database.models.enums import (
    NotificationStatus,
    NotificationType,
    UserStatus,
)
from app.database.models.notification import (
    NotificationLog,
)
from app.database.models.user import User
from app.repositories import (
    NotificationReservation,
    Repositories,
)


class DeliveryResultStatus(StrEnum):
    """
    Результат обробки одного повідомлення.
    """

    SENT = "sent"
    RETRY_SCHEDULED = "retry_scheduled"
    FAILED = "failed"
    SKIPPED = "skipped"
    ALREADY_DELIVERED = "already_delivered"
    NOT_DUE = "not_due"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"


@dataclass(slots=True, frozen=True)
class NotificationDeliveryResult:
    """
    Результат обробки одного повідомлення.
    """

    notification_id: int
    dedupe_key: str

    status: DeliveryResultStatus
    reason: str

    chat_id: int | None = None
    message_id: int | None = None

    retry_at: datetime | None = None
    error_text: str | None = None

    @property
    def was_sent(self) -> bool:
        return self.status == DeliveryResultStatus.SENT

    @property
    def should_retry(self) -> bool:
        return (
            self.status
            == DeliveryResultStatus.RETRY_SCHEDULED
        )


@dataclass(slots=True, frozen=True)
class NotificationBatchResult:
    """
    Результат обробки черги повідомлень.
    """

    started_at: datetime
    finished_at: datetime

    selected_count: int
    processed_count: int

    sent_count: int
    retry_count: int
    failed_count: int
    skipped_count: int

    results: tuple[
        NotificationDeliveryResult,
        ...,
    ]


@dataclass(slots=True, frozen=True)
class QueueNotificationResult:
    """
    Результат додавання повідомлення в чергу.
    """

    notification: NotificationLog
    was_created: bool


class NotificationService:
    """
    Сервіс надсилання Telegram-повідомлень.

    Відповідає за:

    - обробку черги NotificationLog;
    - надсилання тексту;
    - надсилання фото;
    - надсилання документів;
    - роботу з Telegram topics;
    - повторні спроби;
    - обробку RetryAfter;
    - захист від дублів;
    - фіксацію message_id;
    - відновлення після перезапуску Railway.

    Кожне логічне повідомлення повинно мати
    унікальний dedupe_key.
    """

    TELEGRAM_MESSAGE_LIMIT = 4096
    TELEGRAM_CAPTION_LIMIT = 1024

    RETRYABLE_ERRORS = (
        TelegramRetryAfter,
        TelegramNetworkError,
        TelegramServerError,
    )

    def __init__(
        self,
        repositories: Repositories,
        bot: Bot,
    ) -> None:
        self.repositories = repositories
        self.session = repositories.session
        self.bot = bot

    # ==========================================
    # ДОДАВАННЯ ТЕКСТУ В ЧЕРГУ
    # ==========================================

    async def queue_text(
        self,
        *,
        notification_type: NotificationType,
        message_text: str,
        business_date: date | None = None,
        scheduled_for: datetime | None = None,
        recipient_user_id: int | None = None,
        store_id: int | None = None,
        bush_id: int | None = None,
        chat_id: int | None = None,
        topic_id: int | None = None,
        suffix: str | None = None,
        parse_mode: str | None = "HTML",
        disable_notification: bool = False,
        protect_content: bool = False,
        update_existing_pending: bool = False,
    ) -> QueueNotificationResult:
        """Додає текстове повідомлення в чергу."""

        normalized_text = self.normalize_required_text(
            message_text,
            field_name="Текст повідомлення",
        )

        self.validate_message_length(
            normalized_text
        )

        notification, was_created = (
            await self.repositories.notifications
            .get_or_create_from_parts(
                notification_type=notification_type,
                business_date=business_date,
                recipient_user_id=recipient_user_id,
                store_id=store_id,
                bush_id=bush_id,
                chat_id=chat_id,
                topic_id=topic_id,
                suffix=suffix,
                scheduled_for=scheduled_for,
                message_text=normalized_text,
                payload_json={
                    "send_method": "message",
                    "text": normalized_text,
                    "parse_mode": parse_mode,
                    "disable_notification": (
                        disable_notification
                    ),
                    "protect_content": protect_content,
                },
                update_existing_pending=(
                    update_existing_pending
                ),
            )
        )

        return QueueNotificationResult(
            notification=notification,
            was_created=was_created,
        )

    # ==========================================
    # ДОДАВАННЯ ФОТО В ЧЕРГУ
    # ==========================================

    async def queue_photo(
        self,
        *,
        notification_type: NotificationType,
        photo_file_id: str,
        caption: str | None = None,
        business_date: date | None = None,
        scheduled_for: datetime | None = None,
        recipient_user_id: int | None = None,
        store_id: int | None = None,
        bush_id: int | None = None,
        chat_id: int | None = None,
        topic_id: int | None = None,
        suffix: str | None = None,
        parse_mode: str | None = "HTML",
        disable_notification: bool = False,
        protect_content: bool = False,
        has_spoiler: bool = False,
        extra_payload: dict[str, Any] | None = None,
        update_existing_pending: bool = False,
    ) -> QueueNotificationResult:
        """Додає фото в чергу."""

        normalized_file_id = (
            self.normalize_required_text(
                photo_file_id,
                field_name="Telegram photo file_id",
            )
        )

        normalized_caption = (
            self.normalize_optional_text(caption)
        )

        if normalized_caption is not None:
            self.validate_caption_length(
                normalized_caption
            )

        payload = {
            "send_method": "photo",
            "photo_file_id": normalized_file_id,
            "caption": normalized_caption,
            "parse_mode": parse_mode,
            "disable_notification": (
                disable_notification
            ),
            "protect_content": protect_content,
            "has_spoiler": has_spoiler,
        }

        if extra_payload:
            payload.update(extra_payload)

        notification, was_created = (
            await self.repositories.notifications
            .get_or_create_from_parts(
                notification_type=notification_type,
                business_date=business_date,
                recipient_user_id=recipient_user_id,
                store_id=store_id,
                bush_id=bush_id,
                chat_id=chat_id,
                topic_id=topic_id,
                suffix=suffix,
                scheduled_for=scheduled_for,
                message_text=normalized_caption,
                payload_json=payload,
                update_existing_pending=(
                    update_existing_pending
                ),
            )
        )

        return QueueNotificationResult(
            notification=notification,
            was_created=was_created,
        )

    # ==========================================
    # ДОДАВАННЯ ДОКУМЕНТА В ЧЕРГУ
    # ==========================================

    async def queue_document(
        self,
        *,
        notification_type: NotificationType,
        document_file_id: str,
        caption: str | None = None,
        business_date: date | None = None,
        scheduled_for: datetime | None = None,
        recipient_user_id: int | None = None,
        store_id: int | None = None,
        bush_id: int | None = None,
        chat_id: int | None = None,
        topic_id: int | None = None,
        suffix: str | None = None,
        parse_mode: str | None = "HTML",
        disable_notification: bool = False,
        protect_content: bool = False,
        extra_payload: dict[str, Any] | None = None,
        update_existing_pending: bool = False,
    ) -> QueueNotificationResult:
        """Додає документ у чергу."""

        normalized_file_id = (
            self.normalize_required_text(
                document_file_id,
                field_name=(
                    "Telegram document file_id"
                ),
            )
        )

        normalized_caption = (
            self.normalize_optional_text(caption)
        )

        if normalized_caption is not None:
            self.validate_caption_length(
                normalized_caption
            )

        payload = {
            "send_method": "document",
            "document_file_id": (
                normalized_file_id
            ),
            "caption": normalized_caption,
            "parse_mode": parse_mode,
            "disable_notification": (
                disable_notification
            ),
            "protect_content": protect_content,
        }

        if extra_payload:
            payload.update(extra_payload)

        notification, was_created = (
            await self.repositories.notifications
            .get_or_create_from_parts(
                notification_type=notification_type,
                business_date=business_date,
                recipient_user_id=recipient_user_id,
                store_id=store_id,
                bush_id=bush_id,
                chat_id=chat_id,
                topic_id=topic_id,
                suffix=suffix,
                scheduled_for=scheduled_for,
                message_text=normalized_caption,
                payload_json=payload,
                update_existing_pending=(
                    update_existing_pending
                ),
            )
        )

        return QueueNotificationResult(
            notification=notification,
            was_created=was_created,
        )

    # ==========================================
    # ОБРОБКА ВСІЄЇ ЧЕРГИ
    # ==========================================

    async def process_due_notifications(
        self,
        *,
        current_time: datetime | None = None,
        notification_types: set[
            NotificationType
        ]
        | None = None,
        business_date: date | None = None,
        limit: int = 100,
        commit_each: bool = True,
    ) -> NotificationBatchResult:
        """
        Обробляє повідомлення, готові до надсилання.

        Для scheduler рекомендується:

        commit_each=True

        Тоді кожне успішне повідомлення одразу
        фіксується в PostgreSQL.
        """

        started_at = current_time or datetime.now(UTC)

        self.validate_aware_datetime(
            started_at,
            field_name="current_time",
        )

        due_notifications = (
            await self.repositories.notifications
            .get_due_pending(
                current_time=started_at,
                notification_types=(
                    notification_types
                ),
                business_date=business_date,
                limit=limit,
            )
        )

        notification_ids = [
            notification.id
            for notification in due_notifications
        ]

        results: list[
            NotificationDeliveryResult
        ] = []

        for notification_id in notification_ids:
            try:
                result = (
                    await self.process_notification(
                        notification_id=(
                            notification_id
                        ),
                        current_time=(
                            datetime.now(UTC)
                        ),
                        commit=commit_each,
                    )
                )

            except Exception as error:
                if commit_each:
                    await self.session.rollback()

                result = NotificationDeliveryResult(
                    notification_id=(
                        notification_id
                    ),
                    dedupe_key="unknown",
                    status=(
                        DeliveryResultStatus.FAILED
                    ),
                    reason="internal_service_error",
                    error_text=self.error_text(error),
                )

            results.append(result)

        finished_at = datetime.now(UTC)

        return NotificationBatchResult(
            started_at=started_at,
            finished_at=finished_at,
            selected_count=len(notification_ids),
            processed_count=len(results),
            sent_count=sum(
                result.status
                == DeliveryResultStatus.SENT
                for result in results
            ),
            retry_count=sum(
                result.status
                == DeliveryResultStatus
                .RETRY_SCHEDULED
                for result in results
            ),
            failed_count=sum(
                result.status
                == DeliveryResultStatus.FAILED
                for result in results
            ),
            skipped_count=sum(
                result.status
                in {
                    DeliveryResultStatus.SKIPPED,
                    DeliveryResultStatus
                    .ALREADY_DELIVERED,
                    DeliveryResultStatus.NOT_DUE,
                    DeliveryResultStatus
                    .ATTEMPTS_EXHAUSTED,
                }
                for result in results
            ),
            results=tuple(results),
        )

    # ==========================================
    # ОБРОБКА ОДНОГО ПОВІДОМЛЕННЯ
    # ==========================================

    async def process_notification(
        self,
        *,
        notification_id: int,
        current_time: datetime | None = None,
        commit: bool = True,
    ) -> NotificationDeliveryResult:
        """Обробляє одне повідомлення за ID."""

        attempted_at = (
            current_time or datetime.now(UTC)
        )

        self.validate_aware_datetime(
            attempted_at,
            field_name="current_time",
        )

        max_attempts = (
            await self.repositories.settings
            .get_notification_max_attempts()
        )

        reservation = (
            await self.repositories.notifications
            .reserve_by_id(
                notification_id=notification_id,
                attempted_at=attempted_at,
                max_attempts=max_attempts,
            )
        )

        notification = (
            reservation.notification
        )

        if not reservation.should_send:
            result = self.result_from_reservation(
                reservation
            )

            if commit:
                await self.session.commit()

            return result

        try:
            chat_id = await self.resolve_chat_id(
                notification
            )

            if chat_id is None:
                await self.repositories.notifications.mark_skipped(
                    notification,
                    skipped_at=attempted_at,
                    reason=(
                        "Не вдалося визначити "
                        "Telegram chat_id отримувача."
                    ),
                )

                if commit:
                    await self.session.commit()

                return NotificationDeliveryResult(
                    notification_id=notification.id,
                    dedupe_key=notification.dedupe_key,
                    status=(
                        DeliveryResultStatus.SKIPPED
                    ),
                    reason="chat_id_missing",
                )

            message = await self.dispatch(
                notification=notification,
                chat_id=chat_id,
            )

            sent_at = datetime.now(UTC)

            await self.repositories.notifications.mark_sent(
                notification,
                sent_at=sent_at,
                chat_id=message.chat.id,
                message_id=message.message_id,
                topic_id=(
                    message.message_thread_id
                ),
                message_text=(
                    notification.message_text
                ),
            )

            await self.process_delivery_side_effects(
                notification=notification,
                message=message,
                sent_at=sent_at,
            )

            if commit:
                await self.session.commit()

            return NotificationDeliveryResult(
                notification_id=notification.id,
                dedupe_key=notification.dedupe_key,
                status=DeliveryResultStatus.SENT,
                reason="delivered",
                chat_id=message.chat.id,
                message_id=message.message_id,
            )

        except TelegramRetryAfter as error:
            return await self.handle_retryable_error(
                notification=notification,
                error=error,
                current_time=attempted_at,
                max_attempts=max_attempts,
                retry_after_seconds=int(
                    error.retry_after
                ),
                error_code="retry_after",
                commit=commit,
            )

        except TelegramMigrateToChat as error:
            return await self.handle_chat_migration(
                notification=notification,
                error=error,
                current_time=attempted_at,
                max_attempts=max_attempts,
                commit=commit,
            )

        except TelegramNetworkError as error:
            return await self.handle_retryable_error(
                notification=notification,
                error=error,
                current_time=attempted_at,
                max_attempts=max_attempts,
                error_code="network_error",
                commit=commit,
            )

        except TelegramServerError as error:
            return await self.handle_retryable_error(
                notification=notification,
                error=error,
                current_time=attempted_at,
                max_attempts=max_attempts,
                error_code="telegram_server_error",
                commit=commit,
            )

        except TelegramForbiddenError as error:
            return await self.handle_permanent_error(
                notification=notification,
                error=error,
                failed_at=attempted_at,
                error_code="forbidden",
                commit=commit,
            )

        except TelegramBadRequest as error:
            return await self.handle_permanent_error(
                notification=notification,
                error=error,
                failed_at=attempted_at,
                error_code="bad_request",
                commit=commit,
            )

        except TelegramAPIError as error:
            return await self.handle_retryable_error(
                notification=notification,
                error=error,
                current_time=attempted_at,
                max_attempts=max_attempts,
                error_code="telegram_api_error",
                commit=commit,
            )

        except ValueError as error:
            return await self.handle_permanent_error(
                notification=notification,
                error=error,
                failed_at=attempted_at,
                error_code="invalid_payload",
                commit=commit,
            )

        except Exception as error:
            return await self.handle_permanent_error(
                notification=notification,
                error=error,
                failed_at=attempted_at,
                error_code="unknown_error",
                commit=commit,
            )

    # ==========================================
    # НАДСИЛАННЯ ЗА ТИПОМ
    # ==========================================

    async def dispatch(
        self,
        *,
        notification: NotificationLog,
        chat_id: int,
    ) -> Message:
        """Вибирає спосіб надсилання."""

        payload = self.get_payload(notification)

        send_method = str(
            payload.get(
                "send_method",
                "message",
            )
        ).strip().lower()

        if send_method in {
            "message",
            "text",
            "send_message",
        }:
            return await self.send_text(
                notification=notification,
                chat_id=chat_id,
                payload=payload,
            )

        if send_method in {
            "photo",
            "send_photo",
        }:
            return await self.send_photo(
                notification=notification,
                chat_id=chat_id,
                payload=payload,
            )

        if send_method in {
            "document",
            "file",
            "send_document",
        }:
            return await self.send_document(
                notification=notification,
                chat_id=chat_id,
                payload=payload,
            )

        raise ValueError(
            "Непідтримуваний спосіб надсилання: "
            f"{send_method}."
        )

    # ==========================================
    # ТЕКСТОВЕ ПОВІДОМЛЕННЯ
    # ==========================================

    async def send_text(
        self,
        *,
        notification: NotificationLog,
        chat_id: int,
        payload: dict[str, Any],
    ) -> Message:
        """Надсилає звичайне повідомлення."""

        text = (
            payload.get("text")
            or payload.get("message_text")
            or notification.message_text
        )

        normalized_text = (
            self.normalize_required_text(
                str(text or ""),
                field_name="Текст повідомлення",
            )
        )

        self.validate_message_length(
            normalized_text
        )

        return await self.bot.send_message(
            chat_id=chat_id,
            text=normalized_text,
            message_thread_id=(
                self.resolve_topic_id(
                    notification,
                    payload,
                )
            ),
            parse_mode=self.resolve_parse_mode(
                payload.get("parse_mode")
            ),
            disable_notification=bool(
                payload.get(
                    "disable_notification",
                    False,
                )
            ),
            protect_content=bool(
                payload.get(
                    "protect_content",
                    False,
                )
            ),
        )

    # ==========================================
    # ФОТО
    # ==========================================

    async def send_photo(
        self,
        *,
        notification: NotificationLog,
        chat_id: int,
        payload: dict[str, Any],
    ) -> Message:
        """Надсилає Telegram-фото."""

        photo_file_id = (
            payload.get("photo_file_id")
            or payload.get("receipt_file_id")
            or payload.get("file_id")
        )

        normalized_file_id = (
            self.normalize_required_text(
                str(photo_file_id or ""),
                field_name="Telegram photo file_id",
            )
        )

        caption = (
            payload.get("caption")
            or notification.message_text
        )

        normalized_caption = (
            self.normalize_optional_text(
                str(caption)
                if caption is not None
                else None
            )
        )

        if normalized_caption is not None:
            self.validate_caption_length(
                normalized_caption
            )

        return await self.bot.send_photo(
            chat_id=chat_id,
            photo=normalized_file_id,
            caption=normalized_caption,
            message_thread_id=(
                self.resolve_topic_id(
                    notification,
                    payload,
                )
            ),
            parse_mode=self.resolve_parse_mode(
                payload.get("parse_mode")
            ),
            disable_notification=bool(
                payload.get(
                    "disable_notification",
                    False,
                )
            ),
            protect_content=bool(
                payload.get(
                    "protect_content",
                    False,
                )
            ),
            has_spoiler=bool(
                payload.get(
                    "has_spoiler",
                    False,
                )
            ),
        )

    # ==========================================
    # ДОКУМЕНТ
    # ==========================================

    async def send_document(
        self,
        *,
        notification: NotificationLog,
        chat_id: int,
        payload: dict[str, Any],
    ) -> Message:
        """Надсилає Telegram-документ."""

        document_file_id = (
            payload.get("document_file_id")
            or payload.get("file_id")
        )

        normalized_file_id = (
            self.normalize_required_text(
                str(document_file_id or ""),
                field_name=(
                    "Telegram document file_id"
                ),
            )
        )

        caption = (
            payload.get("caption")
            or notification.message_text
        )

        normalized_caption = (
            self.normalize_optional_text(
                str(caption)
                if caption is not None
                else None
            )
        )

        if normalized_caption is not None:
            self.validate_caption_length(
                normalized_caption
            )

        return await self.bot.send_document(
            chat_id=chat_id,
            document=normalized_file_id,
            caption=normalized_caption,
            message_thread_id=(
                self.resolve_topic_id(
                    notification,
                    payload,
                )
            ),
            parse_mode=self.resolve_parse_mode(
                payload.get("parse_mode")
            ),
            disable_notification=bool(
                payload.get(
                    "disable_notification",
                    False,
                )
            ),
            protect_content=bool(
                payload.get(
                    "protect_content",
                    False,
                )
            ),
        )

    # ==========================================
    # ВИЗНАЧЕННЯ ОТРИМУВАЧА
    # ==========================================

    async def resolve_chat_id(
        self,
        notification: NotificationLog,
    ) -> int | None:
        """
        Визначає Telegram chat_id.

        Пріоритет:

        1. chat_id із NotificationLog;
        2. telegram_id користувача.
        """

        if notification.chat_id is not None:
            return int(notification.chat_id)

        if notification.recipient_user_id is None:
            return None

        user = await self.session.get(
            User,
            notification.recipient_user_id,
        )

        if user is None:
            return None

        if (
            user.is_blocked
            or user.status
            in {
                UserStatus.BLOCKED,
                UserStatus.INACTIVE,
            }
        ):
            return None

        if user.telegram_id is None:
            return None

        notification.chat_id = int(
            user.telegram_id
        )

        self.session.add(notification)
        await self.session.flush()

        return int(user.telegram_id)

    # ==========================================
    # RETRYABLE ПОМИЛКИ
    # ==========================================

    async def handle_retryable_error(
        self,
        *,
        notification: NotificationLog,
        error: Exception,
        current_time: datetime,
        max_attempts: int,
        error_code: str,
        commit: bool,
        retry_after_seconds: int | None = None,
    ) -> NotificationDeliveryResult:
        """Обробляє тимчасову помилку."""

        error_text = self.error_text(error)

        await self.repositories.notifications.mark_failed(
            notification,
            failed_at=current_time,
            error_text=error_text,
            telegram_error_code=error_code,
        )

        attempt_count = int(
            notification.attempt_count or 0
        )

        if attempt_count >= max_attempts:
            if commit:
                await self.session.commit()

            return NotificationDeliveryResult(
                notification_id=notification.id,
                dedupe_key=notification.dedupe_key,
                status=(
                    DeliveryResultStatus
                    .ATTEMPTS_EXHAUSTED
                ),
                reason="attempts_exhausted",
                chat_id=notification.chat_id,
                error_text=error_text,
            )

        retry_at = await self.calculate_retry_at(
            current_time=current_time,
            attempt_count=attempt_count,
            retry_after_seconds=(
                retry_after_seconds
            ),
        )

        await self.repositories.notifications.schedule_retry(
            notification,
            retry_at=retry_at,
            reset_error=False,
        )

        if commit:
            await self.session.commit()

        return NotificationDeliveryResult(
            notification_id=notification.id,
            dedupe_key=notification.dedupe_key,
            status=(
                DeliveryResultStatus
                .RETRY_SCHEDULED
            ),
            reason=error_code,
            chat_id=notification.chat_id,
            retry_at=retry_at,
            error_text=error_text,
        )

    async def calculate_retry_at(
        self,
        *,
        current_time: datetime,
        attempt_count: int,
        retry_after_seconds: int | None = None,
    ) -> datetime:
        """Розраховує час наступної спроби."""

        base_delay = (
            await self.repositories.settings
            .get_notification_retry_delay()
        )

        exponential_delay = min(
            base_delay
            * (2 ** max(attempt_count - 1, 0)),
            3600,
        )

        delay_seconds = max(
            exponential_delay,
            int(retry_after_seconds or 0),
        )

        return current_time + timedelta(
            seconds=delay_seconds
        )

    # ==========================================
    # ПОСТІЙНА ПОМИЛКА
    # ==========================================

    async def handle_permanent_error(
        self,
        *,
        notification: NotificationLog,
        error: Exception,
        failed_at: datetime,
        error_code: str,
        commit: bool,
    ) -> NotificationDeliveryResult:
        """Фіксує помилку без повторної спроби."""

        error_text = self.error_text(error)

        await self.repositories.notifications.mark_failed(
            notification,
            failed_at=failed_at,
            error_text=error_text,
            telegram_error_code=error_code,
        )

        if commit:
            await self.session.commit()

        return NotificationDeliveryResult(
            notification_id=notification.id,
            dedupe_key=notification.dedupe_key,
            status=DeliveryResultStatus.FAILED,
            reason=error_code,
            chat_id=notification.chat_id,
            error_text=error_text,
        )

    # ==========================================
    # МІГРАЦІЯ TELEGRAM-ГРУПИ
    # ==========================================

    async def handle_chat_migration(
        self,
        *,
        notification: NotificationLog,
        error: TelegramMigrateToChat,
        current_time: datetime,
        max_attempts: int,
        commit: bool,
    ) -> NotificationDeliveryResult:
        """
        Оновлює chat_id після перетворення
        групи на supergroup.
        """

        new_chat_id = int(
            error.migrate_to_chat_id
        )

        old_chat_id = notification.chat_id

        payload = self.get_payload(
            notification
        )

        payload["migrated_from_chat_id"] = (
            old_chat_id
        )

        notification.chat_id = new_chat_id
        notification.payload_json = payload

        await self.repositories.notifications.mark_failed(
            notification,
            failed_at=current_time,
            error_text=self.error_text(error),
            telegram_error_code="chat_migrated",
        )

        attempt_count = int(
            notification.attempt_count or 0
        )

        if attempt_count >= max_attempts:
            if commit:
                await self.session.commit()

            return NotificationDeliveryResult(
                notification_id=notification.id,
                dedupe_key=notification.dedupe_key,
                status=(
                    DeliveryResultStatus
                    .ATTEMPTS_EXHAUSTED
                ),
                reason="chat_migrated_attempts_exhausted",
                chat_id=new_chat_id,
                error_text=self.error_text(error),
            )

        retry_at = current_time + timedelta(
            seconds=1
        )

        await self.repositories.notifications.schedule_retry(
            notification,
            retry_at=retry_at,
            reset_error=False,
        )

        if commit:
            await self.session.commit()

        return NotificationDeliveryResult(
            notification_id=notification.id,
            dedupe_key=notification.dedupe_key,
            status=(
                DeliveryResultStatus
                .RETRY_SCHEDULED
            ),
            reason="chat_migrated",
            chat_id=new_chat_id,
            retry_at=retry_at,
            error_text=self.error_text(error),
        )

    # ==========================================
    # ДОДАТКОВІ ДІЇ ПІСЛЯ ДОСТАВКИ
    # ==========================================

    async def process_delivery_side_effects(
        self,
        *,
        notification: NotificationLog,
        message: Message,
        sent_at: datetime,
    ) -> None:
        """
        Фіксує доставку пов’язаних об’єктів.

        Наприклад, після надсилання фото чека
        записує message_id у ClosingReport.
        """

        payload = self.get_payload(
            notification
        )

        report_id = payload.get("report_id")
        receipt_file_id = payload.get(
            "receipt_file_id"
        )

        send_method = str(
            payload.get(
                "send_method",
                "",
            )
        ).lower()

        is_closing_group_report = (
            report_id is not None
            and receipt_file_id is not None
            and send_method == "photo"
        )

        if not is_closing_group_report:
            return

        try:
            report = (
                await self.repositories.closings
                .get_report_for_update_or_raise(
                    int(report_id)
                )
            )

            await self.repositories.closings.mark_sent_to_group(
                report,
                chat_id=message.chat.id,
                message_id=message.message_id,
                topic_id=(
                    message.message_thread_id
                ),
                sent_at=sent_at,
            )

        except (
            TypeError,
            ValueError,
            RuntimeError,
        ):
            # Telegram-повідомлення вже доставлене.
            # Помилка додаткової прив’язки не повинна
            # запускати повторне надсилання.
            return

    # ==========================================
    # РЕЗУЛЬТАТ РЕЗЕРВУВАННЯ
    # ==========================================

    @staticmethod
    def result_from_reservation(
        reservation: NotificationReservation,
    ) -> NotificationDeliveryResult:
        """Формує результат без Telegram-запиту."""

        notification = (
            reservation.notification
        )

        mapping = {
            "already_delivered": (
                DeliveryResultStatus
                .ALREADY_DELIVERED
            ),
            "not_due": (
                DeliveryResultStatus.NOT_DUE
            ),
            "attempts_exhausted": (
                DeliveryResultStatus
                .ATTEMPTS_EXHAUSTED
            ),
            "skipped": (
                DeliveryResultStatus.SKIPPED
            ),
        }

        return NotificationDeliveryResult(
            notification_id=notification.id,
            dedupe_key=notification.dedupe_key,
            status=mapping.get(
                reservation.reason,
                DeliveryResultStatus.SKIPPED,
            ),
            reason=reservation.reason,
            chat_id=notification.chat_id,
            message_id=notification.message_id,
        )

    # ==========================================
    # ПОВТОРНІ СПРОБИ
    # ==========================================

    async def return_failed_to_queue(
        self,
        *,
        retry_at: datetime | None = None,
        limit: int = 100,
        commit: bool = True,
    ) -> int:
        """Повертає невдалі повідомлення у чергу."""

        target_time = (
            retry_at or datetime.now(UTC)
        )

        self.validate_aware_datetime(
            target_time,
            field_name="retry_at",
        )

        max_attempts = (
            await self.repositories.settings
            .get_notification_max_attempts()
        )

        notifications = (
            await self.repositories.notifications
            .retry_failed_batch(
                retry_at=target_time,
                max_attempts=max_attempts,
                limit=limit,
            )
        )

        if commit:
            await self.session.commit()

        return len(notifications)

    async def retry_notification(
        self,
        *,
        notification_id: int,
        retry_at: datetime | None = None,
        commit: bool = True,
    ) -> NotificationLog:
        """Повертає конкретне повідомлення у чергу."""

        notification = (
            await self.repositories.notifications
            .schedule_retry_by_id(
                notification_id=(
                    notification_id
                ),
                retry_at=retry_at,
            )
        )

        if commit:
            await self.session.commit()

        return notification

    # ==========================================
    # СТАТИСТИКА
    # ==========================================

    async def get_statistics(
        self,
        *,
        business_date: date | None = None,
    ) -> dict[str, int | float]:
        """Повертає статистику доставки."""

        return (
            await self.repositories.notifications
            .get_statistics(
                business_date=business_date
            )
        )

    async def get_failed_notifications(
        self,
        *,
        business_date: date | None = None,
        limit: int = 100,
    ) -> list[NotificationLog]:
        """Повертає невдалі повідомлення."""

        max_attempts = (
            await self.repositories.settings
            .get_notification_max_attempts()
        )

        return (
            await self.repositories.notifications
            .get_failed(
                max_attempts=max_attempts,
                business_date=business_date,
                limit=limit,
            )
        )

    # ==========================================
    # PAYLOAD
    # ==========================================

    @staticmethod
    def get_payload(
        notification: NotificationLog,
    ) -> dict[str, Any]:
        """Повертає копію payload_json."""

        payload = notification.payload_json

        if payload is None:
            return {}

        if not isinstance(payload, dict):
            raise ValueError(
                "payload_json повідомлення "
                "повинен бути словником."
            )

        return dict(payload)

    @staticmethod
    def resolve_topic_id(
        notification: NotificationLog,
        payload: dict[str, Any],
    ) -> int | None:
        """Визначає Telegram message_thread_id."""

        raw_topic_id = (
            payload.get("topic_id")
            or notification.topic_id
        )

        if raw_topic_id is None:
            return None

        try:
            topic_id = int(raw_topic_id)

        except (TypeError, ValueError) as error:
            raise ValueError(
                "Некоректний Telegram topic_id."
            ) from error

        if topic_id <= 0:
            raise ValueError(
                "Telegram topic_id повинен бути "
                "більшим за нуль."
            )

        return topic_id

    @staticmethod
    def resolve_parse_mode(
        value: Any,
    ) -> ParseMode | None:
        """Перетворює текст у ParseMode."""

        if value is None:
            return None

        normalized_value = str(
            value
        ).strip().upper()

        if not normalized_value:
            return None

        mapping = {
            "HTML": ParseMode.HTML,
            "MARKDOWN": ParseMode.MARKDOWN,
            "MARKDOWNV2": ParseMode.MARKDOWN_V2,
            "MARKDOWN_V2": ParseMode.MARKDOWN_V2,
        }

        if normalized_value not in mapping:
            raise ValueError(
                "Невідомий parse_mode: "
                f"{normalized_value}."
            )

        return mapping[normalized_value]

    # ==========================================
    # ВАЛІДАЦІЯ TELEGRAM-ТЕКСТУ
    # ==========================================

    @classmethod
    def validate_message_length(
        cls,
        text: str,
    ) -> None:
        """Перевіряє ліміт Telegram-повідомлення."""

        if len(text) > cls.TELEGRAM_MESSAGE_LIMIT:
            raise ValueError(
                "Текст повідомлення перевищує "
                f"{cls.TELEGRAM_MESSAGE_LIMIT} символів."
            )

    @classmethod
    def validate_caption_length(
        cls,
        caption: str,
    ) -> None:
        """Перевіряє ліміт підпису до файлу."""

        if len(caption) > cls.TELEGRAM_CAPTION_LIMIT:
            raise ValueError(
                "Підпис до фото або документа "
                f"перевищує {cls.TELEGRAM_CAPTION_LIMIT} "
                "символів."
            )

    # ==========================================
    # ДОПОМІЖНІ МЕТОДИ
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
    def error_text(
        error: Exception,
    ) -> str:
        """Формує безпечний текст помилки."""

        text = str(error).strip()

        if not text:
            text = error.__class__.__name__

        return text[:2000]