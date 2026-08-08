from __future__ import annotations

from functools import cached_property

from aiogram import Bot

from app.repositories import Repositories

# =========================================================
# ACCESS
# =========================================================

from app.services.access import (
    AccessDecision,
    AccessDeniedError,
    AccessPermission,
    AccessService,
    UserAccessScope,
)

# =========================================================
# AUDIT
# =========================================================

from app.services.audit_service import (
    AuditEntryView,
    AuditExportRow,
    AuditFilter,
    AuditPage,
    AuditService,
    AuditStatistics,
)

# =========================================================
# AUTH
# =========================================================

from app.services.auth_service import (
    AuthService,
    PendingUserView,
    RootAdminBootstrapResult,
    UserApprovalResult,
    UserAssignmentResult,
    UserRejectionResult,
    UserRoleChangeResult,
    UserStateChangeResult,
)

# =========================================================
# BINDINGS
# =========================================================

from app.services.binding_service import (
    BindingChangeResult,
    BindingDeactivationResult,
    BindingScope,
    BindingService,
    BindingView,
    BulkBindingItemResult,
    BulkBindingResult,
    BushTransferResult,
    StoreTransferResult,
    UserBindingsResult,
)

# =========================================================
# BUSHES
# =========================================================

from app.services.bush_service import (
    BushBulkItemResult,
    BushBulkResult,
    BushChangeResult,
    BushCreateData,
    BushService,
    BushStatistics,
    BushStatusChangeResult,
    BushStoreMoveResult,
    BushView,
)

# =========================================================
# CASH
# =========================================================

from app.services.cash_service import (
    CashChangeResult,
    CashCorrectionResult,
    CashEntryView,
    CashPeriodReport,
    CashPeriodTotals,
    CashService,
    CashStoreSummary,
    CashValidationResult,
)

# =========================================================
# CLOSING
# =========================================================

from app.services.closing_service import (
    ClosingDeadlineResult,
    ClosingManualUpdateResult,
    ClosingPreparationResult,
    ClosingService,
    ClosingSubmissionResult,
    ReceiptAttachmentResult,
)

# =========================================================
# CLUSTERS
# =========================================================

from app.services.cluster_service import (
    BulkClusterAssignmentItem,
    BulkClusterAssignmentResult,
    ClusterChangeResult,
    ClusterControlTimes,
    ClusterCreateData,
    ClusterLatenessResult,
    ClusterService,
    ClusterStatusChangeResult,
    ClusterStoreAssignmentResult,
    ClusterView,
    DefaultClustersResult,
)

# =========================================================
# EXCEL
# =========================================================

from app.services.excel_service import (
    ExcelService,
    GeneratedExcelFile,
    PreparedSheetData,
)

# =========================================================
# FILES
# =========================================================

from app.services.file_service import (
    DownloadedFile,
    FileCategory,
    FileService,
    FileValidationResult,
    SafeFilenameResult,
    StoredFile,
    TelegramUpload,
    TelegramUploadKind,
)

# =========================================================
# TELEGRAM GROUPS
# =========================================================

from app.services.group_service import (
    BotGroupAccessResult,
    GroupBindingView,
    GroupChangeResult,
    GroupService,
    TelegramDestination,
    TelegramGroupScope,
    TelegramGroupTopic,
    TopicChangeResult,
)

# =========================================================
# IMPORT
# =========================================================

from app.services.import_service import (
    ImportApplyItemResult,
    ImportApplyResult,
    ImportFileFormat,
    ImportIssue,
    ImportIssueLevel,
    ImportPreview,
    ImportRowStatus,
    ImportService,
    ParsedTable,
    StoreImportRow,
)

# =========================================================
# INVITES
# =========================================================

from app.services.invite_service import (
    InviteActivationServiceResult,
    InviteCreationServiceResult,
    InvitePayload,
    InviteRevocationResult,
    InviteScope,
    InviteService,
)

# =========================================================
# NOTIFICATIONS
# =========================================================

from app.services.notification_service import (
    DeliveryResultStatus,
    NotificationBatchResult,
    NotificationDeliveryResult,
    NotificationService,
    QueueNotificationResult,
)

