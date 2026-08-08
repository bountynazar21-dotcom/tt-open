from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import (
    Select,
    delete,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.database.base import Base
from app.logging_config import get_logger


logger = get_logger(__name__)


ModelType = TypeVar(
    "ModelType",
    bound=Base,
)


class BaseRepository(Generic[ModelType]):
    """
    Базовий асинхронний репозиторій SQLAlchemy.

    Кожен окремий репозиторій успадковуватиметься від нього.

    Приклад:

        class UserRepository(BaseRepository[User]):
            model = User

    Використання:

        repository = UserRepository(session)
        user = await repository.get_by_id(1)
    """

    model: type[ModelType]

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

        if not hasattr(self, "model"):
            raise TypeError(
                f"{self.__class__.__name__} повинен мати поле model."
            )

    # ==========================================
    # СТВОРЕННЯ
    # ==========================================

    async def add(
        self,
        instance: ModelType,
        *,
        flush: bool = True,
        refresh: bool = False,
    ) -> ModelType:
        """
        Додає один об’єкт до сесії.

        flush=True:
        - SQL-запит виконується одразу;
        - ID запису стає доступним;
        - транзакція ще не комітиться.

        refresh=True:
        - повторно завантажує запис із бази.
        """

        self.session.add(instance)

        if flush:
            await self.session.flush()

        if refresh:
            await self.session.refresh(instance)

        return instance

    async def add_many(
        self,
        instances: Iterable[ModelType],
        *,
        flush: bool = True,
    ) -> list[ModelType]:
        """Додає декілька об’єктів до сесії."""

        instance_list = list(instances)

        if not instance_list:
            return []

        self.session.add_all(instance_list)

        if flush:
            await self.session.flush()

        return instance_list

    async def create(
        self,
        *,
        flush: bool = True,
        refresh: bool = False,
        **values: Any,
    ) -> ModelType:
        """
        Створює модель із переданих значень.

        Приклад:

            user = await repository.create(
                telegram_id=123,
                full_name="Назар",
            )
        """

        instance = self.model(**values)

        return await self.add(
            instance,
            flush=flush,
            refresh=refresh,
        )

    # ==========================================
    # ПОШУК ЗА ПЕРВИННИМ КЛЮЧЕМ
    # ==========================================

    async def get_by_id(
        self,
        object_id: Any,
    ) -> ModelType | None:
        """Повертає запис за первинним ключем."""

        return await self.session.get(
            self.model,
            object_id,
        )

    async def get_by_id_or_raise(
        self,
        object_id: Any,
        *,
        error_message: str | None = None,
    ) -> ModelType:
        """
        Повертає запис за ID або викликає ValueError.
        """

        instance = await self.get_by_id(object_id)

        if instance is None:
            raise ValueError(
                error_message
                or (
                    f"{self.model.__name__} "
                    f"з ID {object_id} не знайдено."
                )
            )

        return instance

    async def get_by_ids(
        self,
        object_ids: Iterable[Any],
    ) -> list[ModelType]:
        """Повертає записи за списком первинних ключів."""

        normalized_ids = list(dict.fromkeys(object_ids))

        if not normalized_ids:
            return []

        primary_key = self._get_primary_key_column()

        statement = select(self.model).where(
            primary_key.in_(normalized_ids)
        )

        result = await self.session.scalars(statement)

        return list(result.unique().all())

    # ==========================================
    # ПОШУК ЗА ПОЛЯМИ
    # ==========================================

    async def get_one(
        self,
        **filters: Any,
    ) -> ModelType | None:
        """
        Повертає один запис за рівністю полів.

        Приклад:

            user = await repository.get_one(
                telegram_id=5480082089,
            )
        """

        statement = self._base_select()
        statement = self._apply_equal_filters(
            statement,
            filters,
        )
        statement = statement.limit(1)

        result = await self.session.scalars(statement)

        return result.unique().first()

    async def get_one_or_raise(
        self,
        *,
        error_message: str | None = None,
        **filters: Any,
    ) -> ModelType:
        """Повертає запис або викликає ValueError."""

        instance = await self.get_one(**filters)

        if instance is None:
            raise ValueError(
                error_message
                or (
                    f"{self.model.__name__} "
                    f"не знайдено за фільтрами {filters}."
                )
            )

        return instance

    async def get_many(
        self,
        *,
        filters: Sequence[ColumnElement[bool]] | None = None,
        order_by: Sequence[
            ColumnElement[Any] | InstrumentedAttribute[Any]
        ]
        | None = None,
        limit: int | None = None,
        offset: int = 0,
        unique: bool = True,
        **equal_filters: Any,
    ) -> list[ModelType]:
        """
        Повертає список записів.

        filters:
            складні SQLAlchemy-умови.

        equal_filters:
            прості умови рівності.

        Приклад:

            stores = await repository.get_many(
                filters=[
                    Store.city == "Вінниця",
                    Store.is_active.is_(True),
                ],
                order_by=[Store.store_number.asc()],
                limit=20,
            )
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        statement = self._base_select()

        statement = self._apply_equal_filters(
            statement,
            equal_filters,
        )

        if filters:
            statement = statement.where(*filters)

        if order_by:
            statement = statement.order_by(*order_by)

        if offset:
            statement = statement.offset(offset)

        if limit is not None:
            statement = statement.limit(limit)

        result = await self.session.scalars(statement)

        if unique:
            return list(result.unique().all())

        return list(result.all())

    async def get_all(
        self,
        *,
        order_by: Sequence[
            ColumnElement[Any] | InstrumentedAttribute[Any]
        ]
        | None = None,
    ) -> list[ModelType]:
        """Повертає всі записи моделі."""

        return await self.get_many(
            order_by=order_by,
        )

    # ==========================================
    # КІЛЬКІСТЬ ТА ІСНУВАННЯ
    # ==========================================

    async def count(
        self,
        *,
        filters: Sequence[ColumnElement[bool]] | None = None,
        **equal_filters: Any,
    ) -> int:
        """Підраховує кількість записів."""

        statement = select(
            func.count()
        ).select_from(self.model)

        statement = self._apply_equal_filters(
            statement,
            equal_filters,
        )

        if filters:
            statement = statement.where(*filters)

        result = await self.session.scalar(statement)

        return int(result or 0)

    async def exists(
        self,
        *,
        filters: Sequence[ColumnElement[bool]] | None = None,
        **equal_filters: Any,
    ) -> bool:
        """Перевіряє існування хоча б одного запису."""

        statement = select(
            select(self.model)
            .limit(1)
            .exists()
        )

        inner_statement = select(self.model)

        inner_statement = self._apply_equal_filters(
            inner_statement,
            equal_filters,
        )

        if filters:
            inner_statement = inner_statement.where(*filters)

        statement = select(
            inner_statement.exists()
        )

        result = await self.session.scalar(statement)

        return bool(result)

    # ==========================================
    # ОНОВЛЕННЯ
    # ==========================================

    async def update_instance(
        self,
        instance: ModelType,
        *,
        flush: bool = True,
        refresh: bool = False,
        **values: Any,
    ) -> ModelType:
        """
        Оновлює поля вже завантаженого об’єкта.

        Невідомі поля викликають ValueError.
        """

        if not values:
            return instance

        self._validate_model_fields(values)

        for field_name, field_value in values.items():
            setattr(
                instance,
                field_name,
                field_value,
            )

        self.session.add(instance)

        if flush:
            await self.session.flush()

        if refresh:
            await self.session.refresh(instance)

        return instance

    async def update_by_id(
        self,
        object_id: Any,
        *,
        flush: bool = True,
        refresh: bool = False,
        error_message: str | None = None,
        **values: Any,
    ) -> ModelType:
        """Знаходить запис за ID та оновлює його."""

        instance = await self.get_by_id_or_raise(
            object_id,
            error_message=error_message,
        )

        return await self.update_instance(
            instance,
            flush=flush,
            refresh=refresh,
            **values,
        )

    # ==========================================
    # ВИДАЛЕННЯ
    # ==========================================

    async def delete_instance(
        self,
        instance: ModelType,
        *,
        flush: bool = True,
    ) -> None:
        """
        Фізично видаляє запис із бази.

        Для ТТ, користувачів, кущів та історичних даних
        цей метод у звичайній бізнес-логіці не використовуємо.

        Для них застосовуємо deactivate/revoke/block.
        """

        await self.session.delete(instance)

        if flush:
            await self.session.flush()

    async def delete_by_id(
        self,
        object_id: Any,
        *,
        flush: bool = True,
    ) -> bool:
        """
        Фізично видаляє запис за ID.

        Повертає False, якщо запису не існує.
        """

        instance = await self.get_by_id(object_id)

        if instance is None:
            return False

        await self.delete_instance(
            instance,
            flush=flush,
        )

        return True

    async def delete_many_permanently(
        self,
        *,
        filters: Sequence[ColumnElement[bool]],
        flush: bool = True,
    ) -> int:
        """
        Фізично видаляє записи за умовами.

        Використовувати лише для службових або тимчасових даних.
        """

        if not filters:
            raise ValueError(
                "Масове видалення без фільтрів заборонене."
            )

        statement = delete(self.model).where(*filters)

        result = await self.session.execute(statement)

        if flush:
            await self.session.flush()

        return int(result.rowcount or 0)

    # ==========================================
    # ТРАНЗАКЦІЇ
    # ==========================================

    async def flush(self) -> None:
        """Відправляє накопичені зміни до бази без commit."""

        await self.session.flush()

    async def commit(self) -> None:
        """Підтверджує поточну транзакцію."""

        try:
            await self.session.commit()

        except Exception:
            await self.session.rollback()

            logger.exception(
                "Помилка commit для репозиторію %s",
                self.__class__.__name__,
            )

            raise

    async def rollback(self) -> None:
        """Відкочує поточну транзакцію."""

        await self.session.rollback()

    async def refresh(
        self,
        instance: ModelType,
        *,
        attribute_names: Iterable[str] | None = None,
    ) -> ModelType:
        """Повторно завантажує модель із бази."""

        names = (
            list(attribute_names)
            if attribute_names is not None
            else None
        )

        await self.session.refresh(
            instance,
            attribute_names=names,
        )

        return instance

    # ==========================================
    # ДОПОМІЖНІ МЕТОДИ
    # ==========================================

    def _base_select(self) -> Select[tuple[ModelType]]:
        """Створює базовий SELECT для моделі."""

        return select(self.model)

    def _get_primary_key_column(
        self,
    ) -> InstrumentedAttribute[Any]:
        """Повертає єдиний первинний ключ моделі."""

        mapper = inspect(self.model)

        primary_keys = mapper.primary_key

        if len(primary_keys) != 1:
            raise RuntimeError(
                f"Модель {self.model.__name__} повинна мати "
                "рівно один первинний ключ."
            )

        primary_key_name = primary_keys[0].key

        return getattr(
            self.model,
            primary_key_name,
        )

    def _apply_equal_filters(
        self,
        statement: Select[Any],
        filters: dict[str, Any],
    ) -> Select[Any]:
        """Додає прості фільтри рівності."""

        if not filters:
            return statement

        self._validate_model_fields(filters)

        conditions: list[ColumnElement[bool]] = []

        for field_name, field_value in filters.items():
            model_field = getattr(
                self.model,
                field_name,
            )

            if field_value is None:
                conditions.append(
                    model_field.is_(None)
                )
            else:
                conditions.append(
                    model_field == field_value
                )

        return statement.where(*conditions)

    def _validate_model_fields(
        self,
        values: dict[str, Any],
    ) -> None:
        """Перевіряє існування полів у SQLAlchemy-моделі."""

        mapper = inspect(self.model)

        available_fields = {
            attribute.key
            for attribute in mapper.attrs
        }

        unknown_fields = (
            set(values)
            - available_fields
        )

        if unknown_fields:
            formatted_fields = ", ".join(
                sorted(unknown_fields)
            )

            raise ValueError(
                f"Модель {self.model.__name__} "
                f"не містить полів: {formatted_fields}."
            )

    @staticmethod
    def _validate_pagination(
        *,
        limit: int | None,
        offset: int,
    ) -> None:
        """Перевіряє параметри пагінації."""

        if offset < 0:
            raise ValueError(
                "Offset не може бути від’ємним."
            )

        if limit is not None and limit <= 0:
            raise ValueError(
                "Limit повинен бути більшим за нуль."
            )

        if limit is not None and limit > 10_000:
            raise ValueError(
                "За один запит дозволено отримати "
                "не більше 10 000 записів."
            )