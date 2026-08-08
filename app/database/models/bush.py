from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import (
    Base,
    IntegerPrimaryKeyMixin,
    TimestampMixin,
)


if TYPE_CHECKING:
    from app.database.models.binding import UserBushBinding
    from app.database.models.daily_summary import DailySummaryMessage
    from app.database.models.invite import InviteLink
    from app.database.models.schedule import ScheduleException
    from app.database.models.store import Store


class Bush(
    IntegerPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """
    Кущ — група торгових точок.

    До одного куща можуть належати:
    - декілька торгових точок;
    - декілька адміністраторів;
    - декілька левів;
    - окрема тема в Telegram-групі.
    """

    # Вказуємо вручну, бо автоматичне "bushs" було б неправильним.
    __tablename__ = "bushes"

    __table_args__ = (
        Index(
            "ix_bushes_name",
            "name",
        ),
        Index(
            "ix_bushes_active_name",
            "is_active",
            "name",
        ),
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        comment="Назва куща",
    )

    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
        comment="Унікальний короткий код куща",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        index=True,
        comment="Чи активний кущ",
    )

    telegram_topic_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="ID теми куща у Telegram-групі",
    )

    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Внутрішня примітка адміністратора",
    )

    # ==========================================
    # RELATIONSHIPS
    # ==========================================

    stores: Mapped[list[Store]] = relationship(
        "Store",
        back_populates="bush",
        lazy="selectin",
    )

    user_bindings: Mapped[list[UserBushBinding]] = relationship(
        "UserBushBinding",
        back_populates="bush",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    invite_links: Mapped[list[InviteLink]] = relationship(
        "InviteLink",
        back_populates="bush",
        lazy="raise",
    )

    schedule_exceptions: Mapped[list[ScheduleException]] = relationship(
        "ScheduleException",
        back_populates="bush",
        lazy="raise",
    )

    daily_summary_messages: Mapped[list[DailySummaryMessage]] = relationship(
        "DailySummaryMessage",
        back_populates="bush",
        lazy="raise",
    )

    # ==========================================
    # PROPERTIES
    # ==========================================

    @property
    def display_name(self) -> str:
        """Назва куща для повідомлень бота."""

        return self.name

    @property
    def active_stores_count(self) -> int:
        """
        Кількість активних торгових точок.

        Працює, коли relationship stores уже завантажений.
        """

        return sum(
            1
            for store in self.stores
            if store.is_active
        )

    @property
    def total_stores_count(self) -> int:
        """Загальна кількість торгових точок куща."""

        return len(self.stores)

    def activate(self) -> None:
        """Активує кущ."""

        self.is_active = True

    def deactivate(self) -> None:
        """
        Деактивує кущ.

        Історичні дані та торгові точки не видаляються.
        """

        self.is_active = False

    def update_topic(
        self,
        telegram_topic_id: int | None,
    ) -> None:
        """Змінює тему куща у Telegram-групі."""

        self.telegram_topic_id = telegram_topic_id