# =========================================================
# OPENING
# =========================================================

from app.services.opening_service import (
    OpeningConfirmationResult,
    OpeningDeadlineResult,
    OpeningManualUpdateResult,
    OpeningPreparationResult,
    OpeningService,
)

# =========================================================
# REPORTS
# =========================================================

from app.services.report_service import (
    DailyReportResult,
    DailyReportTotals,
    ExcelReportData,
    ExcelSheetData,
    PeriodReportResult,
    PeriodReportTotals,
    ReportPeriodType,
    ReportScope,
    ReportScopeType,
    ReportService,
    StoreDailyReportRow,
    StorePeriodSummary,
)

# =========================================================
# SCHEDULE
# =========================================================

from app.services.schedule_service import (
    ClusterAssignmentResult,
    ScheduleDeletionResult,
    ScheduleExceptionChangeResult,
    SchedulePreviewItem,
    ScheduleService,
    WeekdayScheduleChangeResult,
)

# =========================================================
# SETTINGS
# =========================================================

from app.services.settings_service import (
    BulkSettingsChangeResult,
    SettingView,
    SettingsChangeResult,
    SettingsDashboard,
    SettingsService,
)

# =========================================================
# STORES
# =========================================================

from app.services.store_service import (
    StoreBulkItemResult,
    StoreBulkResult,
    StoreBushChangeResult,
    StoreChangeResult,
    StoreClusterChangeResult,
    StoreCreateData,
    StoreService,
    StoreStatusChangeResult,
    StoreView,
)

# =========================================================
# SUMMARIES
# =========================================================

from app.services.summary_service import (
    PreparedSummaryUpdate,
    SummaryBatchResult,
    SummaryService,
    SummarySyncResult,
    SummarySyncStatus,
)

# =========================================================
# USERS
# =========================================================

from app.services.user_service import (
    AdminUsersDashboard,
    UserAccessView,
    UserListFilter,
    UserListItem,
    UserProfileUpdateResult,
    UserProfileView,
    UserRoleUpdateResult,
    UserSearchResult,
    UserService,
    UserStatistics,
    UserStatusUpdateResult,
)


