from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Index,
    String,
    Text,
    Time,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import (
    Base,
    IntegerPrimaryKeyMixin,
    TimestampMixin,
)


if TYPE_CHECKING:
    from app.database.models.store import Store


class Cluster(
    IntegerPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """
    Кластер визначає стандартний графік торгових точок.

    Основні кластери мережі:
    - 07:00;
    - 08:00;
    - 09:00;
    - 10:00.

    Значення не прописуються жорстко в логіці бота.
    ROOT_ADMIN зможе створювати, редагувати,
    активувати та деактивувати кластери.
    """

    __table_args__ = (
        Index(
            "ix_clusters_active_opening_time",
            "is_active",
            "opening_time",
        ),
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="Назва кластера, наприклад 08:00",
    )

    opening_time: Mapped[time] = mapped_column(
        Time(timezone=False),
        nullable=False,
        index=True,
        comment="Офіційний час відкриття торгової точки",
    )

    opening_control_deadline: Mapped[time] = mapped_column(
        Time(timezone=False),
        nullable=False,
        comment="Час формування списку невідкритих ТТ",
    )

    default_closing_time: Mapped[time | None] = mapped_column(
        Time(timezone=False),
        nullable=True,
        comment="Стандартний час закриття",
    )

    default_closing_deadline: Mapped[time | None] = mapped_column(
        Time(timezone=False),
        nullable=True,
        comment="Контрольний дедлайн вечірнього звіту",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        index=True,
        comment="Чи доступний кластер для нових ТТ",
    )

    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Внутрішня примітка щодо кластера",
    )

    # ==========================================
    # RELATIONSHIPS
    # ==========================================

    stores: Mapped[list[Store]] = relationship(
        "Store",
        back_populates="cluster",
        lazy="selectin",
    )

    # ==========================================
    # PROPERTIES
    # ==========================================

    @property
    def display_name(self) -> str:
        """Назва кластера для повідомлень і кнопок."""

        return self.name

    @property
    def opening_time_text(self) -> str:
        """Час відкриття у форматі 08:00."""

        return self.opening_time.strftime("%H:%M")

    @property
    def opening_deadline_text(self) -> str:
        """Контрольний дедлайн у форматі 08:10."""

        return self.opening_control_deadline.strftime("%H:%M")

    @property
    def closing_time_text(self) -> str | None:
        """Час закриття у форматі 21:00."""

        if self.default_closing_time is None:
            return None

        return self.default_closing_time.strftime("%H:%M")

    @property
    def closing_deadline_text(self) -> str | None:
        """Дедлайн вечірнього звіту у форматі 21:15."""

        if self.default_closing_deadline is None:
            return None

        return self.default_closing_deadline.strftime("%H:%M")

    @property
    def active_stores_count(self) -> int:
        """
        Кількість активних торгових точок кластера.

        Працює після завантаження relationship stores.
        """

        return sum(
            1
            for store in self.stores
            if store.is_active
        )

    # ==========================================
    # METHODS
    # ==========================================

    def activate(self) -> None:
        """Активує кластер."""

        self.is_active = True

    def deactivate(self) -> None:
        """
        Деактивує кластер.

        Існуючі ТТ та історичні записи не видаляються,
        але кластер не показується при створенні нових ТТ.
        """

        self.is_active = False

    def update_opening_schedule(
        self,
        *,
        opening_time: time,
        control_deadline: time,
    ) -> None:
        """Змінює час відкриття і контрольний дедлайн."""

        if control_deadline < opening_time:
            raise ValueError(
                "Контрольний дедлайн відкриття "
                "не може бути раніше часу відкриття."
            )

        self.opening_time = opening_time
        self.opening_control_deadline = control_deadline

    def update_closing_schedule(
        self,
        *,
        closing_time: time | None,
        control_deadline: time | None,
    ) -> None:
        """Змінює стандартний графік закриття."""

        if (
            closing_time is not None
            and control_deadline is not None
            and control_deadline < closing_time
        ):
            raise ValueError(
                "Контрольний дедлайн закриття "
                "не може бути раніше часу закриття."
            )

        self.default_closing_time = closing_time
        self.default_closing_deadline = control_deadline