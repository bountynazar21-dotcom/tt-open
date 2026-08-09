from __future__ import annotations

import math
from dataclasses import dataclass
from typing import (
    Generic,
    Iterable,
    Sequence,
    TypeVar,
)


T = TypeVar("T")


# =========================================================
# CONSTANTS
# =========================================================


DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100


# =========================================================
# NORMALIZATION
# =========================================================


def normalize_page(
    page: int | str | None,
    *,
    default: int = DEFAULT_PAGE,
) -> int:
    """
    Нормалізує номер сторінки.

    Мінімум = 1.
    """

    try:
        value = int(
            page
        )
    except (
        TypeError,
        ValueError,
    ):
        return default

    return max(
        1,
        value,
    )


def normalize_page_size(
    page_size: int | str | None,
    *,
    default: int = DEFAULT_PAGE_SIZE,
    maximum: int = MAX_PAGE_SIZE,
) -> int:
    """
    Нормалізує розмір сторінки.
    """

    try:
        value = int(
            page_size
        )
    except (
        TypeError,
        ValueError,
    ):
        value = default

    value = max(
        1,
        value,
    )

    return min(
        value,
        maximum,
    )


# =========================================================
# CALCULATIONS
# =========================================================


def calculate_offset(
    page: int,
    page_size: int,
) -> int:
    """
    SQL offset для сторінки.

    page=1 -> 0
    page=2 -> page_size
    """

    normalized_page = (
        normalize_page(
            page
        )
    )

    normalized_size = (
        normalize_page_size(
            page_size
        )
    )

    return (
        normalized_page - 1
    ) * normalized_size


def calculate_total_pages(
    total_items: int,
    page_size: int,
) -> int:
    """
    Рахує загальну кількість сторінок.
    """

    total = max(
        0,
        int(total_items),
    )

    size = normalize_page_size(
        page_size
    )

    if total == 0:
        return 0

    return math.ceil(
        total / size
    )


def clamp_page(
    page: int,
    total_pages: int,
) -> int:
    """
    Обмежує page межами доступних сторінок.
    """

    page = normalize_page(
        page
    )

    if total_pages <= 0:
        return 1

    return min(
        page,
        total_pages,
    )


# =========================================================
# PAGE RESULT
# =========================================================


@dataclass(slots=True)
class Page(Generic[T]):
    """
    Універсальний результат пагінації.
    """

    items: list[T]
    page: int
    page_size: int
    total_items: int
    total_pages: int

    @property
    def has_next(self) -> bool:
        return (
            self.total_pages > 0
            and self.page < self.total_pages
        )

    @property
    def has_previous(self) -> bool:
        return (
            self.total_pages > 0
            and self.page > 1
        )

    @property
    def next_page(self) -> int | None:
        if not self.has_next:
            return None

        return (
            self.page + 1
        )

    @property
    def previous_page(self) -> int | None:
        if not self.has_previous:
            return None

        return (
            self.page - 1
        )

    @property
    def is_empty(self) -> bool:
        return not self.items

    @property
    def start_item_number(self) -> int:
        """
        Позиція першого елемента на сторінці.
        """

        if not self.items:
            return 0

        return (
            (self.page - 1)
            * self.page_size
            + 1
        )

    @property
    def end_item_number(self) -> int:
        """
        Позиція останнього елемента на сторінці.
        """

        if not self.items:
            return 0

        return (
            self.start_item_number
            + len(self.items)
            - 1
        )


# =========================================================
# PAGINATE SEQUENCE
# =========================================================


def paginate(
    items: Sequence[T]
    | Iterable[T],
    *,
    page: int = DEFAULT_PAGE,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> Page[T]:
    """
    Пагінація Python-колекції.
    """

    normalized_page = (
        normalize_page(
            page
        )
    )

    normalized_size = (
        normalize_page_size(
            page_size
        )
    )

    if not isinstance(
        items,
        Sequence,
    ):
        items = list(
            items
        )

    total_items = len(
        items
    )

    total_pages = (
        calculate_total_pages(
            total_items,
            normalized_size,
        )
    )

    if total_pages > 0:
        normalized_page = (
            clamp_page(
                normalized_page,
                total_pages,
            )
        )

    offset = calculate_offset(
        normalized_page,
        normalized_size,
    )

    page_items = list(
        items[
            offset:
            offset + normalized_size
        ]
    )

    return Page(
        items=page_items,
        page=normalized_page,
        page_size=normalized_size,
        total_items=total_items,
        total_pages=total_pages,
    )


# =========================================================
# DATABASE RESULT
# =========================================================


def build_page(
    items: Iterable[T],
    *,
    page: int,
    page_size: int,
    total_items: int,
) -> Page[T]:
    """
    Формує Page для результату з БД.

    Використання:

        items = await repo.list(
            limit=page_size,
            offset=offset,
        )

        total = await repo.count()

        return build_page(...)
    """

    normalized_page = (
        normalize_page(
            page
        )
    )

    normalized_size = (
        normalize_page_size(
            page_size
        )
    )

    total = max(
        0,
        int(total_items),
    )

    total_pages = (
        calculate_total_pages(
            total,
            normalized_size,
        )
    )

    return Page(
        items=list(
            items
        ),
        page=normalized_page,
        page_size=normalized_size,
        total_items=total,
        total_pages=total_pages,
    )


# =========================================================
# SIMPLE SLICE
# =========================================================


def page_slice(
    *,
    page: int,
    page_size: int,
) -> slice:
    """
    Повертає slice для Python-списку.
    """

    normalized_size = (
        normalize_page_size(
            page_size
        )
    )

    offset = calculate_offset(
        page,
        normalized_size,
    )

    return slice(
        offset,
        offset + normalized_size,
    )


# =========================================================
# PAGE NUMBERS
# =========================================================


def visible_page_numbers(
    *,
    current_page: int,
    total_pages: int,
    radius: int = 2,
) -> list[int]:
    """
    Список номерів сторінок навколо поточної.

    current=5, total=10, radius=2
    -> [3, 4, 5, 6, 7]
    """

    if total_pages <= 0:
        return []

    current = clamp_page(
        current_page,
        total_pages,
    )

    radius = max(
        0,
        int(radius),
    )

    start = max(
        1,
        current - radius,
    )

    end = min(
        total_pages,
        current + radius,
    )

    return list(
        range(
            start,
            end + 1,
        )
    )


# =========================================================
# DISPLAY
# =========================================================


def format_page_counter(
    page: int,
    total_pages: int,
) -> str:
    """
    Приклад:
        2 / 8
    """

    if total_pages <= 0:
        return "0 / 0"

    current = clamp_page(
        page,
        total_pages,
    )

    return (
        f"{current} / {total_pages}"
    )


def format_items_counter(
    *,
    page: int,
    page_size: int,
    total_items: int,
) -> str:
    """
    Приклад:
        11–20 із 47
    """

    total = max(
        0,
        int(total_items),
    )

    if total == 0:
        return "0 із 0"

    normalized_page = (
        normalize_page(
            page
        )
    )

    normalized_size = (
        normalize_page_size(
            page_size
        )
    )

    start = (
        (normalized_page - 1)
        * normalized_size
        + 1
    )

    end = min(
        start
        + normalized_size
        - 1,
        total,
    )

    return (
        f"{start}–{end} із {total}"
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "DEFAULT_PAGE",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",

    "normalize_page",
    "normalize_page_size",

    "calculate_offset",
    "calculate_total_pages",
    "clamp_page",

    "Page",

    "paginate",
    "build_page",
    "page_slice",

    "visible_page_numbers",

    "format_page_counter",
    "format_items_counter",
]