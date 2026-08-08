from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, TypeAlias

from aiogram import BaseMiddleware
from aiogram.types import (
    CallbackQuery,
    Message,
    TelegramObject,
    User as TelegramUser,
)
from sqlalchemy import select

from app.database.models.enums import (
    UserRole,
    UserStatus,
)
from app.database.models.user import User
from app.repositories import Repositories


HandlerType: TypeAlias = Callable[
    [
        TelegramObject,
        dict[str, Any],
    ],
    Awaitable[Any],
]


class AuthState(StrEnum):
    """
    РџРѕС‚РѕС‡РЅРёР№ СЃС‚Р°РЅ Р°РІС‚РѕСЂРёР·Р°С†С–С— РєРѕСЂРёСЃС‚СѓРІР°С‡Р°.
    """

    ACTIVE = "active"
    NEW_USER = "new_user"

    ANONYMOUS = "anonymous"

    BLOCKED = "blocked"
    INACTIVE = "inactive"

    BOT_DISABLED = "bot_disabled"
    MAINTENANCE = "maintenance"


@dataclass(slots=True, frozen=True)
class AuthMiddlewareContext:
    """
    РљРѕРЅС‚РµРєСЃС‚ Р°РІС‚РѕСЂРёР·Р°С†С–С— РѕРґРЅРѕРіРѕ Telegram update.
    """

    telegram_user: TelegramUser | None
    current_user: User | None

    state: AuthState

    was_created: bool
    profile_was_updated: bool

    bot_enabled: bool
    maintenance_mode: bool

    @property
    def is_authenticated(self) -> bool:
        return self.current_user is not None

    @property
    def is_available(self) -> bool:
        return self.state in {
            AuthState.ACTIVE,
            AuthState.NEW_USER,
        }


@dataclass(slots=True, frozen=True)
class UserResolutionResult:
    """
    Р РµР·СѓР»СЊС‚Р°С‚ РїРѕС€СѓРєСѓ Р°Р±Рѕ СЃС‚РІРѕСЂРµРЅРЅСЏ РєРѕСЂРёСЃС‚СѓРІР°С‡Р°.
    """

    user: User

    was_created: bool
    profile_was_updated: bool


