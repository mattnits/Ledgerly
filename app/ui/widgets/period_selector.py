from datetime import date
from typing import Iterable

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget

from app.ui.widgets.date_dropdown import DateDropdown
from app.ui.theme import awesome_icon, spaced_text_icon, spaced_text_icon_size


Month = tuple[int, int]


class PeriodSelector(QWidget):
    """Shared Monthly/All Time control with an optional month selection."""

    PERIOD_BUTTON_WIDTH = 126
    MONTH_SELECTOR_WIDTH = 210

    selection_changed = Signal(str, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        today = date.today()
        self.period = "monthly"
        self.selected_month: Month = (today.year, today.month)
        self.available_months: set[Month] = set()
        self._empty_month_fallback = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.monthly_button = QPushButton("Monthly")
        self.all_time_button = QPushButton("All Time")
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        for button in (self.monthly_button, self.all_time_button):
            button.setObjectName("periodButton")
            button.setCheckable(True)
            button.setFixedWidth(self.PERIOD_BUTTON_WIDTH)
            self.button_group.addButton(button)
            layout.addWidget(button)

        self.monthly_button.setChecked(True)
        self.monthly_button.clicked.connect(lambda: self.set_period("monthly"))
        self.all_time_button.clicked.connect(lambda: self.set_period("all"))

        self.month_selector = DateDropdown()
        self.month_selector.setIconSize(spaced_text_icon_size())
        self.month_selector.setFixedWidth(self.MONTH_SELECTOR_WIDTH)
        self.month_selector.currentIndexChanged.connect(self._select_month)
        layout.addWidget(self.month_selector)
        layout.addStretch()

        self._refresh_month_choices()
        self.setStyleSheet("""
            QPushButton#periodButton {
                color: #e0e2e5;
                background: #191d22;
                border: 1px solid #343b44;
                border-radius: 10px;
                padding: 10px 14px;
                font-size: 13px;
            }
            QPushButton#periodButton:checked {
                color: #ffffff;
                background: #126fff;
                border-color: #3388ff;
                font-weight: 600;
            }
            QPushButton#periodButton:hover { background: #24292f; }
        """)

    def set_available_months(self, months: Iterable[Month]) -> None:
        self.available_months = set(months)
        if self.available_months:
            if self.selected_month not in self.available_months:
                self.selected_month = max(self.available_months)
            if self._empty_month_fallback:
                self.period = "monthly"
                self._empty_month_fallback = False
        elif self.period == "monthly":
            self.period = "all"
            self._empty_month_fallback = True
        self._sync_period_controls()
        self._refresh_month_choices()

    def set_period(self, period: str, *, emit: bool = True) -> None:
        if period not in ("monthly", "all"):
            raise ValueError(f"Unsupported period: {period}")

        changed = self.period != period
        self.period = period
        self._empty_month_fallback = False
        self._sync_period_controls()
        if emit and changed:
            self.selection_changed.emit(self.period, self.selected_month)

    def set_selected_month(self, month: Month, *, emit: bool = True) -> None:
        changed = self.selected_month != month
        self.selected_month = month
        self._refresh_month_choices()
        if emit and changed:
            self.selection_changed.emit(self.period, self.selected_month)

    def reset(self, *, emit: bool = True) -> None:
        today = date.today()
        old_selection = (self.period, self.selected_month)
        self.period = "monthly"
        self.selected_month = (today.year, today.month)
        self._empty_month_fallback = False
        self._sync_period_controls()
        self._refresh_month_choices()
        if emit and old_selection != (self.period, self.selected_month):
            self.selection_changed.emit(self.period, self.selected_month)

    def _refresh_month_choices(self) -> None:
        months = self.available_months
        with QSignalBlocker(self.month_selector):
            self.month_selector.clear()
            for year, month in sorted(months, reverse=True):
                self.month_selector.addItem(
                    spaced_text_icon(
                        awesome_icon("fa6s.calendar-days", color="#b2b8c1")
                    ),
                    date(year, month, 1).strftime("%B %Y"),
                    (year, month),
                )
            selected_index = next(
                (
                    index
                    for index in range(self.month_selector.count())
                    if self.month_selector.itemData(index) == self.selected_month
                ),
                -1,
            )
            self.month_selector.setCurrentIndex(selected_index)
            self.month_selector.setEnabled(bool(months))

    def _sync_period_controls(self) -> None:
        self.monthly_button.setChecked(self.period == "monthly")
        self.all_time_button.setChecked(self.period == "all")
        self.month_selector.setVisible(self.period == "monthly")

    def _select_month(self, index: int) -> None:
        month = self.month_selector.itemData(index)
        if month is not None:
            self.set_selected_month(month)