class Services:
    """
    Центральний контейнер сервісів застосунку.

    Один update Telegram отримує:

        AsyncSession
            ↓
        Repositories
            ↓
        Services

    Усі сервіси в межах одного update
    використовують одну й ту саму DB session.

    Сервіси створюються ліниво через
    cached_property.
    """

    def __init__(
        self,
        repositories: Repositories,
        *,
        bot: Bot | None = None,
        bot_username: str | None = None,
        file_storage_dir: str = "data/files",
    ) -> None:
        self.repositories = repositories

        self.bot = bot

        self.bot_username = (
            bot_username
            .strip()
            .lstrip("@")
            if bot_username
            else None
        )

        self.file_storage_dir = (
            file_storage_dir
        )

    # =====================================================
    # ACCESS
    # =====================================================

    @cached_property
    def access(self) -> AccessService:
        """
        Права та області доступу.
        """

        return AccessService(
            self.repositories
        )

    # =====================================================
    # AUTH
    # =====================================================

    @cached_property
    def auth(self) -> AuthService:
        """
        Підтвердження користувачів,
        ролі, блокування та активація.
        """

        return AuthService(
            self.repositories,
            access_service=self.access,
        )

    # =====================================================
    # USERS
    # =====================================================

    @cached_property
    def users(self) -> UserService:
        """
        Профілі та списки користувачів.
        """

        return UserService(
            self.repositories,
            access_service=self.access,
        )

    # =====================================================
    # BINDINGS
    # =====================================================

    @cached_property
    def bindings(self) -> BindingService:
        """
        Прив’язки користувачів до
        ТТ та кущів.
        """

        return BindingService(
            self.repositories,
            access_service=self.access,
        )

    # =====================================================
    # STORES
    # =====================================================

    @cached_property
    def stores(self) -> StoreService:
        """
        Торгові точки.
        """

        return StoreService(
            self.repositories,
            access_service=self.access,
        )

    # =====================================================
    # BUSHES
    # =====================================================

    @cached_property
    def bushes(self) -> BushService:
        """
        Кущі мережі.
        """

        return BushService(
            self.repositories,
            access_service=self.access,
        )

    # =====================================================
    # CLUSTERS
    # =====================================================

    @cached_property
    def clusters(self) -> ClusterService:
        """
        Кластери відкриття.
        """

        return ClusterService(
            self.repositories,
            access_service=self.access,
        )

    # =====================================================
    # SCHEDULE
    # =====================================================

    @cached_property
    def schedule(self) -> ScheduleService:
        """
        Графіки роботи ТТ.
        """

        return ScheduleService(
            self.repositories,
            access_service=self.access,
        )

    # =====================================================
    # OPENING
    # =====================================================

    @cached_property
    def opening(self) -> OpeningService:
        """
        Ранкове відкриття ТТ.
        """

        return OpeningService(
            self.repositories,
            access_service=self.access,
        )

    # =====================================================
    # CLOSING
    # =====================================================

    @cached_property
    def closing(self) -> ClosingService:
        """
        Вечірнє закриття ТТ.
        """

        return ClosingService(
            self.repositories,
            access_service=self.access,
        )

    # =====================================================
    # CASH
    # =====================================================

    @cached_property
    def cash(self) -> CashService:
        """
        Каса при закритті.
        """

        return CashService(
            self.repositories,
            access_service=self.access,
        )

    # =====================================================
    # SETTINGS
    # =====================================================

    @cached_property
    def settings(self) -> SettingsService:
        """
        Системні налаштування.
        """

        return SettingsService(
            self.repositories,
            access_service=self.access,
        )

    # =====================================================
    # GROUPS
    # =====================================================

    @cached_property
    def groups(self) -> GroupService:
        """
        Telegram-групи та topics.
        """

        return GroupService(
            self.repositories,
            access_service=self.access,
            bot=self.bot,
        )

    # =====================================================
    # FILES
    # =====================================================

    @cached_property
    def files(self) -> FileService:
        """
        Фото чеків, XLSX, імпорти
        та Telegram file_id.
        """

        return FileService(
            self.repositories,
            bot=self.bot,
            storage_dir=(
                self.file_storage_dir
            ),
        )

    # =====================================================
    # IMPORT
    # =====================================================

    @cached_property
    def imports(self) -> ImportService:
        """
        Імпорт торгових точок.
        """

        return ImportService(
            self.repositories,
            access_service=self.access,
            store_service=self.stores,
        )

    # =====================================================
    # INVITES
    # =====================================================

    @cached_property
    def invites(self) -> InviteService:
        """
        Deep-link запрошення.
        """

        return InviteService(
            self.repositories,
            bot_username=(
                self.require_bot_username()
            ),
            access_service=self.access,
        )

    # =====================================================
    # NOTIFICATIONS
    # =====================================================

    @cached_property
    def notifications(
        self,
    ) -> NotificationService:
        """
        Telegram-повідомлення.
        """

        return NotificationService(
            self.repositories,
            self.require_bot(),
        )

    # =====================================================
    # SUMMARIES
    # =====================================================

    @cached_property
    def summaries(
        self,
    ) -> SummaryService:
        """
        Live-підсумки відкриття
        та закриття.
        """

        return SummaryService(
            self.repositories,
            self.require_bot(),
        )

    # =====================================================
    # REPORTS
    # =====================================================

    @cached_property
    def reports(self) -> ReportService:
        """
        Денні / тижневі /
        місячні звіти.
        """

        return ReportService(
            self.repositories,
            access_service=self.access,
        )

    # =====================================================
    # EXCEL
    # =====================================================

    @cached_property
    def excel(self) -> ExcelService:
        """
        Генерація XLSX.
        """

        return ExcelService()

    # =====================================================
    # AUDIT
    # =====================================================

    @cached_property
    def audit(self) -> AuditService:
        """
        AuditLog.
        """

        return AuditService(
            self.repositories,
            access_service=self.access,
        )

    # =====================================================
    # TELEGRAM BOT
    # =====================================================

    def require_bot(self) -> Bot:
        """
        Повертає Bot або кидає помилку.
        """

        if self.bot is None:
            raise RuntimeError(
                "Цей сервіс потребує "
                "екземпляр aiogram Bot."
            )

        return self.bot

    # =====================================================
    # BOT USERNAME
    # =====================================================

    def require_bot_username(
        self,
    ) -> str:
        """
        Повертає username бота.
        """

        if not self.bot_username:
            raise RuntimeError(
                "Для InviteService потрібно "
                "передати bot_username."
            )

        return self.bot_username

    # =====================================================
    # SESSION
    # =====================================================

    @property
    def session(self):
        """
        Поточна AsyncSession.
        """

        return self.repositories.session

    # =====================================================
    # TRANSACTIONS
    # =====================================================

    async def flush(self) -> None:
        """
        Flush без commit.
        """

        await self.repositories.session.flush()

    async def commit(self) -> None:
        """
        Commit транзакції.
        """

        await self.repositories.session.commit()

    async def rollback(self) -> None:
        """
        Rollback транзакції.
        """

        await self.repositories.session.rollback()


# =========================================================
# FACTORY
# =========================================================


def create_services(
    repositories: Repositories,
    *,
    bot: Bot | None = None,
    bot_username: str | None = None,
    file_storage_dir: str = "data/files",
) -> Services:
    """
    Фабрика контейнера сервісів.
    """

    return Services(
        repositories,
        bot=bot,
        bot_username=bot_username,
        file_storage_dir=file_storage_dir,
    )


ServiceContainer = Services


# =========================================================
# EXPORTS
# =========================================================

__all__ = [
    # -----------------------------------------------------
    # CONTAINER
    # -----------------------------------------------------

    "Services",
    "ServiceContainer",
    "create_services",

    # -----------------------------------------------------
    # ACCESS
    # -----------------------------------------------------

    "AccessService",
    "AccessPermission",
    "AccessDecision",
    "AccessDeniedError",
    "UserAccessScope",

    # -----------------------------------------------------
    # AUTH
    # -----------------------------------------------------

    "AuthService",
    "PendingUserView",
    "UserApprovalResult",
    "UserRejectionResult",
    "UserStateChangeResult",
    "UserRoleChangeResult",
    "UserAssignmentResult",
    "RootAdminBootstrapResult",

    # -----------------------------------------------------
    # USERS
    # -----------------------------------------------------

    "UserService",
    "UserListFilter",
    "UserProfileView",
    "UserListItem",
    "UserSearchResult",
    "UserStatistics",
    "UserRoleUpdateResult",
    "UserStatusUpdateResult",
    "UserProfileUpdateResult",
    "UserAccessView",
    "AdminUsersDashboard",

    # -----------------------------------------------------
    # BINDINGS
    # -----------------------------------------------------

    "BindingService",
    "BindingScope",
    "BindingView",
    "BindingChangeResult",
    "BindingDeactivationResult",
    "StoreTransferResult",
    "BushTransferResult",
    "BulkBindingItemResult",
    "BulkBindingResult",
    "UserBindingsResult",

    # -----------------------------------------------------
    # STORES
    # -----------------------------------------------------

    "StoreService",
    "StoreCreateData",
    "StoreView",
    "StoreChangeResult",
    "StoreStatusChangeResult",
    "StoreBushChangeResult",
    "StoreClusterChangeResult",
    "StoreBulkItemResult",
    "StoreBulkResult",

    # -----------------------------------------------------
    # BUSHES
    # -----------------------------------------------------

    "BushService",
    "BushView",
    "BushCreateData",
    "BushChangeResult",
    "BushStatusChangeResult",
    "BushStoreMoveResult",
    "BushStatistics",
    "BushBulkItemResult",
    "BushBulkResult",

    # -----------------------------------------------------
    # CLUSTERS
    # -----------------------------------------------------

    "ClusterService",
    "ClusterView",
    "ClusterCreateData",
    "ClusterChangeResult",
    "ClusterStatusChangeResult",
    "ClusterStoreAssignmentResult",
    "BulkClusterAssignmentItem",
    "BulkClusterAssignmentResult",
    "ClusterControlTimes",
    "ClusterLatenessResult",
    "DefaultClustersResult",

    # -----------------------------------------------------
    # SCHEDULE
    # -----------------------------------------------------

    "ScheduleService",
    "WeekdayScheduleChangeResult",
    "ScheduleExceptionChangeResult",
    "ScheduleDeletionResult",
    "ClusterAssignmentResult",
    "SchedulePreviewItem",

    # -----------------------------------------------------
    # OPENING
    # -----------------------------------------------------

    "OpeningService",
    "OpeningPreparationResult",
    "OpeningConfirmationResult",
    "OpeningDeadlineResult",
    "OpeningManualUpdateResult",

    # -----------------------------------------------------
    # CLOSING
    # -----------------------------------------------------

    "ClosingService",
    "ClosingPreparationResult",
    "ClosingSubmissionResult",
    "ClosingDeadlineResult",
    "ClosingManualUpdateResult",
    "ReceiptAttachmentResult",

    # -----------------------------------------------------
    # CASH
    # -----------------------------------------------------

    "CashService",
    "CashEntryView",
    "CashValidationResult",
    "CashChangeResult",
    "CashCorrectionResult",
    "CashStoreSummary",
    "CashPeriodTotals",
    "CashPeriodReport",

    # -----------------------------------------------------
    # SETTINGS
    # -----------------------------------------------------

    "SettingsService",
    "SettingView",
    "SettingsChangeResult",
    "BulkSettingsChangeResult",
    "SettingsDashboard",

    # -----------------------------------------------------
    # GROUPS
    # -----------------------------------------------------

    "GroupService",
    "TelegramGroupScope",
    "TelegramGroupTopic",
    "TelegramDestination",
    "GroupBindingView",
    "GroupChangeResult",
    "TopicChangeResult",
    "BotGroupAccessResult",

    # -----------------------------------------------------
    # FILES
    # -----------------------------------------------------

    "FileService",
    "FileCategory",
    "TelegramUploadKind",
    "TelegramUpload",
    "FileValidationResult",
    "DownloadedFile",
    "StoredFile",
    "SafeFilenameResult",

    # -----------------------------------------------------
    # IMPORT
    # -----------------------------------------------------

    "ImportService",
    "ImportFileFormat",
    "ImportRowStatus",
    "ImportIssueLevel",
    "ImportIssue",
    "StoreImportRow",
    "ImportPreview",
    "ImportApplyItemResult",
    "ImportApplyResult",
    "ParsedTable",

    # -----------------------------------------------------
    # INVITES
    # -----------------------------------------------------

    "InviteService",
    "InviteScope",
    "InvitePayload",
    "InviteCreationServiceResult",
    "InviteActivationServiceResult",
    "InviteRevocationResult",

    # -----------------------------------------------------
    # NOTIFICATIONS
    # -----------------------------------------------------

    "NotificationService",
    "DeliveryResultStatus",
    "NotificationDeliveryResult",
    "NotificationBatchResult",
    "QueueNotificationResult",

    # -----------------------------------------------------
    # SUMMARIES
    # -----------------------------------------------------

    "SummaryService",
    "SummarySyncStatus",
    "PreparedSummaryUpdate",
    "SummarySyncResult",
    "SummaryBatchResult",

    # -----------------------------------------------------
    # REPORTS
    # -----------------------------------------------------

    "ReportService",
    "ReportPeriodType",
    "ReportScopeType",
    "ReportScope",
    "StoreDailyReportRow",
    "DailyReportTotals",
    "DailyReportResult",
    "StorePeriodSummary",
    "PeriodReportTotals",
    "PeriodReportResult",
    "ExcelSheetData",
    "ExcelReportData",

    # -----------------------------------------------------
    # EXCEL
    # -----------------------------------------------------

    "ExcelService",
    "GeneratedExcelFile",
    "PreparedSheetData",

    # -----------------------------------------------------
    # AUDIT
    # -----------------------------------------------------

    "AuditService",
    "AuditFilter",
    "AuditEntryView",
    "AuditPage",
    "AuditExportRow",
    "AuditStatistics",
]