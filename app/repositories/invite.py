from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload, selectinload

from app.database.models.binding import (
    UserBushBinding,
    UserStoreBinding,
)
from app.database.models.enums import (
    BindingStatus,
    InviteStatus,
    InviteType,
    UserRole,
    UserStatus,
)
from app.database.models.invite import (
    InviteLink,
    InviteUsage,
)
from app.database.models.user import User
from app.repositories.binding import BindingRepository
from app.repositories.user import UserRepository


@dataclass(slots=True)
class CreatedInvite:
    """
    Результат створення нового запрошення.

    raw_token і deep_link потрібно показати
    адміністратору лише один раз.
    """

    invite: InviteLink
    raw_token: str
    deep_link: str


@dataclass(slots=True)
class InviteActivationResult:
    """
    Результат активації Telegram-запрошення.
    """

    invite: InviteLink
    user: User

    was_activated_now: bool
    was_already_used: bool

    usage: InviteUsage | None = None

    store_binding: UserStoreBinding | None = None
    bush_binding: UserBushBinding | None = None

    @property
    def target_role(self) -> UserRole:
        return self.invite.target_role

    @property
    def store_id(self) -> int | None:
        return self.invite.store_id

    @property
    def bush_id(self) -> int | None:
        return self.invite.bush_id


