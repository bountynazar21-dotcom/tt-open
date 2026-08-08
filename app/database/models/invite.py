from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import (
    Base,
    IntegerPrimaryKeyMixin,
    TimestampMixin,
)
from app.database.models.enums import (
    InviteStatus,
    InviteType,
    UserRole,
)


if TYPE_CHECKING:
    from app.database.models.bush import Bush
    from app.database.models.store import Store
    from app.database.models.user import User


class InviteLink(
    IntegerPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """
    Захищене посилання-запрошення в Telegram-бот.

    Сирий токен не зберігається в базі.
    У базі зберігається лише його SHA-256 HMAC-хеш.

    Приклад deep link:

    https://t.me/soskaopen_bot?start=invite_AbCdEf123
    """

    __tablename__ = "invite_links"

    __table_args__ = (
        CheckConstraint(
            "max_uses > 0",
            name="max_uses_positive",
        ),
        CheckConstraint(
            "used_count >= 0",
            name="used_count_non_negative",
        ),
        CheckConstraint(
            "used_count <= max_uses",
            name="used_count_not_above_max",
        ),
        UniqueConstraint(
            "token_hash",
            name="uq_invite_links_token_hash",
        ),
        Index(
            "ix_invite_links_active_expires",
            "is_revoked",
            "expires_at",
        ),
        Index(
            "ix_invite_links_bush_role",
            "bush_id",
            "target_role",
        ),
        Index(
            "ix_invite_links_store_role",
            "store_id",
            "target_role",
        ),
        Index(
            "ix_invite_links_created_by",
            "created_by_id",
            "created_at",
        ),
    )

    # ==========================================
    # ТОКЕН
    # ==========================================

    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="HMAC SHA-256 хеш токена",
    )

    token_prefix: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
        index=True,
        comment="Початок токена для пошуку та адмін-інтерфейсу",
    )

    invite_type: Mapped[InviteType] = mapped_column(
        Enum(
            InviteType,
            name="invite_type",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_class: [
                item.value
                for item in enum_class
            ],
        ),
        nullable=False,
        index=True,
    )

    target_role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_class: [
                item.value
                for item in enum_class
            ],
        ),
        nullable=False,
        index=True,
        comment="Роль, яка буде видана після використання",
    )

    # ==========================================
    # ЦІЛЬ ЗАПРОШЕННЯ
    # ==========================================

    bush_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "bushes.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
        comment="Кущ для адміністратора або лева",
    )

    store_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "stores.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
        comment="ТТ для працівника магазину",
    )

    # ==========================================
    # АВТОР ЗАПРОШЕННЯ
    # ==========================================

    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Користувач, який створив запрошення",
    )

    # ==========================================
    # ТЕРМІН І КІЛЬКІСТЬ ВИКОРИСТАНЬ
    # ==========================================

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Дата і час завершення дії запрошення",
    )

    max_uses: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        comment="Максимальна кількість використань",
    )

    used_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Поточна кількість використань",
    )

    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Час останнього використання",
    )

    # ==========================================
    # ВІДКЛИКАННЯ
    # ==========================================

    is_revoked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        index=True,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    revoked_by_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    revocation_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    note: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Внутрішня примітка",
    )

    # ==========================================
    # RELATIONSHIPS
    # ==========================================

    bush: Mapped[Bush | None] = relationship(
        "Bush",
        back_populates="invite_links",
        lazy="joined",
    )

    store: Mapped[Store | None] = relationship(
        "Store",
        back_populates="invite_links",
        lazy="joined",
    )

    created_by: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[created_by_id],
        back_populates="created_invites",
        lazy="joined",
    )

    revoked_by: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[revoked_by_id],
        lazy="joined",
    )

    usages: Mapped[list[InviteUsage]] = relationship(
        "InviteUsage",
        back_populates="invite",
        cascade="all, delete-orphan",
        lazy="raise",
    )

    # ==========================================
    # СТВОРЕННЯ ТОКЕНА
    # ==========================================

    @staticmethod
    def generate_raw_token() -> str:
        """
        Створює криптографічно стійкий токен.

        token_urlsafe зручно використовувати
        всередині Telegram deep link.
        """

        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_token(
        raw_token: str,
        *,
        salt: str,
    ) -> str:
        """
        Створює HMAC SHA-256 хеш токена.

        Сирий токен не потрібно зберігати в базі.
        """

        normalized_token = raw_token.strip()
        normalized_salt = salt.strip()

        if not normalized_token:
            raise ValueError(
                "Токен запрошення не може бути порожнім."
            )

        if not normalized_salt:
            raise ValueError(
                "Сіль для токена не може бути порожньою."
            )

        return hmac.new(
            normalized_salt.encode("utf-8"),
            normalized_token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @classmethod
    def create(
        cls,
        *,
        invite_type: InviteType,
        target_role: UserRole,
        created_by_id: int | None,
        salt: str,
        expires_at: datetime | None = None,
        expiration_hours: int = 24,
        max_uses: int = 1,
        bush_id: int | None = None,
        store_id: int | None = None,
        note: str | None = None,
        now: datetime | None = None,
    ) -> tuple[InviteLink, str]:
        """
        Створює запрошення і повертає:

        1. Об’єкт InviteLink для запису в базу.
        2. Сирий токен, який можна показати лише один раз.
        """

        current_time = now or datetime.now(UTC)

        if current_time.tzinfo is None:
            raise ValueError(
                "Параметр now повинен містити часовий пояс."
            )

        if max_uses <= 0:
            raise ValueError(
                "Кількість використань повинна бути більшою за нуль."
            )

        if expiration_hours <= 0:
            raise ValueError(
                "Термін дії повинен бути більшим за нуль."
            )

        cls.validate_target(
            invite_type=invite_type,
            target_role=target_role,
            bush_id=bush_id,
            store_id=store_id,
        )

        raw_token = cls.generate_raw_token()

        final_expires_at = expires_at or (
            current_time + timedelta(
                hours=expiration_hours
            )
        )

        if final_expires_at.tzinfo is None:
            raise ValueError(
                "expires_at повинен містити часовий пояс."
            )

        if final_expires_at <= current_time:
            raise ValueError(
                "Дата завершення дії повинна бути у майбутньому."
            )

        invite = cls(
            token_hash=cls.hash_token(
                raw_token,
                salt=salt,
            ),
            token_prefix=raw_token[:12],
            invite_type=invite_type,
            target_role=target_role,
            bush_id=bush_id,
            store_id=store_id,
            created_by_id=created_by_id,
            expires_at=final_expires_at,
            max_uses=max_uses,
            used_count=0,
            is_revoked=False,
            note=note.strip() if note else None,
        )

        return invite, raw_token

    # ==========================================
    # ПЕРЕВІРКА ТИПУ ЗАПРОШЕННЯ
    # ==========================================

    @staticmethod
    def validate_target(
        *,
        invite_type: InviteType,
        target_role: UserRole,
        bush_id: int | None,
        store_id: int | None,
    ) -> None:
        """Перевіряє правильність цілі запрошення."""

        if invite_type == InviteType.BUSH:
            if bush_id is None:
                raise ValueError(
                    "Для запрошення до куща потрібно вказати bush_id."
                )

            if store_id is not None:
                raise ValueError(
                    "Запрошення до куща не може містити store_id."
                )

            if target_role not in {
                UserRole.BUSH_ADMIN,
                UserRole.LION,
            }:
                raise ValueError(
                    "До куща можна запросити лише "
                    "адміністратора куща або лева."
                )

            return

        if invite_type == InviteType.STORE:
            if store_id is None:
                raise ValueError(
                    "Для запрошення до ТТ потрібно вказати store_id."
                )

            if bush_id is not None:
                raise ValueError(
                    "Запрошення до ТТ не може містити bush_id."
                )

            if target_role != UserRole.STORE_USER:
                raise ValueError(
                    "До торгової точки можна запросити "
                    "лише користувача ТТ."
                )

            return

        if invite_type == InviteType.ROLE:
            if bush_id is not None or store_id is not None:
                raise ValueError(
                    "Загальне запрошення на роль не повинно "
                    "містити bush_id або store_id."
                )

            if target_role == UserRole.ROOT_ADMIN:
                raise ValueError(
                    "ROOT_ADMIN не можна призначати через запрошення."
                )

            return

        raise ValueError(
            "Невідомий тип запрошення."
        )

    # ==========================================
    # DEEP LINK
    # ==========================================

    @staticmethod
    def build_start_payload(
        raw_token: str,
    ) -> str:
        """Створює параметр для Telegram-команди /start."""

        normalized_token = raw_token.strip()

        if not normalized_token:
            raise ValueError(
                "Токен не може бути порожнім."
            )

        return f"invite_{normalized_token}"

    @classmethod
    def build_deep_link(
        cls,
        *,
        bot_username: str,
        raw_token: str,
    ) -> str:
        """Створює повне Telegram-посилання."""

        normalized_username = (
            bot_username.strip().removeprefix("@")
        )

        if not normalized_username:
            raise ValueError(
                "Username Telegram-бота не може бути порожнім."
            )

        payload = cls.build_start_payload(
            raw_token
        )

        return (
            f"https://t.me/{normalized_username}"
            f"?start={payload}"
        )

    @staticmethod
    def extract_raw_token(
        start_payload: str,
    ) -> str:
        """
        Витягує сирий токен із параметра /start.

        invite_AbCdEf123 -> AbCdEf123
        """

        normalized_payload = start_payload.strip()
        prefix = "invite_"

        if not normalized_payload.startswith(prefix):
            raise ValueError(
                "Некоректний формат запрошення."
            )

        raw_token = normalized_payload.removeprefix(
            prefix
        )

        if not raw_token:
            raise ValueError(
                "Токен запрошення відсутній."
            )

        return raw_token

    # ==========================================
    # СТАН ЗАПРОШЕННЯ
    # ==========================================

    def get_status(
        self,
        *,
        now: datetime | None = None,
    ) -> InviteStatus:
        """Повертає поточний статус запрошення."""

        current_time = now or datetime.now(UTC)

        if self.is_revoked:
            return InviteStatus.REVOKED

        if self.used_count >= self.max_uses:
            return InviteStatus.USED_UP

        if current_time >= self.expires_at:
            return InviteStatus.EXPIRED

        return InviteStatus.ACTIVE

    def can_be_used(
        self,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Чи можна зараз використати запрошення."""

        return self.get_status(
            now=now
        ) == InviteStatus.ACTIVE

    def verify_raw_token(
        self,
        raw_token: str,
        *,
        salt: str,
    ) -> bool:
        """Порівнює сирий токен із хешем у базі."""

        candidate_hash = self.hash_token(
            raw_token,
            salt=salt,
        )

        return hmac.compare_digest(
            self.token_hash,
            candidate_hash,
        )

    # ==========================================
    # ВИКОРИСТАННЯ
    # ==========================================

    def register_use(
        self,
        *,
        used_at: datetime,
    ) -> None:
        """Збільшує лічильник використань."""

        if not self.can_be_used(now=used_at):
            raise ValueError(
                "Це запрошення більше не діє."
            )

        self.used_count += 1
        self.last_used_at = used_at

    # ==========================================
    # ВІДКЛИКАННЯ
    # ==========================================

    def revoke(
        self,
        *,
        revoked_by_id: int,
        revoked_at: datetime,
        reason: str | None = None,
    ) -> None:
        """Відкликає посилання-запрошення."""

        if self.is_revoked:
            raise ValueError(
                "Запрошення вже відкликане."
            )

        self.is_revoked = True
        self.revoked_by_id = revoked_by_id
        self.revoked_at = revoked_at

        self.revocation_reason = (
            reason.strip()
            if reason
            else None
        )

    # ==========================================
    # PROPERTIES
    # ==========================================

    @property
    def remaining_uses(self) -> int:
        """Кількість доступних використань."""

        return max(
            self.max_uses - self.used_count,
            0,
        )

    @property
    def target_name(self) -> str:
        """Назва цілі запрошення."""

        if self.store is not None:
            return self.store.code

        if self.bush is not None:
            return self.bush.name

        return self.target_role.value

    @property
    def is_single_use(self) -> bool:
        return self.max_uses == 1


class InviteUsage(
    IntegerPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """
    Історія використання запрошень.

    Один запис створюється при кожній успішній
    активації посилання.
    """

    __tablename__ = "invite_usages"

    __table_args__ = (
        UniqueConstraint(
            "invite_id",
            "user_id",
            name="uq_invite_usages_invite_user",
        ),
        Index(
            "ix_invite_usages_invite_used",
            "invite_id",
            "used_at",
        ),
        Index(
            "ix_invite_usages_user_used",
            "user_id",
            "used_at",
        ),
    )

    invite_id: Mapped[int] = mapped_column(
        ForeignKey(
            "invite_links.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    telegram_chat_id: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    result_role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_class: [
                item.value
                for item in enum_class
            ],
        ),
        nullable=False,
    )

    invite: Mapped[InviteLink] = relationship(
        "InviteLink",
        back_populates="usages",
        lazy="joined",
    )

    user: Mapped[User] = relationship(
        "User",
        foreign_keys=[user_id],
        lazy="joined",
    )