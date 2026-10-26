"""Compatibility names for the shared Ledgerly dropdown implementation."""
from app.ui.widgets.dropdown import LedgerlyComboBox


class AppComboBox(LedgerlyComboBox):
    """Standard dropdown used in forms, dialogs and filters."""


class FramelessPopupComboBox(AppComboBox):
    """Compatibility name; every AppComboBox now uses the same owned popup."""
