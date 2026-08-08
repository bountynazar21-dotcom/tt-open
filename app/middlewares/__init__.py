from __future__ import annotations

# =========================================================
# ACCESS
# =========================================================

from app.middlewares.access import (
    AccessMiddleware,
    MiddlewareAccessContext,
    PermissionMiddleware,
    UserAccessMiddleware,
)

# =========================================================
# AUTH
# =========================================================

from app.middlewares.auth import (
    AuthenticationMiddleware,
    AuthMiddleware,
    AuthMiddlewareContext,
    AuthState,
    UserResolutionResult,
)

# =========================================================
# DATABASE
# =========================================================

from app.middlewares.database import (
    DatabaseMiddleware,
    DatabaseMiddlewareContext,
    DatabaseSessionMiddleware,
)

# =========================================================
# ERROR HANDLER
# =========================================================

from app.middlewares.error_handler import (
    ErrorHandlerMiddleware,
    ErrorInfo,
    GlobalErrorMiddleware,
)

# =========================================================
# LOGGING
# =========================================================

from app.middlewares.logging import (
    LoggingMiddleware,
    RequestLoggingMiddleware,
    UpdateExecutionResult,
    UpdateLogContext,
    UpdateLoggingMiddleware,
)

# =========================================================
# THROTTLING
# =========================================================

from app.middlewares.throttling import (
    AntiSpamMiddleware,
    ThrottleDecision,
    ThrottleEventType,
    ThrottleMiddleware,
    ThrottleRule,
    ThrottlingMiddleware,
)


__all__ = [
    # -----------------------------------------------------
    # ACCESS
    # -----------------------------------------------------

    "AccessMiddleware",
    "UserAccessMiddleware",
    "PermissionMiddleware",
    "MiddlewareAccessContext",

    # -----------------------------------------------------
    # AUTH
    # -----------------------------------------------------

    "AuthMiddleware",
    "AuthenticationMiddleware",
    "AuthMiddlewareContext",
    "AuthState",
    "UserResolutionResult",

    # -----------------------------------------------------
    # DATABASE
    # -----------------------------------------------------

    "DatabaseMiddleware",
    "DatabaseSessionMiddleware",
    "DatabaseMiddlewareContext",

    # -----------------------------------------------------
    # ERROR HANDLER
    # -----------------------------------------------------

    "ErrorHandlerMiddleware",
    "GlobalErrorMiddleware",
    "ErrorInfo",

    # -----------------------------------------------------
    # LOGGING
    # -----------------------------------------------------

    "LoggingMiddleware",
    "RequestLoggingMiddleware",
    "UpdateLoggingMiddleware",
    "UpdateLogContext",
    "UpdateExecutionResult",

    # -----------------------------------------------------
    # THROTTLING
    # -----------------------------------------------------

    "ThrottlingMiddleware",
    "ThrottleMiddleware",
    "AntiSpamMiddleware",
    "ThrottleEventType",
    "ThrottleRule",
    "ThrottleDecision",
]