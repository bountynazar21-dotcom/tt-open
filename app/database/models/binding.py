from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import (
    Base,
    IntegerPrimaryKeyMixin,
    TimestampMixin,
)
from app.database.models.enums import (
    BindingStatus,
    UserRole,
)


if TYPE_CHECKING:
    from app.database.models.bush import Bush
    from app.database.models.store import Store
    from app.database.models.user import User


class UserStoreBinding(
    IntegerPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """
    Прив’язка Telegram-користувача до торгової точки.

    Один користувач може бути прив’язаний до декількох ТТ,
    якщо це дозволено налаштуваннями системи.

    Одна торгова точка може мати декількох користувачів.
    """

    __tablename__ = "user_store_bindings"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "store_id",
            name="uq_user_store_bindings_user_store",
        ),
        Index(
            "ix_user_store_bindings_store_status",
            "store_id",
            "status",
        ),
        Index(
            "ix_user_store_bindings_user_status",
            "user_id",
            "status",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
        comment="Користувач, який прив’язується до ТТ",
    )

    store_id: Mapped[int] = mapped_column(
        ForeignKey(
            "stores.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
        comment="Торгова точка користувача",
    )

    status: Mapped[BindingStatus] = mapped_column(
        Enum(
            BindingStatus,
            name="binding_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_class: [
                item.value
                for item in enum_class
            ],
        ),
        nullable=False,
        default=BindingStatus.PENDING,
        server_default=BindingStatus.PENDING.value,
        index=True,
    )

    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Адміністратор, який підтвердив заявку",
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    rejected_by_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    rejection_reason: Mapped[str | None] = mapped_column(
        String(500),
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

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    revocation_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # ==========================================
    # RELATIONSHIPS
    # ==========================================

    user: Mapped[User] = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="store_bindings",
        lazy="joined",
    )

    store: Mapped[Store] = relationship(
        "Store",
        foreign_keys=[store_id],
        back_populates="user_bindings",
        lazy="joined",
    )

    approved_by: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[approved_by_id],
        lazy="joined",
    )

    rejected_by: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[rejected_by_id],
        lazy="joined",
    )

    revoked_by: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[revoked_by_id],
        lazy="joined",
    )

    # ==========================================
    # PROPERTIES
    # ==========================================

    @property
    def is_pending(self) -> bool:
        return self.status == BindingStatus.PENDING

    @property
    def is_approved(self) -> bool:
        return self.status == BindingStatus.APPROVED

    @property
    def is_rejected(self) -> bool:
        return self.status == BindingStatus.REJECTED

    @property
    def is_revoked(self) -> bool:
        return self.status == BindingStatus.REVOKED

    @property
    def can_use_store(self) -> bool:
        """
        Чи може користувач виконувати дії від імені ТТ.
        """

        return (
            self.status == BindingStatus.APPROVED
            and self.user.is_active
            and self.store.is_active
        )

    # ==========================================
    # METHODS
    # ==========================================

    def approve(
        self,
        *,
        approved_by_id: int,
        approved_at: datetime,
    ) -> None:
        """Підтверджує прив’язку користувача до ТТ."""

        self.status = BindingStatus.APPROVED

        self.approved_by_id = approved_by_id
        self.approved_at = approved_at

        self.rejected_by_id = None
        self.rejected_at = None
        self.rejection_reason = None

        self.revoked_by_id = None
        self.revoked_at = None
        self.revocation_reason = None

    def reject(
        self,
        *,
        rejected_by_id: int,
        rejected_at: datetime,
        reason: str | None = None,
    ) -> None:
        """Відхиляє заявку на прив’язку."""

        self.status = BindingStatus.REJECTED

        self.rejected_by_id = rejected_by_id
        self.rejected_at = rejected_at
        self.rejection_reason = (
            reason.strip()
            if reason
            else None
        )

        self.approved_by_id = None
        self.approved_at = None

    def revoke(
        self,
        *,
        revoked_by_id: int,
        revoked_at: datetime,
        reason: str | None = None,
    ) -> None:
        """
        Відв’язує користувача від торгової точки.

        Історія заявки залишається у базі.
        """

        self.status = BindingStatus.REVOKED

        self.revoked_by_id = revoked_by_id
        self.revoked_at = revoked_at
        self.revocation_reason = (
            reason.strip()
            if reason
            else None
        )

    def reopen_request(self) -> None:
        """
        Повторно переводить прив’язку у статус очікування.

        Використовується, якщо раніше користувача відв’язали,
        але тепер потрібно знову надати доступ.
        """

        self.status = BindingStatus.PENDING

        self.approved_by_id = None
        self.approved_at = None

        self.rejected_by_id = None
        self.rejected_at = None
        self.rejection_reason = None

        self.revoked_by_id = None
        self.revoked_at = None
        self.revocation_reason = None