class InviteRepository:
    """
    Репозиторій захищених запрошень.

    Сирий токен не зберігається у базі.

    У базі зберігаються:
    - HMAC SHA-256 хеш;
    - короткий префікс;
    - термін дії;
    - кількість використань;
    - історія активацій.

    Commit виконується у сервісі або handler.
    """

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

        self.binding_repository = (
            BindingRepository(session)
        )

        self.user_repository = (
            UserRepository(session)
        )

    # ==========================================
    # ПОШУК ЗАПРОШЕННЯ
    # ==========================================

    async def get_by_id(
        self,
        invite_id: int,
        *,
        for_update: bool = False,
    ) -> InviteLink | None:
        """Повертає запрошення за внутрішнім ID."""

        self.validate_positive_id(
            invite_id,
            field_name="ID запрошення",
        )

        statement = (
            select(InviteLink)
            .options(
                selectinload(
                    InviteLink.bush
                ),
                selectinload(
                    InviteLink.store
                ),
                selectinload(
                    InviteLink.created_by
                ),
                selectinload(
                    InviteLink.revoked_by
                ),
            )
            .where(
                InviteLink.id == invite_id
            )
            .limit(1)
        )

        if for_update:
            statement = (
                statement
                .options(
                    lazyload(
                        InviteLink.bush
                    ),
                    lazyload(
                        InviteLink.store
                    ),
                    lazyload(
                        InviteLink.created_by
                    ),
                    lazyload(
                        InviteLink.revoked_by
                    ),
                    lazyload(
                        InviteLink.usages
                    ),
                )
                .with_for_update(
                    of=InviteLink
                )
            )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_by_id_or_raise(
        self,
        invite_id: int,
        *,
        for_update: bool = False,
    ) -> InviteLink:
        """Повертає запрошення або викликає помилку."""

        invite = await self.get_by_id(
            invite_id,
            for_update=for_update,
        )

        if invite is None:
            raise ValueError(
                "Запрошення не знайдено."
            )

        return invite

    async def find_by_raw_token(
        self,
        *,
        raw_token: str,
        salt: str,
    ) -> InviteLink | None:
        """
        Шукає запрошення за сирим токеном.

        Спочатку пошук виконується за коротким
        префіксом, після чого перевіряється HMAC-хеш.
        """

        normalized_token = self.normalize_raw_token(
            raw_token
        )

        token_prefix = normalized_token[:12]

        statement = (
            select(InviteLink)
            .where(
                InviteLink.token_prefix
                == token_prefix
            )
            .order_by(
                InviteLink.created_at.desc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        candidates = list(
            result.unique().all()
        )

        for candidate in candidates:
            if candidate.verify_raw_token(
                normalized_token,
                salt=salt,
            ):
                return candidate

        return None

    async def find_by_raw_token_or_raise(
        self,
        *,
        raw_token: str,
        salt: str,
    ) -> InviteLink:
        """Повертає запрошення або помилку."""

        invite = await self.find_by_raw_token(
            raw_token=raw_token,
            salt=salt,
        )

        if invite is None:
            raise ValueError(
                "Посилання-запрошення недійсне."
            )

        return invite

    async def get_for_update_by_raw_token(
        self,
        *,
        raw_token: str,
        salt: str,
    ) -> InviteLink:
        """
        Знаходить запрошення за токеном
        і блокує його до завершення транзакції.
        """

        found_invite = (
            await self.find_by_raw_token_or_raise(
                raw_token=raw_token,
                salt=salt,
            )
        )

        invite = await self.get_by_id_or_raise(
            found_invite.id,
            for_update=True,
        )

        if not invite.verify_raw_token(
            raw_token,
            salt=salt,
        ):
            raise ValueError(
                "Посилання-запрошення недійсне."
            )

        return invite

    # ==========================================
    # СТВОРЕННЯ ЗАПРОШЕННЯ
    # ==========================================

    async def create_invite(
        self,
        *,
        invite_type: InviteType,
        target_role: UserRole,
        created_by_id: int,
        salt: str,
        bot_username: str,
        expires_at: datetime | None = None,
        expiration_hours: int = 24,
        max_uses: int = 1,
        bush_id: int | None = None,
        store_id: int | None = None,
        note: str | None = None,
        now: datetime | None = None,
    ) -> CreatedInvite:
        """
        Створює запрошення та Telegram deep link.

        Сирий токен повертається лише в результаті
        цього методу і не записується в базу.
        """

        self.validate_positive_id(
            created_by_id,
            field_name="ID автора запрошення",
        )

        current_time = now or datetime.now(UTC)

        self.validate_aware_datetime(
            current_time,
            field_name="now",
        )

        if expires_at is not None:
            self.validate_aware_datetime(
                expires_at,
                field_name="expires_at",
            )

        invite, raw_token = InviteLink.create(
            invite_type=invite_type,
            target_role=target_role,
            created_by_id=created_by_id,
            salt=salt,
            expires_at=expires_at,
            expiration_hours=expiration_hours,
            max_uses=max_uses,
            bush_id=bush_id,
            store_id=store_id,
            note=note,
            now=current_time,
        )

        self.session.add(invite)
        await self.session.flush()

        deep_link = InviteLink.build_deep_link(
            bot_username=bot_username,
            raw_token=raw_token,
        )

        return CreatedInvite(
            invite=invite,
            raw_token=raw_token,
            deep_link=deep_link,
        )

    async def create_store_invite(
        self,
        *,
        store_id: int,
        created_by_id: int,
        salt: str,
        bot_username: str,
        expires_at: datetime | None = None,
        expiration_hours: int = 24,
        max_uses: int = 1,
        note: str | None = None,
        now: datetime | None = None,
    ) -> CreatedInvite:
        """Створює запрошення працівника на конкретну ТТ."""

        self.validate_positive_id(
            store_id,
            field_name="ID торгової точки",
        )

        return await self.create_invite(
            invite_type=InviteType.STORE,
            target_role=UserRole.STORE_USER,
            created_by_id=created_by_id,
            salt=salt,
            bot_username=bot_username,
            expires_at=expires_at,
            expiration_hours=expiration_hours,
            max_uses=max_uses,
            store_id=store_id,
            note=note,
            now=now,
        )

    async def create_bush_invite(
        self,
        *,
        bush_id: int,
        role: UserRole,
        created_by_id: int,
        salt: str,
        bot_username: str,
        expires_at: datetime | None = None,
        expiration_hours: int = 24,
        max_uses: int = 1,
        note: str | None = None,
        now: datetime | None = None,
    ) -> CreatedInvite:
        """
        Створює запрошення адміністратора
        або лева до конкретного куща.
        """

        if role not in {
            UserRole.BUSH_ADMIN,
            UserRole.LION,
        }:
            raise ValueError(
                "До куща можна запросити лише "
                "адміністратора куща або лева."
            )

        self.validate_positive_id(
            bush_id,
            field_name="ID куща",
        )

        return await self.create_invite(
            invite_type=InviteType.BUSH,
            target_role=role,
            created_by_id=created_by_id,
            salt=salt,
            bot_username=bot_username,
            expires_at=expires_at,
            expiration_hours=expiration_hours,
            max_uses=max_uses,
            bush_id=bush_id,
            note=note,
            now=now,
        )

    async def create_director_invite(
        self,
        *,
        created_by_id: int,
        salt: str,
        bot_username: str,
        expires_at: datetime | None = None,
        expiration_hours: int = 24,
        max_uses: int = 1,
        note: str | None = None,
        now: datetime | None = None,
    ) -> CreatedInvite:
        """Створює запрошення на роль директора."""

        return await self.create_invite(
            invite_type=InviteType.ROLE,
            target_role=UserRole.DIRECTOR,
            created_by_id=created_by_id,
            salt=salt,
            bot_username=bot_username,
            expires_at=expires_at,
            expiration_hours=expiration_hours,
            max_uses=max_uses,
            note=note,
            now=now,
        )

    # ==========================================
    # АКТИВАЦІЯ DEEP LINK
    # ==========================================

    async def activate_start_payload(
        self,
        *,
        start_payload: str,
        user_id: int,
        salt: str,
        used_at: datetime,
        telegram_chat_id: int | None = None,
    ) -> InviteActivationResult:
        """
        Активує Telegram-параметр:

        /start invite_AbCdEf123
        """

        raw_token = InviteLink.extract_raw_token(
            start_payload
        )

        return await self.activate_raw_token(
            raw_token=raw_token,
            user_id=user_id,
            salt=salt,
            used_at=used_at,
            telegram_chat_id=telegram_chat_id,
        )

    async def activate_raw_token(
        self,
        *,
        raw_token: str,
        user_id: int,
        salt: str,
        used_at: datetime,
        telegram_chat_id: int | None = None,
    ) -> InviteActivationResult:
        """
        Перевіряє та активує запрошення.

        Операція виконується під блокуванням рядка,
        тому одне одноразове посилання не зможуть
        одночасно використати дві людини.
        """

        self.validate_positive_id(
            user_id,
            field_name="ID користувача",
        )

        self.validate_aware_datetime(
            used_at,
            field_name="used_at",
        )

        normalized_used_at = used_at.astimezone(
            UTC
        )

        user = await self.session.get(
            User,
            user_id,
        )

        if user is None:
            raise ValueError(
                "Користувача не знайдено."
            )

        if (
            user.is_blocked
            or user.status == UserStatus.BLOCKED
        ):
            raise ValueError(
                "Заблокований користувач не може "
                "активувати запрошення."
            )

        invite = await self.get_for_update_by_raw_token(
            raw_token=raw_token,
            salt=salt,
        )

        existing_usage = await self.get_usage(
            invite_id=invite.id,
            user_id=user.id,
        )

        if existing_usage is not None:
            return InviteActivationResult(
                invite=invite,
                user=user,
                usage=existing_usage,
                was_activated_now=False,
                was_already_used=True,
            )

        status = invite.get_status(
            now=normalized_used_at
        )

        self.ensure_invite_is_active(
            status=status
        )

        store_binding: UserStoreBinding | None = None
        bush_binding: UserBushBinding | None = None

        if invite.invite_type == InviteType.STORE:
            store_binding = (
                await self.activate_store_invite(
                    invite=invite,
                    user=user,
                    used_at=normalized_used_at,
                )
            )

        elif invite.invite_type == InviteType.BUSH:
            bush_binding = (
                await self.activate_bush_invite(
                    invite=invite,
                    user=user,
                    used_at=normalized_used_at,
                )
            )

        elif invite.invite_type == InviteType.ROLE:
            await self.activate_role_invite(
                invite=invite,
                user=user,
            )

        else:
            raise ValueError(
                "Невідомий тип запрошення."
            )

        invite.register_use(
            used_at=normalized_used_at
        )

        usage = InviteUsage(
            invite_id=invite.id,
            user_id=user.id,
            used_at=normalized_used_at,
            telegram_chat_id=telegram_chat_id,
            result_role=invite.target_role,
        )

        self.session.add(invite)
        self.session.add(usage)

        await self.session.flush()

        return InviteActivationResult(
            invite=invite,
            user=user,
            usage=usage,
            store_binding=store_binding,
            bush_binding=bush_binding,
            was_activated_now=True,
            was_already_used=False,
        )

    # ==========================================
    # ВИДАЧА ДОСТУПУ ДО ТТ
    # ==========================================

    async def activate_store_invite(
        self,
        *,
        invite: InviteLink,
        user: User,
        used_at: datetime,
    ) -> UserStoreBinding:
        """Автоматично прив’язує користувача до ТТ."""

        if invite.store_id is None:
            raise ValueError(
                "У запрошенні відсутня торгова точка."
            )

        existing_binding = (
            await self.binding_repository
            .get_store_binding(
                user_id=user.id,
                store_id=invite.store_id,
                for_update=True,
            )
        )

        if (
            existing_binding is not None
            and existing_binding.status
            == BindingStatus.APPROVED
        ):
            return existing_binding

        binding, _ = (
            await self.binding_repository
            .create_store_request(
                user_id=user.id,
                store_id=invite.store_id,
                requested_at=used_at,
            )
        )

        if binding.status != BindingStatus.APPROVED:
            binding = (
                await self.binding_repository
                .approve_store_binding(
                    binding,
                    approved_by_id=(
                        invite.created_by_id
                        or user.id
                    ),
                    approved_at=used_at,
                    activate_user=True,
                )
            )

        return binding

    # ==========================================
    # ВИДАЧА ДОСТУПУ ДО КУЩА
    # ==========================================

    async def activate_bush_invite(
        self,
        *,
        invite: InviteLink,
        user: User,
        used_at: datetime,
    ) -> UserBushBinding:
        """Автоматично призначає роль у кущі."""

        if invite.bush_id is None:
            raise ValueError(
                "У запрошенні відсутній кущ."
            )

        if invite.target_role not in {
            UserRole.BUSH_ADMIN,
            UserRole.LION,
        }:
            raise ValueError(
                "Некоректна роль для куща."
            )

        existing_binding = (
            await self.binding_repository
            .get_bush_binding(
                user_id=user.id,
                bush_id=invite.bush_id,
                role=invite.target_role,
                for_update=True,
            )
        )

        if (
            existing_binding is not None
            and existing_binding.status
            == BindingStatus.APPROVED
        ):
            return existing_binding

        binding, _ = (
            await self.binding_repository
            .assign_bush_role(
                user_id=user.id,
                bush_id=invite.bush_id,
                role=invite.target_role,
                assigned_by_id=(
                    invite.created_by_id
                    or user.id
                ),
                assigned_at=used_at,
            )
        )

        return binding

    # ==========================================
    # ВИДАЧА ЗАГАЛЬНОЇ РОЛІ
    # ==========================================

    async def activate_role_invite(
        self,
        *,
        invite: InviteLink,
        user: User,
    ) -> User:
        """Автоматично призначає загальну роль."""

        if invite.target_role != UserRole.DIRECTOR:
            raise ValueError(
                "Через загальне запрошення дозволено "
                "призначати лише директора."
            )

        if user.role == UserRole.ROOT_ADMIN:
            user.status = UserStatus.ACTIVE
            user.is_blocked = False

            self.session.add(user)
            await self.session.flush()

            return user

        return await self.user_repository.assign_role(
            user,
            role=UserRole.DIRECTOR,
        )

    # ==========================================
    # ІСТОРІЯ ВИКОРИСТАНЬ
    # ==========================================

    async def get_usage(
        self,
        *,
        invite_id: int,
        user_id: int,
    ) -> InviteUsage | None:
        """Повертає використання запрошення користувачем."""

        statement = (
            select(InviteUsage)
            .where(
                InviteUsage.invite_id == invite_id,
                InviteUsage.user_id == user_id,
            )
            .limit(1)
        )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_usages_for_invite(
        self,
        invite_id: int,
    ) -> list[InviteUsage]:
        """Повертає історію конкретного запрошення."""

        statement = (
            select(InviteUsage)
            .options(
                selectinload(
                    InviteUsage.user
                ),
            )
            .where(
                InviteUsage.invite_id
                == invite_id
            )
            .order_by(
                InviteUsage.used_at.asc(),
                InviteUsage.id.asc(),
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_usages_for_user(
        self,
        user_id: int,
    ) -> list[InviteUsage]:
        """Повертає запрошення, використані користувачем."""

        statement = (
            select(InviteUsage)
            .options(
                selectinload(
                    InviteUsage.invite
                ),
            )
            .where(
                InviteUsage.user_id == user_id
            )
            .order_by(
                InviteUsage.used_at.desc(),
                InviteUsage.id.desc(),
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    # ==========================================
    # ВІДКЛИКАННЯ
    # ==========================================

    async def revoke_invite(
        self,
        invite: InviteLink,
        *,
        revoked_by_id: int,
        revoked_at: datetime,
        reason: str | None = None,
    ) -> InviteLink:
        """Відкликає конкретне запрошення."""

        self.validate_aware_datetime(
            revoked_at,
            field_name="revoked_at",
        )

        if invite.is_revoked:
            return invite

        invite.revoke(
            revoked_by_id=revoked_by_id,
            revoked_at=revoked_at.astimezone(UTC),
            reason=reason,
        )

        self.session.add(invite)
        await self.session.flush()

        return invite

    async def revoke_by_id(
        self,
        *,
        invite_id: int,
        revoked_by_id: int,
        revoked_at: datetime,
        reason: str | None = None,
    ) -> InviteLink:
        """Знаходить і відкликає запрошення."""

        invite = await self.get_by_id_or_raise(
            invite_id,
            for_update=True,
        )

        return await self.revoke_invite(
            invite,
            revoked_by_id=revoked_by_id,
            revoked_at=revoked_at,
            reason=reason,
        )

    async def revoke_active_store_invites(
        self,
        *,
        store_id: int,
        revoked_by_id: int,
        revoked_at: datetime,
        reason: str,
    ) -> list[InviteLink]:
        """Відкликає всі активні запрошення конкретної ТТ."""

        return await self.revoke_target_invites(
            store_id=store_id,
            revoked_by_id=revoked_by_id,
            revoked_at=revoked_at,
            reason=reason,
        )

    async def revoke_active_bush_invites(
        self,
        *,
        bush_id: int,
        revoked_by_id: int,
        revoked_at: datetime,
        reason: str,
    ) -> list[InviteLink]:
        """Відкликає активні запрошення конкретного куща."""

        return await self.revoke_target_invites(
            bush_id=bush_id,
            revoked_by_id=revoked_by_id,
            revoked_at=revoked_at,
            reason=reason,
        )

    async def revoke_target_invites(
        self,
        *,
        revoked_by_id: int,
        revoked_at: datetime,
        reason: str,
        store_id: int | None = None,
        bush_id: int | None = None,
    ) -> list[InviteLink]:
        """Відкликає активні запрошення вибраної цілі."""

        self.validate_aware_datetime(
            revoked_at,
            field_name="revoked_at",
        )

        if store_id is None and bush_id is None:
            raise ValueError(
                "Потрібно вказати торгову точку або кущ."
            )

        if store_id is not None and bush_id is not None:
            raise ValueError(
                "Не можна одночасно вказувати ТТ і кущ."
            )

        current_time = revoked_at.astimezone(UTC)

        conditions = [
            InviteLink.is_revoked.is_(False),
            InviteLink.expires_at > current_time,
            InviteLink.used_count
            < InviteLink.max_uses,
        ]

        if store_id is not None:
            conditions.append(
                InviteLink.store_id == store_id
            )

        if bush_id is not None:
            conditions.append(
                InviteLink.bush_id == bush_id
            )

        statement = (
            select(InviteLink)
            .where(*conditions)
            .with_for_update(
                of=InviteLink,
                skip_locked=True,
            )
        )

        result = await self.session.scalars(
            statement
        )

        invites = list(
            result.unique().all()
        )

        for invite in invites:
            invite.revoke(
                revoked_by_id=revoked_by_id,
                revoked_at=current_time,
                reason=reason,
            )

            self.session.add(invite)

        if invites:
            await self.session.flush()

        return invites

    # ==========================================
    # СПИСКИ ЗАПРОШЕНЬ
    # ==========================================

    async def get_by_status(
        self,
        *,
        status: InviteStatus,
        now: datetime | None = None,
        created_by_id: int | None = None,
        store_id: int | None = None,
        bush_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[InviteLink]:
        """Повертає запрошення за обчислюваним статусом."""

        current_time = now or datetime.now(UTC)

        self.validate_aware_datetime(
            current_time,
            field_name="now",
        )

        self.validate_pagination(
            limit=limit,
            offset=offset,
        )

        conditions = self.build_status_conditions(
            status=status,
            now=current_time,
        )

        if created_by_id is not None:
            conditions.append(
                InviteLink.created_by_id
                == created_by_id
            )

        if store_id is not None:
            conditions.append(
                InviteLink.store_id == store_id
            )

        if bush_id is not None:
            conditions.append(
                InviteLink.bush_id == bush_id
            )

        statement = (
            select(InviteLink)
            .options(
                selectinload(
                    InviteLink.store
                ),
                selectinload(
                    InviteLink.bush
                ),
                selectinload(
                    InviteLink.created_by
                ),
            )
            .where(*conditions)
            .order_by(
                InviteLink.created_at.desc()
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

    async def get_active_invites(
        self,
        *,
        now: datetime | None = None,
        created_by_id: int | None = None,
        store_id: int | None = None,
        bush_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[InviteLink]:
        """Повертає активні запрошення."""

        return await self.get_by_status(
            status=InviteStatus.ACTIVE,
            now=now,
            created_by_id=created_by_id,
            store_id=store_id,
            bush_id=bush_id,
            limit=limit,
            offset=offset,
        )

    async def get_expired_invites(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[InviteLink]:
        """Повертає протерміновані запрошення."""

        return await self.get_by_status(
            status=InviteStatus.EXPIRED,
            now=now,
            limit=limit,
            offset=offset,
        )

    async def get_revoked_invites(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[InviteLink]:
        """Повертає відкликані запрошення."""

        return await self.get_by_status(
            status=InviteStatus.REVOKED,
            limit=limit,
            offset=offset,
        )

    async def get_used_up_invites(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[InviteLink]:
        """Повертає повністю використані запрошення."""

        return await self.get_by_status(
            status=InviteStatus.USED_UP,
            limit=limit,
            offset=offset,
        )

    # ==========================================
    # СТАТИСТИКА
    # ==========================================

    async def count_by_status(
        self,
        *,
        now: datetime | None = None,
    ) -> dict[InviteStatus, int]:
        """Підраховує запрошення за статусами."""

        current_time = now or datetime.now(UTC)

        self.validate_aware_datetime(
            current_time,
            field_name="now",
        )

        counts: dict[InviteStatus, int] = {}

        for status in InviteStatus:
            statement = (
                select(
                    func.count(InviteLink.id)
                )
                .where(
                    *self.build_status_conditions(
                        status=status,
                        now=current_time,
                    )
                )
            )

            result = await self.session.scalar(
                statement
            )

            counts[status] = int(result or 0)

        return counts

    async def count_usages(
        self,
        *,
        invite_id: int | None = None,
        user_id: int | None = None,
    ) -> int:
        """Підраховує успішні активації."""

        conditions = []

        if invite_id is not None:
            conditions.append(
                InviteUsage.invite_id == invite_id
            )

        if user_id is not None:
            conditions.append(
                InviteUsage.user_id == user_id
            )

        statement = (
            select(
                func.count(InviteUsage.id)
            )
            .where(*conditions)
        )

        result = await self.session.scalar(
            statement
        )

        return int(result or 0)

    # ==========================================
    # УМОВИ СТАТУСУ
    # ==========================================

    @staticmethod
    def build_status_conditions(
        *,
        status: InviteStatus,
        now: datetime,
    ) -> list[Any]:
        """
        Формує SQL-умови відповідно до логіки
        InviteLink.get_status().
        """

        if status == InviteStatus.REVOKED:
            return [
                InviteLink.is_revoked.is_(True),
            ]

        if status == InviteStatus.USED_UP:
            return [
                InviteLink.is_revoked.is_(False),
                InviteLink.used_count
                >= InviteLink.max_uses,
            ]

        if status == InviteStatus.EXPIRED:
            return [
                InviteLink.is_revoked.is_(False),
                InviteLink.used_count
                < InviteLink.max_uses,
                InviteLink.expires_at <= now,
            ]

        if status == InviteStatus.ACTIVE:
            return [
                InviteLink.is_revoked.is_(False),
                InviteLink.used_count
                < InviteLink.max_uses,
                InviteLink.expires_at > now,
            ]

        raise ValueError(
            "Невідомий статус запрошення."
        )

    @staticmethod
    def ensure_invite_is_active(
        *,
        status: InviteStatus,
    ) -> None:
        """Перевіряє можливість використання посилання."""

        if status == InviteStatus.ACTIVE:
            return

        messages = {
            InviteStatus.REVOKED: (
                "Це посилання було відкликане."
            ),
            InviteStatus.EXPIRED: (
                "Термін дії посилання завершився."
            ),
            InviteStatus.USED_UP: (
                "Ліміт використань посилання вичерпано."
            ),
        }

        raise ValueError(
            messages.get(
                status,
                "Це посилання більше не діє.",
            )
        )

    # ==========================================
    # ДОПОМІЖНІ МЕТОДИ
    # ==========================================

    @staticmethod
    def normalize_raw_token(
        raw_token: str,
    ) -> str:
        """Нормалізує сирий токен."""

        normalized_token = raw_token.strip()

        if not normalized_token:
            raise ValueError(
                "Токен запрошення не може бути порожнім."
            )

        if len(normalized_token) > 128:
            raise ValueError(
                "Некоректна довжина токена."
            )

        return normalized_token

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
    def validate_pagination(
        *,
        limit: int,
        offset: int,
    ) -> None:
        """Перевіряє пагінацію."""

        if limit <= 0 or limit > 1000:
            raise ValueError(
                "Limit повинен бути від 1 до 1000."
            )

        if offset < 0:
            raise ValueError(
                "Offset не може бути від’ємним."
            )