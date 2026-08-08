from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from aiogram import Bot
from aiogram.types import (
    BufferedInputFile,
    Document,
    Message,
    PhotoSize,
)

from app.repositories import Repositories


class FileCategory(StrEnum):
    """
    Категорія файлу.
    """

    RECEIPT = "receipts"
    IMPORT = "imports"
    EXCEL = "excel"
    TEMP = "temp"
    OTHER = "other"


class TelegramUploadKind(StrEnum):
    """
    Тип Telegram-вкладення.
    """

    PHOTO = "photo"
    DOCUMENT = "document"


@dataclass(slots=True, frozen=True)
class TelegramUpload:
    """
    Файл, отриманий із Telegram.
    """

    file_id: str
    file_unique_id: str

    kind: TelegramUploadKind

    file_name: str | None
    mime_type: str | None

    file_size: int | None

    width: int | None = None
    height: int | None = None

    @property
    def extension(self) -> str | None:
        if not self.file_name:
            return None

        extension = Path(
            self.file_name
        ).suffix.lower()

        return extension or None


@dataclass(slots=True, frozen=True)
class FileValidationResult:
    """
    Результат перевірки файлу.
    """

    is_valid: bool

    category: FileCategory

    file_name: str | None
    mime_type: str | None

    file_size: int | None

    extension: str | None

    error: str | None

    @property
    def size_mb(self) -> float | None:
        if self.file_size is None:
            return None

        return (
            self.file_size
            / 1024
            / 1024
        )


@dataclass(slots=True, frozen=True)
class DownloadedFile:
    """
    Завантажений із Telegram файл.
    """

    file_id: str

    file_unique_id: str | None

    file_name: str
    mime_type: str | None

    extension: str

    content: bytes

    sha256: str

    size_bytes: int

    telegram_file_path: str | None

    category: FileCategory

    @property
    def size_kb(self) -> float:
        return (
            self.size_bytes
            / 1024
        )

    @property
    def size_mb(self) -> float:
        return (
            self.size_bytes
            / 1024
            / 1024
        )

    def as_buffered_input_file(
        self,
    ) -> BufferedInputFile:
        """
        Перетворює назад у Telegram-файл.
        """

        return BufferedInputFile(
            self.content,
            filename=self.file_name,
        )


@dataclass(slots=True, frozen=True)
class StoredFile:
    """
    Файл, записаний у локальне сховище.
    """

    path: Path

    relative_path: str

    file_name: str

    category: FileCategory

    size_bytes: int

    sha256: str

    created_at: datetime

    @property
    def exists(self) -> bool:
        return self.path.exists()

    @property
    def size_mb(self) -> float:
        return (
            self.size_bytes
            / 1024
            / 1024
        )


@dataclass(slots=True, frozen=True)
class SafeFilenameResult:
    """
    Результат нормалізації назви.
    """

    original_name: str

    safe_name: str

    extension: str

    was_changed: bool


