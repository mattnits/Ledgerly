from __future__ import annotations

from datetime import date

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import COLORS, awesome_icon, icon_pixmap, set_button_icon
from app.ui.widgets.combo_box import AppComboBox
from app.ui.widgets.dropdown import DropdownItemDelegate


# Kept as an import alias for callers that inspect popup row metrics.
MonthYearItemDelegate = DropdownItemDelegate


class MonthYearChoice(AppComboBox):
    """Month/year field retaining its integrated chevron and shared popup."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, compact=True)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = COLORS["text_muted"] if self.isEnabled() else COLORS["text_dim"]
        painter.setPen(QPen(QColor(color), 1.4))
        center_x = self.width() - 12
        center_y = self.height() // 2
        painter.drawLine(center_x - 3, center_y - 2, center_x, center_y + 1)
        painter.drawLine(center_x, center_y + 1, center_x + 3, center_y - 2)


class MonthYearPicker(QWidget):
    """Reusable month/year navigator shared by every monthly page."""

    period_changed = Signal(int, int)
    # Compatibility for existing Goals integrations while callers migrate to
    # the more explicit shared signal name.
    month_changed = Signal(int, int)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        compact: bool = False,
        minimum_year: int | None = None,
        maximum_year: int | None = None,
    ) -> None:
        super().__init__(parent)
        today = date.today()
        self.year = today.year
        self.month = today.month
        self.minimum_year = minimum_year or today.year - 10
        self.maximum_year = maximum_year or today.year + 10
        if self.minimum_year > self.maximum_year:
            raise ValueError("minimum_year cannot be greater than maximum_year")

        height = 38 if compact else 40
        button_size = height
        month_width = 108 if compact else 124
        year_width = 78 if compact else 84
        control_gap = 6

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(control_gap)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.previous_button = QToolButton()
        self.next_button = QToolButton()
        self.display = QFrame()
        self.display.setObjectName("monthYearDisplay")
        self.display.setFixedSize(
            8 + 22 + month_width + 1 + year_width + 3 + 7,
            height,
        )
        display_layout = QHBoxLayout(self.display)
        display_layout.setContentsMargins(8, 0, 7, 0)
        display_layout.setSpacing(1)

        self.calendar_icon = QLabel()
        self.calendar_icon.setObjectName("monthYearCalendarIcon")
        self.calendar_icon.setPixmap(
            icon_pixmap(awesome_icon("fa6s.calendar-days", color="#d5dde7"), 14, 14)
        )
        self.calendar_icon.setFixedWidth(22)

        self.month_selector = MonthYearChoice()
        self.month_selector.setObjectName("monthYearMonthSelector")
        self.month_selector.setAccessibleName("Month")
        self.month_selector.setToolTip("Select month")
        self.month_selector.setFixedWidth(month_width)
        for month in range(1, 13):
            self.month_selector.addItem(
                date(2000, month, 1).strftime("%B"), month
            )

        self.divider = QFrame()
        self.divider.setObjectName("monthYearDivider")
        self.divider.setFixedSize(1, height - 14)

        self.year_selector = MonthYearChoice()
        self.year_selector.setObjectName("monthYearYearSelector")
        self.year_selector.setAccessibleName("Year")
        self.year_selector.setToolTip("Select year")
        self.year_selector.setFixedWidth(year_width)
        self._populate_years()

        display_layout.addWidget(self.calendar_icon)
        display_layout.addWidget(self.month_selector)
        display_layout.addWidget(self.divider)
        display_layout.addWidget(self.year_selector)

        for button, icon, tooltip in (
            (self.previous_button, "fa6s.chevron-left", "Previous month"),
            (self.next_button, "fa6s.chevron-right", "Next month"),
        ):
            button.setObjectName("monthYearButton")
            button.setFixedSize(button_size, button_size)
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
            set_button_icon(
                button,
                icon,
                color="#c7d0db",
                active_color="#ffffff",
                size=12,
            )

        self.previous_button.clicked.connect(lambda: self.step(-1))
        self.next_button.clicked.connect(lambda: self.step(1))
        self.month_selector.currentIndexChanged.connect(self._select_period)
        self.year_selector.currentIndexChanged.connect(self._select_period)

        layout.addWidget(self.previous_button)
        layout.addWidget(self.display)
        layout.addWidget(self.next_button)
        self._apply_style(compact)
        self._sync()

    @property
    def selected_month(self) -> tuple[int, int]:
        return self.year, self.month

    @property
    def selected_period(self) -> tuple[int, int]:
        return self.year, self.month

    def get_selected_month(self) -> int:
        return self.month

    def get_selected_year(self) -> int:
        return self.year

    def set_selected_period(
        self,
        month: int,
        year: int,
        *,
        emit: bool = False,
    ) -> None:
        self.set_period(year, month, emit=emit)

    def set_month(self, year: int, month: int, *, emit: bool = False) -> None:
        self.set_period(year, month, emit=emit)

    def set_period(self, year: int, month: int, *, emit: bool = False) -> None:
        if not 1 <= month <= 12:
            raise ValueError("month must be between 1 and 12")
        self._ensure_year_available(year)
        changed = (self.year, self.month) != (year, month)
        self.year, self.month = year, month
        self._sync()
        if emit and changed:
            self._emit_change()

    def step(self, direction: int) -> None:
        value = self.year * 12 + self.month - 1 + direction
        year, zero_month = divmod(value, 12)
        self.set_period(year, zero_month + 1, emit=True)

    def _populate_years(self) -> None:
        current = self.year_selector.currentData()
        with QSignalBlocker(self.year_selector):
            self.year_selector.clear()
            for year in range(self.minimum_year, self.maximum_year + 1):
                self.year_selector.addItem(str(year), year)
            if current is not None:
                self.year_selector.setCurrentIndex(
                    self.year_selector.findData(current)
                )

    def _ensure_year_available(self, year: int) -> None:
        if self.minimum_year <= year <= self.maximum_year:
            return
        self.minimum_year = min(self.minimum_year, year)
        self.maximum_year = max(self.maximum_year, year)
        self._populate_years()

    def _sync(self) -> None:
        self._ensure_year_available(self.year)
        with (
            QSignalBlocker(self.month_selector),
            QSignalBlocker(self.year_selector),
        ):
            self.month_selector.setCurrentIndex(
                self.month_selector.findData(self.month)
            )
            self.year_selector.setCurrentIndex(
                self.year_selector.findData(self.year)
            )
        self._sync_tooltips()

    def _sync_tooltips(self) -> None:
        current = date(self.year, self.month, 1)
        previous_value = self.year * 12 + self.month - 2
        previous_year, previous_zero_month = divmod(previous_value, 12)
        next_value = self.year * 12 + self.month
        next_year, next_zero_month = divmod(next_value, 12)
        self.previous_button.setToolTip(
            "Previous month ("
            + date(previous_year, previous_zero_month + 1, 1).strftime("%B %Y")
            + ")"
        )
        self.next_button.setToolTip(
            "Next month ("
            + date(next_year, next_zero_month + 1, 1).strftime("%B %Y")
            + ")"
        )
        self.setAccessibleName(current.strftime("%B %Y"))

    def _select_period(self, _index: int) -> None:
        month = self.month_selector.currentData()
        year = self.year_selector.currentData()
        if month is None or year is None:
            return
        selected = int(year), int(month)
        if selected == (self.year, self.month):
            return
        self.year, self.month = selected
        self._sync_tooltips()
        self._emit_change()

    def _emit_change(self) -> None:
        self.period_changed.emit(self.year, self.month)
        self.month_changed.emit(self.year, self.month)

    def _apply_style(self, compact: bool) -> None:
        font_size = 11 if compact else 12
        self.setStyleSheet(f"""
            QFrame#monthYearDisplay {{
                background: #151b21;
                border: 1px solid #34404d;
                border-radius: 8px;
            }}
            QComboBox#monthYearMonthSelector,
            QComboBox#monthYearYearSelector {{
                color: #edf2f7;
                background: transparent;
                border: none;
                border-radius: 0;
                min-height: 20px;
                padding: 6px 21px 6px 7px;
                font-size: {font_size}px;
            }}
            QComboBox#monthYearMonthSelector:hover,
            QComboBox#monthYearYearSelector:hover,
            QComboBox#monthYearMonthSelector:focus,
            QComboBox#monthYearYearSelector:focus {{
                background: #222b35;
            }}
            QComboBox#monthYearMonthSelector::drop-down,
            QComboBox#monthYearYearSelector::drop-down {{
                width: 20px;
                border: none;
                background: transparent;
            }}
            QComboBox#monthYearMonthSelector::down-arrow,
            QComboBox#monthYearYearSelector::down-arrow {{
                image: none;
            }}
            QFrame#monthYearDivider {{
                background: #34404d;
                border: none;
            }}
            QToolButton#monthYearButton {{
                background: #151b21;
                border: 1px solid #34404d;
                border-radius: 8px;
                padding: 5px;
            }}
            QToolButton#monthYearButton:hover,
            QToolButton#monthYearButton:focus {{
                background: #27313c;
                border-color: #45617d;
            }}
            QToolButton#monthYearButton:pressed {{
                background: #172f57;
                border-color: {COLORS['primary']};
            }}
        """)
