from __future__ import annotations

from collections.abc import Iterable
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

from app.database.models.daily_summary import (
    DailySummaryMessage,
)
from app.database.models.enums import SummaryType
from app.repositories import (
    Repositories,
    SummaryScope,
    SummaryUpdateDecision,
)


class SummarySyncStatus(StrEnum):
    """
    Результат синхронізації живого підсумку.
    """

    SENT = "sent"
    EDITED = "edited"
    RECREATED = "recreated"

    UNCHANGED = "unchanged"
    SKIPPED = "skipped"

    RETRY_REQUIRED = "retry_required"
    FAILED = "failed"


@dataclass(slots=True, frozen=True)
class PreparedSummaryUpdate:
    """
    Повністю підготовлене оновлення підсумку.

    На відміну від SummaryUpdateDecision,
    цей об’єкт також містить новий текст
    і статистичний snapshot.
    """

    decision: SummaryUpdateDecision

    message_text: str
    snapshot_json: dict[str, Any] | None

    parse_mode: ParseMode | None = ParseMode.HTML
    disable_notification: bool = True
    protect_content: bool = False

    @property
    def summary(self) -> DailySummaryMessage:
        return self.decision.summary


@dataclass(slots=True, frozen=True)
class SummarySyncResult:
    """
    Результат надсилання або редагування
    одного живого підсумку.
    """

    summary_id: int
    summary_type: SummaryType
    business_date: date

    status: SummarySyncStatus
    reason: str

    chat_id: int
    topic_id: int | None
    message_id: int | None

    content_changed: bool

    retry_at: datetime | None = None
    error_text: str | None = None

    @property
    def was_synchronized(self) -> bool:
        return self.status in {
            SummarySyncStatus.SENT,
            SummarySyncStatus.EDITED,
            SummarySyncStatus.RECREATED,
            SummarySyncStatus.UNCHANGED,
        }


@dataclass(slots=True, frozen=True)
class SummaryBatchResult:
    """
    Результат обробки декількох підсумків.
    """

    started_at: datetime
    finished_at: datetime

    total_count: int

    sent_count: int
    edited_count: int
    recreated_count: int
    unchanged_count: int

    retry_count: int
    failed_count: int
    skipped_count: int

    results: tuple[SummarySyncResult, ...]


