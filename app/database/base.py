from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declared_attr,
    mapped_column,
)


# Єдині правила назв для індексів і обмежень.
# Це важливо для Alembic: назви міграцій будуть стабільними
# та зрозумілими.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": (
        "fk_%(table_name)s_"
        "%(column_0_name)s_"
        "%(referred_table_name)s"
    ),
    "pk": "pk_%(table_name)s",
}


metadata = MetaData(
    naming_convention=NAMING_CONVENTION,
)


def camel_to_snake(value: str) -> str:
    """
    Перетворює назву Python-класу в назву таблиці.

    Приклади:
    UserStoreBinding -> user_store_bindings
    OpeningCheckin   -> opening_checkins
    """

    first_pass = re.sub(
        r"(.)([A-Z][a-z]+)",
        r"\1_\2",
        value,
    )

    snake_case = re.sub(
        r"([a-z0-9])([A-Z])",
        r"\1_\2",
        first_pass,
    ).lower()

    return snake_case


class Base(DeclarativeBase):
    """
    Базовий клас для всіх SQLAlchemy-моделей.

    Кожна модель успадковуватиметься від Base.
    """

    metadata = metadata

    @declared_attr.directive
    def __tablename__(cls) -> str:
        """
        Автоматично створює назву таблиці з назви класу.

        Наприкінці додається літера `s`.

        User -> users
        Store -> stores
        Cluster -> clusters
        """

        table_name = camel_to_snake(cls.__name__)

        if table_name.endswith("s"):
            return table_name

        return f"{table_name}s"

    def to_dict(self) -> dict[str, Any]:
        """
        Перетворює завантажені поля моделі у словник.

        Не виконує додаткових SQL-запитів
        і не завантажує relationships автоматично.
        """

        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }

    def __repr__(self) -> str:
        """
        Зручне представлення моделі в логах.

        Наприклад:
        <User id=1>
        """

        primary_key_columns = self.__table__.primary_key.columns

        primary_key_values = " ".join(
            (
                f"{column.name}="
                f"{getattr(self, column.name, None)!r}"
            )
            for column in primary_key_columns
        )

        return (
            f"<{self.__class__.__name__} "
            f"{primary_key_values}>"
        )


class IntegerPrimaryKeyMixin:
    """Додає звичайний числовий первинний ключ."""

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )


class TimestampMixin:
    """
    Додає час створення та оновлення запису.

    Використовується PostgreSQL TIMESTAMP WITH TIME ZONE.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )