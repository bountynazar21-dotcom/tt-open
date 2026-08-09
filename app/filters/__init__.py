from __future__ import annotations

from app.filters.access import (
    AccessFilter,
    BushManagementFilter,
    BushViewFilter,
    ExportReportsFilter,
    NetworkAccessFilter,
    NetworkManagementFilter,
    ReportsAccessFilter,
    RootSettingsFilter,
    StoreManagementFilter,
    StoreOperationFilter,
    StoreViewFilter,
)
from app.filters.group_chat import (
    GroupChatFilter,
    IsGroupChat,
)
from app.filters.private_chat import (
    IsPrivateChat,
    PrivateChatFilter,
)
from app.filters.role import (
    BushAdminFilter,
    DirectorFilter,
    HasRole,
    IsBushAdmin,
    IsDirector,
    IsLion,
    IsRootAdmin,
    IsStoreUser,
    LionFilter,
    ManagerFilter,
    RoleFilter,
    RootAdminFilter,
    StaffFilter,
    StoreUserFilter,
)


__all__ = [
    # Access
    "AccessFilter",
    "NetworkAccessFilter",
    "NetworkManagementFilter",
    "StoreViewFilter",
    "StoreOperationFilter",
    "StoreManagementFilter",
    "BushViewFilter",
    "BushManagementFilter",
    "ReportsAccessFilter",
    "ExportReportsFilter",
    "RootSettingsFilter",

    # Chat type
    "GroupChatFilter",
    "IsGroupChat",
    "PrivateChatFilter",
    "IsPrivateChat",

    # Roles
    "RoleFilter",
    "HasRole",
    "RootAdminFilter",
    "DirectorFilter",
    "BushAdminFilter",
    "LionFilter",
    "StoreUserFilter",
    "ManagerFilter",
    "StaffFilter",

    # Role aliases
    "IsRootAdmin",
    "IsDirector",
    "IsBushAdmin",
    "IsLion",
    "IsStoreUser",
]