from __future__ import annotations

from datetime import date

from PySide6.QtCore import QEvent, QSize, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QListView,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import COLORS, awesome_icon, icon_pixmap, set_button_icon
from app.ui.widgets.combo_box import AppComboBox


class MonthYearItemDelegate(QStyledItemDelegate):
    """Paint a clean popup row without native menu checks or padding."""

    ROW_HEIGHT = 34

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        row = option.rect.adjusted(3, 1, -3, -1)
        if selected:
            painter.setBrush(QColor("#4468f2"))
            painter.setPen(QPen(QColor("#5d7cff"), 1))
            painter.drawRoundedRect(row, 6, 6)
        elif hovered:
            painter.setBrush(QColor("#27313c"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(row, 6, 6)

        painter.setPen(QColor("#ffffff" if selected else "#e5e8ee"))
        painter.setFont(option.font)
        painter.drawText(
            row.adjusted(10, 0, -10, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            str(index.data(Qt.ItemDataRole.DisplayRole) or ""),
        )
        painter.restore()

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        size = super().sizeHint(option, index)
        size.setHeight(self.ROW_HEIGHT)
        return size


class MonthYearChoice(AppComboBox):
    """Month/year combo with a consistent chevron and clean list popup."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        popup = QListView(self)
        popup.setMouseTracking(True)
        popup.setUniformItemSizes(True)
        popup.setSpacing(0)
        popup.setCursor(Qt.CursorShape.PointingHandCursor)
        popup.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        popup.setItemDelegate(MonthYearItemDelegate(popup))
        self.setView(popup)
        popup.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerItem
        )
        self._popup_window = QFrame(
            self,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self._popup_window.setObjectName("monthYearPopup")
        self._popup_window.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground, True
        )
        self._popup_window.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, False
        )
        self._popup_window.setAutoFillBackground(True)
        popup_layout = QVBoxLayout(self._popup_window)
        popup_layout.setContentsMargins(0, 0, 0, 0)
        popup_layout.setSpacing(0)
        popup_layout.addWidget(popup)
        popup.clicked.connect(self._activate_popup_index)
        popup.installEventFilter(self)
        self._popup_window.setStyleSheet("""
            QFrame#monthYearPopup {
                background: #171b21;
                border: none;
            }
            QFrame#monthYearPopup QListView {
                color: #e5e8ee;
                background: #171b21;
                border: 1px solid #343c48;
                padding: 0;
                margin: 0;
                outline: none;
            }
            QFrame#monthYearPopup QScrollBar:vertical {
                width: 10px;
                margin: 3px 2px 3px 0;
                background: transparent;
            }
            QFrame#monthYearPopup QScrollBar::handle:vertical {
                min-height: 28px;
                background: #59616d;
                border-radius: 4px;
            }
            QFrame#monthYearPopup QScrollBar::add-line:vertical,
            QFrame#monthYearPopup QScrollBar::sub-line:vertical,
            QFrame#monthYearPopup QScrollBar::add-page:vertical,
            QFrame#monthYearPopup QScrollBar::sub-page:vertical {
                height: 0;
                background: transparent;
                border: none;
            }
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def showPopup(self) -> None:  # noqa: N802
        view = self.view()
        current = self.model().index(self.currentIndex(), self.modelColumn())
        if current.isValid():
            view.setCurrentIndex(current)
        self._fit_popup_rows()
        self._popup_window.show()
        self._popup_window.raise_()
        view.setFocus(Qt.FocusReason.PopupFocusReason)
        QTimer.singleShot(0, self._fit_popup_rows)

    def hidePopup(self) -> None:  # noqa: N802
        self._popup_window.hide()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.view() and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.hidePopup()
                self.setFocus(Qt.FocusReason.PopupFocusReason)
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._activate_popup_index(self.view().currentIndex())
                return True
        return super().eventFilter(watched, event)

    def _activate_popup_index(self, index) -> None:
        if not index.isValid():
            return
        self.setCurrentIndex(index.row())
        self.hidePopup()
        self.setFocus(Qt.FocusReason.PopupFocusReason)

    def _fit_popup_rows(self) -> None:
        view = self.view()
        popup = self._popup_window
        if self.count() == 0:
            return

        # QComboBox switches custom list views back to pixel scrolling each
        # time it opens them. Restore row scrolling so the first and last
        # visible entries are always complete rather than partially clipped.
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
        row_height = MonthYearItemDelegate.ROW_HEIGHT
        desired_rows = min(self.count(), self.maxVisibleItems())
        desired_height = desired_rows * row_height + 2
        screen = self.screen()
        if screen is None:
            return
        available = screen.availableGeometry()
        field_top_left = self.mapToGlobal(self.rect().topLeft())
        field_bottom_right = self.mapToGlobal(self.rect().bottomRight())
        field_top = field_top_left.y()
        field_bottom = field_bottom_right.y()
        popup_gap = 4
        space_below = available.bottom() - field_bottom - popup_gap
        space_above = field_top - available.top() - popup_gap
        if desired_height <= space_below:
            opens_above = False
        elif desired_height <= space_above:
            opens_above = True
        else:
            opens_above = space_above > space_below
        available_height = space_above if opens_above else space_below
        fitting_rows = max(1, (available_height - 2) // row_height)
        target_rows = min(desired_rows, fitting_rows)
        target_height = target_rows * row_height + 2
        target_width = self.width()
        target_x = min(
            max(field_top_left.x(), available.left()),
            available.right() - target_width + 1,
        )
        target_y = (
            field_top - popup_gap - target_height
            if opens_above
            else field_bottom + popup_gap + 1
        )
        popup.setGeometry(
            target_x,
            target_y,
            target_width,
            target_height,
        )
        if popup.layout() is not None:
            popup.layout().activate()
        current = self.model().index(self.currentIndex(), 0)
        if current.isValid():
            view.scrollTo(
                current,
                QAbstractItemView.ScrollHint.PositionAtCenter,
            )

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
        self.month_selector.setMaxVisibleItems(12)
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
        self.year_selector.setMaxVisibleItems(10)
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
            QComboBox#monthYearMonthSelector QAbstractItemView,
            QComboBox#monthYearYearSelector QAbstractItemView {{
                color: #e5e8ee;
                background: #171b21;
                border: 1px solid #343c48;
                selection-color: #ffffff;
                selection-background-color: #4468f2;
                padding: 0;
                margin: 0;
                outline: none;
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