class FileService:
    """
    Сервіс роботи з файлами.

    Підтримує:

    - Telegram photo;
    - Telegram document;
    - фото чеків;
    - Telegram file_id;
    - завантаження файлів;
    - перевірку MIME;
    - перевірку extension;
    - перевірку розміру;
    - перевірку сигнатури файлу;
    - безпечні назви;
    - локальне тимчасове збереження;
    - Excel-файли;
    - файли імпорту;
    - SHA-256.

    Для фото чеків у базі краще зберігати:

        receipt_file_id
        receipt_file_unique_id

    Сам файл не обов’язково тримати локально.
    """

    RECEIPT_MAX_BYTES = (
        10 * 1024 * 1024
    )

    IMPORT_MAX_BYTES = (
        25 * 1024 * 1024
    )

    EXCEL_MAX_BYTES = (
        50 * 1024 * 1024
    )

    TEMP_MAX_BYTES = (
        50 * 1024 * 1024
    )

    OTHER_MAX_BYTES = (
        25 * 1024 * 1024
    )

    IMAGE_EXTENSIONS = frozenset(
        {
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        }
    )

    IMAGE_MIME_TYPES = frozenset(
        {
            "image/jpeg",
            "image/jpg",
            "image/png",
            "image/webp",
        }
    )

    IMPORT_EXTENSIONS = frozenset(
        {
            ".xlsx",
            ".xls",
            ".csv",
        }
    )

    IMPORT_MIME_TYPES = frozenset(
        {
            (
                "application/"
                "vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            "application/vnd.ms-excel",
            "text/csv",
            "application/csv",
            "text/plain",
            "application/octet-stream",
        }
    )

    EXCEL_EXTENSIONS = frozenset(
        {
            ".xlsx",
        }
    )

    EXCEL_MIME_TYPES = frozenset(
        {
            (
                "application/"
                "vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            "application/octet-stream",
        }
    )

    WINDOWS_RESERVED_NAMES = frozenset(
        {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            "COM1",
            "COM2",
            "COM3",
            "COM4",
            "COM5",
            "COM6",
            "COM7",
            "COM8",
            "COM9",
            "LPT1",
            "LPT2",
            "LPT3",
            "LPT4",
            "LPT5",
            "LPT6",
            "LPT7",
            "LPT8",
            "LPT9",
        }
    )

    INVALID_FILENAME_PATTERN = re.compile(
        r'[<>:"/\\|?*\x00-\x1f]'
    )

    MULTIPLE_UNDERSCORES = re.compile(
        r"_+"
    )

    def __init__(
        self,
        repositories: Repositories,
        *,
        bot: Bot | None = None,
        storage_dir: str | Path = "data/files",
    ) -> None:
        self.repositories = repositories
        self.bot = bot

        self.storage_dir = Path(
            storage_dir
        ).resolve()

    # ==========================================
    # BOT
    # ==========================================

    def require_bot(self) -> Bot:
        """
        Повертає Telegram Bot.
        """

        if self.bot is None:
            raise RuntimeError(
                "Для завантаження Telegram-файлів "
                "потрібно передати Bot у FileService."
            )

        return self.bot

    # ==========================================
    # TELEGRAM MESSAGE
    # ==========================================

    def extract_upload(
        self,
        message: Message,
        *,
        prefer_photo: bool = True,
    ) -> TelegramUpload | None:
        """
        Витягує файл із Message.

        Для фото Telegram надсилає декілька
        розмірів. Беремо найбільший.
        """

        if (
            prefer_photo
            and message.photo
        ):
            return self.upload_from_photo(
                message.photo[-1]
            )

        if message.document:
            return self.upload_from_document(
                message.document
            )

        if message.photo:
            return self.upload_from_photo(
                message.photo[-1]
            )

        return None

    def extract_receipt_upload(
        self,
        message: Message,
    ) -> TelegramUpload:
        """
        Витягує фото чека.
        """

        upload = self.extract_upload(
            message,
            prefer_photo=True,
        )

        if upload is None:
            raise ValueError(
                "Надішліть фото чека."
            )

        validation = self.validate_upload(
            upload,
            category=FileCategory.RECEIPT,
        )

        if not validation.is_valid:
            raise ValueError(
                validation.error
                or "Некоректне фото чека."
            )

        return upload

    def extract_import_upload(
        self,
        message: Message,
    ) -> TelegramUpload:
        """
        Витягує Excel/CSV для імпорту.
        """

        if message.document is None:
            raise ValueError(
                "Надішліть файл Excel або CSV "
                "як документ."
            )

        upload = self.upload_from_document(
            message.document
        )

        validation = self.validate_upload(
            upload,
            category=FileCategory.IMPORT,
        )

        if not validation.is_valid:
            raise ValueError(
                validation.error
                or "Некоректний файл імпорту."
            )

        return upload

    # ==========================================
    # PHOTO / DOCUMENT
    # ==========================================

    @staticmethod
    def upload_from_photo(
        photo: PhotoSize,
    ) -> TelegramUpload:
        """
        Формує TelegramUpload із PhotoSize.
        """

        return TelegramUpload(
            file_id=photo.file_id,
            file_unique_id=(
                photo.file_unique_id
            ),
            kind=(
                TelegramUploadKind.PHOTO
            ),
            file_name=None,
            mime_type="image/jpeg",
            file_size=photo.file_size,
            width=photo.width,
            height=photo.height,
        )

    @staticmethod
    def upload_from_document(
        document: Document,
    ) -> TelegramUpload:
        """
        Формує TelegramUpload із Document.
        """

        return TelegramUpload(
            file_id=document.file_id,
            file_unique_id=(
                document.file_unique_id
            ),
            kind=(
                TelegramUploadKind.DOCUMENT
            ),
            file_name=document.file_name,
            mime_type=document.mime_type,
            file_size=document.file_size,
        )

    # ==========================================
    # ВАЛІДАЦІЯ TELEGRAM UPLOAD
    # ==========================================

    def validate_upload(
        self,
        upload: TelegramUpload,
        *,
        category: FileCategory,
    ) -> FileValidationResult:
        """
        Перевіряє Telegram-файл
        до його завантаження.
        """

        extension = (
            upload.extension
            or self.extension_from_mime(
                upload.mime_type
            )
        )

        max_size = self.max_size_for_category(
            category
        )

        if (
            upload.file_size is not None
            and upload.file_size > max_size
        ):
            return FileValidationResult(
                is_valid=False,
                category=category,
                file_name=upload.file_name,
                mime_type=upload.mime_type,
                file_size=upload.file_size,
                extension=extension,
                error=(
                    "Файл занадто великий. "
                    "Максимальний розмір: "
                    f"{self.format_size(max_size)}."
                ),
            )

        if category == FileCategory.RECEIPT:
            return self.validate_receipt_upload(
                upload,
                extension=extension,
            )

        if category == FileCategory.IMPORT:
            return self.validate_import_upload(
                upload,
                extension=extension,
            )

        if category == FileCategory.EXCEL:
            return self.validate_excel_upload(
                upload,
                extension=extension,
            )

        return FileValidationResult(
            is_valid=True,
            category=category,
            file_name=upload.file_name,
            mime_type=upload.mime_type,
            file_size=upload.file_size,
            extension=extension,
            error=None,
        )

    def validate_receipt_upload(
        self,
        upload: TelegramUpload,
        *,
        extension: str | None,
    ) -> FileValidationResult:
        """
        Перевіряє фото чека.
        """

        if (
            upload.kind
            == TelegramUploadKind.PHOTO
        ):
            return FileValidationResult(
                is_valid=True,
                category=(
                    FileCategory.RECEIPT
                ),
                file_name=upload.file_name,
                mime_type=upload.mime_type,
                file_size=upload.file_size,
                extension=(
                    extension or ".jpg"
                ),
                error=None,
            )

        mime_valid = (
            upload.mime_type
            in self.IMAGE_MIME_TYPES
        )

        extension_valid = (
            extension
            in self.IMAGE_EXTENSIONS
        )

        if (
            not mime_valid
            and not extension_valid
        ):
            return FileValidationResult(
                is_valid=False,
                category=(
                    FileCategory.RECEIPT
                ),
                file_name=upload.file_name,
                mime_type=upload.mime_type,
                file_size=upload.file_size,
                extension=extension,
                error=(
                    "Чек повинен бути зображенням "
                    "JPG, PNG або WEBP."
                ),
            )

        return FileValidationResult(
            is_valid=True,
            category=FileCategory.RECEIPT,
            file_name=upload.file_name,
            mime_type=upload.mime_type,
            file_size=upload.file_size,
            extension=extension,
            error=None,
        )

    def validate_import_upload(
        self,
        upload: TelegramUpload,
        *,
        extension: str | None,
    ) -> FileValidationResult:
        """
        Перевіряє файл імпорту.
        """

        if (
            extension
            not in self.IMPORT_EXTENSIONS
        ):
            return FileValidationResult(
                is_valid=False,
                category=(
                    FileCategory.IMPORT
                ),
                file_name=upload.file_name,
                mime_type=upload.mime_type,
                file_size=upload.file_size,
                extension=extension,
                error=(
                    "Для імпорту дозволені "
                    "файли XLSX, XLS або CSV."
                ),
            )

        if (
            upload.mime_type
            and upload.mime_type
            not in self.IMPORT_MIME_TYPES
        ):
            return FileValidationResult(
                is_valid=False,
                category=(
                    FileCategory.IMPORT
                ),
                file_name=upload.file_name,
                mime_type=upload.mime_type,
                file_size=upload.file_size,
                extension=extension,
                error=(
                    "Telegram визначив "
                    "непідтримуваний тип файлу."
                ),
            )

        return FileValidationResult(
            is_valid=True,
            category=FileCategory.IMPORT,
            file_name=upload.file_name,
            mime_type=upload.mime_type,
            file_size=upload.file_size,
            extension=extension,
            error=None,
        )

    def validate_excel_upload(
        self,
        upload: TelegramUpload,
        *,
        extension: str | None,
    ) -> FileValidationResult:
        """
        Перевіряє XLSX.
        """

        if (
            extension
            not in self.EXCEL_EXTENSIONS
        ):
            return FileValidationResult(
                is_valid=False,
                category=FileCategory.EXCEL,
                file_name=upload.file_name,
                mime_type=upload.mime_type,
                file_size=upload.file_size,
                extension=extension,
                error=(
                    "Очікується файл XLSX."
                ),
            )

        return FileValidationResult(
            is_valid=True,
            category=FileCategory.EXCEL,
            file_name=upload.file_name,
            mime_type=upload.mime_type,
            file_size=upload.file_size,
            extension=extension,
            error=None,
        )

    # ==========================================
    # ЗАВАНТАЖЕННЯ З TELEGRAM
    # ==========================================

    async def download_upload(
        self,
        upload: TelegramUpload,
        *,
        category: FileCategory,
        preferred_name: str | None = None,
    ) -> DownloadedFile:
        """
        Завантажує TelegramUpload у пам’ять.
        """

        validation = self.validate_upload(
            upload,
            category=category,
        )

        if not validation.is_valid:
            raise ValueError(
                validation.error
                or "Некоректний файл."
            )

        return await self.download_file(
            file_id=upload.file_id,
            category=category,
            preferred_name=(
                preferred_name
                or upload.file_name
            ),
            mime_type=upload.mime_type,
            expected_size=upload.file_size,
            file_unique_id=(
                upload.file_unique_id
            ),
        )

    async def download_file(
        self,
        *,
        file_id: str,
        category: FileCategory,
        preferred_name: str | None = None,
        mime_type: str | None = None,
        expected_size: int | None = None,
        file_unique_id: str | None = None,
    ) -> DownloadedFile:
        """
        Завантажує файл за Telegram file_id.
        """

        normalized_file_id = (
            str(file_id).strip()
        )

        if not normalized_file_id:
            raise ValueError(
                "Telegram file_id порожній."
            )

        bot = self.require_bot()

        telegram_file = await bot.get_file(
            normalized_file_id
        )

        telegram_path = (
            telegram_file.file_path
        )

        if not telegram_path:
            raise RuntimeError(
                "Telegram не повернув "
                "шлях до файлу."
            )

        telegram_size = getattr(
            telegram_file,
            "file_size",
            None,
        )

        known_size = (
            telegram_size
            or expected_size
        )

        max_size = self.max_size_for_category(
            category
        )

        if (
            known_size is not None
            and known_size > max_size
        ):
            raise ValueError(
                "Файл занадто великий. "
                "Максимум: "
                f"{self.format_size(max_size)}."
            )

        buffer = BytesIO()

        await bot.download_file(
            telegram_path,
            destination=buffer,
        )

        content = buffer.getvalue()

        if not content:
            raise ValueError(
                "Telegram повернув "
                "порожній файл."
            )

        if len(content) > max_size:
            raise ValueError(
                "Файл занадто великий. "
                "Максимум: "
                f"{self.format_size(max_size)}."
            )

        extension = (
            self.extension_from_filename(
                preferred_name
            )
            or self.extension_from_mime(
                mime_type
            )
            or self.detect_extension(
                content
            )
            or self.default_extension(
                category
            )
        )

        file_name = self.safe_filename(
            preferred_name
            or self.default_filename(
                category=category,
                extension=extension,
            ),
            forced_extension=extension,
        ).safe_name

        self.validate_downloaded_content(
            content=content,
            category=category,
            extension=extension,
        )

        return DownloadedFile(
            file_id=normalized_file_id,
            file_unique_id=(
                file_unique_id
                or getattr(
                    telegram_file,
                    "file_unique_id",
                    None,
                )
            ),
            file_name=file_name,
            mime_type=(
                mime_type
                or self.mime_from_extension(
                    extension
                )
            ),
            extension=extension,
            content=content,
            sha256=self.sha256(content),
            size_bytes=len(content),
            telegram_file_path=(
                telegram_path
            ),
            category=category,
        )

    # ==========================================
    # ПЕРЕВІРКА ФАКТИЧНОГО КОНТЕНТУ
    # ==========================================

    def validate_downloaded_content(
        self,
        *,
        content: bytes,
        category: FileCategory,
        extension: str,
    ) -> None:
        """
        Перевіряє сигнатуру вже
        завантаженого файлу.
        """

        if not content:
            raise ValueError(
                "Файл порожній."
            )

        if category == FileCategory.RECEIPT:
            detected = self.detect_extension(
                content
            )

            if (
                detected
                not in self.IMAGE_EXTENSIONS
            ):
                raise ValueError(
                    "Вміст файлу не схожий "
                    "на зображення."
                )

            return

        if category == FileCategory.EXCEL:
            if not self.is_xlsx_content(
                content
            ):
                raise ValueError(
                    "Файл має розширення XLSX, "
                    "але його вміст не схожий "
                    "на Excel XLSX."
                )

            return

        if category == FileCategory.IMPORT:
            if extension == ".xlsx":
                if not self.is_xlsx_content(
                    content
                ):
                    raise ValueError(
                        "Некоректний XLSX-файл."
                    )

            elif extension == ".xls":
                if not self.is_xls_content(
                    content
                ):
                    raise ValueError(
                        "Некоректний XLS-файл."
                    )

            elif extension == ".csv":
                if self.looks_binary(
                    content
                ):
                    raise ValueError(
                        "CSV-файл містить "
                        "бінарні дані."
                    )

    # ==========================================
    # ЛОКАЛЬНЕ ЗБЕРЕЖЕННЯ
    # ==========================================

    async def save_downloaded(
        self,
        downloaded: DownloadedFile,
        *,
        business_date: date | None = None,
        unique_name: bool = True,
    ) -> StoredFile:
        """
        Зберігає завантажений файл локально.
        """

        return await self.save_bytes(
            content=downloaded.content,
            category=downloaded.category,
            file_name=downloaded.file_name,
            business_date=business_date,
            unique_name=unique_name,
        )

    async def save_bytes(
        self,
        *,
        content: bytes,
        category: FileCategory,
        file_name: str,
        business_date: date | None = None,
        unique_name: bool = True,
    ) -> StoredFile:
        """
        Безпечно записує bytes на диск.
        """

        if not content:
            raise ValueError(
                "Не можна зберегти "
                "порожній файл."
            )

        max_size = self.max_size_for_category(
            category
        )

        if len(content) > max_size:
            raise ValueError(
                "Файл перевищує "
                "допустимий розмір."
            )

        safe = self.safe_filename(
            file_name
        )

        directory = self.category_directory(
            category=category,
            business_date=business_date,
        )

        await asyncio.to_thread(
            directory.mkdir,
            parents=True,
            exist_ok=True,
        )

        final_name = safe.safe_name

        if unique_name:
            final_name = self.unique_filename(
                final_name
            )

        target = (
            directory
            / final_name
        ).resolve()

        self.ensure_inside_storage(
            target
        )

        temporary = (
            target.parent
            / (
                f".{target.name}."
                f"{uuid4().hex}.tmp"
            )
        )

        def write_file() -> None:
            with temporary.open(
                "wb"
            ) as file_handle:
                file_handle.write(
                    content
                )

            temporary.replace(
                target
            )

        try:
            await asyncio.to_thread(
                write_file
            )

        finally:
            if temporary.exists():
                try:
                    await asyncio.to_thread(
                        temporary.unlink
                    )
                except OSError:
                    pass

        relative_path = str(
            target.relative_to(
                self.storage_dir
            )
        )

        return StoredFile(
            path=target,
            relative_path=relative_path,
            file_name=target.name,
            category=category,
            size_bytes=len(content),
            sha256=self.sha256(
                content
            ),
            created_at=datetime.now()
            .astimezone(),
        )

    # ==========================================
    # ЧИТАННЯ ЛОКАЛЬНОГО ФАЙЛУ
    # ==========================================

    async def read_stored_file(
        self,
        path: str | Path,
    ) -> bytes:
        """
        Читає лише файл усередині storage_dir.
        """

        resolved = self.resolve_storage_path(
            path
        )

        if not resolved.exists():
            raise FileNotFoundError(
                "Файл не знайдено."
            )

        if not resolved.is_file():
            raise ValueError(
                "Шлях не є файлом."
            )

        return await asyncio.to_thread(
            resolved.read_bytes
        )

    # ==========================================
    # ВИДАЛЕННЯ
    # ==========================================

    async def delete_stored_file(
        self,
        path: str | Path,
        *,
        missing_ok: bool = True,
    ) -> bool:
        """
        Видаляє локальний файл.

        Не дозволяє вийти за storage_dir.
        """

        resolved = self.resolve_storage_path(
            path
        )

        if not resolved.exists():
            if missing_ok:
                return False

            raise FileNotFoundError(
                "Файл не знайдено."
            )

        if not resolved.is_file():
            raise ValueError(
                "Шлях не є файлом."
            )

        await asyncio.to_thread(
            resolved.unlink
        )

        return True

    # ==========================================
    # STORAGE PATH
    # ==========================================

    def category_directory(
        self,
        *,
        category: FileCategory,
        business_date: date | None = None,
    ) -> Path:
        """
        Формує каталог категорії.
        """

        directory = (
            self.storage_dir
            / category.value
        )

        if business_date is not None:
            directory = (
                directory
                / f"{business_date.year:04d}"
                / f"{business_date.month:02d}"
                / f"{business_date.day:02d}"
            )

        resolved = directory.resolve()

        self.ensure_inside_storage(
            resolved
        )

        return resolved

    def resolve_storage_path(
        self,
        path: str | Path,
    ) -> Path:
        """
        Безпечно нормалізує storage path.
        """

        supplied = Path(path)

        if supplied.is_absolute():
            resolved = supplied.resolve()

        else:
            resolved = (
                self.storage_dir
                / supplied
            ).resolve()

        self.ensure_inside_storage(
            resolved
        )

        return resolved

    def ensure_inside_storage(
        self,
        path: Path,
    ) -> None:
        """
        Захист від path traversal.
        """

        root = self.storage_dir.resolve()
        resolved = path.resolve()

        if (
            resolved != root
            and root
            not in resolved.parents
        ):
            raise ValueError(
                "Некоректний шлях до файлу."
            )

    # ==========================================
    # SAFE FILENAME
    # ==========================================

    def safe_filename(
        self,
        file_name: str,
        *,
        forced_extension: str | None = None,
        max_length: int = 180,
    ) -> SafeFilenameResult:
        """
        Формує безпечне ім’я файлу.
        """

        original = str(
            file_name or ""
        ).strip()

        if not original:
            original = "file"

        original_path = Path(
            original
        )

        extension = (
            forced_extension
            or original_path.suffix
        ).lower()

        if extension:
            if not extension.startswith("."):
                extension = (
                    f".{extension}"
                )

            extension = re.sub(
                r"[^a-zA-Z0-9.]",
                "",
                extension,
            ).lower()

        stem = (
            original_path.stem
            if original_path.suffix
            else original_path.name
        )

        stem = self.INVALID_FILENAME_PATTERN.sub(
            "_",
            stem,
        )

        stem = re.sub(
            r"\s+",
            "_",
            stem,
        )

        stem = re.sub(
            r"[^0-9A-Za-zА-Яа-яІіЇїЄєҐґ._()-]",
            "_",
            stem,
        )

        stem = self.MULTIPLE_UNDERSCORES.sub(
            "_",
            stem,
        )

        stem = stem.strip(
            " ._-"
        )

        if not stem:
            stem = "file"

        if (
            stem.upper()
            in self.WINDOWS_RESERVED_NAMES
        ):
            stem = (
                f"file_{stem}"
            )

        extension_length = len(
            extension
        )

        max_stem_length = max(
            1,
            max_length
            - extension_length,
        )

        stem = stem[
            :max_stem_length
        ].rstrip(
            " ."
        )

        safe_name = (
            f"{stem}{extension}"
        )

        return SafeFilenameResult(
            original_name=original,
            safe_name=safe_name,
            extension=extension,
            was_changed=(
                safe_name != original
            ),
        )

    # ==========================================
    # НАЗВА EXCEL
    # ==========================================

    def build_excel_filename(
        self,
        *,
        prefix: str,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> str:
        """
        Генерує назву XLSX-звіту.
        """

        safe_prefix = self.safe_filename(
            prefix,
            forced_extension="",
        ).safe_name

        parts = [
            safe_prefix
        ]

        if (
            date_from is not None
            and date_to is not None
        ):
            if date_from == date_to:
                parts.append(
                    date_from.strftime(
                        "%Y-%m-%d"
                    )
                )

            else:
                parts.append(
                    date_from.strftime(
                        "%Y-%m-%d"
                    )
                )

                parts.append(
                    date_to.strftime(
                        "%Y-%m-%d"
                    )
                )

        elif date_from is not None:
            parts.append(
                date_from.strftime(
                    "%Y-%m-%d"
                )
            )

        result = "_".join(
            part
            for part in parts
            if part
        )

        return self.safe_filename(
            result,
            forced_extension=".xlsx",
        ).safe_name

    # ==========================================
    # НАЗВА IMPORT
    # ==========================================

    def build_import_filename(
        self,
        *,
        original_name: str | None,
        prefix: str = "import",
    ) -> str:
        """
        Формує безпечну назву імпорту.
        """

        extension = (
            self.extension_from_filename(
                original_name
            )
            or ".xlsx"
        )

        timestamp = (
            datetime.now()
            .astimezone()
            .strftime(
                "%Y%m%d_%H%M%S"
            )
        )

        return self.safe_filename(
            (
                f"{prefix}_"
                f"{timestamp}_"
                f"{original_name or 'file'}"
            ),
            forced_extension=extension,
        ).safe_name

    # ==========================================
    # UNIQUE FILE NAME
    # ==========================================

    @staticmethod
    def unique_filename(
        file_name: str,
    ) -> str:
        """
        Додає короткий UUID до назви.
        """

        path = Path(
            file_name
        )

        token = uuid4().hex[:10]

        return (
            f"{path.stem}_"
            f"{token}"
            f"{path.suffix}"
        )

    # ==========================================
    # DEFAULT FILE NAME
    # ==========================================

    @staticmethod
    def default_filename(
        *,
        category: FileCategory,
        extension: str,
    ) -> str:
        """
        Стандартне ім’я файлу.
        """

        timestamp = (
            datetime.now()
            .astimezone()
            .strftime(
                "%Y%m%d_%H%M%S"
            )
        )

        return (
            f"{category.value}_"
            f"{timestamp}_"
            f"{uuid4().hex[:8]}"
            f"{extension}"
        )

    @staticmethod
    def default_extension(
        category: FileCategory,
    ) -> str:
        """
        Стандартне розширення.
        """

        if (
            category
            == FileCategory.RECEIPT
        ):
            return ".jpg"

        if (
            category
            == FileCategory.EXCEL
        ):
            return ".xlsx"

        if (
            category
            == FileCategory.IMPORT
        ):
            return ".xlsx"

        return ".bin"

    # ==========================================
    # EXTENSION
    # ==========================================

    @staticmethod
    def extension_from_filename(
        file_name: str | None,
    ) -> str | None:
        """
        Отримує extension із назви.
        """

        if not file_name:
            return None

        suffix = Path(
            file_name
        ).suffix.lower()

        return suffix or None

    @staticmethod
    def extension_from_mime(
        mime_type: str | None,
    ) -> str | None:
        """
        Отримує extension із MIME.
        """

        if not mime_type:
            return None

        explicit = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",

            (
                "application/"
                "vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ): ".xlsx",

            "application/vnd.ms-excel": (
                ".xls"
            ),

            "text/csv": ".csv",
            "application/csv": ".csv",
        }

        result = explicit.get(
            mime_type.lower()
        )

        if result:
            return result

        guessed = mimetypes.guess_extension(
            mime_type
        )

        if guessed:
            return guessed.lower()

        return None

    @staticmethod
    def mime_from_extension(
        extension: str,
    ) -> str | None:
        """
        Отримує MIME за extension.
        """

        explicit = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",

            ".xlsx": (
                "application/"
                "vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),

            ".xls": (
                "application/vnd.ms-excel"
            ),

            ".csv": "text/csv",
        }

        return explicit.get(
            extension.lower()
        )

    # ==========================================
    # MAGIC / SIGNATURE
    # ==========================================

    @staticmethod
    def detect_extension(
        content: bytes,
    ) -> str | None:
        """
        Визначає тип файлу за сигнатурою.
        """

        if content.startswith(
            b"\xff\xd8\xff"
        ):
            return ".jpg"

        if content.startswith(
            b"\x89PNG\r\n\x1a\n"
        ):
            return ".png"

        if (
            len(content) >= 12
            and content[:4] == b"RIFF"
            and content[8:12] == b"WEBP"
        ):
            return ".webp"

        if FileService.is_xlsx_content(
            content
        ):
            return ".xlsx"

        if FileService.is_xls_content(
            content
        ):
            return ".xls"

        return None

    @staticmethod
    def is_xlsx_content(
        content: bytes,
    ) -> bool:
        """
        XLSX — ZIP-контейнер.
        """

        return content.startswith(
            (
                b"PK\x03\x04",
                b"PK\x05\x06",
                b"PK\x07\x08",
            )
        )

    @staticmethod
    def is_xls_content(
        content: bytes,
    ) -> bool:
        """
        Старий XLS — OLE Compound File.
        """

        return content.startswith(
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
        )

    @staticmethod
    def looks_binary(
        content: bytes,
        *,
        sample_size: int = 8192,
    ) -> bool:
        """
        Груба перевірка CSV на binary.
        """

        sample = content[
            :sample_size
        ]

        if not sample:
            return False

        if b"\x00" in sample:
            return True

        control_count = sum(
            (
                byte < 9
                or 13 < byte < 32
            )
            for byte in sample
        )

        ratio = (
            control_count
            / len(sample)
        )

        return ratio > 0.10

    # ==========================================
    # HASH
    # ==========================================

    @staticmethod
    def sha256(
        content: bytes,
    ) -> str:
        """
        SHA-256 файлу.
        """

        return hashlib.sha256(
            content
        ).hexdigest()

    # ==========================================
    # MAX SIZE
    # ==========================================

    @classmethod
    def max_size_for_category(
        cls,
        category: FileCategory,
    ) -> int:
        """
        Максимальний розмір категорії.
        """

        mapping = {
            FileCategory.RECEIPT: (
                cls.RECEIPT_MAX_BYTES
            ),
            FileCategory.IMPORT: (
                cls.IMPORT_MAX_BYTES
            ),
            FileCategory.EXCEL: (
                cls.EXCEL_MAX_BYTES
            ),
            FileCategory.TEMP: (
                cls.TEMP_MAX_BYTES
            ),
            FileCategory.OTHER: (
                cls.OTHER_MAX_BYTES
            ),
        }

        return mapping[
            category
        ]

    # ==========================================
    # FORMAT SIZE
    # ==========================================

    @staticmethod
    def format_size(
        size_bytes: int,
    ) -> str:
        """
        Форматує розмір файлу.
        """

        if size_bytes < 1024:
            return (
                f"{size_bytes} Б"
            )

        size_kb = (
            size_bytes / 1024
        )

        if size_kb < 1024:
            return (
                f"{size_kb:.1f} КБ"
            )

        size_mb = (
            size_kb / 1024
        )

        return (
            f"{size_mb:.1f} МБ"
        )

    # ==========================================
    # TELEGRAM FORMAT
    # ==========================================

    @classmethod
    def format_upload(
        cls,
        upload: TelegramUpload,
    ) -> str:
        """
        Коротка інформація про файл.
        """

        name = (
            upload.file_name
            or (
                "Фото"
                if upload.kind
                == TelegramUploadKind.PHOTO
                else "Файл"
            )
        )

        size_text = (
            cls.format_size(
                upload.file_size
            )
            if upload.file_size
            is not None
            else "невідомо"
        )

        lines = [
            f"📎 <b>{name}</b>",
            (
                "Розмір: "
                f"<b>{size_text}</b>"
            ),
        ]

        if upload.mime_type:
            lines.append(
                "Тип: "
                f"<code>{upload.mime_type}</code>"
            )

        if (
            upload.width is not None
            and upload.height is not None
        ):
            lines.append(
                "Роздільна здатність: "
                f"<b>{upload.width}×"
                f"{upload.height}</b>"
            )

        return "\n".join(
            lines
        )


__all__ = [
    "FileService",
    "FileCategory",
    "TelegramUploadKind",
    "TelegramUpload",
    "FileValidationResult",
    "DownloadedFile",
    "StoredFile",
    "SafeFilenameResult",
]