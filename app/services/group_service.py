from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum, StrEnum
from html import escape
from typing import Any, TypeVar

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
)
from aiogram.types import Message
from sqlalchemy import select

from app.database.models.enums import (
    AuditAction,
    EntityType,
)
from app.database.models.system_setting import (
    SystemSetting,
)
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


class TelegramGroupScope(StrEnum):
    """
    Область Telegram-групи.
    """

    NETWORK = "network"
    BUSH = "bush"


class TelegramGroupTopic(StrEnum):
    """
    Тип topic/thread усередині групи.
    """

    GENERAL = "general"

    OPENING = "opening"
    CLOSING = "closing"

    ALERTS = "alerts"
    SUMMARIES = "summaries"


@dataclass(slots=True, frozen=True)
class TelegramDestination:
    """
    Куди саме Telegram-бот має
    відправити повідомлення.
    """

    chat_id: int

    message_thread_id: int | None

    scope: TelegramGroupScope
    topic: TelegramGroupTopic

    bush_id: int | None

    title: str | None

    @property
    def has_topic(self) -> bool:
        return (
            self.message_thread_id
            is not None
        )


@dataclass(slots=True, frozen=True)
class GroupBindingView:
    """
    Поточна конфігурація Telegram-групи.
    """

    scope: TelegramGroupScope

    chat_id: int
    title: str | None

    bush_id: int | None

    opening_thread_id: int | None
    closing_thread_id: int | None
    alerts_thread_id: int | None
    summaries_thread_id: int | None

    configured: bool = True


@dataclass(slots=True, frozen=True)
class GroupChangeResult:
    """
    Результат зміни Telegram-групи.
    """

    scope: TelegramGroupScope

    bush_id: int | None

    previous_chat_id: int | None
    current_chat_id: int | None

    previous_title: str | None
    current_title: str | None

    was_changed: bool

    changed_at: datetime
    changed_by_id: int

    reason: str


@dataclass(slots=True, frozen=True)
class TopicChangeResult:
    """
    Результат зміни Telegram topic.
    """

    scope: TelegramGroupScope
    topic: TelegramGroupTopic

    bush_id: int | None

    chat_id: int

    previous_thread_id: int | None
    current_thread_id: int | None

    was_changed: bool

    changed_at: datetime
    changed_by_id: int

    reason: str


@dataclass(slots=True, frozen=True)
class BotGroupAccessResult:
    """
    Результат перевірки доступу бота
    до Telegram-групи.
    """

    chat_id: int

    accessible: bool
    can_send_messages: bool

    chat_title: str | None
    chat_type: str | None

    bot_status: str | None

    error: str | None


