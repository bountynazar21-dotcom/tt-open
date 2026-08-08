from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import (
    Base,
    IntegerPrimaryKeyMixin,
    TimestampMixin,
)
from app.database.models.enums import UserRole, UserStatus


if TYPE_CHECKING:
    from app.database.models.audit_log import AuditLog
    from app.database.models.binding import (
        UserBushBinding,
        UserStoreBinding,
    )
    from app.database.models.closing_report import ClosingReport
    from app.database.models.invite import InviteLink
    from app.database.models.opening_checkin import OpeningCheckin


class User(
    IntegerPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """
    Telegram-користувач системи.

    Користувач може бути:
    - головним адміністратором;
    - директором;
    - адміністратором куща;
    - левом;
    - представником торгової точки.
    """

    __table_args__ = (
        Index(
            "ix_users_role_status",
            "role",
            "status",
        ),
        Index(
            "ix_users_username",
            "username",
        ),
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        unique=True,
        index=True,
        comment="Унікальний Telegram ID користувача",
    )

    username: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Telegram username без символу @",
    )

    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Ім’я користувача з Telegram",
    )

    phone: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="Номер телефону користувача",
    )

    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
        default=UserRole.STORE_USER,
        server_default=UserRole.STORE_USER.value,
        index=True,
    )

    status: Mapped[UserStatus] = mapped_column(
        Enum(
            UserStatus,
            name="user_status",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
        default=UserStatus.PENDING,
        server_default=UserStatus.PENDING.value,
        index=True,
    )

    is_blocked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        index=True,
    )

    blocked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    blocked_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # ==========================================
    # RELATIONSHIPS
    # ==========================================

    store_bindings: Mapped[list[UserStoreBinding]] = relationship(
        "UserStoreBinding",
        foreign_keys="UserStoreBinding.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    bush_bindings: Mapped[list[UserBushBinding]] = relationship(
        "UserBushBinding",
        foreign_keys="UserBushBinding.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    opening_checkins: Mapped[list[OpeningCheckin]] = relationship(
        "OpeningCheckin",
        foreign_keys="OpeningCheckin.submitted_by_id",
        back_populates="submitted_by",
        lazy="raise",
    )

    closing_reports: Mapped[list[ClosingReport]] = relationship(
        "ClosingReport",
        foreign_keys="ClosingReport.submitted_by_id",
        back_populates="submitted_by",
        lazy="raise",
    )

    created_invites: Mapped[list[InviteLink]] = relationship(
        "InviteLink",
        foreign_keys="InviteLink.created_by_id",
        back_populates="created_by",
        lazy="raise",
    )

    audit_actions: Mapped[list[AuditLog]] = relationship(
        "AuditLog",
        foreign_keys="AuditLog.actor_user_id",
        back_populates="actor",
        lazy="raise",
    )

    # ==========================================
    # PROPERTIES
    # ==========================================

    @property
    def display_name(self) -> str:
        """Повертає зручне ім’я користувача."""

        if self.username:
            return f"{self.full_name} (@{self.username})"

        return self.full_name

    @property
    def is_active(self) -> bool:
        """Чи може користувач працювати з ботом."""

        return (
            self.status == UserStatus.ACTIVE
            and not self.is_blocked
        )

    @property
    def is_root_admin(self) -> bool:
        return self.role == UserRole.ROOT_ADMIN

    @property
    def is_director(self) -> bool:
        return self.role == UserRole.DIRECTOR

    @property
    def is_bush_admin(self) -> bool:
        return self.role == UserRole.BUSH_ADMIN

    @property
    def is_lion(self) -> bool:
        return self.role == UserRole.LION

    @property
    def is_store_user(self) -> bool:
        return self.role == UserRole.STORE_USER

    def has_any_role(
        self,
        *roles: UserRole,
    ) -> bool:
        """Перевіряє, чи має користувач одну із переданих ролей."""

        return self.role in roles

    def can_manage_network(self) -> bool:
        """Доступ до всієї мережі."""

        return self.role in {
            UserRole.ROOT_ADMIN,
            UserRole.DIRECTOR,
        }

    def can_manage_users(self) -> bool:
        """Право керувати користувачами."""

        return self.role == UserRole.ROOT_ADMIN

    def block(
        self,
        *,
        blocked_at: datetime,
        reason: str | None = None,
    ) -> None:
        """Блокує користувача."""

        self.is_blocked = True
        self.status = UserStatus.BLOCKED
        self.blocked_at = blocked_at
        self.blocked_reason = reason

    def unblock(self) -> None:
        """Розблоковує користувача."""

        self.is_blocked = False
        self.status = UserStatus.ACTIVE
        self.blocked_at = None
        self.blocked_reason = None