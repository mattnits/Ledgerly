from datetime import date
from typing import Iterable

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QButtonGroup, QComboBox, QHBoxLayout, QPushButton, QWidget

from ui.theme import awesome_icon


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

        self.month_selector = QComboBox()
        self.month_selector.setObjectName("monthSelector")
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
            QComboBox#monthSelector {
                color: #e3e5e8;
                background: #191d22;
                border: 1px solid #343b44;
                border-radius: 10px;
                padding: 9px 30px 9px 12px;
            }
            QComboBox#monthSelector::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 28px;
                border: none;
                background: transparent;
            }
        """)

    def set_available_months(self, months: Iterable[Month]) -> None:
        self.available_months = set(months)
        self._refresh_month_choices()

    def set_period(self, period: str, *, emit: bool = True) -> None:
        if period not in ("monthly", "all"):
            raise ValueError(f"Unsupported period: {period}")

        changed = self.period != period
        self.period = period
        self.monthly_button.setChecked(period == "monthly")
        self.all_time_button.setChecked(period == "all")
        self.month_selector.setVisible(period == "monthly")
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
        self.monthly_button.setChecked(True)
        self.all_time_button.setChecked(False)
        self.month_selector.show()
        self._refresh_month_choices()
        if emit and old_selection != (self.period, self.selected_month):
            self.selection_changed.emit(self.period, self.selected_month)

    def _refresh_month_choices(self) -> None:
        today = date.today()
        months = self.available_months | {
            self.selected_month,
            (today.year, today.month),
        }
        with QSignalBlocker(self.month_selector):
            self.month_selector.clear()
            for year, month in sorted(months, reverse=True):
                self.month_selector.addItem(
                    awesome_icon("fa6s.calendar-days", color="#b2b8c1"),
                    date(year, month, 1).strftime("%B %Y"),
                    (year, month),
                )
            selected_index = next(
                index
                for index in range(self.month_selector.count())
                if self.month_selector.itemData(index) == self.selected_month
            )
            self.month_selector.setCurrentIndex(selected_index)

    def _select_month(self, index: int) -> None:
        month = self.month_selector.itemData(index)
        if month is not None:
            self.set_selected_month(month)
