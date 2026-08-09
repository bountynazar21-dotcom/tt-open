from __future__ import annotations

import inspect
import logging
from typing import Any

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from app.states.registration import RegistrationStates
from aiogram.types import (
    CallbackQuery,
    Message,
)

from app.database.models.user import User as DatabaseUser
from app.keyboards.invites import invite_activation_error_keyboard
from app.keyboards.registration import (
    RegistrationAction,
    RegistrationCallback,
    blocked_registration_keyboard,
    contact_request_keyboard,
    contact_retry_keyboard,
    inactive_registration_keyboard,
    invite_activated_keyboard,
    pending_registration_keyboard,
    registration_cancel_keyboard,
    registration_completed_keyboard,
    registration_help_keyboard,
    registration_refresh_keyboard,
    registration_start_keyboard,
    rejected_registration_keyboard,
    remove_registration_reply_keyboard,
)
from app.handlers.common import (
    build_help_text,
    get_database_user,
    safe_edit,
    show_home_message,
    user_status_name,
)


logger = logging.getLogger(
    __name__
)


# =========================================================
# ROUTER
# =========================================================


router = Router(
    name="registration",
)


# =========================================================
# STATUS GROUPS
# =========================================================


ACTIVE_STATUSES = {
    "ACTIVE",
    "APPROVED",
}

PENDING_STATUSES = {
    "PENDING",
    "NEW",
    "WAITING",
    "WAITING_APPROVAL",
}

BLOCKED_STATUSES = {
    "BLOCKED",
    "BANNED",
}

INACTIVE_STATUSES = {
    "INACTIVE",
    "DISABLED",
}

REJECTED_STATUSES = {
    "REJECTED",
    "DECLINED",
}


# =========================================================
# START ARGUMENT
# =========================================================


def extract_start_argument(
    message: Message,
) -> str | None:
    """
    Витягує аргумент:

        /start abc123

    -> abc123
    """

    text = (
        message.text
        or ""
    ).strip()

    if not text:
        return None

    parts = text.split(
        maxsplit=1
    )

    if len(parts) < 2:
        return None

    argument = (
        parts[1]
        .strip()
    )

    return (
        argument
        or None
    )


def normalize_invite_token(
    argument: str | None,
) -> str | None:
    """
    Нормалізує deep-link token.

    Підтримує:

        invite_xxx
        invite-xxx
        inv_xxx
        token_xxx
        xxx

    Сам InviteService може очікувати
    або весь аргумент, або сам token,
    тому зберігаємо максимально
    нормалізоване значення.
    """

    if not argument:
        return None

    value = (
        argument
        .strip()
    )

    prefixes = (
        "invite_",
        "invite-",
        "inv_",
        "inv-",
        "token_",
        "token-",
    )

    lower_value = (
        value.lower()
    )

    for prefix in prefixes:
        if lower_value.startswith(
            prefix
        ):
            candidate = value[
                len(prefix):
            ].strip()

            return (
                candidate
                or value
            )

    return value


# =========================================================
# GENERIC CALL
# =========================================================


