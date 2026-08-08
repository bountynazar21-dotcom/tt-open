from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
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
from app.database.models.enums import StoreStatus


if TYPE_CHECKING:
    from app.database.models.binding import UserStoreBinding
    from app.database.models.bush import Bush
    from app.database.models.closing_report import ClosingReport
    from app.database.models.cluster import Cluster
    from app.database.models.invite import InviteLink
    from app.database.models.notification import NotificationLog
    from app.database.models.opening_checkin import OpeningCheckin
    from app.database.models.schedule import (
        ScheduleException,
        StoreSchedule,
    )
    from app.database.models.user import User


class Store(
    IntegerPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """
    Торгова точка мережі.

    Торгова точка існує окремо від Telegram-користувачів.
    До однієї ТТ може бути прив'язано декілька працівників.

    При кіку ТТ не видаляється фізично з бази:
    - історія відкриттів зберігається;
    - історія закриттів зберігається;
    - касові звіти зберігаються;
    - ТТ перестає потрапляти у щоденний контроль.
    """

    __table_args__ = (
        CheckConstraint(
            "store_number > 0",
            name="store_number_positive",
        ),
        Index(
            "ix_stores_city_active",
            "city",
            "is_active",
        ),
        Index(
            "ix_stores_bush_active",
            "bush_id",
            "is_active",
        ),
        Index(
            "ix_stores_cluster_active",
            "cluster_id",
            "is_active",
        ),
        Index(
            "ix_stores_status_city",
            "status",
            "city",
        ),
    )

    # ==========================================
    # ОСНОВНА ІНФОРМАЦІЯ
    # ==========================================

    store_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        unique=True,
        index=True,
        comment="Числовий номер торгової точки",
    )

    code: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
        index=True,
        comment="Код торгової точки, наприклад SB-76",
    )

    name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        comment="Додаткова назва торгової точки",
    )

    address: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Повна адреса торгової точки",
    )

    city: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
        comment="Місто торгової точки",
    )

    phone: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="Контактний номер торгової точки",
    )

    store_format: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Формат магазину або торгової точки",
    )

    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Europe/Kyiv",
        server_default="Europe/Kyiv",
        comment="Часовий пояс торгової точки",
    )

    telegram_topic_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Окрема тема ТТ у Telegram-групі",
    )

    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Внутрішня примітка адміністратора",
    )

    # ==========================================
    # КУЩ І КЛАСТЕР
    # ==========================================

    bush_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "bushes.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Кущ, до якого належить ТТ",
    )

    cluster_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "clusters.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Кластер часу відкриття",
    )

    # ==========================================
    # СТАТУС ТОРГОВОЇ ТОЧКИ
    # ==========================================

    status: Mapped[StoreStatus] = mapped_column(
        Enum(
            StoreStatus,
            name="store_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_class: [
                item.value
                for item in enum_class
            ],
        ),
        nullable=False,
        default=StoreStatus.ACTIVE,
        server_default=StoreStatus.ACTIVE.value,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        index=True,
        comment="Чи бере ТТ участь у щоденному контролі",
    )

    temporarily_closed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="До якої дати ТТ тимчасово зачинена",
    )

    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата і час деактивації ТТ",
    )

    deactivated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Адміністратор, який кікнув ТТ",
    )

    deactivation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Причина деактивації або тимчасового закриття",
    )

    # ==========================================
    # RELATIONSHIPS
    # ==========================================

    bush: Mapped[Bush | None] = relationship(
        "Bush",
        back_populates="stores",
        lazy="joined",
    )

    cluster: Mapped[Cluster | None] = relationship(
        "Cluster",
        back_populates="stores",
        lazy="joined",
    )

    deactivated_by: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[deactivated_by_id],
        lazy="joined",
    )

    user_bindings: Mapped[list[UserStoreBinding]] = relationship(
        "UserStoreBinding",
        back_populates="store",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    schedules: Mapped[list[StoreSchedule]] = relationship(
        "StoreSchedule",
        back_populates="store",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    schedule_exceptions: Mapped[list[ScheduleException]] = relationship(
        "ScheduleException",
        back_populates="store",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    opening_checkins: Mapped[list[OpeningCheckin]] = relationship(
        "OpeningCheckin",
        back_populates="store",
        lazy="raise",
    )

    closing_reports: Mapped[list[ClosingReport]] = relationship(
        "ClosingReport",
        back_populates="store",
        lazy="raise",
    )

    invite_links: Mapped[list[InviteLink]] = relationship(
        "InviteLink",
        back_populates="store",
        lazy="raise",
    )

    notification_logs: Mapped[list[NotificationLog]] = relationship(
        "NotificationLog",
        back_populates="store",
        lazy="raise",
    )

    # ==========================================
    # СТВОРЕННЯ ТТ
    # ==========================================

    @classmethod
    def create(
        cls,
        *,
        store_number: int,
        address: str,
        city: str,
        name: str | None = None,
        phone: str | None = None,
        store_format: str | None = None,
        bush_id: int | None = None,
        cluster_id: int | None = None,
        note: str | None = None,
    ) -> Store:
        """
        Створює нову торгову точку.

        Код SB формується автоматично з номера.
        """

        if store_number <= 0:
            raise ValueError(
                "Номер торгової точки повинен бути більшим за нуль."
            )

        normalized_city = city.strip()
        normalized_address = address.strip()

        if not normalized_city:
            raise ValueError(
                "Місто торгової точки не може бути порожнім."
            )

        if not normalized_address:
            raise ValueError(
                "Адреса торгової точки не може бути порожньою."
            )

        return cls(
            store_number=store_number,
            code=cls.build_code(store_number),
            name=name.strip() if name else None,
            address=normalized_address,
            city=normalized_city,
            phone=phone.strip() if phone else None,
            store_format=(
                store_format.strip()
                if store_format
                else None
            ),
            bush_id=bush_id,
            cluster_id=cluster_id,
            note=note.strip() if note else None,
            status=StoreStatus.ACTIVE,
            is_active=True,
        )

    @staticmethod
    def build_code(store_number: int) -> str:
        """Формує код торгової точки, наприклад SB-76."""

        if store_number <= 0:
            raise ValueError(
                "Номер торгової точки повинен бути більшим за нуль."
            )

        return f"SB-{store_number}"

    # ==========================================
    # PROPERTIES
    # ==========================================

    @property
    def display_name(self) -> str:
        """Коротка назва торгової точки."""

        return self.code

    @property
    def full_display_name(self) -> str:
        """Назва ТТ разом із містом та адресою."""

        return (
            f"{self.code} — "
            f"{self.city}, {self.address}"
        )

    @property
    def is_temporarily_closed(self) -> bool:
        """Чи має ТТ статус тимчасово зачиненої."""

        return self.status == StoreStatus.TEMPORARILY_CLOSED

    @property
    def is_ready_for_monitoring(self) -> bool:
        """
        Чи готова ТТ до ранкового та вечірнього контролю.

        Для роботи повинні бути:
        - активний статус;
        - кущ;
        - кластер.
        """

        return (
            self.is_active
            and self.status == StoreStatus.ACTIVE
            and self.bush_id is not None
            and self.cluster_id is not None
        )

    @property
    def bush_name(self) -> str | None:
        """Назва куща, якщо він призначений."""

        if self.bush is None:
            return None

        return self.bush.name

    @property
    def cluster_name(self) -> str | None:
        """Назва кластера, якщо він призначений."""

        if self.cluster is None:
            return None

        return self.cluster.name

    # ==========================================
    # КЕРУВАННЯ ТОРГОВОЮ ТОЧКОЮ
    # ==========================================

    def activate(self) -> None:
        """
        Повторно активує торгову точку.

        Після цього ТТ знову братиме участь у контролі,
        якщо для неї призначені кущ і кластер.
        """

        self.status = StoreStatus.ACTIVE
        self.is_active = True

        self.temporarily_closed_until = None
        self.deactivated_at = None
        self.deactivated_by_id = None
        self.deactivation_reason = None

    def deactivate(
        self,
        *,
        deactivated_at: datetime,
        deactivated_by_id: int,
        reason: str | None = None,
    ) -> None:
        """
        Кікає торгову точку із системи контролю.

        Запис ТТ та вся історія залишаються у базі.
        """

        self.status = StoreStatus.INACTIVE
        self.is_active = False

        self.deactivated_at = deactivated_at
        self.deactivated_by_id = deactivated_by_id
        self.deactivation_reason = (
            reason.strip()
            if reason
            else None
        )

        self.temporarily_closed_until = None

    def temporarily_close(
        self,
        *,
        closed_until: datetime | None,
        reason: str | None = None,
        changed_by_id: int | None = None,
        changed_at: datetime | None = None,
    ) -> None:
        """
        Тимчасово закриває торгову точку.

        Наприклад:
        - ремонт;
        - переїзд;
        - технічні причини;
        - тимчасове припинення роботи.
        """

        self.status = StoreStatus.TEMPORARILY_CLOSED
        self.is_active = False

        self.temporarily_closed_until = closed_until
        self.deactivation_reason = (
            reason.strip()
            if reason
            else None
        )

        self.deactivated_by_id = changed_by_id
        self.deactivated_at = changed_at

    def move_to_bush(
        self,
        bush_id: int | None,
    ) -> None:
        """Переносить торгову точку в інший кущ."""

        self.bush_id = bush_id

    def change_cluster(
        self,
        cluster_id: int | None,
    ) -> None:
        """Змінює кластер відкриття торгової точки."""

        self.cluster_id = cluster_id

    def change_store_number(
        self,
        new_store_number: int,
    ) -> None:
        """Змінює номер ТТ та автоматично оновлює код SB."""

        if new_store_number <= 0:
            raise ValueError(
                "Новий номер ТТ повинен бути більшим за нуль."
            )

        self.store_number = new_store_number
        self.code = self.build_code(new_store_number)

    def update_location(
        self,
        *,
        city: str,
        address: str,
    ) -> None:
        """Оновлює місто та адресу торгової точки."""

        normalized_city = city.strip()
        normalized_address = address.strip()

        if not normalized_city:
            raise ValueError(
                "Місто не може бути порожнім."
            )

        if not normalized_address:
            raise ValueError(
                "Адреса не може бути порожньою."
            )

        self.city = normalized_city
        self.address = normalized_address