class GroupService:
    """
    Telegram-групи мережі.

    Підтримує:

    - головну групу мережі;
    - окремі групи кущів;
    - topic відкриття;
    - topic закриття;
    - topic запізнень;
    - topic live-підсумків;
    - автоматичну реєстрацію з Telegram;
    - перевірку доступу бота;
    - fallback із групи куща
      на групу мережі;
    - AuditLog.

    Конфігурація зберігається через
    SystemSetting.

    Приклад ключів:

        telegram_groups.network.chat_id
        telegram_groups.network.title
        telegram_groups.network.alerts.thread_id

        telegram_groups.bush.4.chat_id
        telegram_groups.bush.4.title
        telegram_groups.bush.4.opening.thread_id
    """

    SETTINGS_PREFIX = (
        "telegram_groups"
    )

    def __init__(
        self,
        repositories: Repositories,
        *,
        access_service: AccessService | None = None,
        bot: Bot | None = None,
    ) -> None:
        self.repositories = repositories
        self.session = repositories.session

        self.access = (
            access_service
            or AccessService(repositories)
        )

        self.bot = bot

    # ==========================================
    # NETWORK GROUP
    # ==========================================

    async def set_network_group(
        self,
        *,
        actor: User,
        chat_id: int,
        title: str | None = None,
        reason: str,
        changed_at: datetime | None = None,
    ) -> GroupChangeResult:
        """
        Встановлює основну групу мережі.
        """

        self.access.require_network_management(
            actor
        )

        return await self.set_group(
            actor=actor,
            scope=(
                TelegramGroupScope.NETWORK
            ),
            chat_id=chat_id,
            bush_id=None,
            title=title,
            reason=reason,
            changed_at=changed_at,
        )

    # ==========================================
    # BUSH GROUP
    # ==========================================

    async def set_bush_group(
        self,
        *,
        actor: User,
        bush_id: int,
        chat_id: int,
        title: str | None = None,
        reason: str,
        changed_at: datetime | None = None,
    ) -> GroupChangeResult:
        """
        Прив’язує Telegram-групу до куща.
        """

        if bush_id <= 0:
            raise ValueError(
                "ID куща повинен бути "
                "більшим за нуль."
            )

        decision = (
            await self.access.can_manage_bush(
                actor,
                bush_id,
            )
        )

        decision.raise_if_denied()

        return await self.set_group(
            actor=actor,
            scope=(
                TelegramGroupScope.BUSH
            ),
            chat_id=chat_id,
            bush_id=bush_id,
            title=title,
            reason=reason,
            changed_at=changed_at,
        )

    # ==========================================
    # ЗАГАЛЬНА ЗМІНА ГРУПИ
    # ==========================================

    async def set_group(
        self,
        *,
        actor: User,
        scope: TelegramGroupScope,
        chat_id: int,
        bush_id: int | None,
        title: str | None,
        reason: str,
        changed_at: datetime | None,
    ) -> GroupChangeResult:
        """
        Записує Telegram-групу.
        """

        now = (
            changed_at
            or datetime.now(UTC)
        )

        self.validate_aware_datetime(
            now,
            field_name="changed_at",
        )

        self.validate_scope(
            scope=scope,
            bush_id=bush_id,
        )

        self.validate_group_chat_id(
            chat_id
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
                max_length=2000,
            )
        )

        normalized_title = (
            self.normalize_optional_text(
                title,
                max_length=255,
            )
        )

        chat_key = self.chat_id_key(
            scope=scope,
            bush_id=bush_id,
        )

        title_key = self.title_key(
            scope=scope,
            bush_id=bush_id,
        )

        previous_chat_id = (
            await self.get_int_setting(
                chat_key
            )
        )

        previous_title = (
            await self.get_string_setting(
                title_key
            )
        )

        await self.set_setting(
            chat_key,
            str(chat_id),
        )

        if normalized_title:
            await self.set_setting(
                title_key,
                normalized_title,
            )

        else:
            await self.delete_setting(
                title_key
            )

        was_changed = (
            previous_chat_id != chat_id
            or previous_title
            != normalized_title
        )

        if was_changed:
            await self.log_group_change(
                actor=actor,
                scope=scope,
                bush_id=bush_id,
                description=(
                    "Змінено Telegram-групу"
                ),
                reason=normalized_reason,
                old_values={
                    "chat_id": (
                        previous_chat_id
                    ),
                    "title": (
                        previous_title
                    ),
                },
                new_values={
                    "chat_id": chat_id,
                    "title": (
                        normalized_title
                    ),
                },
            )

        return GroupChangeResult(
            scope=scope,
            bush_id=bush_id,

            previous_chat_id=(
                previous_chat_id
            ),
            current_chat_id=chat_id,

            previous_title=(
                previous_title
            ),
            current_title=(
                normalized_title
            ),

            was_changed=was_changed,

            changed_at=now,
            changed_by_id=actor.id,

            reason=normalized_reason,
        )

    # ==========================================
    # REGISTER FROM TELEGRAM MESSAGE
    # ==========================================

    async def register_from_message(
        self,
        *,
        actor: User,
        message: Message,
        scope: TelegramGroupScope,
        bush_id: int | None = None,
        reason: str = (
            "Реєстрація Telegram-групи"
        ),
    ) -> GroupChangeResult:
        """
        Реєструє групу без ручного введення chat_id.

        Команду можна виконати прямо
        всередині потрібної Telegram-групи.
        """

        chat_type = self.chat_type_value(
            message.chat.type
        )

        if chat_type not in {
            "group",
            "supergroup",
        }:
            raise ValueError(
                "Цю команду потрібно "
                "виконати в Telegram-групі."
            )

        title = getattr(
            message.chat,
            "title",
            None,
        )

        if scope == TelegramGroupScope.NETWORK:
            return await self.set_network_group(
                actor=actor,
                chat_id=message.chat.id,
                title=title,
                reason=reason,
            )

        if bush_id is None:
            raise ValueError(
                "Для групи куща "
                "потрібно вказати bush_id."
            )

        return await self.set_bush_group(
            actor=actor,
            bush_id=bush_id,
            chat_id=message.chat.id,
            title=title,
            reason=reason,
        )

    # ==========================================
    # TOPIC
    # ==========================================

    async def set_network_topic(
        self,
        *,
        actor: User,
        topic: TelegramGroupTopic,
        thread_id: int | None,
        reason: str,
        changed_at: datetime | None = None,
    ) -> TopicChangeResult:
        """
        Налаштовує topic головної групи.
        """

        self.access.require_network_management(
            actor
        )

        return await self.set_topic(
            actor=actor,
            scope=(
                TelegramGroupScope.NETWORK
            ),
            bush_id=None,
            topic=topic,
            thread_id=thread_id,
            reason=reason,
            changed_at=changed_at,
        )

    async def set_bush_topic(
        self,
        *,
        actor: User,
        bush_id: int,
        topic: TelegramGroupTopic,
        thread_id: int | None,
        reason: str,
        changed_at: datetime | None = None,
    ) -> TopicChangeResult:
        """
        Налаштовує topic групи куща.
        """

        decision = (
            await self.access.can_manage_bush(
                actor,
                bush_id,
            )
        )

        decision.raise_if_denied()

        return await self.set_topic(
            actor=actor,
            scope=TelegramGroupScope.BUSH,
            bush_id=bush_id,
            topic=topic,
            thread_id=thread_id,
            reason=reason,
            changed_at=changed_at,
        )

    async def set_topic(
        self,
        *,
        actor: User,
        scope: TelegramGroupScope,
        bush_id: int | None,
        topic: TelegramGroupTopic,
        thread_id: int | None,
        reason: str,
        changed_at: datetime | None,
    ) -> TopicChangeResult:
        """
        Встановлює Telegram thread/topic.
        """

        if topic == TelegramGroupTopic.GENERAL:
            raise ValueError(
                "Для GENERAL topic "
                "thread_id не використовується."
            )

        now = (
            changed_at
            or datetime.now(UTC)
        )

        self.validate_aware_datetime(
            now,
            field_name="changed_at",
        )

        self.validate_scope(
            scope=scope,
            bush_id=bush_id,
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
                max_length=2000,
            )
        )

        if thread_id is not None:
            self.validate_thread_id(
                thread_id
            )

        chat_id = await self.get_int_setting(
            self.chat_id_key(
                scope=scope,
                bush_id=bush_id,
            )
        )

        if chat_id is None:
            raise ValueError(
                "Спочатку потрібно "
                "налаштувати Telegram-групу."
            )

        key = self.thread_key(
            scope=scope,
            bush_id=bush_id,
            topic=topic,
        )

        previous_thread_id = (
            await self.get_int_setting(
                key
            )
        )

        if thread_id is None:
            await self.delete_setting(
                key
            )

        else:
            await self.set_setting(
                key,
                str(thread_id),
            )

        was_changed = (
            previous_thread_id
            != thread_id
        )

        if was_changed:
            await self.log_group_change(
                actor=actor,
                scope=scope,
                bush_id=bush_id,
                description=(
                    "Змінено Telegram topic "
                    f"{topic.value}"
                ),
                reason=normalized_reason,
                old_values={
                    "topic": topic.value,
                    "thread_id": (
                        previous_thread_id
                    ),
                },
                new_values={
                    "topic": topic.value,
                    "thread_id": thread_id,
                },
            )

        return TopicChangeResult(
            scope=scope,
            topic=topic,
            bush_id=bush_id,
            chat_id=chat_id,

            previous_thread_id=(
                previous_thread_id
            ),
            current_thread_id=(
                thread_id
            ),

            was_changed=was_changed,

            changed_at=now,
            changed_by_id=actor.id,

            reason=normalized_reason,
        )

    # ==========================================
    # REGISTER TOPIC FROM MESSAGE
    # ==========================================

    async def register_topic_from_message(
        self,
        *,
        actor: User,
        message: Message,
        scope: TelegramGroupScope,
        topic: TelegramGroupTopic,
        bush_id: int | None = None,
        reason: str = (
            "Реєстрація Telegram topic"
        ),
    ) -> TopicChangeResult:
        """
        Запам’ятовує поточний Telegram topic.
        """

        thread_id = getattr(
            message,
            "message_thread_id",
            None,
        )

        if thread_id is None:
            raise ValueError(
                "Команду потрібно виконати "
                "всередині Telegram topic."
            )

        configured_chat_id = (
            await self.get_int_setting(
                self.chat_id_key(
                    scope=scope,
                    bush_id=bush_id,
                )
            )
        )

        if configured_chat_id is None:
            raise ValueError(
                "Спочатку зареєструйте "
                "Telegram-групу."
            )

        if (
            configured_chat_id
            != message.chat.id
        ):
            raise ValueError(
                "Цей topic належить "
                "іншій Telegram-групі."
            )

        if scope == TelegramGroupScope.NETWORK:
            return await self.set_network_topic(
                actor=actor,
                topic=topic,
                thread_id=thread_id,
                reason=reason,
            )

        if bush_id is None:
            raise ValueError(
                "Не вказано bush_id."
            )

        return await self.set_bush_topic(
            actor=actor,
            bush_id=bush_id,
            topic=topic,
            thread_id=thread_id,
            reason=reason,
        )

    # ==========================================
    # GET NETWORK GROUP
    # ==========================================

    async def get_network_group(
        self,
    ) -> GroupBindingView | None:
        """
        Повертає групу мережі.
        """

        return await self.get_group(
            scope=TelegramGroupScope.NETWORK,
            bush_id=None,
        )

    # ==========================================
    # GET BUSH GROUP
    # ==========================================

    async def get_bush_group(
        self,
        bush_id: int,
    ) -> GroupBindingView | None:
        """
        Повертає групу куща.
        """

        if bush_id <= 0:
            raise ValueError(
                "Некоректний bush_id."
            )

        return await self.get_group(
            scope=TelegramGroupScope.BUSH,
            bush_id=bush_id,
        )

    # ==========================================
    # GET GENERIC GROUP
    # ==========================================

    async def get_group(
        self,
        *,
        scope: TelegramGroupScope,
        bush_id: int | None,
    ) -> GroupBindingView | None:
        """
        Читає повну конфігурацію групи.
        """

        self.validate_scope(
            scope=scope,
            bush_id=bush_id,
        )

        chat_id = await self.get_int_setting(
            self.chat_id_key(
                scope=scope,
                bush_id=bush_id,
            )
        )

        if chat_id is None:
            return None

        title = (
            await self.get_string_setting(
                self.title_key(
                    scope=scope,
                    bush_id=bush_id,
                )
            )
        )

        opening_thread_id = (
            await self.get_int_setting(
                self.thread_key(
                    scope=scope,
                    bush_id=bush_id,
                    topic=(
                        TelegramGroupTopic
                        .OPENING
                    ),
                )
            )
        )

        closing_thread_id = (
            await self.get_int_setting(
                self.thread_key(
                    scope=scope,
                    bush_id=bush_id,
                    topic=(
                        TelegramGroupTopic
                        .CLOSING
                    ),
                )
            )
        )

        alerts_thread_id = (
            await self.get_int_setting(
                self.thread_key(
                    scope=scope,
                    bush_id=bush_id,
                    topic=(
                        TelegramGroupTopic
                        .ALERTS
                    ),
                )
            )
        )

        summaries_thread_id = (
            await self.get_int_setting(
                self.thread_key(
                    scope=scope,
                    bush_id=bush_id,
                    topic=(
                        TelegramGroupTopic
                        .SUMMARIES
                    ),
                )
            )
        )

        return GroupBindingView(
            scope=scope,
            chat_id=chat_id,
            title=title,
            bush_id=bush_id,

            opening_thread_id=(
                opening_thread_id
            ),
            closing_thread_id=(
                closing_thread_id
            ),
            alerts_thread_id=(
                alerts_thread_id
            ),
            summaries_thread_id=(
                summaries_thread_id
            ),
        )

    # ==========================================
    # RESOLVE DESTINATION
    # ==========================================

    async def resolve_destination(
        self,
        *,
        topic: TelegramGroupTopic,
        bush_id: int | None = None,
        fallback_to_network: bool = True,
    ) -> TelegramDestination | None:
        """
        Визначає, куди відправити повідомлення.

        Якщо для куща окрема група
        не налаштована, може використати
        головну групу мережі.
        """

        if bush_id is not None:
            bush_group = (
                await self.get_bush_group(
                    bush_id
                )
            )

            if bush_group is not None:
                return self.destination_from_view(
                    bush_group,
                    topic=topic,
                )

        if not fallback_to_network:
            return None

        network_group = (
            await self.get_network_group()
        )

        if network_group is None:
            return None

        return self.destination_from_view(
            network_group,
            topic=topic,
        )

    # ==========================================
    # DESTINATION FROM VIEW
    # ==========================================

    @staticmethod
    def destination_from_view(
        group: GroupBindingView,
        *,
        topic: TelegramGroupTopic,
    ) -> TelegramDestination:
        """
        Формує TelegramDestination.
        """

        thread_id: int | None

        if topic == TelegramGroupTopic.OPENING:
            thread_id = (
                group.opening_thread_id
            )

        elif topic == TelegramGroupTopic.CLOSING:
            thread_id = (
                group.closing_thread_id
            )

        elif topic == TelegramGroupTopic.ALERTS:
            thread_id = (
                group.alerts_thread_id
            )

        elif topic == TelegramGroupTopic.SUMMARIES:
            thread_id = (
                group.summaries_thread_id
            )

        else:
            thread_id = None

        return TelegramDestination(
            chat_id=group.chat_id,
            message_thread_id=thread_id,
            scope=group.scope,
            topic=topic,
            bush_id=group.bush_id,
            title=group.title,
        )

    # ==========================================
    # CLEAR NETWORK
    # ==========================================

    async def clear_network_group(
        self,
        *,
        actor: User,
        reason: str,
    ) -> GroupChangeResult:
        """
        Видаляє конфігурацію групи мережі.
        """

        self.access.require_network_management(
            actor
        )

        return await self.clear_group(
            actor=actor,
            scope=TelegramGroupScope.NETWORK,
            bush_id=None,
            reason=reason,
        )

    # ==========================================
    # CLEAR BUSH
    # ==========================================

    async def clear_bush_group(
        self,
        *,
        actor: User,
        bush_id: int,
        reason: str,
    ) -> GroupChangeResult:
        """
        Видаляє конфігурацію групи куща.
        """

        decision = (
            await self.access.can_manage_bush(
                actor,
                bush_id,
            )
        )

        decision.raise_if_denied()

        return await self.clear_group(
            actor=actor,
            scope=TelegramGroupScope.BUSH,
            bush_id=bush_id,
            reason=reason,
        )

    # ==========================================
    # CLEAR GROUP
    # ==========================================

    async def clear_group(
        self,
        *,
        actor: User,
        scope: TelegramGroupScope,
        bush_id: int | None,
        reason: str,
    ) -> GroupChangeResult:
        """
        Повністю очищає групу та її topics.
        """

        now = datetime.now(UTC)

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
                max_length=2000,
            )
        )

        current = await self.get_group(
            scope=scope,
            bush_id=bush_id,
        )

        previous_chat_id = (
            current.chat_id
            if current
            else None
        )

        previous_title = (
            current.title
            if current
            else None
        )

        keys = [
            self.chat_id_key(
                scope=scope,
                bush_id=bush_id,
            ),
            self.title_key(
                scope=scope,
                bush_id=bush_id,
            ),
        ]

        for topic in (
            TelegramGroupTopic.OPENING,
            TelegramGroupTopic.CLOSING,
            TelegramGroupTopic.ALERTS,
            TelegramGroupTopic.SUMMARIES,
        ):
            keys.append(
                self.thread_key(
                    scope=scope,
                    bush_id=bush_id,
                    topic=topic,
                )
            )

        for key in keys:
            await self.delete_setting(
                key
            )

        was_changed = (
            current is not None
        )

        if was_changed:
            await self.log_group_change(
                actor=actor,
                scope=scope,
                bush_id=bush_id,
                description=(
                    "Видалено конфігурацію "
                    "Telegram-групи"
                ),
                reason=normalized_reason,
                old_values={
                    "chat_id": (
                        previous_chat_id
                    ),
                    "title": (
                        previous_title
                    ),
                },
                new_values={
                    "chat_id": None,
                    "title": None,
                },
            )

        return GroupChangeResult(
            scope=scope,
            bush_id=bush_id,

            previous_chat_id=(
                previous_chat_id
            ),
            current_chat_id=None,

            previous_title=(
                previous_title
            ),
            current_title=None,

            was_changed=was_changed,

            changed_at=now,
            changed_by_id=actor.id,

            reason=normalized_reason,
        )

    # ==========================================
    # BOT ACCESS CHECK
    # ==========================================

    async def verify_bot_access(
        self,
        chat_id: int,
    ) -> BotGroupAccessResult:
        """
        Перевіряє, чи бот бачить групу
        та чи може туди писати.
        """

        self.validate_group_chat_id(
            chat_id
        )

        if self.bot is None:
            return BotGroupAccessResult(
                chat_id=chat_id,
                accessible=False,
                can_send_messages=False,
                chat_title=None,
                chat_type=None,
                bot_status=None,
                error=(
                    "Bot не переданий "
                    "у GroupService."
                ),
            )

        try:
            chat = await self.bot.get_chat(
                chat_id
            )

            bot_user = await self.bot.get_me()

            member = (
                await self.bot.get_chat_member(
                    chat_id=chat_id,
                    user_id=bot_user.id,
                )
            )

            status = self.member_status_value(
                getattr(
                    member,
                    "status",
                    None,
                )
            )

            can_send = self.member_can_send(
                member
            )

            return BotGroupAccessResult(
                chat_id=chat_id,
                accessible=True,
                can_send_messages=can_send,

                chat_title=getattr(
                    chat,
                    "title",
                    None,
                ),

                chat_type=self.chat_type_value(
                    getattr(
                        chat,
                        "type",
                        None,
                    )
                ),

                bot_status=status,

                error=None,
            )

        except TelegramForbiddenError:
            return BotGroupAccessResult(
                chat_id=chat_id,
                accessible=False,
                can_send_messages=False,
                chat_title=None,
                chat_type=None,
                bot_status=None,
                error=(
                    "Бота немає в групі "
                    "або йому заборонено доступ."
                ),
            )

        except TelegramBadRequest as error:
            return BotGroupAccessResult(
                chat_id=chat_id,
                accessible=False,
                can_send_messages=False,
                chat_title=None,
                chat_type=None,
                bot_status=None,
                error=str(error),
            )

    # ==========================================
    # SEND TEST MESSAGE
    # ==========================================

    async def send_test_message(
        self,
        *,
        destination: TelegramDestination,
        text: str = (
            "✅ <b>Тестове повідомлення</b>\n\n"
            "Telegram-групу налаштовано правильно."
        ),
    ) -> int:
        """
        Надсилає тестове повідомлення.
        """

        if self.bot is None:
            raise RuntimeError(
                "Bot не переданий "
                "у GroupService."
            )

        message = await self.bot.send_message(
            chat_id=destination.chat_id,
            text=text,
            message_thread_id=(
                destination
                .message_thread_id
            ),
        )

        return message.message_id

    # ==========================================
    # SETTINGS KEYS
    # ==========================================

    @classmethod
    def scope_prefix(
        cls,
        *,
        scope: TelegramGroupScope,
        bush_id: int | None,
    ) -> str:
        """
        Формує prefix SystemSetting.
        """

        cls.validate_scope(
            scope=scope,
            bush_id=bush_id,
        )

        if scope == TelegramGroupScope.NETWORK:
            return (
                f"{cls.SETTINGS_PREFIX}"
                ".network"
            )

        return (
            f"{cls.SETTINGS_PREFIX}"
            f".bush.{bush_id}"
        )

    @classmethod
    def chat_id_key(
        cls,
        *,
        scope: TelegramGroupScope,
        bush_id: int | None,
    ) -> str:
        """
        Ключ chat_id.
        """

        return (
            f"{cls.scope_prefix(scope=scope, bush_id=bush_id)}"
            ".chat_id"
        )

    @classmethod
    def title_key(
        cls,
        *,
        scope: TelegramGroupScope,
        bush_id: int | None,
    ) -> str:
        """
        Ключ title.
        """

        return (
            f"{cls.scope_prefix(scope=scope, bush_id=bush_id)}"
            ".title"
        )

    @classmethod
    def thread_key(
        cls,
        *,
        scope: TelegramGroupScope,
        bush_id: int | None,
        topic: TelegramGroupTopic,
    ) -> str:
        """
        Ключ message_thread_id.
        """

        if topic == TelegramGroupTopic.GENERAL:
            raise ValueError(
                "GENERAL не має thread_id."
            )

        return (
            f"{cls.scope_prefix(scope=scope, bush_id=bush_id)}"
            f".{topic.value}.thread_id"
        )

    # ==========================================
    # SYSTEM SETTINGS
    # ==========================================

    async def get_string_setting(
        self,
        key: str,
    ) -> str | None:
        """
        Читає SystemSetting.
        """

        setting = await self.find_setting(
            key
        )

        if setting is None:
            return None

        value = self.setting_value(
            setting
        )

        if value is None:
            return None

        normalized = str(
            value
        ).strip()

        return normalized or None

    async def get_int_setting(
        self,
        key: str,
    ) -> int | None:
        """
        Читає int із SystemSetting.
        """

        value = (
            await self.get_string_setting(
                key
            )
        )

        if value is None:
            return None

        try:
            return int(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

    async def set_setting(
        self,
        key: str,
        value: str,
    ) -> SystemSetting:
        """
        Створює або оновлює SystemSetting.
        """

        normalized_key = (
            self.normalize_setting_key(
                key
            )
        )

        normalized_value = str(
            value
        )

        setting = await self.find_setting(
            normalized_key,
            for_update=True,
        )

        now = datetime.now(UTC)

        if setting is None:
            payload = {
                "key": normalized_key,
                "name": normalized_key,
                "setting_key": (
                    normalized_key
                ),

                "value": normalized_value,
                "setting_value": (
                    normalized_value
                ),
                "value_text": (
                    normalized_value
                ),

                "created_at": now,
                "updated_at": now,
            }

            setting = SystemSetting(
                **self.filter_setting_payload(
                    payload
                )
            )

            self.session.add(
                setting
            )

        else:
            self.set_setting_value(
                setting,
                normalized_value,
            )

            self.set_first_existing_attribute(
                setting,
                now,
                "updated_at",
                "modified_at",
            )

            self.session.add(
                setting
            )

        await self.session.flush()

        return setting

    async def delete_setting(
        self,
        key: str,
    ) -> bool:
        """
        Видаляє конкретне SystemSetting.

        Тут фізичне видалення допустиме,
        бо це лише конфігураційний ключ.
        """

        setting = await self.find_setting(
            key,
            for_update=True,
        )

        if setting is None:
            return False

        await self.session.delete(
            setting
        )

        await self.session.flush()

        return True

    async def find_setting(
        self,
        key: str,
        *,
        for_update: bool = False,
    ) -> SystemSetting | None:
        """
        Шукає SystemSetting за ключем.
        """

        key_column = (
            self.setting_key_column()
        )

        statement = (
            select(SystemSetting)
            .where(
                key_column == key
            )
            .limit(1)
        )

        if for_update:
            statement = (
                statement.with_for_update()
            )

        return await self.session.scalar(
            statement
        )

    # ==========================================
    # SYSTEM SETTING MODEL
    # ==========================================

    @staticmethod
    def setting_key_column() -> Any:
        """
        Визначає колонку ключа.
        """

        for field_name in (
            "key",
            "setting_key",
            "name",
        ):
            column = getattr(
                SystemSetting,
                field_name,
                None,
            )

            if column is not None:
                return column

        raise AttributeError(
            "SystemSetting не містить "
            "колонки key/setting_key/name."
        )

    @staticmethod
    def setting_value(
        setting: SystemSetting,
    ) -> Any:
        """
        Читає значення SystemSetting.
        """

        for field_name in (
            "value",
            "setting_value",
            "value_text",
        ):
            if hasattr(
                setting,
                field_name,
            ):
                return getattr(
                    setting,
                    field_name,
                )

        return None

    @staticmethod
    def set_setting_value(
        setting: SystemSetting,
        value: str,
    ) -> None:
        """
        Записує значення.
        """

        for field_name in (
            "value",
            "setting_value",
            "value_text",
        ):
            if hasattr(
                setting,
                field_name,
            ):
                setattr(
                    setting,
                    field_name,
                    value,
                )

                return

        raise AttributeError(
            "SystemSetting не містить "
            "поля для value."
        )

    @staticmethod
    def filter_setting_payload(
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Залишає реальні колонки.
        """

        columns = {
            column.key
            for column
            in SystemSetting.__mapper__.columns
        }

        result: dict[
            str,
            Any,
        ] = {}

        # Не можна одночасно передавати
        # key/name/setting_key.
        for alternatives in (
            (
                "key",
                "setting_key",
                "name",
            ),
            (
                "value",
                "setting_value",
                "value_text",
            ),
        ):
            for field_name in alternatives:
                if (
                    field_name in columns
                    and field_name in payload
                ):
                    result[field_name] = (
                        payload[field_name]
                    )
                    break

        for field_name in (
            "created_at",
            "updated_at",
        ):
            if (
                field_name in columns
                and field_name in payload
            ):
                result[field_name] = (
                    payload[field_name]
                )

        return result

    # ==========================================
    # AUDIT LOG
    # ==========================================

    async def log_group_change(
        self,
        *,
        actor: User,
        scope: TelegramGroupScope,
        bush_id: int | None,
        description: str,
        reason: str,
        old_values: dict[str, Any],
        new_values: dict[str, Any],
    ) -> None:
        """
        Фіксує зміну Telegram-групи.
        """

        action = (
            self.resolve_audit_action(
                "update",
                "changed",
            )
        )

        entity_type = (
            self.resolve_entity_type(
                "setting",
                "system",
                "configuration",
            )
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=(
                bush_id
                if bush_id is not None
                else None
            ),

            context=AuditContext(
                actor_user_id=actor.id,
                reason=reason,
                description=description,
                source="telegram_bot",
            ),

            old_values={
                **old_values,
                "scope": scope.value,
                "bush_id": bush_id,
            },

            new_values={
                **new_values,
                "scope": scope.value,
                "bush_id": bush_id,
            },
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

        result = cls.resolve_enum_member(
            AuditAction,
            *names,
            default=None,
        )

        if result is not None:
            return result

        result = cls.resolve_enum_member(
            AuditAction,
            "update",
            default=None,
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

        result = cls.resolve_enum_member(
            EntityType,
            *names,
            default=None,
        )

        if result is not None:
            return result

        result = cls.resolve_enum_member(
            EntityType,
            "system",
            default=None,
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
        Пошук enum за name/value.
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
    # BOT MEMBER
    # ==========================================

    @staticmethod
    def member_status_value(
        value: Any,
    ) -> str | None:
        """
        Нормалізує ChatMemberStatus.
        """

        if value is None:
            return None

        enum_value = getattr(
            value,
            "value",
            None,
        )

        if enum_value is not None:
            return str(
                enum_value
            )

        return str(
            value
        )

    @classmethod
    def member_can_send(
        cls,
        member: Any,
    ) -> bool:
        """
        Чи може бот надсилати повідомлення.
        """

        status = cls.member_status_value(
            getattr(
                member,
                "status",
                None,
            )
        )

        if status in {
            "administrator",
            "creator",
            "owner",
        }:
            return True

        if status in {
            "left",
            "kicked",
            "banned",
        }:
            return False

        can_send_messages = getattr(
            member,
            "can_send_messages",
            None,
        )

        if can_send_messages is not None:
            return bool(
                can_send_messages
            )

        return status == "member"

    # ==========================================
    # VALIDATION
    # ==========================================

    @staticmethod
    def validate_scope(
        *,
        scope: TelegramGroupScope,
        bush_id: int | None,
    ) -> None:
        """
        Перевіряє scope.
        """

        if (
            scope
            == TelegramGroupScope.NETWORK
            and bush_id is not None
        ):
            raise ValueError(
                "NETWORK не повинен "
                "містити bush_id."
            )

        if (
            scope
            == TelegramGroupScope.BUSH
            and bush_id is None
        ):
            raise ValueError(
                "Для BUSH потрібно "
                "вказати bush_id."
            )

        if (
            bush_id is not None
            and bush_id <= 0
        ):
            raise ValueError(
                "Некоректний bush_id."
            )

    @staticmethod
    def validate_group_chat_id(
        chat_id: int,
    ) -> None:
        """
        Перевіряє Telegram chat_id.

        Групи та supergroup мають
        від’ємний chat_id.
        """

        if isinstance(
            chat_id,
            bool,
        ):
            raise ValueError(
                "Некоректний chat_id."
            )

        if chat_id >= 0:
            raise ValueError(
                "Очікується chat_id "
                "Telegram-групи або supergroup."
            )

    @staticmethod
    def validate_thread_id(
        thread_id: int,
    ) -> None:
        """
        Перевіряє message_thread_id.
        """

        if (
            isinstance(
                thread_id,
                bool,
            )
            or thread_id <= 0
        ):
            raise ValueError(
                "Некоректний "
                "message_thread_id."
            )

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
    def normalize_setting_key(
        value: str,
    ) -> str:
        """
        Нормалізує ключ.
        """

        normalized = (
            value.strip().lower()
        )

        if not normalized:
            raise ValueError(
                "Порожній ключ setting."
            )

        if len(normalized) > 255:
            raise ValueError(
                "Ключ setting "
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
        Обов’язковий текст.
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
        max_length: int,
    ) -> str | None:
        """
        Необов’язковий текст.
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

    # ==========================================
    # GENERIC ATTRIBUTES
    # ==========================================

    @staticmethod
    def set_first_existing_attribute(
        target: Any,
        value: Any,
        *names: str,
    ) -> bool:
        """
        Записує перший наявний атрибут.
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
    def chat_type_value(
        value: Any,
    ) -> str | None:
        """
        Нормалізує ChatType.
        """

        if value is None:
            return None

        enum_value = getattr(
            value,
            "value",
            None,
        )

        if enum_value is not None:
            return str(
                enum_value
            )

        return str(
            value
        ).lower()

    # ==========================================
    # TELEGRAM FORMAT
    # ==========================================

    @staticmethod
    def format_group(
        group: GroupBindingView,
    ) -> str:
        """
        Формує картку групи.
        """

        scope_text = (
            "Мережа"
            if group.scope
            == TelegramGroupScope.NETWORK
            else (
                f"Кущ #{group.bush_id}"
            )
        )

        lines = [
            "💬 <b>Telegram-група</b>",
            "",
            (
                "Область: "
                f"<b>{escape(scope_text)}</b>"
            ),
            (
                "Chat ID: "
                f"<code>{group.chat_id}</code>"
            ),
        ]

        if group.title:
            lines.append(
                "Назва: "
                f"<b>{escape(group.title)}</b>"
            )

        lines.extend(
            [
                "",
                (
                    "🌅 Відкриття: "
                    f"<code>{group.opening_thread_id or 'GENERAL'}</code>"
                ),
                (
                    "🌙 Закриття: "
                    f"<code>{group.closing_thread_id or 'GENERAL'}</code>"
                ),
                (
                    "🚨 Запізнення: "
                    f"<code>{group.alerts_thread_id or 'GENERAL'}</code>"
                ),
                (
                    "📊 Підсумки: "
                    f"<code>{group.summaries_thread_id or 'GENERAL'}</code>"
                ),
            ]
        )

        return "\n".join(
            lines
        )

    @staticmethod
    def format_access_result(
        result: BotGroupAccessResult,
    ) -> str:
        """
        Формує результат перевірки бота.
        """

        if not result.accessible:
            return "\n".join(
                [
                    "❌ <b>Група недоступна</b>",
                    "",
                    (
                        "Chat ID: "
                        f"<code>{result.chat_id}</code>"
                    ),
                    (
                        "Причина: "
                        f"{escape(result.error or 'невідомо')}"
                    ),
                ]
            )

        send_status = (
            "може ✅"
            if result.can_send_messages
            else "не може ❌"
        )

        lines = [
            "✅ <b>Група доступна</b>",
            "",
            (
                "Chat ID: "
                f"<code>{result.chat_id}</code>"
            ),
            (
                "Надсилати повідомлення: "
                f"<b>{send_status}</b>"
            ),
        ]

        if result.chat_title:
            lines.append(
                "Назва: "
                f"<b>{escape(result.chat_title)}</b>"
            )

        if result.bot_status:
            lines.append(
                "Статус бота: "
                f"<code>{escape(result.bot_status)}</code>"
            )

        return "\n".join(
            lines
        )


__all__ = [
    "GroupService",
    "TelegramGroupScope",
    "TelegramGroupTopic",
    "TelegramDestination",
    "GroupBindingView",
    "GroupChangeResult",
    "TopicChangeResult",
    "BotGroupAccessResult",
]