def filter_kwargs(
    method: Any,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Передає методу тільки ті kwargs,
    які є в його сигнатурі.
    """

    try:
        signature = inspect.signature(
            method
        )

    except (
        TypeError,
        ValueError,
    ):
        return dict(
            payload
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
        if key
        in signature.parameters
    }


async def call_method(
    method: Any,
    payload: dict[str, Any],
) -> Any:
    """
    Викликає sync/async method.
    """

    kwargs = filter_kwargs(
        method,
        payload,
    )

    result = method(
        **kwargs
    )

    if inspect.isawaitable(
        result
    ):
        result = await result

    return result


# =========================================================
# DATABASE USER RESOLUTION
# =========================================================


async def resolve_database_user(
    *,
    telegram_id: int,
    data: dict[str, Any],
) -> DatabaseUser | None:
    """
    Спочатку беремо користувача
    з AuthMiddleware.

    Якщо його немає — пробуємо
    знайти через UserRepository.
    """

    user = get_database_user(
        data
    )

    if user is not None:
        return user

    repositories = data.get(
        "repositories"
    )

    if repositories is None:
        return None

    users_repository = getattr(
        repositories,
        "users",
        None,
    )

    if users_repository is None:
        return None

    for method_name in (
        "get_by_telegram_id",
        "find_by_telegram_id",
        "get_user_by_telegram_id",
        "find_user_by_telegram_id",
    ):
        method = getattr(
            users_repository,
            method_name,
            None,
        )

        if not callable(
            method
        ):
            continue

        try:
            result = await call_method(
                method,
                {
                    "telegram_id":
                        telegram_id,
                },
            )

        except Exception:
            logger.exception(
                "Failed resolving user "
                "by telegram_id=%s",
                telegram_id,
            )

            continue

        if isinstance(
            result,
            DatabaseUser,
        ):
            return result

    return None


# =========================================================
# USER PHONE
# =========================================================


def user_phone(
    user: DatabaseUser,
) -> str | None:
    """
    Номер телефону користувача.
    """

    for field_name in (
        "phone",
        "phone_number",
        "telephone",
    ):
        value = getattr(
            user,
            field_name,
            None,
        )

        if value:
            return str(
                value
            )

    return None


def set_user_phone(
    user: DatabaseUser,
    phone: str,
) -> bool:
    """
    Записує телефон у доступне поле User.
    """

    normalized = (
        phone.strip()
    )

    if not normalized:
        return False

    for field_name in (
        "phone",
        "phone_number",
        "telephone",
    ):
        if hasattr(
            user,
            field_name,
        ):
            setattr(
                user,
                field_name,
                normalized,
            )

            return True

    return False


# =========================================================
# FLUSH
# =========================================================


async def flush_changes(
    data: dict[str, Any],
) -> None:
    """
    Flush поточної транзакції.

    Commit робить DatabaseMiddleware.
    """

    repositories = data.get(
        "repositories"
    )

    if repositories is not None:
        method = getattr(
            repositories,
            "flush",
            None,
        )

        if callable(
            method
        ):
            result = method()

            if inspect.isawaitable(
                result
            ):
                await result

            return

    session = (
        data.get("session")
        or data.get("db_session")
    )

    if session is not None:
        flush = getattr(
            session,
            "flush",
            None,
        )

        if callable(
            flush
        ):
            result = flush()

            if inspect.isawaitable(
                result
            ):
                await result


# =========================================================
# INVITE SERVICE
# =========================================================


def get_invite_service(
    data: dict[str, Any],
) -> Any | None:
    """
    Дістає InviteService
    з Services container.
    """

    services = data.get(
        "services"
    )

    if services is None:
        return None

    try:
        return services.invites

    except Exception:
        return getattr(
            services,
            "invite",
            None,
        )


# =========================================================
# INVITE RESULT HELPERS
# =========================================================


def result_bool(
    result: Any,
    *field_names: str,
) -> bool | None:
    """
    Витягує bool із result.
    """

    if isinstance(
        result,
        bool,
    ):
        return result

    if result is None:
        return None

    for field_name in field_names:
        value = getattr(
            result,
            field_name,
            None,
        )

        if isinstance(
            value,
            bool,
        ):
            return value

    return None


def result_text(
    result: Any,
    *field_names: str,
) -> str | None:
    """
    Витягує текст причини/повідомлення.
    """

    if result is None:
        return None

    for field_name in field_names:
        value = getattr(
            result,
            field_name,
            None,
        )

        if value:
            return str(
                value
            )

    return None


# =========================================================
# ACTIVATE INVITE
# =========================================================


async def activate_invite(
    *,
    token: str,
    user: DatabaseUser,
    message: Message,
    data: dict[str, Any],
) -> tuple[
    bool,
    str | None,
]:
    """
    Активація invite.

    Підтримує кілька можливих назв
    методу InviteService.
    """

    service = get_invite_service(
        data
    )

    if service is None:
        return (
            False,
            "InviteService недоступний.",
        )

    telegram_user = (
        message.from_user
    )

    payload = {
        "token_or_payload": token,
        "token": token,
        "invite_token": token,
        "code": token,
        "raw_token": token,

        "user": user,
        "db_user": user,
        "database_user": user,

        "user_id": getattr(
            user,
            "id",
            None,
        ),

        "telegram_id": (
            telegram_user.id
            if telegram_user
            else getattr(
                user,
                "telegram_id",
                None,
            )
        ),

        "telegram_user":
            telegram_user,

        "telegram_username": (
            telegram_user.username
            if telegram_user
            else None
        ),

        "username": (
            telegram_user.username
            if telegram_user
            else None
        ),

        "first_name": (
            telegram_user.first_name
            if telegram_user
            else None
        ),

        "last_name": (
            telegram_user.last_name
            if telegram_user
            else None
        ),

        "full_name": (
            telegram_user.full_name
            if telegram_user
            else getattr(
                user,
                "full_name",
                None,
            )
        ),

        "language_code": (
            telegram_user.language_code
            if telegram_user
            else None
        ),

        "telegram_chat_id": (
            message.chat.id
            if message.chat
            else None
        ),

        "chat_id": (
            message.chat.id
            if message.chat
            else None
        ),

        "telegram_message_id":
            message.message_id,

        "message_id":
            message.message_id,
    }

    last_error: Exception | None = None

    for method_name in (
        "activate_invite",
        "activate",
        "activate_token",
        "use_invite",
        "consume_invite",
        "accept_invite",
    ):
        method = getattr(
            service,
            method_name,
            None,
        )

        if not callable(
            method
        ):
            continue

        try:
            result = await call_method(
                method,
                payload,
            )

        except (
            TypeError,
            ValueError,
            LookupError,
        ) as error:
            last_error = error

            logger.warning(
                "Invite activation method rejected | "
                "method=%s user_id=%s error=%s",
                method_name,
                getattr(
                    user,
                    "id",
                    None,
                ),
                error,
            )

            continue

        except Exception as error:
            logger.exception(
                "Invite activation failed | "
                "method=%s user_id=%s",
                method_name,
                getattr(
                    user,
                    "id",
                    None,
                ),
            )

            last_error = error

            continue

        success = result_bool(
            result,
            "success",
            "activated",
            "accepted",
            "consumed",
            "used",
            "is_success",
        )

        if success is None:
            success = (
                result is not None
            )

        reason = result_text(
            result,
            "message",
            "reason",
            "error",
            "detail",
            "description",
        )

        if success:
            await flush_changes(
                data
            )

            logger.info(
                "Invite activated | "
                "user_id=%s method=%s",
                getattr(
                    user,
                    "id",
                    None,
                ),
                method_name,
            )

            return (
                True,
                reason,
            )

        return (
            False,
            reason
            or "Запрошення не вдалося активувати.",
        )

    if last_error is not None:
        logger.warning(
            "Invite activation unavailable | "
            "user_id=%s error_type=%s",
            getattr(
                user,
                "id",
                None,
            ),
            type(
                last_error
            ).__name__,
        )

        return (
            False,
            str(
                last_error
            ),
        )

    return (
        False,
        "Метод активації invite не знайдено.",
    )


# =========================================================
# STATUS UI
# =========================================================


async def send_status_message(
    message: Message,
    *,
    user: DatabaseUser,
) -> None:
    """
    Показує поточний стан користувача.
    """

    status = user_status_name(
        user
    )

    # -----------------------------------------------------
    # ACTIVE
    # -----------------------------------------------------

    if status in ACTIVE_STATUSES:
        await message.answer(
            "✅ <b>Ваш доступ активний.</b>\n\n"
            "Можете переходити до роботи.",
            reply_markup=(
                registration_completed_keyboard()
            ),
        )

        return

    # -----------------------------------------------------
    # PENDING
    # -----------------------------------------------------

    if status in PENDING_STATUSES:
        await message.answer(
            "⏳ <b>Заявка надіслана.</b>\n\n"
            "Очікуйте підтвердження "
            "адміністратором.\n\n"
            "Коли доступ буде відкрито, "
            "натисніть «Перевірити статус».",
            reply_markup=(
                pending_registration_keyboard()
            ),
        )

        return

    # -----------------------------------------------------
    # BLOCKED
    # -----------------------------------------------------

    if status in BLOCKED_STATUSES:
        await message.answer(
            "⛔ <b>Ваш обліковий запис "
            "заблокований.</b>\n\n"
            "Якщо це помилка, зверніться "
            "до адміністратора.",
            reply_markup=(
                blocked_registration_keyboard()
            ),
        )

        return

    # -----------------------------------------------------
    # INACTIVE
    # -----------------------------------------------------

    if status in INACTIVE_STATUSES:
        await message.answer(
            "⚫ <b>Ваш доступ наразі "
            "неактивний.</b>",
            reply_markup=(
                inactive_registration_keyboard()
            ),
        )

        return

    # -----------------------------------------------------
    # REJECTED
    # -----------------------------------------------------

    if status in REJECTED_STATUSES:
        await message.answer(
            "❌ <b>Заявку було відхилено.</b>\n\n"
            "За потреби можете спробувати "
            "зареєструватися повторно.",
            reply_markup=(
                rejected_registration_keyboard()
            ),
        )

        return

    # -----------------------------------------------------
    # UNKNOWN
    # -----------------------------------------------------

    await message.answer(
        "📝 Для початку роботи "
        "потрібно завершити реєстрацію.",
        reply_markup=(
            registration_start_keyboard()
        ),
    )


async def edit_status_message(
    callback: CallbackQuery,
    *,
    user: DatabaseUser,
) -> None:
    """
    Те саме, але через callback.
    """

    status = user_status_name(
        user
    )

    if status in ACTIVE_STATUSES:
        await safe_edit(
            callback,
            text=(
                "✅ <b>Доступ активовано.</b>\n\n"
                "Можете переходити "
                "до головного меню."
            ),
            reply_markup=(
                registration_completed_keyboard()
            ),
        )

        return

    if status in PENDING_STATUSES:
        await safe_edit(
            callback,
            text=(
                "⏳ <b>Заявка ще очікує "
                "підтвердження.</b>\n\n"
                "Спробуйте перевірити "
                "статус пізніше."
            ),
            reply_markup=(
                pending_registration_keyboard()
            ),
        )

        return

    if status in BLOCKED_STATUSES:
        await safe_edit(
            callback,
            text=(
                "⛔ <b>Ваш обліковий запис "
                "заблокований.</b>"
            ),
            reply_markup=(
                blocked_registration_keyboard()
            ),
        )

        return

    if status in INACTIVE_STATUSES:
        await safe_edit(
            callback,
            text=(
                "⚫ <b>Ваш доступ "
                "неактивний.</b>"
            ),
            reply_markup=(
                inactive_registration_keyboard()
            ),
        )

        return

    if status in REJECTED_STATUSES:
        await safe_edit(
            callback,
            text=(
                "❌ <b>Заявку було "
                "відхилено.</b>"
            ),
            reply_markup=(
                rejected_registration_keyboard()
            ),
        )

        return

    await safe_edit(
        callback,
        text=(
            "📝 Реєстрацію ще "
            "не завершено."
        ),
        reply_markup=(
            registration_start_keyboard()
        ),
    )


# =========================================================
# BEGIN CONTACT REGISTRATION
# =========================================================


async def begin_contact_registration(
    *,
    message: Message,
    state: FSMContext,
) -> None:
    """
    Починає збір телефону.
    """

    await state.set_state(
        RegistrationStates
        .waiting_contact
    )

    await message.answer(
        "📱 <b>Підтвердьте ваш номер "
        "телефону.</b>\n\n"
        "Натисніть кнопку нижче "
        "«Надіслати мій номер».\n\n"
        "Важливо: потрібно надіслати "
        "саме свій Telegram-контакт.",
        reply_markup=(
            contact_request_keyboard()
        ),
    )


# =========================================================
# /START
# =========================================================


@router.message(
    CommandStart()
)
async def start_handler(
    message: Message,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    /start

    Також обробляє:

        /start <invite_token>
    """

    await state.clear()

    telegram_user = (
        message.from_user
    )

    if telegram_user is None:
        return

    user = await resolve_database_user(
        telegram_id=telegram_user.id,
        data=data,
    )

    # AuthMiddleware повинен створювати
    # нового користувача автоматично.
    if user is None:
        await message.answer(
            "⚠️ Не вдалося створити "
            "обліковий запис.\n\n"
            "Спробуйте /start ще раз."
        )

        return

    # -----------------------------------------------------
    # INVITE DEEP LINK
    # -----------------------------------------------------

    argument = extract_start_argument(
        message
    )

    invite_token = normalize_invite_token(
        argument
    )

    if invite_token:
        success, reason = (
            await activate_invite(
                token=invite_token,
                user=user,
                message=message,
                data=data,
            )
        )

        if success:
            await state.clear()

            await message.answer(
                "✅ <b>Запрошення "
                "активовано.</b>\n\n"
                "Доступ успішно надано.",
                reply_markup=(
                    invite_activated_keyboard()
                ),
            )

            return

        logger.warning(
            "Invite activation rejected | "
            "user_id=%s reason=%s",
            getattr(
                user,
                "id",
                None,
            ),
            reason,
        )

        await message.answer(
            "❌ <b>Не вдалося активувати "
            "запрошення.</b>\n\n"
            "Посилання могло бути "
            "прострочене, використане "
            "або відкликане.",
            reply_markup=(
                invite_activation_error_keyboard()
            ),
        )

        return

    # -----------------------------------------------------
    # ACTIVE USER
    # -----------------------------------------------------

    status = user_status_name(
        user
    )

    if status in ACTIVE_STATUSES:
        await show_home_message(
            message,
            user=user,
            data=data,
        )

        return

    # -----------------------------------------------------
    # USER ALREADY HAS PHONE
    # -----------------------------------------------------

    if user_phone(
        user
    ):
        await send_status_message(
            message,
            user=user,
        )

        return

    # -----------------------------------------------------
    # NEW REGISTRATION
    # -----------------------------------------------------

    await message.answer(
        "👋 <b>Вітаємо!</b>\n\n"
        "Для роботи з ботом потрібно "
        "пройти коротку реєстрацію.",
        reply_markup=(
            registration_start_keyboard()
        ),
    )


# =========================================================
# START REGISTRATION CALLBACK
# =========================================================


@router.callback_query(
    RegistrationCallback.filter(
        F.action
        == RegistrationAction.START
    )
)
async def registration_start_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """
    Кнопка Почати реєстрацію.
    """

    await callback.answer()

    if callback.message is None:
        return

    await begin_contact_registration(
        message=callback.message,
        state=state,
    )


# =========================================================
# RECEIVE CONTACT
# =========================================================


@router.message(
    RegistrationStates.waiting_contact,
    F.contact,
)
async def registration_contact_handler(
    message: Message,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Отримує Telegram contact.
    """

    telegram_user = (
        message.from_user
    )

    contact = (
        message.contact
    )

    if (
        telegram_user is None
        or contact is None
    ):
        return

    # -----------------------------------------------------
    # SECURITY CHECK
    # -----------------------------------------------------

    if (
        contact.user_id is not None
        and contact.user_id
        != telegram_user.id
    ):
        await message.answer(
            "⚠️ Потрібно надіслати "
            "<b>саме свій номер</b> "
            "через кнопку нижче.",
            reply_markup=(
                contact_retry_keyboard()
            ),
        )

        return

    user = await resolve_database_user(
        telegram_id=telegram_user.id,
        data=data,
    )

    if user is None:
        await message.answer(
            "⚠️ Не вдалося знайти "
            "ваш обліковий запис.",
            reply_markup=(
                remove_registration_reply_keyboard()
            ),
        )

        await state.clear()

        return

    phone_number = (
        contact.phone_number
        .strip()
    )

    if not phone_number:
        await message.answer(
            "⚠️ Telegram не передав "
            "номер телефону.\n\n"
            "Спробуйте ще раз.",
            reply_markup=(
                contact_retry_keyboard()
            ),
        )

        return

    if not set_user_phone(
        user,
        phone_number,
    ):
        logger.error(
            "User model has no phone field: "
            "user_id=%s",
            getattr(
                user,
                "id",
                None,
            ),
        )

        await message.answer(
            "⚠️ Не вдалося зберегти "
            "номер телефону.\n\n"
            "Повідомте адміністратора.",
            reply_markup=(
                remove_registration_reply_keyboard()
            ),
        )

        await state.clear()

        return

    # -----------------------------------------------------
    # SYNC TELEGRAM PROFILE
    # -----------------------------------------------------

    for field_name, value in (
        (
            "username",
            telegram_user.username,
        ),
        (
            "first_name",
            telegram_user.first_name,
        ),
        (
            "last_name",
            telegram_user.last_name,
        ),
    ):
        if (
            value is not None
            and hasattr(
                user,
                field_name,
            )
        ):
            setattr(
                user,
                field_name,
                value,
            )

    await flush_changes(
        data
    )

    await state.clear()

    # -----------------------------------------------------
    # REMOVE REPLY KEYBOARD
    # -----------------------------------------------------

    await message.answer(
        "✅ Номер телефону збережено.",
        reply_markup=(
            remove_registration_reply_keyboard()
        ),
    )

    # -----------------------------------------------------
    # CURRENT STATUS
    # -----------------------------------------------------

    await send_status_message(
        message,
        user=user,
    )


# =========================================================
# WRONG INPUT WHILE WAITING CONTACT
# =========================================================


@router.message(
    RegistrationStates.waiting_contact,
)
async def registration_wrong_contact(
    message: Message,
) -> None:
    """
    Якщо замість Telegram contact
    користувач написав номер текстом.
    """

    await message.answer(
        "📱 Будь ласка, не вводьте "
        "номер вручну.\n\n"
        "Натисніть кнопку "
        "<b>«Надіслати мій номер»</b>.",
        reply_markup=(
            contact_retry_keyboard()
        ),
    )


# =========================================================
# REFRESH STATUS
# =========================================================


@router.callback_query(
    RegistrationCallback.filter(
        F.action
        == RegistrationAction.REFRESH
    )
)
async def registration_refresh_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    Повторна перевірка статусу.
    """

    await callback.answer(
        "Перевіряю статус…"
    )

    telegram_user = (
        callback.from_user
    )

    user = await resolve_database_user(
        telegram_id=telegram_user.id,
        data=data,
    )

    if user is None:
        await safe_edit(
            callback,
            text=(
                "⚠️ Обліковий запис "
                "не знайдено.\n\n"
                "Використайте /start."
            ),
            reply_markup=(
                registration_refresh_keyboard()
            ),
        )

        return

    await edit_status_message(
        callback,
        user=user,
    )


# =========================================================
# STATUS CALLBACK
# =========================================================


@router.callback_query(
    RegistrationCallback.filter(
        F.action
        == RegistrationAction.STATUS
    )
)
async def registration_status_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    Показ поточного статусу.
    """

    await callback.answer()

    user = await resolve_database_user(
        telegram_id=callback.from_user.id,
        data=data,
    )

    if user is None:
        return

    await edit_status_message(
        callback,
        user=user,
    )


# =========================================================
# RETRY
# =========================================================


@router.callback_query(
    RegistrationCallback.filter(
        F.action
        == RegistrationAction.RETRY
    )
)
async def registration_retry_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """
    Повторна реєстрація.
    """

    await callback.answer()

    if callback.message is None:
        return

    await state.clear()

    await begin_contact_registration(
        message=callback.message,
        state=state,
    )


# =========================================================
# CANCEL
# =========================================================


@router.callback_query(
    RegistrationCallback.filter(
        F.action
        == RegistrationAction.CANCEL
    )
)
async def registration_cancel_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """
    Скасування реєстрації.
    """

    await callback.answer(
        "Реєстрацію скасовано."
    )

    await state.clear()

    if callback.message is None:
        return

    await callback.message.answer(
        "❌ Реєстрацію скасовано.",
        reply_markup=(
            remove_registration_reply_keyboard()
        ),
    )

    await safe_edit(
        callback,
        text=(
            "Реєстрацію скасовано.\n\n"
            "Ви можете почати її "
            "знову будь-коли."
        ),
        reply_markup=(
            registration_start_keyboard()
        ),
    )


# =========================================================
# HELP
# =========================================================


@router.callback_query(
    RegistrationCallback.filter(
        F.action
        == RegistrationAction.HELP
    )
)
async def registration_help_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    Допомога під час реєстрації.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    text = (
        "ℹ️ <b>Реєстрація в боті</b>\n\n"
        "1. Натисніть "
        "«Почати реєстрацію».\n"
        "2. Надішліть свій номер "
        "через Telegram-кнопку.\n"
        "3. Заявка потрапить "
        "адміністратору.\n"
        "4. Після підтвердження "
        "натисніть "
        "«Перевірити статус».\n\n"
        "Якщо ви отримали спеціальне "
        "invite-посилання — відкрийте "
        "бота саме через нього."
    )

    if user is not None:
        status = user_status_name(
            user
        )

        if status:
            text += (
                "\n\nВаш поточний статус: "
                f"<b>{status}</b>"
            )

    await safe_edit(
        callback,
        text=text,
        reply_markup=(
            registration_help_keyboard()
        ),
    )


# =========================================================
# HOME FROM REGISTRATION
# =========================================================


@router.callback_query(
    RegistrationCallback.filter(
        F.action
        == RegistrationAction.HOME
    )
)
async def registration_home_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    Перехід у головне меню,
    якщо доступ уже активний.
    """

    await callback.answer()

    user = await resolve_database_user(
        telegram_id=callback.from_user.id,
        data=data,
    )

    if user is None:
        return

    status = user_status_name(
        user
    )

    if status not in ACTIVE_STATUSES:
        await edit_status_message(
            callback,
            user=user,
        )

        return

    if callback.message is None:
        return

    # Даємо нове повідомлення,
    # щоб не залежати від типу
    # попереднього registration message.
    await show_home_message(
        callback.message,
        user=user,
        data=data,
    )


# =========================================================
# FALLBACK REGISTRATION CALLBACK
# =========================================================


@router.callback_query(
    RegistrationCallback.filter()
)
async def unknown_registration_callback(
    callback: CallbackQuery,
) -> None:
    """
    Захист від старих callback
    після оновлення бота.
    """

    await callback.answer(
        "Ця кнопка вже неактуальна. "
        "Використайте /start.",
        show_alert=False,
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "router",

    "RegistrationStates",

    "ACTIVE_STATUSES",
    "PENDING_STATUSES",
    "BLOCKED_STATUSES",
    "INACTIVE_STATUSES",
    "REJECTED_STATUSES",

    "extract_start_argument",
    "normalize_invite_token",

    "filter_kwargs",
    "call_method",

    "resolve_database_user",

    "user_phone",
    "set_user_phone",

    "flush_changes",

    "get_invite_service",
    "activate_invite",

    "send_status_message",
    "edit_status_message",

    "begin_contact_registration",
]