from __future__ import annotations

import asyncio
import sys
from datetime import time
from typing import Any

from sqlalchemy import select

from app.database.models.cluster import Cluster
from app.database.session import (
    async_session_factory,
)


# =========================================================
# DEFAULT DATA
# =========================================================


DEFAULT_CLUSTER_HOURS = (
    7,
    8,
    9,
    10,
)


# =========================================================
# MODEL HELPERS
# =========================================================


def model_has_field(
    model: type[Any],
    field_name: str,
) -> bool:
    """
    Перевіряє, чи SQLAlchemy model
    має конкретне поле.
    """

    return hasattr(
        model,
        field_name,
    )


def set_if_supported(
    target: Any,
    field_name: str,
    value: Any,
) -> bool:
    """
    Встановлює значення тільки якщо
    поле реально існує в model.
    """

    if not hasattr(
        target,
        field_name,
    ):
        return False

    setattr(
        target,
        field_name,
        value,
    )

    return True


# =========================================================
# CLUSTER VALUE
# =========================================================


def cluster_hour(
    cluster: Cluster,
) -> int | None:
    """
    Витягує годину відкриття
    з існуючого Cluster.

    Підтримує різні варіанти model:
    - opening_time
    - start_time
    - hour
    - opening_hour
    - name/code
    """

    for field_name in (
        "opening_time",
        "start_time",
    ):
        value = getattr(
            cluster,
            field_name,
            None,
        )

        if isinstance(
            value,
            time,
        ):
            return value.hour

    for field_name in (
        "hour",
        "opening_hour",
    ):
        value = getattr(
            cluster,
            field_name,
            None,
        )

        if value is None:
            continue

        try:
            hour = int(
                value
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        if 0 <= hour <= 23:
            return hour

    for field_name in (
        "name",
        "title",
        "code",
        "slug",
    ):
        value = getattr(
            cluster,
            field_name,
            None,
        )

        if not value:
            continue

        text = (
            str(value)
            .strip()
            .lower()
        )

        for hour in range(
            24
        ):
            variants = {
                str(hour),
                f"{hour:02d}",
                f"{hour:02d}:00",
                f"{hour}:00",
                f"cluster_{hour:02d}",
                f"cluster-{hour:02d}",
            }

            if text in variants:
                return hour

    return None


# =========================================================
# BUILD CLUSTER
# =========================================================


def build_cluster_kwargs(
    hour: int,
) -> dict[str, Any]:
    """
    Формує kwargs тільки для тих полів,
    які реально існують у Cluster model.
    """

    kwargs: dict[
        str,
        Any,
    ] = {}

    # -----------------------------------------
    # NAME
    # -----------------------------------------

    if model_has_field(
        Cluster,
        "name",
    ):
        kwargs[
            "name"
        ] = f"{hour:02d}:00"

    elif model_has_field(
        Cluster,
        "title",
    ):
        kwargs[
            "title"
        ] = f"{hour:02d}:00"

    # -----------------------------------------
    # CODE
    # -----------------------------------------

    if model_has_field(
        Cluster,
        "code",
    ):
        kwargs[
            "code"
        ] = (
            f"CLUSTER_{hour:02d}"
        )

    if model_has_field(
        Cluster,
        "slug",
    ):
        kwargs[
            "slug"
        ] = (
            f"cluster-{hour:02d}"
        )

    # -----------------------------------------
    # TIME
    # -----------------------------------------

    if model_has_field(
        Cluster,
        "opening_time",
    ):
        kwargs[
            "opening_time"
        ] = time(
            hour,
            0,
        )

    elif model_has_field(
        Cluster,
        "start_time",
    ):
        kwargs[
            "start_time"
        ] = time(
            hour,
            0,
        )

    elif model_has_field(
        Cluster,
        "hour",
    ):
        kwargs[
            "hour"
        ] = hour

    elif model_has_field(
        Cluster,
        "opening_hour",
    ):
        kwargs[
            "opening_hour"
        ] = hour

    # -----------------------------------------
    # ACTIVE
    # -----------------------------------------

    if model_has_field(
        Cluster,
        "is_active",
    ):
        kwargs[
            "is_active"
        ] = True

    # -----------------------------------------
    # DEADLINE
    # -----------------------------------------

    for field_name in (
        "deadline_minutes",
        "opening_deadline_minutes",
        "deadline_offset_minutes",
    ):
        if model_has_field(
            Cluster,
            field_name,
        ):
            kwargs[
                field_name
            ] = 10

            break

    return kwargs


# =========================================================
# UPDATE EXISTING
# =========================================================


def update_existing_cluster(
    cluster: Cluster,
    *,
    hour: int,
) -> bool:
    """
    Акуратно приводить існуючий cluster
    до базових значень.

    Повертає True, якщо щось змінилось.
    """

    changed = False

    # -----------------------------------------
    # ACTIVE
    # -----------------------------------------

    if hasattr(
        cluster,
        "is_active",
    ):
        if (
            getattr(
                cluster,
                "is_active",
                None,
            )
            is not True
        ):
            cluster.is_active = True
            changed = True

    # -----------------------------------------
    # OPENING TIME
    # -----------------------------------------

    expected_time = time(
        hour,
        0,
    )

    if hasattr(
        cluster,
        "opening_time",
    ):
        current = getattr(
            cluster,
            "opening_time",
            None,
        )

        if current != expected_time:
            cluster.opening_time = (
                expected_time
            )

            changed = True

    elif hasattr(
        cluster,
        "start_time",
    ):
        current = getattr(
            cluster,
            "start_time",
            None,
        )

        if current != expected_time:
            cluster.start_time = (
                expected_time
            )

            changed = True

    elif hasattr(
        cluster,
        "hour",
    ):
        if (
            getattr(
                cluster,
                "hour",
                None,
            )
            != hour
        ):
            cluster.hour = hour
            changed = True

    elif hasattr(
        cluster,
        "opening_hour",
    ):
        if (
            getattr(
                cluster,
                "opening_hour",
                None,
            )
            != hour
        ):
            cluster.opening_hour = (
                hour
            )

            changed = True

    return changed


# =========================================================
# VALIDATE MODEL
# =========================================================


def validate_cluster_model() -> None:
    """
    Перевіряє, що Cluster має хоча б
    одне поле, через яке можна визначити
    годину.
    """

    supported_fields = {
        "opening_time",
        "start_time",
        "hour",
        "opening_hour",
        "name",
        "title",
        "code",
        "slug",
    }

    available = {
        field_name
        for field_name
        in supported_fields
        if model_has_field(
            Cluster,
            field_name,
        )
    }

    if not available:
        raise RuntimeError(
            "Cluster model не має жодного "
            "підтримуваного поля для seed."
        )


# =========================================================
# SEED CLUSTERS
# =========================================================


async def seed_clusters(
    session,
) -> tuple[
    int,
    int,
    int,
]:
    """
    Створює відсутні кластери:

        07:00
        08:00
        09:00
        10:00

    Повертає:

        created,
        updated,
        unchanged
    """

    validate_cluster_model()

    result = await session.scalars(
        select(
            Cluster
        )
    )

    existing_clusters = list(
        result
        .unique()
        .all()
    )

    by_hour: dict[
        int,
        Cluster,
    ] = {}

    for cluster in existing_clusters:
        hour = cluster_hour(
            cluster
        )

        if hour is not None:
            by_hour[
                hour
            ] = cluster

    created = 0
    updated = 0
    unchanged = 0

    for hour in (
        DEFAULT_CLUSTER_HOURS
    ):
        existing = by_hour.get(
            hour
        )

        # -------------------------------------
        # UPDATE EXISTING
        # -------------------------------------

        if existing is not None:
            changed = (
                update_existing_cluster(
                    existing,
                    hour=hour,
                )
            )

            if changed:
                updated += 1

                print(
                    "🔄 Оновлено кластер "
                    f"{hour:02d}:00"
                )

            else:
                unchanged += 1

                print(
                    "✅ Кластер "
                    f"{hour:02d}:00 "
                    "вже існує."
                )

            continue

        # -------------------------------------
        # CREATE
        # -------------------------------------

        kwargs = (
            build_cluster_kwargs(
                hour
            )
        )

        if not kwargs:
            raise RuntimeError(
                "Не вдалося сформувати "
                "дані для Cluster."
            )

        cluster = Cluster(
            **kwargs
        )

        session.add(
            cluster
        )

        created += 1

        print(
            "🆕 Створено кластер "
            f"{hour:02d}:00"
        )

    await session.flush()

    return (
        created,
        updated,
        unchanged,
    )


# =========================================================
# MAIN SEED
# =========================================================


async def seed_data() -> None:
    async with (
        async_session_factory()
        as session
    ):
        try:
            (
                clusters_created,
                clusters_updated,
                clusters_unchanged,
            ) = await seed_clusters(
                session
            )

            await session.commit()

        except Exception:
            await session.rollback()
            raise

    print()
    print("=" * 50)
    print("SEED ЗАВЕРШЕНО")
    print("=" * 50)

    print(
        "Кластери створено: "
        f"{clusters_created}"
    )

    print(
        "Кластери оновлено: "
        f"{clusters_updated}"
    )

    print(
        "Кластери без змін: "
        f"{clusters_unchanged}"
    )

    print()
    print(
        "✅ Базові дані TT-open готові."
    )


# =========================================================
# ENTRYPOINT
# =========================================================


async def async_main() -> int:
    try:
        await seed_data()

    except Exception as error:
        print()
        print(
            "❌ SEED DATA ERROR"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        return 1

    return 0


def main() -> None:
    exit_code = asyncio.run(
        async_main()
    )

    sys.exit(
        exit_code
    )


if __name__ == "__main__":
    main()