class SummaryService:
    """
    Сервіс живих Telegram-підсумків.

    Відповідає за:

    - створення першого повідомлення;
    - редагування наявного повідомлення;
    - відновлення видаленого повідомлення;
    - роботу з Telegram topics;
    - збереження message_id;
    - перевірку зміни тексту;
    - обробку Telegram-помилок;
    - повторну синхронізацію після перезапуску;
    - ранкові та вечірні підсумки.

    У кожному чаті або topic існує лише один
    живий підсумок відповідного типу на день.
    """

    TELEGRAM_MESSAGE_LIMIT = 4096

    def __init__(
        self,
        repositories: Repositories,
        bot: Bot,
    ) -> None:
        self.repositories = repositories
        self.session = repositories.session
        self.bot = bot

    # ==========================================
    # ПІДГОТОВКА ОНОВЛЕННЯ
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
        parse_mode: ParseMode | None = ParseMode.HTML,
        disable_notification: bool = True,
        protect_content: bool = False,
    ) -> PreparedSummaryUpdate:
        """
        Підготовлює рішення щодо Telegram-повідомлення.

        Можливі рішення:

        - створити нове;
        - відредагувати наявне;
        - нічого не робити.
        """

        normalized_text = self.normalize_required_text(
            message_text,
            field_name="Текст підсумку",
        )

        self.validate_message_length(
            normalized_text
        )

        self.validate_chat_id(chat_id)
        self.validate_topic_id(topic_id)

        decision = (
            await self.repositories.daily_summaries
            .prepare_update(
                summary_type=summary_type,
                business_date=business_date,
                chat_id=chat_id,
                bush_id=bush_id,
                topic_id=topic_id,
                message_text=normalized_text,
                snapshot_json=snapshot_json,
            )
        )

        return PreparedSummaryUpdate(
            decision=decision,
            message_text=normalized_text,
            snapshot_json=snapshot_json,
            parse_mode=parse_mode,
            disable_notification=(
                disable_notification
            ),
            protect_content=protect_content,
        )

    async def prepare_from_scope(
        self,
        scope: SummaryScope,
        *,
        message_text: str,
        snapshot_json: dict[str, Any] | None = None,
        parse_mode: ParseMode | None = ParseMode.HTML,
        disable_notification: bool = True,
        protect_content: bool = False,
    ) -> PreparedSummaryUpdate:
        """Готує оновлення за SummaryScope."""

        return await self.prepare_update(
            summary_type=scope.summary_type,
            business_date=scope.business_date,
            chat_id=scope.chat_id,
            bush_id=scope.bush_id,
            topic_id=scope.topic_id,
            message_text=message_text,
            snapshot_json=snapshot_json,
            parse_mode=parse_mode,
            disable_notification=disable_notification,
            protect_content=protect_content,
        )

    # ==========================================
    # ПОВНИЙ ЦИКЛ СИНХРОНІЗАЦІЇ
    # ==========================================

    async def sync_summary(
        self,
        *,
        summary_type: SummaryType,
        business_date: date,
        chat_id: int,
        message_text: str,
        bush_id: int | None = None,
        topic_id: int | None = None,
        snapshot_json: dict[str, Any] | None = None,
        parse_mode: ParseMode | None = ParseMode.HTML,
        disable_notification: bool = True,
        protect_content: bool = False,
        current_time: datetime | None = None,
        commit: bool = True,
    ) -> SummarySyncResult:
        """
        Готує та одразу синхронізує підсумок.
        """

        prepared = await self.prepare_update(
            summary_type=summary_type,
            business_date=business_date,
            chat_id=chat_id,
            bush_id=bush_id,
            topic_id=topic_id,
            message_text=message_text,
            snapshot_json=snapshot_json,
            parse_mode=parse_mode,
            disable_notification=disable_notification,
            protect_content=protect_content,
        )

        return await self.sync_prepared(
            prepared,
            current_time=current_time,
            commit=commit,
        )

    async def sync_prepared(
        self,
        prepared: PreparedSummaryUpdate,
        *,
        current_time: datetime | None = None,
        commit: bool = True,
    ) -> SummarySyncResult:
        """
        Синхронізує підготовлене оновлення.
        """

        processed_at = (
            current_time or datetime.now(UTC)
        )

        self.validate_aware_datetime(
            processed_at,
            field_name="current_time",
        )

        decision = prepared.decision
        summary = decision.summary

        try:
            if decision.should_send:
                result = await self.send_new_message(
                    summary=summary,
                    message_text=(
                        prepared.message_text
                    ),
                    snapshot_json=(
                        prepared.snapshot_json
                    ),
                    parse_mode=prepared.parse_mode,
                    disable_notification=(
                        prepared.disable_notification
                    ),
                    protect_content=(
                        prepared.protect_content
                    ),
                    sent_at=processed_at,
                    recreated=False,
                )

            elif decision.should_edit:
                result = await self.edit_existing_message(
                    summary=summary,
                    message_text=(
                        prepared.message_text
                    ),
                    snapshot_json=(
                        prepared.snapshot_json
                    ),
                    parse_mode=prepared.parse_mode,
                    disable_notification=(
                        prepared.disable_notification
                    ),
                    protect_content=(
                        prepared.protect_content
                    ),
                    edited_at=processed_at,
                )

            else:
                await (
                    self.repositories.daily_summaries
                    .clear_sync_error(summary)
                )

                result = self.build_result(
                    summary=summary,
                    status=SummarySyncStatus.UNCHANGED,
                    reason="content_unchanged",
                    content_changed=False,
                )

            if commit:
                await self.session.commit()

            return result

        except TelegramRetryAfter as error:
            result = await self.handle_retryable_error(
                summary=summary,
                error=error,
                failed_at=processed_at,
                retry_after_seconds=int(
                    error.retry_after
                ),
                reason="telegram_retry_after",
            )

        except TelegramMigrateToChat as error:
            result = await self.handle_chat_migration(
                summary=summary,
                prepared=prepared,
                error=error,
                processed_at=processed_at,
            )

        except (
            TelegramNetworkError,
            TelegramServerError,
        ) as error:
            result = await self.handle_retryable_error(
                summary=summary,
                error=error,
                failed_at=processed_at,
                reason="telegram_temporary_error",
            )

        except TelegramForbiddenError as error:
            result = await self.handle_permanent_error(
                summary=summary,
                error=error,
                failed_at=processed_at,
                reason="telegram_forbidden",
            )

        except TelegramBadRequest as error:
            result = await self.handle_bad_request(
                summary=summary,
                prepared=prepared,
                error=error,
                processed_at=processed_at,
            )

        except TelegramAPIError as error:
            result = await self.handle_retryable_error(
                summary=summary,
                error=error,
                failed_at=processed_at,
                reason="telegram_api_error",
            )

        except Exception as error:
            result = await self.handle_permanent_error(
                summary=summary,
                error=error,
                failed_at=processed_at,
                reason="internal_summary_error",
            )

        if commit:
            await self.session.commit()

        return result

    # ==========================================
    # СИНХРОНІЗАЦІЯ ГОТОВОГО DECISION
    # ==========================================

    async def sync_decision(
        self,
        decision: SummaryUpdateDecision,
        *,
        message_text: str | None = None,
        snapshot_json: dict[str, Any] | None = None,
        parse_mode: ParseMode | None = ParseMode.HTML,
        disable_notification: bool = True,
        protect_content: bool = False,
        current_time: datetime | None = None,
        commit: bool = True,
    ) -> SummarySyncResult:
        """
        Синхронізує SummaryUpdateDecision.

        Якщо текст не переданий явно, сервіс
        спробує взяти його з pending-полів моделі.
        """

        resolved_text = (
            message_text
            or self.get_pending_message_text(
                decision.summary
            )
        )

        if resolved_text is None:
            raise ValueError(
                "Для синхронізації підсумку "
                "потрібно передати message_text."
            )

        resolved_snapshot = (
            snapshot_json
            if snapshot_json is not None
            else self.get_pending_snapshot(
                decision.summary
            )
        )

        prepared = PreparedSummaryUpdate(
            decision=decision,
            message_text=(
                self.normalize_required_text(
                    resolved_text,
                    field_name="Текст підсумку",
                )
            ),
            snapshot_json=resolved_snapshot,
            parse_mode=parse_mode,
            disable_notification=(
                disable_notification
            ),
            protect_content=protect_content,
        )

        return await self.sync_prepared(
            prepared,
            current_time=current_time,
            commit=commit,
        )

    # ==========================================
    # ПЕРШЕ НАДСИЛАННЯ
    # ==========================================

    async def send_new_message(
        self,
        *,
        summary: DailySummaryMessage,
        message_text: str,
        snapshot_json: dict[str, Any] | None,
        parse_mode: ParseMode | None,
        disable_notification: bool,
        protect_content: bool,
        sent_at: datetime,
        recreated: bool,
    ) -> SummarySyncResult:
        """Надсилає новий живий підсумок."""

        self.validate_chat_id(
            summary.chat_id
        )

        message = await self.bot.send_message(
            chat_id=summary.chat_id,
            text=message_text,
            message_thread_id=summary.topic_id,
            parse_mode=parse_mode,
            disable_notification=(
                disable_notification
            ),
            protect_content=protect_content,
        )

        await self.repositories.daily_summaries.mark_sent(
            summary,
            message_id=message.message_id,
            message_text=message_text,
            sent_at=sent_at,
            snapshot_json=snapshot_json,
            chat_id=message.chat.id,
            topic_id=(
                message.message_thread_id
                or summary.topic_id
            ),
        )

        return self.build_result(
            summary=summary,
            status=(
                SummarySyncStatus.RECREATED
                if recreated
                else SummarySyncStatus.SENT
            ),
            reason=(
                "telegram_message_recreated"
                if recreated
                else "telegram_message_created"
            ),
            content_changed=True,
            message_id=message.message_id,
        )

    # ==========================================
    # РЕДАГУВАННЯ
    # ==========================================

    async def edit_existing_message(
        self,
        *,
        summary: DailySummaryMessage,
        message_text: str,
        snapshot_json: dict[str, Any] | None,
        parse_mode: ParseMode | None,
        disable_notification: bool,
        protect_content: bool,
        edited_at: datetime,
    ) -> SummarySyncResult:
        """Редагує наявний живий підсумок."""

        if summary.message_id is None:
            return await self.send_new_message(
                summary=summary,
                message_text=message_text,
                snapshot_json=snapshot_json,
                parse_mode=parse_mode,
                disable_notification=(
                    disable_notification
                ),
                protect_content=protect_content,
                sent_at=edited_at,
                recreated=True,
            )

        await self.bot.edit_message_text(
            chat_id=summary.chat_id,
            message_id=summary.message_id,
            text=message_text,
            parse_mode=parse_mode,
        )

        await self.repositories.daily_summaries.mark_edited(
            summary,
            message_text=message_text,
            edited_at=edited_at,
            snapshot_json=snapshot_json,
        )

        return self.build_result(
            summary=summary,
            status=SummarySyncStatus.EDITED,
            reason="telegram_message_edited",
            content_changed=True,
        )

    # ==========================================
    # TELEGRAM BAD REQUEST
    # ==========================================

    async def handle_bad_request(
        self,
        *,
        summary: DailySummaryMessage,
        prepared: PreparedSummaryUpdate,
        error: TelegramBadRequest,
        processed_at: datetime,
    ) -> SummarySyncResult:
        """Обробляє помилки редагування Telegram."""

        error_text = self.error_text(error)
        normalized_error = error_text.lower()

        if self.is_message_not_modified_error(
            normalized_error
        ):
            await self.repositories.daily_summaries.mark_edited(
                summary,
                message_text=(
                    prepared.message_text
                ),
                edited_at=processed_at,
                snapshot_json=(
                    prepared.snapshot_json
                ),
            )

            return self.build_result(
                summary=summary,
                status=SummarySyncStatus.UNCHANGED,
                reason="telegram_message_not_modified",
                content_changed=False,
            )

        if (
            prepared.decision.should_edit
            and self.is_missing_message_error(
                normalized_error
            )
        ):
            await (
                self.repositories.daily_summaries
                .detach_telegram_message(
                    summary,
                    detached_at=processed_at,
                    reason=error_text,
                )
            )

            return await self.send_new_message(
                summary=summary,
                message_text=(
                    prepared.message_text
                ),
                snapshot_json=(
                    prepared.snapshot_json
                ),
                parse_mode=prepared.parse_mode,
                disable_notification=(
                    prepared.disable_notification
                ),
                protect_content=(
                    prepared.protect_content
                ),
                sent_at=processed_at,
                recreated=True,
            )

        return await self.handle_permanent_error(
            summary=summary,
            error=error,
            failed_at=processed_at,
            reason="telegram_bad_request",
        )

    # ==========================================
    # CHAT MIGRATION
    # ==========================================

    async def handle_chat_migration(
        self,
        *,
        summary: DailySummaryMessage,
        prepared: PreparedSummaryUpdate,
        error: TelegramMigrateToChat,
        processed_at: datetime,
    ) -> SummarySyncResult:
        """
        Обробляє перетворення звичайної групи
        на Telegram supergroup.
        """

        new_chat_id = int(
            error.migrate_to_chat_id
        )

        await (
            self.repositories.daily_summaries
            .change_destination(
                summary,
                chat_id=new_chat_id,
                topic_id=None,
                reset_message_id=True,
            )
        )

        return await self.send_new_message(
            summary=summary,
            message_text=prepared.message_text,
            snapshot_json=prepared.snapshot_json,
            parse_mode=prepared.parse_mode,
            disable_notification=(
                prepared.disable_notification
            ),
            protect_content=(
                prepared.protect_content
            ),
            sent_at=processed_at,
            recreated=True,
        )

    # ==========================================
    # ТИМЧАСОВА ПОМИЛКА
    # ==========================================

    async def handle_retryable_error(
        self,
        *,
        summary: DailySummaryMessage,
        error: Exception,
        failed_at: datetime,
        reason: str,
        retry_after_seconds: int | None = None,
    ) -> SummarySyncResult:
        """Фіксує тимчасову Telegram-помилку."""

        error_text = self.error_text(error)

        await (
            self.repositories.daily_summaries
            .mark_sync_failed(
                summary,
                failed_at=failed_at,
                error_text=error_text,
            )
        )

        retry_delay = (
            retry_after_seconds
            if retry_after_seconds is not None
            else await self.repositories.settings
            .get_notification_retry_delay()
        )

        retry_at = failed_at + timedelta(
            seconds=max(int(retry_delay), 1)
        )

        return self.build_result(
            summary=summary,
            status=(
                SummarySyncStatus.RETRY_REQUIRED
            ),
            reason=reason,
            content_changed=True,
            retry_at=retry_at,
            error_text=error_text,
        )

    # ==========================================
    # ПОСТІЙНА ПОМИЛКА
    # ==========================================

    async def handle_permanent_error(
        self,
        *,
        summary: DailySummaryMessage,
        error: Exception,
        failed_at: datetime,
        reason: str,
    ) -> SummarySyncResult:
        """Фіксує помилку без автоматичної паузи."""

        error_text = self.error_text(error)

        await (
            self.repositories.daily_summaries
            .mark_sync_failed(
                summary,
                failed_at=failed_at,
                error_text=error_text,
            )
        )

        return self.build_result(
            summary=summary,
            status=SummarySyncStatus.FAILED,
            reason=reason,
            content_changed=True,
            error_text=error_text,
        )

    # ==========================================
    # МАСОВА СИНХРОНІЗАЦІЯ
    # ==========================================

    async def sync_many(
        self,
        updates: Iterable[PreparedSummaryUpdate],
        *,
        current_time: datetime | None = None,
        commit_each: bool = True,
    ) -> SummaryBatchResult:
        """Синхронізує декілька живих підсумків."""

        started_at = (
            current_time or datetime.now(UTC)
        )

        self.validate_aware_datetime(
            started_at,
            field_name="current_time",
        )

        prepared_updates = list(updates)

        results: list[SummarySyncResult] = []

        for prepared in prepared_updates:
            try:
                result = await self.sync_prepared(
                    prepared,
                    current_time=datetime.now(UTC),
                    commit=commit_each,
                )

            except Exception as error:
                if commit_each:
                    await self.session.rollback()

                summary = prepared.summary

                result = self.build_result(
                    summary=summary,
                    status=SummarySyncStatus.FAILED,
                    reason="batch_internal_error",
                    content_changed=True,
                    error_text=self.error_text(error),
                )

            results.append(result)

        if not commit_each:
            await self.session.commit()

        finished_at = datetime.now(UTC)

        return SummaryBatchResult(
            started_at=started_at,
            finished_at=finished_at,
            total_count=len(results),
            sent_count=sum(
                result.status
                == SummarySyncStatus.SENT
                for result in results
            ),
            edited_count=sum(
                result.status
                == SummarySyncStatus.EDITED
                for result in results
            ),
            recreated_count=sum(
                result.status
                == SummarySyncStatus.RECREATED
                for result in results
            ),
            unchanged_count=sum(
                result.status
                == SummarySyncStatus.UNCHANGED
                for result in results
            ),
            retry_count=sum(
                result.status
                == SummarySyncStatus.RETRY_REQUIRED
                for result in results
            ),
            failed_count=sum(
                result.status
                == SummarySyncStatus.FAILED
                for result in results
            ),
            skipped_count=sum(
                result.status
                == SummarySyncStatus.SKIPPED
                for result in results
            ),
            results=tuple(results),
        )

    async def sync_decisions(
        self,
        decisions: Iterable[
            SummaryUpdateDecision
        ],
        *,
        message_texts: dict[int, str] | None = None,
        snapshots: dict[
            int,
            dict[str, Any] | None,
        ]
        | None = None,
        current_time: datetime | None = None,
        commit_each: bool = True,
    ) -> SummaryBatchResult:
        """
        Синхронізує набір SummaryUpdateDecision.

        message_texts:
            ключ — summary.id;
            значення — новий текст.
        """

        prepared_updates: list[
            PreparedSummaryUpdate
        ] = []

        texts = message_texts or {}
        snapshot_map = snapshots or {}

        for decision in decisions:
            summary_id = decision.summary.id

            message_text = (
                texts.get(summary_id)
                or self.get_pending_message_text(
                    decision.summary
                )
            )

            if message_text is None:
                continue

            prepared_updates.append(
                PreparedSummaryUpdate(
                    decision=decision,
                    message_text=message_text,
                    snapshot_json=(
                        snapshot_map.get(
                            summary_id,
                            self.get_pending_snapshot(
                                decision.summary
                            ),
                        )
                    ),
                )
            )

        return await self.sync_many(
            prepared_updates,
            current_time=current_time,
            commit_each=commit_each,
        )

    # ==========================================
    # ВІДНОВЛЕННЯ ПІСЛЯ ПЕРЕЗАПУСКУ
    # ==========================================

    async def process_pending_for_date(
        self,
        *,
        business_date: date,
        summary_types: set[SummaryType] | None = None,
        limit: int = 500,
        commit_each: bool = True,
    ) -> SummaryBatchResult:
        """
        Відновлює незавершені оновлення після
        перезапуску Railway.

        Працює, якщо модель містить поля:

        - pending_message_text;
        - next_message_text;
        - pending_snapshot_json;
        - next_snapshot_json.
        """

        summaries = (
            await self.repositories.daily_summaries
            .get_for_date(
                business_date=business_date,
                summary_types=summary_types,
            )
        )[:limit]

        updates: list[
            PreparedSummaryUpdate
        ] = []

        for summary in summaries:
            pending_text = (
                self.get_pending_message_text(
                    summary
                )
            )

            if pending_text is None:
                continue

            decision = (
                await self.repositories
                .daily_summaries
                .prepare_update(
                    summary_type=(
                        summary.summary_type
                    ),
                    business_date=(
                        summary.business_date
                    ),
                    chat_id=summary.chat_id,
                    bush_id=summary.bush_id,
                    topic_id=summary.topic_id,
                    message_text=pending_text,
                    snapshot_json=(
                        self.get_pending_snapshot(
                            summary
                        )
                    ),
                )
            )

            updates.append(
                PreparedSummaryUpdate(
                    decision=decision,
                    message_text=pending_text,
                    snapshot_json=(
                        self.get_pending_snapshot(
                            summary
                        )
                    ),
                )
            )

        return await self.sync_many(
            updates,
            commit_each=commit_each,
        )

    # ==========================================
    # РУЧНЕ ВІДНОВЛЕННЯ ПОВІДОМЛЕННЯ
    # ==========================================

    async def recreate_summary(
        self,
        *,
        summary_id: int,
        message_text: str,
        snapshot_json: dict[str, Any] | None = None,
        current_time: datetime | None = None,
        commit: bool = True,
    ) -> SummarySyncResult:
        """
        Примусово створює нове повідомлення.

        Старий message_id буде від’єднаний.
        """

        processed_at = (
            current_time or datetime.now(UTC)
        )

        self.validate_aware_datetime(
            processed_at,
            field_name="current_time",
        )

        summary = (
            await self.repositories.daily_summaries
            .get_by_id_or_raise(
                summary_id,
                for_update=True,
            )
        )

        await (
            self.repositories.daily_summaries
            .detach_telegram_message(
                summary,
                detached_at=processed_at,
                reason=(
                    "Примусове відновлення "
                    "живого підсумку"
                ),
            )
        )

        result = await self.send_new_message(
            summary=summary,
            message_text=(
                self.normalize_required_text(
                    message_text,
                    field_name="Текст підсумку",
                )
            ),
            snapshot_json=snapshot_json,
            parse_mode=ParseMode.HTML,
            disable_notification=True,
            protect_content=False,
            sent_at=processed_at,
            recreated=True,
        )

        if commit:
            await self.session.commit()

        return result

    async def detach_summary_message(
        self,
        *,
        summary_id: int,
        reason: str,
        detached_at: datetime | None = None,
        commit: bool = True,
    ) -> DailySummaryMessage:
        """Від’єднує Telegram message_id."""

        processed_at = (
            detached_at or datetime.now(UTC)
        )

        self.validate_aware_datetime(
            processed_at,
            field_name="detached_at",
        )

        summary = (
            await self.repositories.daily_summaries
            .get_by_id_or_raise(
                summary_id,
                for_update=True,
            )
        )

        await (
            self.repositories.daily_summaries
            .detach_telegram_message(
                summary,
                detached_at=processed_at,
                reason=reason,
            )
        )

        if commit:
            await self.session.commit()

        return summary

    # ==========================================
    # ЗМІНА TELEGRAM-ГРУПИ АБО TOPIC
    # ==========================================

    async def change_destination(
        self,
        *,
        summary_id: int,
        chat_id: int,
        topic_id: int | None,
        reset_message_id: bool = True,
        commit: bool = True,
    ) -> DailySummaryMessage:
        """Переносить підсумок у новий чат або topic."""

        self.validate_chat_id(chat_id)
        self.validate_topic_id(topic_id)

        summary = (
            await self.repositories.daily_summaries
            .get_by_id_or_raise(
                summary_id,
                for_update=True,
            )
        )

        summary = (
            await self.repositories.daily_summaries
            .change_destination(
                summary,
                chat_id=chat_id,
                topic_id=topic_id,
                reset_message_id=reset_message_id,
            )
        )

        if commit:
            await self.session.commit()

        return summary

    # ==========================================
    # СТАТИСТИКА
    # ==========================================

    async def get_statistics(
        self,
        *,
        business_date: date,
    ) -> dict[str, int]:
        """Повертає статистику живих підсумків."""

        return (
            await self.repositories.daily_summaries
            .get_statistics(
                business_date=business_date
            )
        )

    # ==========================================
    # PENDING-ТЕКСТ
    # ==========================================

    @staticmethod
    def get_pending_message_text(
        summary: DailySummaryMessage,
    ) -> str | None:
        """Повертає текст, який очікує синхронізації."""

        for field_name in (
            "pending_message_text",
            "next_message_text",
        ):
            value = getattr(
                summary,
                field_name,
                None,
            )

            if (
                isinstance(value, str)
                and value.strip()
            ):
                return value.strip()

        if summary.message_id is None:
            for field_name in (
                "message_text",
                "last_message_text",
                "last_text",
                "rendered_text",
            ):
                value = getattr(
                    summary,
                    field_name,
                    None,
                )

                if (
                    isinstance(value, str)
                    and value.strip()
                ):
                    return value.strip()

        return None

    @staticmethod
    def get_pending_snapshot(
        summary: DailySummaryMessage,
    ) -> dict[str, Any] | None:
        """Повертає статистику, що очікує синхронізації."""

        for field_name in (
            "pending_snapshot_json",
            "next_snapshot_json",
        ):
            value = getattr(
                summary,
                field_name,
                None,
            )

            if isinstance(value, dict):
                return dict(value)

        if summary.message_id is None:
            for field_name in (
                "snapshot_json",
                "statistics_json",
                "stats_json",
                "payload_json",
            ):
                value = getattr(
                    summary,
                    field_name,
                    None,
                )

                if isinstance(value, dict):
                    return dict(value)

        return None

    # ==========================================
    # РЕЗУЛЬТАТ
    # ==========================================

    @staticmethod
    def build_result(
        *,
        summary: DailySummaryMessage,
        status: SummarySyncStatus,
        reason: str,
        content_changed: bool,
        message_id: int | None = None,
        retry_at: datetime | None = None,
        error_text: str | None = None,
    ) -> SummarySyncResult:
        """Формує результат синхронізації."""

        return SummarySyncResult(
            summary_id=summary.id,
            summary_type=summary.summary_type,
            business_date=summary.business_date,
            status=status,
            reason=reason,
            chat_id=summary.chat_id,
            topic_id=summary.topic_id,
            message_id=(
                message_id
                if message_id is not None
                else summary.message_id
            ),
            content_changed=content_changed,
            retry_at=retry_at,
            error_text=error_text,
        )

    # ==========================================
    # ВИЗНАЧЕННЯ TELEGRAM-ПОМИЛОК
    # ==========================================

    @staticmethod
    def is_message_not_modified_error(
        error_text: str,
    ) -> bool:
        """Чи повідомлення вже має такий текст."""

        return (
            "message is not modified"
            in error_text
        )

    @staticmethod
    def is_missing_message_error(
        error_text: str,
    ) -> bool:
        """Чи старе повідомлення неможливо редагувати."""

        markers = (
            "message to edit not found",
            "message can't be edited",
            "message can not be edited",
            "message_id_invalid",
            "message identifier is not specified",
            "message was deleted",
        )

        return any(
            marker in error_text
            for marker in markers
        )

    # ==========================================
    # ВАЛІДАЦІЯ
    # ==========================================

    @classmethod
    def validate_message_length(
        cls,
        message_text: str,
    ) -> None:
        """Перевіряє ліміт Telegram."""

        if (
            len(message_text)
            > cls.TELEGRAM_MESSAGE_LIMIT
        ):
            raise ValueError(
                "Текст живого підсумку перевищує "
                f"{cls.TELEGRAM_MESSAGE_LIMIT} символів."
            )

    @staticmethod
    def validate_chat_id(
        chat_id: int,
    ) -> None:
        """Перевіряє Telegram chat_id."""

        if not isinstance(chat_id, int):
            raise ValueError(
                "Telegram chat_id повинен бути числом."
            )

        if chat_id == 0:
            raise ValueError(
                "Telegram chat_id не може дорівнювати нулю."
            )

    @staticmethod
    def validate_topic_id(
        topic_id: int | None,
    ) -> None:
        """Перевіряє Telegram topic_id."""

        if topic_id is None:
            return

        if topic_id <= 0:
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

        normalized_value = value.strip()

        if not normalized_value:
            raise ValueError(
                f"{field_name} не може бути порожнім."
            )

        return normalized_value

    @staticmethod
    def error_text(
        error: Exception,
    ) -> str:
        """Формує безпечний текст помилки."""

        text = str(error).strip()

        if not text:
            text = error.__class__.__name__

        return text[:2000]