class UserBushBinding(
    IntegerPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """
    Прив’язка адміністратора або лева до куща.

    Один користувач може відповідати за декілька кущів.
    Один кущ може мати декількох адміністраторів і левів.
    """

    __tablename__ = "user_bush_bindings"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "bush_id",
            "role",
            name="uq_user_bush_bindings_user_bush_role",
        ),
        Index(
            "ix_user_bush_bindings_bush_role_status",
            "bush_id",
            "role",
            "status",
        ),
        Index(
            "ix_user_bush_bindings_user_role",
            "user_id",
            "role",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    bush_id: Mapped[int] = mapped_column(
        ForeignKey(
            "bushes.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    role: Mapped[UserRole] = mapped_column(
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
        comment="Роль користувача саме у цьому кущі",
    )

    status: Mapped[BindingStatus] = mapped_column(
        Enum(
            BindingStatus,
            name="binding_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_class: [
                item.value
                for item in enum_class
            ],
        ),
        nullable=False,
        default=BindingStatus.APPROVED,
        server_default=BindingStatus.APPROVED.value,
        index=True,
    )

    assigned_by_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    assigned_at: Mapped[datetime | None] = mapped_column(
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

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    revocation_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # ==========================================
    # RELATIONSHIPS
    # ==========================================

    user: Mapped[User] = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="bush_bindings",
        lazy="joined",
    )

    bush: Mapped[Bush] = relationship(
        "Bush",
        foreign_keys=[bush_id],
        back_populates="user_bindings",
        lazy="joined",
    )

    assigned_by: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[assigned_by_id],
        lazy="joined",
    )

    revoked_by: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[revoked_by_id],
        lazy="joined",
    )

    # ==========================================
    # PROPERTIES
    # ==========================================

    @property
    def is_active(self) -> bool:
        return self.status == BindingStatus.APPROVED

    @property
    def is_admin_binding(self) -> bool:
        return self.role == UserRole.BUSH_ADMIN

    @property
    def is_lion_binding(self) -> bool:
        return self.role == UserRole.LION

    # ==========================================
    # METHODS
    # ==========================================

    @classmethod
    def create(
        cls,
        *,
        user_id: int,
        bush_id: int,
        role: UserRole,
        assigned_by_id: int | None,
        assigned_at: datetime,
    ) -> UserBushBinding:
        """
        Створює прив’язку користувача до куща.

        Для кущів дозволені лише ролі:
        - BUSH_ADMIN;
        - LION.
        """

        if role not in {
            UserRole.BUSH_ADMIN,
            UserRole.LION,
        }:
            raise ValueError(
                "До куща можна прив’язати лише "
                "адміністратора куща або лева."
            )

        return cls(
            user_id=user_id,
            bush_id=bush_id,
            role=role,
            status=BindingStatus.APPROVED,
            assigned_by_id=assigned_by_id,
            assigned_at=assigned_at,
        )

    def revoke(
        self,
        *,
        revoked_by_id: int,
        revoked_at: datetime,
        reason: str | None = None,
    ) -> None:
        """Відв’язує адміністратора або лева від куща."""

        self.status = BindingStatus.REVOKED

        self.revoked_by_id = revoked_by_id
        self.revoked_at = revoked_at
        self.revocation_reason = (
            reason.strip()
            if reason
            else None
        )

    def restore(
        self,
        *,
        assigned_by_id: int,
        assigned_at: datetime,
    ) -> None:
        """Повторно активує прив’язку до куща."""

        self.status = BindingStatus.APPROVED

        self.assigned_by_id = assigned_by_id
        self.assigned_at = assigned_at

        self.revoked_by_id = None
        self.revoked_at = None
        self.revocation_reason = None