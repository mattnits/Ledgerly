from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QWidget

from app.ui.widgets.combo_box import AppComboBox


class DateDropdown(AppComboBox):
    """Date-range filter with the same popup as every other selector."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dateDropdown")
        self.setIconSize(QSize(16, 16))
        self.setMinimumHeight(40)
