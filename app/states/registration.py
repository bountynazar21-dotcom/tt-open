from __future__ import annotations

from aiogram.fsm.state import (
    State,
    StatesGroup,
)


# =========================================================
# REGISTRATION
# =========================================================


class RegistrationStates(
    StatesGroup
):
    """
    FSM-стани процесу реєстрації користувача.
    """

    waiting_contact = State()


# =========================================================
# ALIASES
# =========================================================


RegistrationState = RegistrationStates


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "RegistrationStates",
    "RegistrationState",
]