class AuthMiddleware(BaseMiddleware):
    """
    Middleware Р°РІС‚РѕСЂРёР·Р°С†С–С— Telegram-РєРѕСЂРёСЃС‚СѓРІР°С‡Р°.

    РџСЂР°С†СЋС” РїС–СЃР»СЏ DatabaseMiddleware.

    РЈ РєРѕР¶РµРЅ handler РїРµСЂРµРґР°С”:

        current_user: User
        auth_context: AuthMiddlewareContext
        is_new_user: bool

    Р›РѕРіС–РєР°:

    1. РћС‚СЂРёРјСѓС” Telegram-РєРѕСЂРёСЃС‚СѓРІР°С‡Р°.
    2. РЁСѓРєР°С” Р№РѕРіРѕ РІ PostgreSQL.
    3. РЎС‚РІРѕСЂСЋС”, СЏРєС‰Рѕ Р№РѕРіРѕ С‰Рµ РЅРµРјР°С”.
    4. РћРЅРѕРІР»СЋС” Telegram-РїСЂРѕС„С–Р»СЊ.
    5. РџРµСЂРµРІС–СЂСЏС” Р±Р»РѕРєСѓРІР°РЅРЅСЏ.
    6. РџРµСЂРµРІС–СЂСЏС” С‚РµС…РЅС–С‡РЅРёР№ СЂРµР¶РёРј.
    7. Р—Р°РїСѓСЃРєР°С” handler.
    """

    DEFAULT_BLOCKED_MESSAGE = (
        "в›” <b>Р”РѕСЃС‚СѓРї РґРѕ Р±РѕС‚Р° РѕР±РјРµР¶РµРЅРѕ.</b>\n\n"
        "Р”Р»СЏ СѓС‚РѕС‡РЅРµРЅРЅСЏ Р·РІРµСЂРЅС–С‚СЊСЃСЏ РґРѕ Р°РґРјС–РЅС–СЃС‚СЂР°С‚РѕСЂР°."
    )

    DEFAULT_INACTIVE_MESSAGE = (
        "вљ пёЏ <b>Р’Р°С€ РѕР±Р»С–РєРѕРІРёР№ Р·Р°РїРёСЃ РЅРµР°РєС‚РёРІРЅРёР№.</b>\n\n"
        "Р—РІРµСЂРЅС–С‚СЊСЃСЏ РґРѕ РІС–РґРїРѕРІС–РґР°Р»СЊРЅРѕРіРѕ Р°РґРјС–РЅС–СЃС‚СЂР°С‚РѕСЂР°."
    )

    DEFAULT_BOT_DISABLED_MESSAGE = (
        "рџ”ґ <b>Р‘РѕС‚ С‚РёРјС‡Р°СЃРѕРІРѕ РІРёРјРєРЅРµРЅРёР№.</b>\n\n"
        "РЎРїСЂРѕР±СѓР№С‚Рµ СЃРєРѕСЂРёСЃС‚Р°С‚РёСЃСЏ РЅРёРј РїС–Р·РЅС–С€Рµ."
    )

    DEFAULT_MAINTENANCE_MESSAGE = (
        "рџ›  <b>РЈ Р±РѕС‚С– РїСЂРѕРІРѕРґСЏС‚СЊСЃСЏ С‚РµС…РЅС–С‡РЅС– СЂРѕР±РѕС‚Рё.</b>\n\n"
        "РЎРїСЂРѕР±СѓР№С‚Рµ С‰Рµ СЂР°Р· С‚СЂРѕС…Рё РїС–Р·РЅС–С€Рµ."
    )

    def __init__(
        self,
        *,
        auto_create_users: bool = True,
        update_profile: bool = True,
        block_inactive_users: bool = True,
        allow_anonymous_updates: bool = True,
        blocked_message: str | None = None,
        inactive_message: str | None = None,
        bot_disabled_message: str | None = None,
        maintenance_message: str | None = None,
    ) -> None:
        self.auto_create_users = auto_create_users
        self.update_profile = update_profile

        self.block_inactive_users = (
            block_inactive_users
        )

        self.allow_anonymous_updates = (
            allow_anonymous_updates
        )

        self.blocked_message = (
            blocked_message
            or self.DEFAULT_BLOCKED_MESSAGE
        )

        self.inactive_message = (
            inactive_message
            or self.DEFAULT_INACTIVE_MESSAGE
        )

        self.bot_disabled_message = (
            bot_disabled_message
            or self.DEFAULT_BOT_DISABLED_MESSAGE
        )

        self.maintenance_message = (
            maintenance_message
            or self.DEFAULT_MAINTENANCE_MESSAGE
        )

    # ==========================================
    # Р“РћР›РћР’РќРР™ Р’РРљР›РРљ
    # ==========================================

    async def __call__(
        self,
        handler: HandlerType,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """
        РђРІС‚РѕСЂРёР·СѓС” РєРѕСЂРёСЃС‚СѓРІР°С‡Р° РїРµСЂРµРґ handler.
        """

        repositories = (
            self.get_repositories(data)
        )

        telegram_user = (
            self.resolve_telegram_user(
                event=event,
                data=data,
            )
        )

        if telegram_user is None:
            context = AuthMiddlewareContext(
                telegram_user=None,
                current_user=None,
                state=AuthState.ANONYMOUS,
                was_created=False,
                profile_was_updated=False,
                bot_enabled=True,
                maintenance_mode=False,
            )

            if not self.allow_anonymous_updates:
                return None

            return await self.call_handler(
                handler=handler,
                event=event,
                data=data,
                context=context,
            )

        if telegram_user.is_bot:
            return None

        resolution = (
            await self.resolve_or_create_user(
                repositories=repositories,
                telegram_user=telegram_user,
            )
        )

        current_user = resolution.user

        bot_enabled = await self.is_bot_enabled(
            repositories
        )

        maintenance_mode = (
            await self.is_maintenance_mode(
                repositories
            )
        )

        is_root_admin = self.is_root_admin(
            current_user
        )

        if self.is_blocked_user(
            current_user
        ):
            context = AuthMiddlewareContext(
                telegram_user=telegram_user,
                current_user=current_user,
                state=AuthState.BLOCKED,
                was_created=(
                    resolution.was_created
                ),
                profile_was_updated=(
                    resolution
                    .profile_was_updated
                ),
                bot_enabled=bot_enabled,
                maintenance_mode=(
                    maintenance_mode
                ),
            )

            await self.answer_restriction(
                event=event,
                text=self.blocked_message,
            )

            return None

        if (
            self.block_inactive_users
            and self.is_inactive_user(
                current_user
            )
            and not is_root_admin
        ):
            context = AuthMiddlewareContext(
                telegram_user=telegram_user,
                current_user=current_user,
                state=AuthState.INACTIVE,
                was_created=(
                    resolution.was_created
                ),
                profile_was_updated=(
                    resolution
                    .profile_was_updated
                ),
                bot_enabled=bot_enabled,
                maintenance_mode=(
                    maintenance_mode
                ),
            )

            await self.answer_restriction(
                event=event,
                text=self.inactive_message,
            )

            return None

        if (
            not bot_enabled
            and not is_root_admin
        ):
            context = AuthMiddlewareContext(
                telegram_user=telegram_user,
                current_user=current_user,
                state=AuthState.BOT_DISABLED,
                was_created=(
                    resolution.was_created
                ),
                profile_was_updated=(
                    resolution
                    .profile_was_updated
                ),
                bot_enabled=False,
                maintenance_mode=(
                    maintenance_mode
                ),
            )

            await self.answer_restriction(
                event=event,
                text=(
                    self.bot_disabled_message
                ),
            )

            return None

        if (
            maintenance_mode
            and not is_root_admin
        ):
            context = AuthMiddlewareContext(
                telegram_user=telegram_user,
                current_user=current_user,
                state=AuthState.MAINTENANCE,
                was_created=(
                    resolution.was_created
                ),
                profile_was_updated=(
                    resolution
                    .profile_was_updated
                ),
                bot_enabled=bot_enabled,
                maintenance_mode=True,
            )

            maintenance_text = (
                await self.get_maintenance_message(
                    repositories
                )
            )

            await self.answer_restriction(
                event=event,
                text=(
                    maintenance_text
                    or self.maintenance_message
                ),
            )

            return None

        state = (
            AuthState.NEW_USER
            if resolution.was_created
            else AuthState.ACTIVE
        )

        context = AuthMiddlewareContext(
            telegram_user=telegram_user,
            current_user=current_user,
            state=state,
            was_created=(
                resolution.was_created
            ),
            profile_was_updated=(
                resolution.profile_was_updated
            ),
            bot_enabled=bot_enabled,
            maintenance_mode=(
                maintenance_mode
            ),
        )

        return await self.call_handler(
            handler=handler,
            event=event,
            data=data,
            context=context,
        )

    # ==========================================
    # Р—РђРџРЈРЎРљ HANDLER
    # ==========================================

    async def call_handler(
        self,
        *,
        handler: HandlerType,
        event: TelegramObject,
        data: dict[str, Any],
        context: AuthMiddlewareContext,
    ) -> Any:
        """
        РџРµСЂРµРґР°С” Р°РІС‚РѕСЂРёР·Р°С†С–Р№РЅС– РґР°РЅС– Сѓ handler.
        """

        dependencies: dict[str, Any] = {
            "current_user": (
                context.current_user
            ),
            "auth_context": context,
            "is_new_user": (
                context.was_created
            ),
        }

        previous_values: dict[
            str,
            tuple[bool, Any],
        ] = {}

        for key, value in dependencies.items():
            previous_values[key] = (
                key in data,
                data.get(key),
            )

            data[key] = value

        try:
            return await handler(
                event,
                data,
            )

        finally:
            for key, (
                existed,
                previous_value,
            ) in previous_values.items():
                if existed:
                    data[key] = previous_value
                else:
                    data.pop(
                        key,
                        None,
                    )

    # ==========================================
    # РџРћРЁРЈРљ РђР‘Рћ РЎРўР’РћР Р•РќРќРЇ
    # ==========================================

    async def resolve_or_create_user(
        self,
        *,
        repositories: Repositories,
        telegram_user: TelegramUser,
    ) -> UserResolutionResult:
        """
        РЁСѓРєР°С” РєРѕСЂРёСЃС‚СѓРІР°С‡Р° Р°Р±Рѕ СЃС‚РІРѕСЂСЋС” РЅРѕРІРѕРіРѕ.
        """

        repository_result = (
            await self.try_repository_upsert(
                repositories=repositories,
                telegram_user=telegram_user,
            )
        )

        if repository_result is not None:
            return repository_result

        return await self.fallback_upsert_user(
            repositories=repositories,
            telegram_user=telegram_user,
        )

    async def try_repository_upsert(
        self,
        *,
        repositories: Repositories,
        telegram_user: TelegramUser,
    ) -> UserResolutionResult | None:
        """
        РџСЂРѕР±СѓС” РІРёРєРѕСЂРёСЃС‚Р°С‚Рё РіРѕС‚РѕРІРёР№ РјРµС‚РѕРґ
        UserRepository.
        """

        repository = repositories.users

        method_names = (
            "get_or_create_from_telegram",
            "get_or_create_telegram_user",
            "upsert_from_telegram",
            "sync_telegram_user",
            "resolve_telegram_user",
        )

        payload = {
            "telegram_user": telegram_user,

            "telegram_id": telegram_user.id,

            "telegram_username": (
                telegram_user.username
            ),
            "username": telegram_user.username,

            "first_name": (
                telegram_user.first_name
            ),
            "last_name": (
                telegram_user.last_name
            ),

        "full_name": (
            telegram_user.full_name
        ),

            "language_code": (
                telegram_user.language_code
            ),
            "is_premium": bool(
                telegram_user.is_premium
            ),

            "current_time": datetime.now(
                UTC
            ),
            "seen_at": datetime.now(UTC),

            "auto_create": (
                self.auto_create_users
            ),
            "update_profile": (
                self.update_profile
            ),
        }

        for method_name in method_names:
            method = getattr(
                repository,
                method_name,
                None,
            )

            if method is None or not callable(
                method
            ):
                continue

            accepted_payload = (
                self.filter_method_kwargs(
                    method,
                    payload,
                )
            )

            result = method(
                **accepted_payload
            )

            if inspect.isawaitable(result):
                result = await result

            parsed_result = (
                self.parse_repository_result(
                    result
                )
            )

            if parsed_result is not None:
                return parsed_result

        return None

    # ==========================================
    # Р Р•Р—Р•Р Р’РќРР™ UPSERT
    # ==========================================

    async def fallback_upsert_user(
        self,
        *,
        repositories: Repositories,
        telegram_user: TelegramUser,
    ) -> UserResolutionResult:
        """
        Р РµР·РµСЂРІРЅРёР№ SQLAlchemy upsert.

        Р’РёРєРѕСЂРёСЃС‚РѕРІСѓС”С‚СЊСЃСЏ, СЏРєС‰Рѕ UserRepository
        РЅРµ РјС–СЃС‚РёС‚СЊ СЃРїРµС†С–Р°Р»СЊРЅРѕРіРѕ РјРµС‚РѕРґСѓ.
        """

        statement = (
            select(User)
            .where(
                User.telegram_id
                == telegram_user.id
            )
            .limit(1)
        )

        user = await repositories.session.scalar(
            statement
        )

        if user is None:
            if not self.auto_create_users:
                raise PermissionError(
                    "РљРѕСЂРёСЃС‚СѓРІР°С‡Р° РЅРµ Р·РЅР°Р№РґРµРЅРѕ, "
                    "Р° Р°РІС‚РѕРјР°С‚РёС‡РЅРµ СЃС‚РІРѕСЂРµРЅРЅСЏ РІРёРјРєРЅРµРЅРµ."
                )

            user = self.create_user_model(
                telegram_user
            )

            repositories.session.add(user)

            await repositories.session.flush()

            return UserResolutionResult(
                user=user,
                was_created=True,
                profile_was_updated=True,
            )

        profile_was_updated = False

        if self.update_profile:
            profile_was_updated = (
                self.update_user_profile(
                    user=user,
                    telegram_user=(
                        telegram_user
                    ),
                )
            )

        self.update_last_seen(user)

        repositories.session.add(user)

        await repositories.session.flush()

        return UserResolutionResult(
            user=user,
            was_created=False,
            profile_was_updated=(
                profile_was_updated
            ),
        )

    # ==========================================
    # РЎРўР’РћР Р•РќРќРЇ РњРћР”Р•Р›Р† USER
    # ==========================================

    def create_user_model(
        self,
        telegram_user: TelegramUser,
    ) -> User:
        """
        РЎС‚РІРѕСЂСЋС” РЅРѕРІРѕРіРѕ РєРѕСЂРёСЃС‚СѓРІР°С‡Р°.

        РќРѕРІРёР№ РєРѕСЂРёСЃС‚СѓРІР°С‡ РѕС‚СЂРёРјСѓС”:

        - СЂРѕР»СЊ STORE_USER;
        - СЃС‚Р°С‚СѓСЃ PENDING, СЏРєС‰Рѕ РІС–РЅ С” РІ enum;
        - Telegram-РїСЂРѕС„С–Р»СЊ.
        """

        available_columns = {
            column.key
            for column
            in User.__mapper__.columns
        }

        payload: dict[str, Any] = {
            "telegram_id": (
                telegram_user.id
            ),
            "telegram_username": (
                telegram_user.username
            ),
            "username": telegram_user.username,
            "first_name": (
                telegram_user.first_name
            ),
            "last_name": (
                telegram_user.last_name
            ),

        "full_name": (
            telegram_user.full_name
        ),
            "language_code": (
                telegram_user.language_code
            ),
            "is_premium": bool(
                telegram_user.is_premium
            ),
            "role": self.default_user_role(),
            "status": (
                self.default_user_status()
            ),
            "is_blocked": False,
            "last_seen_at": (
                datetime.now(UTC)
            ),
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        filtered_payload = {
            key: value
            for key, value in payload.items()
            if (
                key in available_columns
                and value is not None
            )
        }

        return User(
            **filtered_payload
        )

    # ==========================================
    # РћРќРћР’Р›Р•РќРќРЇ РџР РћР¤Р†Р›Р®
    # ==========================================

    def update_user_profile(
        self,
        *,
        user: User,
        telegram_user: TelegramUser,
    ) -> bool:
        """
        РћРЅРѕРІР»СЋС” Р·РјС–РЅРµРЅС– РїРѕР»СЏ Telegram-РїСЂРѕС„С–Р»СЋ.
        """

        changed = False

        field_values = {
            "telegram_username": (
                telegram_user.username
            ),
            "username": telegram_user.username,
            "first_name": (
                telegram_user.first_name
            ),
            "last_name": (
                telegram_user.last_name
            ),

        "full_name": (
            telegram_user.full_name
        ),
            "language_code": (
                telegram_user.language_code
            ),
            "is_premium": bool(
                telegram_user.is_premium
            ),
        }

        for field_name, value in (
            field_values.items()
        ):
            if not hasattr(
                user,
                field_name,
            ):
                continue

            current_value = getattr(
                user,
                field_name,
                None,
            )

            if current_value == value:
                continue

            setattr(
                user,
                field_name,
                value,
            )

            changed = True

        if (
            changed
            and hasattr(user, "updated_at")
        ):
            user.updated_at = datetime.now(
                UTC
            )

        return changed

    @staticmethod
    def update_last_seen(
        user: User,
    ) -> None:
        """РћРЅРѕРІР»СЋС” РґР°С‚Сѓ РѕСЃС‚Р°РЅРЅСЊРѕС— Р°РєС‚РёРІРЅРѕСЃС‚С–."""

        now = datetime.now(UTC)

        for field_name in (
            "last_seen_at",
            "last_activity_at",
            "telegram_last_seen_at",
        ):
            if hasattr(user, field_name):
                setattr(
                    user,
                    field_name,
                    now,
                )

                break

    # ==========================================
    # Р Р•Р—РЈР›Р¬РўРђРў Р Р•РџРћР—РРўРћР Р†Р®
    # ==========================================

    @staticmethod
    def parse_repository_result(
        result: Any,
    ) -> UserResolutionResult | None:
        """
        Р РѕР·Р±РёСЂР°С” СЂС–Р·РЅС– С„РѕСЂРјР°С‚Рё СЂРµР·СѓР»СЊС‚Р°С‚С–РІ.
        """

        if isinstance(result, User):
            return UserResolutionResult(
                user=result,
                was_created=False,
                profile_was_updated=False,
            )

        if (
            isinstance(result, tuple)
            and result
            and isinstance(result[0], User)
        ):
            user = result[0]

            was_created = bool(
                result[1]
            ) if len(result) > 1 else False

            profile_was_updated = bool(
                result[2]
            ) if len(result) > 2 else False

            return UserResolutionResult(
                user=user,
                was_created=was_created,
                profile_was_updated=(
                    profile_was_updated
                ),
            )

        user = getattr(
            result,
            "user",
            None,
        )

        if isinstance(user, User):
            return UserResolutionResult(
                user=user,
                was_created=bool(
                    getattr(
                        result,
                        "was_created",
                        getattr(
                            result,
                            "created",
                            False,
                        ),
                    )
                ),
                profile_was_updated=bool(
                    getattr(
                        result,
                        "profile_was_updated",
                        getattr(
                            result,
                            "was_updated",
                            False,
                        ),
                    )
                ),
            )

        return None

    # ==========================================
    # РќРђР›РђРЁРўРЈР’РђРќРќРЇ РЎРРЎРўР•РњР
    # ==========================================

    async def is_bot_enabled(
        self,
        repositories: Repositories,
    ) -> bool:
        """Р§Рё СѓРІС–РјРєРЅРµРЅРёР№ Р±РѕС‚."""

        settings = repositories.settings

        method = getattr(
            settings,
            "is_bot_enabled",
            None,
        )

        if callable(method):
            result = method()

            if inspect.isawaitable(result):
                result = await result

            return bool(result)

        key = getattr(
            settings,
            "BOT_ENABLED",
            "bot_enabled",
        )

        return await settings.get_bool(
            key,
            default=True,
        )

    async def is_maintenance_mode(
        self,
        repositories: Repositories,
    ) -> bool:
        """Р§Рё СѓРІС–РјРєРЅРµРЅРёР№ С‚РµС…РЅС–С‡РЅРёР№ СЂРµР¶РёРј."""

        settings = repositories.settings

        method = getattr(
            settings,
            "is_maintenance_mode",
            None,
        )

        if callable(method):
            result = method()

            if inspect.isawaitable(result):
                result = await result

            return bool(result)

        key = getattr(
            settings,
            "MAINTENANCE_MODE",
            "maintenance_mode",
        )

        return await settings.get_bool(
            key,
            default=False,
        )

    async def get_maintenance_message(
        self,
        repositories: Repositories,
    ) -> str | None:
        """
        РџРѕРІРµСЂС‚Р°С” РЅР°Р»Р°С€С‚РѕРІР°РЅРёР№ С‚РµРєСЃС‚
        С‚РµС…РЅС–С‡РЅРѕРіРѕ СЂРµР¶РёРјСѓ.
        """

        settings = repositories.settings

        method = getattr(
            settings,
            "get_maintenance_message",
            None,
        )

        if callable(method):
            result = method()

            if inspect.isawaitable(result):
                result = await result

            normalized = str(
                result or ""
            ).strip()

            return normalized or None

        key = getattr(
            settings,
            "MAINTENANCE_MESSAGE",
            "maintenance_message",
        )

        get_string = getattr(
            settings,
            "get_string",
            None,
        )

        if callable(get_string):
            result = get_string(
                key,
                default=None,
            )

            if inspect.isawaitable(result):
                result = await result

            normalized = str(
                result or ""
            ).strip()

            return normalized or None

        return None

    # ==========================================
    # РЎРўРђРўРЈРЎ РљРћР РРЎРўРЈР’РђР§Рђ
    # ==========================================

    @staticmethod
    def is_root_admin(
        user: User,
    ) -> bool:
        """Р§Рё С” РєРѕСЂРёСЃС‚СѓРІР°С‡ ROOT_ADMIN."""

        role = getattr(
            user,
            "role",
            None,
        )

        if role is None:
            return False

        values = {
            str(
                getattr(
                    role,
                    "name",
                    role,
                )
            ).lower(),
            str(
                getattr(
                    role,
                    "value",
                    role,
                )
            ).lower(),
        }

        return bool(
            values.intersection(
                {
                    "root_admin",
                    "root",
                    "superadmin",
                    "super_admin",
                }
            )
        )

    @staticmethod
    def is_blocked_user(
        user: User,
    ) -> bool:
        """Р§Рё Р·Р°Р±Р»РѕРєРѕРІР°РЅРёР№ РєРѕСЂРёСЃС‚СѓРІР°С‡."""

        if bool(
            getattr(
                user,
                "is_blocked",
                False,
            )
        ):
            return True

        status_values = (
            AuthMiddleware
            .user_status_values(user)
        )

        return bool(
            status_values.intersection(
                {
                    "blocked",
                    "banned",
                    "ban",
                }
            )
        )

    @staticmethod
    def is_inactive_user(
        user: User,
    ) -> bool:
        """Р§Рё РґРµР°РєС‚РёРІРѕРІР°РЅРёР№ РєРѕСЂРёСЃС‚СѓРІР°С‡."""

        status_values = (
            AuthMiddleware
            .user_status_values(user)
        )

        return bool(
            status_values.intersection(
                {
                    "inactive",
                    "deactivated",
                    "disabled",
                }
            )
        )

    @staticmethod
    def user_status_values(
        user: User,
    ) -> set[str]:
        """РџРѕРІРµСЂС‚Р°С” РЅР°Р·РІСѓ С– Р·РЅР°С‡РµРЅРЅСЏ СЃС‚Р°С‚СѓСЃСѓ."""

        status = getattr(
            user,
            "status",
            None,
        )

        if status is None:
            return set()

        return {
            str(
                getattr(
                    status,
                    "name",
                    status,
                )
            ).lower(),
            str(
                getattr(
                    status,
                    "value",
                    status,
                )
            ).lower(),
        }

    # ==========================================
    # РЎРўРђРќР”РђР РўРќРђ Р РћР›Р¬ Р† РЎРўРђРўРЈРЎ
    # ==========================================

    @staticmethod
    def default_user_role(
    ) -> UserRole | None:
        """РЎС‚Р°РЅРґР°СЂС‚РЅР° СЂРѕР»СЊ РЅРѕРІРѕРіРѕ РєРѕСЂРёСЃС‚СѓРІР°С‡Р°."""

        return AuthMiddleware.resolve_enum_member(
            UserRole,
            "store_user",
            "store",
            "employee",
            default=None,
        )

    @staticmethod
    def default_user_status(
    ) -> UserStatus | None:
        """
        РЎС‚Р°РЅРґР°СЂС‚РЅРёР№ СЃС‚Р°С‚СѓСЃ РЅРѕРІРѕРіРѕ РєРѕСЂРёСЃС‚СѓРІР°С‡Р°.

        РЎРїРѕС‡Р°С‚РєСѓ С€СѓРєР°С”РјРѕ PENDING.
        РЇРєС‰Рѕ Р№РѕРіРѕ РЅРµРјР°С” вЂ” ACTIVE.
        """

        pending = (
            AuthMiddleware.resolve_enum_member(
                UserStatus,
                "pending",
                "waiting_approval",
                "unverified",
                default=None,
            )
        )

        if pending is not None:
            return pending

        return AuthMiddleware.resolve_enum_member(
            UserStatus,
            "active",
            "enabled",
            default=None,
        )

    @staticmethod
    def resolve_enum_member(
        enum_class: type[Any],
        *names: str,
        default: Any = None,
    ) -> Any:
        """РЁСѓРєР°С” enum Р·Р° РЅР°Р·РІРѕСЋ Р°Р±Рѕ Р·РЅР°С‡РµРЅРЅСЏРј."""

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

        return default

    # ==========================================
    # Р’Р†Р”РџРћР’Р†Р”Р¬ РџР Рћ РћР‘РњР•Р–Р•РќРќРЇ
    # ==========================================

    async def answer_restriction(
        self,
        *,
        event: TelegramObject,
        text: str,
    ) -> None:
        """
        Р’С–РґРїРѕРІС–РґР°С” РєРѕСЂРёСЃС‚СѓРІР°С‡Сѓ Р±РµР· Р·Р°РїСѓСЃРєСѓ handler.
        """

        if isinstance(event, CallbackQuery):
            try:
                await event.answer(
                    "Р”РѕСЃС‚СѓРї С‚РёРјС‡Р°СЃРѕРІРѕ РѕР±РјРµР¶РµРЅРѕ",
                    show_alert=True,
                )
            except Exception:
                pass

            if isinstance(
                event.message,
                Message,
            ):
                try:
                    await event.message.answer(
                        text,
                    )
                except Exception:
                    pass

            return

        if isinstance(event, Message):
            try:
                await event.answer(
                    text,
                )
            except Exception:
                pass

    # ==========================================
    # TELEGRAM USER
    # ==========================================

    @staticmethod
    def resolve_telegram_user(
        *,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> TelegramUser | None:
        """
        Р’РёР·РЅР°С‡Р°С” Р°РІС‚РѕСЂР° Telegram update.
        """

        event_from_user = data.get(
            "event_from_user"
        )

        if isinstance(
            event_from_user,
            TelegramUser,
        ):
            return event_from_user

        from_user = getattr(
            event,
            "from_user",
            None,
        )

        if isinstance(
            from_user,
            TelegramUser,
        ):
            return from_user

        return None

    # ==========================================
    # REPOSITORIES
    # ==========================================

    @staticmethod
    def get_repositories(
        data: dict[str, Any],
    ) -> Repositories:
        """
        РћС‚СЂРёРјСѓС” Repositories С–Р· DatabaseMiddleware.
        """

        repositories = data.get(
            "repositories"
        )

        if not isinstance(
            repositories,
            Repositories,
        ):
            raise RuntimeError(
                "AuthMiddleware РїРѕРІРёРЅРµРЅ РїСЂР°С†СЋРІР°С‚Рё "
                "РїС–СЃР»СЏ DatabaseMiddleware. "
                "РЈ aiogram data РІС–РґСЃСѓС‚РЅС–Р№ Repositories."
            )

        return repositories

    # ==========================================
    # INTROSPECTION
    # ==========================================

    @staticmethod
    def filter_method_kwargs(
        method: Callable[..., Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        РџСЂРёР±РёСЂР°С” Р°СЂРіСѓРјРµРЅС‚Рё, СЏРєРёС… РЅРµРјР°С”
        Сѓ СЃРёРіРЅР°С‚СѓСЂС– РјРµС‚РѕРґСѓ.
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
            return dict(payload)

        return {
            key: value
            for key, value in payload.items()
            if key in signature.parameters
        }


AuthenticationMiddleware = AuthMiddleware


__all__ = [
    "AuthMiddleware",
    "AuthenticationMiddleware",
    "AuthMiddlewareContext",
    "AuthState",
    "UserResolutionResult",
]
