from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, QRectF, QSignalBlocker, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.db import SessionLocal
from app.services.goals import (
    CategoryBudgetProgress,
    MonthlySavingsBreakdown,
    SavingsGoalRecord,
    create_or_update_category_budget,
    create_savings_goal,
    delete_category_budget,
    delete_savings_goal,
    get_category_budgets,
    get_monthly_savings_breakdown,
    get_savings_goals,
    list_budget_categories,
    set_monthly_savings_goal,
    update_savings_goal,
)
from app.ui.dialogs.generic_dialog import GenericDialog
from app.ui.widgets.combo_box import AppComboBox
from app.ui.widgets.date_picker import DatePickerEdit
from app.ui.widgets.page_header import PageHeader
from app.ui.theme import (
    awesome_icon,
    category_icon_name,
    set_button_icon,
    spaced_text_icon,
    spaced_text_icon_size,
)


MONEY_STEP = 25.0


def _money(value: Decimal, *, signed: bool = False) -> str:
    value = Decimal(value)
    sign = ""
    if signed and value > 0:
        sign = "+"
    elif value < 0:
        sign = "−"
    absolute = abs(value)
    formatted = f"{absolute:,.0f}" if absolute == absolute.to_integral() else f"{absolute:,.2f}"
    return f"{sign}${formatted}"


def _badge_pixmap(icon_name: str, color: str, size: int = 34) -> QPixmap:
    """Render the compact coloured icon badges used throughout the Goals page."""
    background = QColor(color)
    if not background.isValid():
        background = QColor("#398cff")
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    tint = QColor(background)
    tint.setAlpha(205)
    painter.setPen(QPen(background.lighter(125), 1))
    painter.setBrush(tint)
    painter.drawRoundedRect(QRectF(1, 1, size - 2, size - 2), 9, 9)
    icon_size = max(14, int(size * 0.48))
    icon = awesome_icon(icon_name, color="#f8fbff").pixmap(icon_size, icon_size)
    offset = (size - icon_size) // 2
    painter.drawPixmap(offset, offset, icon)
    painter.end()
    return pixmap


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())


def _money_editor(value: Decimal = Decimal()) -> QDoubleSpinBox:
    editor = QDoubleSpinBox()
    editor.setRange(0.0, 999_999_999.99)
    editor.setDecimals(2)
    editor.setSingleStep(MONEY_STEP)
    editor.setPrefix("$ ")
    editor.setValue(float(value))
    editor.setMinimumHeight(38)
    return editor


def _dialog_field_label(text: str, buddy: QWidget | None = None) -> QLabel:
    label = QLabel(text)
    label.setObjectName("dialogFieldLabel")
    if buddy is not None:
        label.setBuddy(buddy)
    return label


def _dialog_month_field(year: int, month: int) -> QFrame:
    field = QFrame()
    field.setObjectName("dialogDisplayField")
    field.setMinimumHeight(54)
    layout = QHBoxLayout(field)
    layout.setContentsMargins(16, 0, 16, 0)
    layout.setSpacing(14)
    calendar = QLabel()
    calendar.setPixmap(
        awesome_icon("fa6s.calendar-days", color="#b8c9e3").pixmap(20, 20)
    )
    value = QLabel(date(year, month, 1).strftime("%B %Y"))
    value.setObjectName("dialogDisplayValue")
    chevron = QLabel()
    chevron.setPixmap(
        awesome_icon("fa6s.chevron-down", color="#9eacc0").pixmap(12, 12)
    )
    layout.addWidget(calendar)
    layout.addWidget(value, 1)
    layout.addWidget(chevron)
    return field


def _style_form_labels(form: QFormLayout, fields: tuple[QWidget, ...]) -> None:
    for field in fields:
        label = form.labelForField(field)
        if label is not None:
            label.setObjectName("dialogFieldLabel")


class MonthChoiceComboBox(AppComboBox):
    """Compact combo box with a consistently visible dropdown chevron."""

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API spelling
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#aeb8c5"), 1.4))
        center_x = self.width() - 12
        center_y = self.height() // 2
        painter.drawLine(center_x - 3, center_y - 2, center_x, center_y + 1)
        painter.drawLine(center_x, center_y + 1, center_x + 3, center_y - 2)


class MonthNavigator(QWidget):
    month_changed = Signal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        today = date.today()
        self.year = today.year
        self.month = today.month
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.previous_button = QToolButton()
        self.next_button = QToolButton()
        self.display = QFrame()
        self.display.setObjectName("goalsMonthDisplay")
        self.display.setFixedHeight(38)
        display_layout = QHBoxLayout(self.display)
        display_layout.setContentsMargins(10, 0, 6, 0)
        display_layout.setSpacing(2)
        calendar_icon = QLabel()
        calendar_icon.setPixmap(
            awesome_icon("fa6s.calendar-days", color="#d5dde7").pixmap(15, 15)
        )
        calendar_icon.setFixedWidth(20)
        self.month_selector = MonthChoiceComboBox()
        self.month_selector.setObjectName("goalsMonthSelector")
        self.month_selector.setAccessibleName("Month")
        self.month_selector.setToolTip("Select month")
        self.month_selector.setFixedWidth(148)
        self.month_selector.setMaxVisibleItems(12)
        for month in range(1, 13):
            self.month_selector.addItem(
                date(2000, month, 1).strftime("%B"),
                month,
            )
        divider = QFrame()
        divider.setObjectName("goalsMonthDivider")
        divider.setFixedSize(1, 22)
        self.year_selector = MonthChoiceComboBox()
        self.year_selector.setObjectName("goalsYearSelector")
        self.year_selector.setAccessibleName("Year")
        self.year_selector.setToolTip("Select year")
        self.year_selector.setFixedWidth(114)
        for year in range(today.year + 10, today.year - 21, -1):
            self.year_selector.addItem(str(year), year)
        display_layout.addWidget(calendar_icon)
        display_layout.addWidget(self.month_selector)
        display_layout.addWidget(divider)
        display_layout.addWidget(self.year_selector)
        for button, icon, tooltip in (
            (self.previous_button, "fa6s.chevron-left", "Previous month"),
            (self.next_button, "fa6s.chevron-right", "Next month"),
        ):
            button.setObjectName("goalsMonthButton")
            button.setFixedSize(38, 38)
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
            set_button_icon(button, icon, color="#c7d0db", active_color="#ffffff", size=13)
        self.previous_button.clicked.connect(lambda: self.step(-1))
        self.next_button.clicked.connect(lambda: self.step(1))
        self.month_selector.currentIndexChanged.connect(self._select_date)
        self.year_selector.currentIndexChanged.connect(self._select_date)
        layout.addWidget(self.previous_button)
        layout.addWidget(self.display)
        layout.addWidget(self.next_button)
        self._sync()

    @property
    def selected_month(self) -> tuple[int, int]:
        return self.year, self.month

    def set_month(self, year: int, month: int, *, emit: bool = False) -> None:
        self.year, self.month = year, month
        self._sync()
        if emit:
            self.month_changed.emit(year, month)

    def step(self, direction: int) -> None:
        value = self.year * 12 + self.month - 1 + direction
        self.year, zero_month = divmod(value, 12)
        self.month = zero_month + 1
        self._sync()
        self.month_changed.emit(self.year, self.month)

    def _sync(self) -> None:
        month_blocker = QSignalBlocker(self.month_selector)
        year_blocker = QSignalBlocker(self.year_selector)
        if self.year_selector.findData(self.year) < 0:
            years = {
                self.year_selector.itemData(index)
                for index in range(self.year_selector.count())
            }
            years.add(self.year)
            self.year_selector.clear()
            for year in sorted(years, reverse=True):
                self.year_selector.addItem(str(year), year)
        self.month_selector.setCurrentIndex(
            self.month_selector.findData(self.month)
        )
        self.year_selector.setCurrentIndex(
            self.year_selector.findData(self.year)
        )
        del month_blocker, year_blocker

    def _select_date(self, _index: int) -> None:
        month = self.month_selector.currentData()
        year = self.year_selector.currentData()
        if month is None or year is None:
            return
        selected = int(year), int(month)
        if selected == (self.year, self.month):
            return
        self.year, self.month = selected
        self.month_changed.emit(self.year, self.month)


class SectionCard(QFrame):
    def __init__(self, object_name: str = "goalsCard", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)


class ProgressRing(QWidget):
    """Large antialiased monthly-goal progress indicator."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._percent = Decimal()
        self._goal_set = False
        self.setFixedSize(168, 168)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API spelling
        return QSize(168, 168)

    def set_progress(self, percent: Decimal, goal_set: bool) -> None:
        self._percent = max(Decimal(), percent)
        self._goal_set = goal_set
        self.update()

    def set_dense(self, dense: bool) -> None:
        diameter = 112 if dense else 168
        self.setFixedSize(diameter, diameter)
        self.updateGeometry()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API spelling
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        scale = side / 168
        stroke = max(10, round(15 * scale))
        ring = QRectF(
            (self.width() - side) / 2 + stroke / 2,
            (self.height() - side) / 2 + stroke / 2,
            side - stroke,
            side - stroke,
        )
        track = QPen(QColor("#293440"), stroke)
        track.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track)
        painter.drawArc(ring, 0, 360 * 16)
        if self._goal_set:
            progress = QPen(QColor("#4fd594"), stroke)
            progress.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(progress)
            painter.drawArc(
                ring,
                90 * 16,
                -int(min(self._percent, Decimal(100)) / Decimal(100) * 360 * 16),
            )
        painter.setPen(QColor("#f5f7fa"))
        font = painter.font()
        font.setPixelSize(max(25, round(34 * scale)))
        font.setBold(True)
        painter.setFont(font)
        value = f"{self._percent:.0f}%" if self._goal_set else "—"
        painter.drawText(
            QRectF(0, 48 * scale, self.width(), 46 * scale),
            Qt.AlignmentFlag.AlignCenter,
            value,
        )
        painter.setPen(QColor("#aeb8c5"))
        font.setPixelSize(max(10, round(12 * scale)))
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(
            QRectF(0, 92 * scale, self.width(), 28 * scale),
            Qt.AlignmentFlag.AlignCenter,
            "of goal" if self._goal_set else "goal not set",
        )
        painter.end()


class MetricTile(QFrame):
    def __init__(self, title: str, icon: str, color: str) -> None:
        super().__init__()
        self._dense = False
        self.setObjectName("goalsMetricTile")
        self.setMinimumHeight(88)
        self.tile_layout = QGridLayout(self)
        self.tile_layout.setContentsMargins(14, 12, 14, 11)
        self.tile_layout.setHorizontalSpacing(8)
        self.tile_layout.setVerticalSpacing(2)
        icon_label = QLabel()
        icon_label.setPixmap(awesome_icon(icon, color=color).pixmap(24, 24))
        icon_label.setFixedSize(28, 28)
        title_label = QLabel(title)
        title_label.setObjectName("goalsMetricTitle")
        title_label.setWordWrap(True)
        title_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.value_label = QLabel("$0")
        self.value_label.setObjectName("goalsMetricValue")
        self.detail_label = QLabel("")
        self.detail_label.setObjectName("goalsMetricDetail")
        self.detail_label.setWordWrap(True)
        self.tile_layout.addWidget(icon_label, 0, 0, 2, 1, alignment=Qt.AlignmentFlag.AlignTop)
        self.tile_layout.addWidget(title_label, 0, 1)
        self.tile_layout.addWidget(self.value_label, 1, 1)
        self.tile_layout.addWidget(self.detail_label, 2, 0, 1, 2)
        self.tile_layout.setColumnStretch(1, 1)

    def set_dense(self, dense: bool) -> None:
        self._dense = dense
        self.setMinimumHeight(52 if dense else 88)
        self.tile_layout.setContentsMargins(
            8 if dense else 14,
            4 if dense else 12,
            8 if dense else 14,
            4 if dense else 11,
        )
        self.detail_label.setVisible(bool(self.detail_label.text()) and not dense)

    def set_data(self, value: Decimal, detail: str = "") -> None:
        self.value_label.setText(_money(value))
        self.detail_label.setText(detail)
        self.detail_label.setVisible(bool(detail) and not self._dense)


class MonthlySavingsCard(SectionCard):
    edit_requested = Signal()

    def __init__(self) -> None:
        super().__init__("monthlySavingsCard")
        self._dense = False
        self._compact: bool | None = None
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(20, 16, 20, 16)
        self.root_layout.setSpacing(12)
        heading = QHBoxLayout()
        heading.setSpacing(0)
        icon = QLabel()
        icon.setPixmap(awesome_icon("fa6s.bullseye", color="#49a4ff").pixmap(25, 25))
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Monthly Savings Goal")
        title.setObjectName("goalsSectionTitle")
        self.subtitle = QLabel(
            "Your target is based on usable income after spending; RRSP contributions are excluded."
        )
        self.subtitle.setObjectName("goalsMuted")
        self.subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(self.subtitle)
        self.edit_button = QPushButton("Set Goal")
        self.edit_button.setObjectName("secondaryActionButton")
        set_button_icon(
            self.edit_button, "fa6s.pen", color="#8fc5ff",
            active_color="#ffffff", size=13,
        )
        self.edit_button.clicked.connect(self.edit_requested)
        heading.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
        heading.addSpacing(8)
        heading.addLayout(titles, 1)
        heading.addWidget(self.edit_button, alignment=Qt.AlignmentFlag.AlignTop)
        self.root_layout.addLayout(heading)

        self.body = QGridLayout()
        self.body.setContentsMargins(0, 2, 0, 0)
        self.body.setHorizontalSpacing(22)
        self.body.setVerticalSpacing(14)
        self.ring_widget = ProgressRing(self)

        self.summary_widget = QWidget(self)
        summary = QVBoxLayout(self.summary_widget)
        summary.setContentsMargins(0, 0, 0, 0)
        summary.setSpacing(8)
        summary.addStretch()
        self.actual_label = QLabel("$0")
        self.actual_label.setObjectName("monthlySavingsValue")
        self.target_label = QLabel("No monthly goal set")
        self.target_label.setObjectName("goalsTarget")
        self.target_label.setWordWrap(True)
        self.target_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.progress = QProgressBar()
        self.progress.setObjectName("goalsProgress")
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(12)
        self.progress.setMinimumWidth(175)
        self.remaining_label = QLabel("Set a goal to track monthly progress")
        self.remaining_label.setObjectName("goalsRemaining")
        self.remaining_label.setWordWrap(True)
        self.remaining_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.status_label = QLabel("")
        self.status_label.setObjectName("goalsStatus")
        self.status_label.setWordWrap(True)
        self.status_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        summary.addWidget(self.actual_label)
        summary.addWidget(self.target_label)
        summary.addWidget(self.progress)
        summary.addWidget(self.remaining_label)
        summary.addWidget(self.status_label)
        summary.addStretch()

        self.breakdown_frame = QFrame(self)
        self.breakdown_frame.setObjectName("goalsBreakdown")
        self.breakdown_layout = QGridLayout(self.breakdown_frame)
        self.breakdown_layout.setContentsMargins(14, 12, 14, 12)
        self.breakdown_layout.setHorizontalSpacing(18)
        self.breakdown_layout.setVerticalSpacing(7)
        heading_label = QLabel("Goal calculation  (RRSP excluded)")
        heading_label.setObjectName("goalsSmallHeading")
        self.breakdown_layout.addWidget(heading_label, 0, 0, 1, 3)
        self.breakdown_values: dict[str, QLabel] = {}
        self.breakdown_names: dict[str, QLabel] = {}
        rows = (
            ("income", "Income", "#4fd594"),
            ("spending", "Spending", "#ff6670"),
            ("employee", "Work RRSP (employee)", "#53a8ff"),
            ("employer", "Work RRSP (employer)", "#bd69ee"),
        )
        for row, (key, label, color) in enumerate(rows, 1):
            dot = QLabel()
            dot.setFixedWidth(10)
            dot.setPixmap(awesome_icon("fa6s.circle", color=color).pixmap(7, 7))
            name = QLabel(label)
            name.setObjectName("goalsBreakdownName")
            name.setStyleSheet(f"color: {color};")
            value = QLabel("$0")
            value.setObjectName("goalsBreakdownValue")
            value.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.breakdown_layout.addWidget(dot, row, 0)
            self.breakdown_layout.addWidget(name, row, 1)
            self.breakdown_layout.addWidget(value, row, 2)
            self.breakdown_names[key] = name
            self.breakdown_values[key] = value
        divider = QFrame()
        divider.setObjectName("goalsBreakdownDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        self.breakdown_layout.addWidget(divider, 5, 0, 1, 3)
        net_dot = QLabel()
        net_dot.setFixedWidth(10)
        net_dot.setPixmap(
            awesome_icon("fa6s.circle", color="#4fd594").pixmap(7, 7)
        )
        net_name = QLabel("Net Savings")
        net_name.setStyleSheet("color: #4fd594; font-weight: 650;")
        net_value = QLabel("$0")
        net_value.setObjectName("goalsBreakdownNet")
        net_value.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.breakdown_layout.addWidget(net_dot, 6, 0)
        self.breakdown_layout.addWidget(net_name, 6, 1)
        self.breakdown_layout.addWidget(net_value, 6, 2)
        self.breakdown_values["net"] = net_value
        self.root_layout.addLayout(self.body)
        self.set_compact(False)

    def set_dense(self, dense: bool) -> None:
        self._dense = dense
        self.root_layout.setContentsMargins(
            14 if dense else 20,
            10 if dense else 16,
            14 if dense else 20,
            10 if dense else 16,
        )
        self.root_layout.setSpacing(7 if dense else 12)
        self.body.setHorizontalSpacing(12 if dense else 22)
        self.body.setVerticalSpacing(8 if dense else 14)
        self.breakdown_layout.setContentsMargins(
            10 if dense else 14,
            8 if dense else 12,
            10 if dense else 14,
            8 if dense else 12,
        )
        self.breakdown_layout.setHorizontalSpacing(8 if dense else 18)
        self.breakdown_layout.setVerticalSpacing(4 if dense else 7)
        self.progress.setMinimumWidth(125 if dense else 175)
        self.breakdown_names["employee"].setText(
            "RRSP employee (excluded)"
            if dense else "Work RRSP employee (excluded)"
        )
        self.breakdown_names["employer"].setText(
            "RRSP employer (excluded)"
            if dense else "Work RRSP employer (excluded)"
        )
        self.subtitle.setVisible(not dense)
        self.status_label.setVisible(not dense and bool(self.status_label.text()))
        self.ring_widget.set_dense(dense)

    def set_compact(self, compact: bool) -> None:
        if compact == self._compact:
            return
        self._compact = compact
        for widget in (self.ring_widget, self.summary_widget, self.breakdown_frame):
            self.body.removeWidget(widget)
        if compact:
            self.body.addWidget(self.ring_widget, 0, 0, alignment=Qt.AlignmentFlag.AlignCenter)
            self.body.addWidget(self.summary_widget, 1, 0)
            self.body.addWidget(self.breakdown_frame, 2, 0)
            stretches = (1, 0, 0)
        else:
            self.body.addWidget(self.ring_widget, 0, 0, alignment=Qt.AlignmentFlag.AlignCenter)
            self.body.addWidget(self.summary_widget, 0, 1)
            self.body.addWidget(self.breakdown_frame, 0, 2)
            stretches = (2, 3, 3)
        for column, stretch in enumerate(stretches):
            self.body.setColumnStretch(column, stretch)

    def set_data(self, data: MonthlySavingsBreakdown, month_label: str) -> None:
        self.actual_label.setText(_money(data.net_savings))
        self.breakdown_values["income"].setText(_money(data.income))
        self.breakdown_values["spending"].setText(f"−{_money(data.spending)}")
        self.breakdown_values["employee"].setText(_money(data.work_rrsp_employee))
        self.breakdown_values["employer"].setText(_money(data.work_rrsp_employer))
        self.breakdown_values["net"].setText(_money(data.net_savings))
        if data.target is None:
            self.ring_widget.set_progress(Decimal(), False)
            self.target_label.setText(f"No savings goal set for {month_label}")
            self.remaining_label.setText("Set a goal to track monthly progress")
            self.status_label.hide()
            self.edit_button.setText("Set Goal")
            self.progress.setValue(0)
            return
        percent = data.net_savings / data.target * Decimal(100) if data.target else Decimal()
        self.ring_widget.set_progress(percent, True)
        self.target_label.setText(f"of {_money(data.target)}")
        self.progress.setValue(max(0, min(100, int(percent))))
        difference = data.net_savings - data.target
        if difference >= 0:
            self.remaining_label.setText(f"You exceeded your goal by {_money(difference)}")
            self.status_label.setText("⚑  You’re on track! Keep it up.")
            self.status_label.setProperty("state", "positive")
        else:
            self.remaining_label.setText(f"{_money(-difference)} left to reach your goal")
            if data.net_savings >= 0:
                self.status_label.setText("⚑  You’re on track! Keep it up.")
                self.status_label.setProperty("state", "positive")
            else:
                self.status_label.setText("Review this month’s spending to get back on track.")
                self.status_label.setProperty("state", "warning")
        self.status_label.setVisible(not self._dense)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.edit_button.setText("Edit Goal")


class QuickStatsCard(SectionCard):
    def __init__(self) -> None:
        super().__init__("quickStatsCard")
        self._compact: bool | None = None
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(18, 18, 18, 18)
        self.root_layout.setSpacing(14)
        self.header_widget = QWidget()
        self.header_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        heading = QHBoxLayout(self.header_widget)
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(8)
        icon = QLabel()
        icon.setPixmap(awesome_icon("fa6s.chart-simple", color="#49a4ff").pixmap(20, 20))
        self.title_label = QLabel("Quick Stats")
        self.title_label.setObjectName("goalsSectionTitle")
        self.month_label = QLabel()
        self.month_label.setObjectName("goalsMuted")
        heading.addWidget(icon)
        heading.addWidget(self.title_label)
        heading.addStretch()
        heading.addWidget(self.month_label)
        self.root_layout.addWidget(self.header_widget, 0, Qt.AlignmentFlag.AlignTop)

        self.metrics_widget = QWidget()
        self.metrics_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.grid = QGridLayout(self.metrics_widget)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        self.income = MetricTile("Income", "fa6s.wallet", "#49a4ff")
        self.spending = MetricTile("Spending", "fa6s.credit-card", "#ff6670")
        self.rrsp = MetricTile("RRSP Contributions", "fa6s.piggy-bank", "#bd69ee")
        self.net = MetricTile("Net Savings", "fa6s.bullseye", "#4fd594")
        for tile in (self.income, self.spending, self.rrsp, self.net):
            tile.setParent(self.metrics_widget)
        self.set_compact(False)
        self.root_layout.addWidget(self.metrics_widget, 1)

    def set_dense(self, dense: bool) -> None:
        margin = 10 if dense else 18
        self.root_layout.setContentsMargins(margin, margin, margin, margin)
        self.root_layout.setSpacing(8 if dense else 14)
        self.grid.setSpacing(7 if dense else 10)
        for tile in (self.income, self.spending, self.rrsp, self.net):
            tile.set_dense(dense)

    def set_compact(self, compact: bool) -> None:
        if compact == self._compact:
            return
        self._compact = compact
        widgets = (self.income, self.spending, self.rrsp, self.net)
        for widget in widgets:
            self.grid.removeWidget(widget)
        columns = 1 if compact else 2
        for index, widget in enumerate(widgets):
            self.grid.addWidget(widget, index // columns, index % columns)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 0 if compact else 1)
        for row in range(4):
            self.grid.setRowStretch(row, 1 if row < len(widgets) // columns else 0)

    def set_data(self, data: MonthlySavingsBreakdown, month_label: str) -> None:
        self.month_label.setText(month_label)
        self.income.set_data(data.income)
        self.spending.set_data(data.spending)
        total_rrsp = data.work_rrsp_employee + data.work_rrsp_employer
        self.rrsp.set_data(
            total_rrsp,
            f"{_money(data.work_rrsp_employee)} employee • {_money(data.work_rrsp_employer)} employer",
        )
        ratio = (data.net_savings / data.income * Decimal(100)) if data.income else Decimal()
        self.net.set_data(data.net_savings, f"{ratio:.0f}% of income")


class BudgetRow(QFrame):
    edit_requested = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, item: CategoryBudgetProgress, compact: bool, dense: bool = False) -> None:
        super().__init__()
        self.item = item
        self.setObjectName("budgetRow")
        if dense:
            self.setFixedHeight(22)
        else:
            self.setMinimumHeight(46)
        self.layout = QGridLayout(self)
        self.layout.setContentsMargins(9, 2 if dense else 6, 7, 2 if dense else 6)
        self.layout.setHorizontalSpacing(12)
        self.layout.setVerticalSpacing(6)
        self.category_cell = QWidget()
        category_layout = QHBoxLayout(self.category_cell)
        category_layout.setContentsMargins(0, 0, 0, 0)
        category_layout.setSpacing(8)
        category_icon = QLabel()
        badge_size = 18 if dense else 32
        category_icon.setPixmap(_badge_pixmap(
            category_icon_name(item.category_name), item.category_color, badge_size
        ))
        category_icon.setFixedSize(badge_size, badge_size)
        self.category = QLabel(item.category_name)
        self.category.setObjectName("goalsValue")
        category_layout.addWidget(category_icon)
        category_layout.addWidget(self.category)
        category_layout.addStretch()
        self.spent = QLabel(_money(item.spent))
        self.target = QLabel(_money(item.target))
        remaining = item.remaining
        self.remaining = QLabel(_money(remaining) if remaining >= 0 else f"{_money(-remaining)} over")
        self.remaining.setStyleSheet(
            f"color: {'#ff6670' if remaining < 0 else '#4fd594'};"
        )
        self.compact_amount = QLabel(f"{_money(item.spent)} / {_money(item.target)}")
        self.compact_amount.setObjectName("goalsBudgetCompactAmount")
        self.progress = QProgressBar()
        self.progress.setObjectName("goalsProgress")
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(max(0, min(100, int(item.percent))))
        color = "#ff6670" if item.percent > 100 else "#f5ae42" if item.percent >= 85 else "#4fd594"
        self.progress.setStyleSheet(
            "QProgressBar { background:#27313c; border:none; border-radius:5px; }"
            f"QProgressBar::chunk {{ background:{color}; border-radius:5px; }}"
        )
        self.percent = QLabel(f"{item.percent:.0f}%")
        self.action = QToolButton()
        self.action.setObjectName("goalsMenuButton")
        self.action.setFixedSize(22 if dense else 34, 20 if dense else 32)
        self.action.setToolTip(f"Actions for {item.category_name}")
        self.action.setAccessibleName(f"Actions for {item.category_name}")
        set_button_icon(self.action, "fa6s.ellipsis", color="#bbc6d3", active_color="#ffffff")
        self.action.clicked.connect(self._show_menu)
        self.compact = not compact
        self.set_compact(compact)

    def _set_column_stretches(self, compact: bool) -> None:
        stretches = (3, 1, 1, 1, 3, 0, 0) if not compact else (1, 1, 0, 0, 0, 0, 0)
        for column, stretch in enumerate(stretches):
            self.layout.setColumnStretch(column, stretch)

    def set_compact(self, compact: bool) -> None:
        if self.compact == compact:
            return
        self.compact = compact
        for widget in (
            self.category_cell, self.spent, self.target, self.remaining,
            self.compact_amount, self.progress, self.percent, self.action,
        ):
            self.layout.removeWidget(widget)
        if compact:
            self.layout.addWidget(self.category_cell, 0, 0, 1, 2)
            self.layout.addWidget(self.action, 0, 2, alignment=Qt.AlignmentFlag.AlignRight)
            self.layout.addWidget(self.compact_amount, 1, 0)
            self.layout.addWidget(self.remaining, 1, 1, 1, 2, alignment=Qt.AlignmentFlag.AlignRight)
            self.layout.addWidget(self.progress, 2, 0, 1, 2)
            self.layout.addWidget(self.percent, 2, 2, alignment=Qt.AlignmentFlag.AlignRight)
        else:
            self.layout.addWidget(self.category_cell, 0, 0)
            self.layout.addWidget(self.spent, 0, 1)
            self.layout.addWidget(self.target, 0, 2)
            self.layout.addWidget(self.remaining, 0, 3)
            self.layout.addWidget(self.progress, 0, 4)
            self.layout.addWidget(self.percent, 0, 5)
            self.layout.addWidget(self.action, 0, 6)
        self._set_column_stretches(compact)

    def _show_menu(self) -> None:
        menu = QMenu(self)
        edit_action = menu.addAction("Edit budget")
        delete_action = menu.addAction("Remove budget")
        selected = menu.exec(self.action.mapToGlobal(self.action.rect().bottomLeft()))
        if selected is edit_action:
            self.edit_requested.emit(self.item.category_id)
        elif selected is delete_action:
            self.delete_requested.emit(self.item.category_id)


def _goal_visual(name: str) -> tuple[str, str]:
    normalized = name.casefold()
    if any(term in normalized for term in ("house", "home", "down payment")):
        return "fa6s.house", "#2388e8"
    if any(term in normalized for term in ("vacation", "travel", "trip")):
        return "fa6s.plane", "#2388e8"
    if any(term in normalized for term in ("car", "vehicle")):
        return "fa6s.car", "#9a36ba"
    if any(term in normalized for term in ("emergency", "rainy")):
        return "fa6s.umbrella", "#b85f22"
    if any(term in normalized for term in ("school", "education")):
        return "fa6s.graduation-cap", "#2779c8"
    return "fa6s.flag", "#267f92"


class SavingsGoalCard(SectionCard):
    edit_requested = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, item: SavingsGoalRecord, dense: bool = False) -> None:
        super().__init__("savingsGoalCard")
        self.item = item
        self.setMinimumWidth(190 if dense else 235)
        self.setMinimumHeight(82 if dense else 136)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            9 if dense else 13,
            5 if dense else 12,
            9 if dense else 13,
            5 if dense else 11,
        )
        layout.setSpacing(4 if dense else 7)
        heading = QHBoxLayout()
        heading.setSpacing(8)
        icon_name, accent = _goal_visual(item.name)
        icon = QLabel()
        badge_size = 26 if dense else 38
        icon.setPixmap(_badge_pixmap(icon_name, accent, badge_size))
        icon.setFixedSize(badge_size, badge_size)
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title = QLabel(item.name)
        title.setObjectName("savingsGoalTitle")
        title.setWordWrap(True)
        term = QLabel(
            "Long term goal" if item.target_date is None else "Savings target",
            self,
        )
        term.setObjectName("goalsMuted")
        title_box.addWidget(title)
        title_box.addWidget(term)
        term.setHidden(dense)
        action = QToolButton()
        action.setObjectName("goalsMenuButton")
        action.setFixedSize(24 if dense else 32, 22 if dense else 30)
        action.setAccessibleName(f"Actions for {item.name}")
        set_button_icon(action, "fa6s.ellipsis", color="#bbc6d3", active_color="#ffffff")
        action.clicked.connect(self._show_menu)
        self.action = action
        heading.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
        heading.addLayout(title_box, 1)
        heading.addWidget(action, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(heading)
        amount_row = QHBoxLayout()
        amount_row.setSpacing(8)
        amount = QLabel(_money(item.current_amount))
        amount.setObjectName("savingsGoalAmount")
        target_amount = QLabel(f"of {_money(item.target_amount)}")
        target_amount.setObjectName("goalsMuted")
        amount_row.addWidget(amount)
        amount_row.addWidget(target_amount)
        amount_row.addStretch()
        layout.addLayout(amount_row)
        progress_row = QHBoxLayout()
        progress = QProgressBar()
        progress.setObjectName("goalsProgress")
        progress.setTextVisible(False)
        progress.setValue(max(0, min(100, int(item.percent))))
        progress.setStyleSheet(
            "QProgressBar { background:#293440; border:none; border-radius:5px; }"
            f"QProgressBar::chunk {{ background:{accent}; border-radius:5px; }}"
        )
        percent = QLabel(f"{item.percent:.0f}%")
        percent.setObjectName("goalsPercent")
        progress_row.addWidget(progress, 1)
        progress_row.addWidget(percent)
        layout.addLayout(progress_row)
        target = QLabel(
            f"Target date: {item.target_date.strftime('%b %d, %Y')}"
            if item.target_date else "No target date",
            self,
        )
        target.setObjectName("goalsMuted")
        layout.addWidget(target)
        target.setHidden(dense)
        layout.addStretch()

    def _show_menu(self) -> None:
        menu = QMenu(self)
        edit_action = menu.addAction("Edit goal")
        delete_action = menu.addAction("Delete goal")
        selected = menu.exec(self.action.mapToGlobal(self.action.rect().bottomLeft()))
        if selected is edit_action:
            self.edit_requested.emit(self.item.id)
        elif selected is delete_action:
            self.delete_requested.emit(self.item.id)


class MonthlySavingsGoalDialog(GenericDialog):
    def __init__(self, year: int, month: int, current: Decimal, parent=None) -> None:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)

        month_field = _dialog_month_field(year, month)
        layout.addWidget(_dialog_field_label("Month"))
        layout.addWidget(month_field)
        layout.addSpacing(14)

        self.amount = _money_editor(current)
        self.amount.setObjectName("dialogMoneyInput")
        self.amount.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.amount.setMinimumHeight(56)
        self.amount.setAccessibleName("Savings target")
        layout.addWidget(_dialog_field_label("Savings target", self.amount))
        layout.addWidget(self.amount)
        layout.addStretch()

        super().__init__(
            "Monthly Savings Goal",
            content,
            parent,
            submit_label="Save Goal",
            subtitle="Set one calculated savings target for this profile and month.",
            icon_name="fa6s.bullseye",
            info_text=(
                "This target carries forward to future months until you change it. "
                "Progress uses income - spending. Work RRSP employee contributions "
                "and employer matches are excluded because they are not currently usable cash."
            ),
        )
        self.resize(720, 560)
        self.setMinimumSize(580, 510)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API spelling
        super().showEvent(event)
        self.amount.setFocus()
        self.amount.selectAll()


class BudgetDialog(GenericDialog):
    def __init__(self, categories, year: int, month: int, existing=None, parent=None) -> None:
        content = QWidget()
        form = QFormLayout(content)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.category = AppComboBox()
        self.category.setIconSize(spaced_text_icon_size())
        for category_id, name, color in categories:
            self.category.addItem(
                spaced_text_icon(awesome_icon("fa6s.circle", color=color)),
                name,
                category_id,
            )
        self.month = QLabel(date(year, month, 1).strftime("%B %Y"))
        self.amount = _money_editor(existing.target if existing else Decimal())
        form.addRow("Category", self.category)
        form.addRow("Month", self.month)
        form.addRow("Budget amount", self.amount)
        _style_form_labels(form, (self.category, self.month, self.amount))
        if existing:
            index = self.category.findData(existing.category_id)
            self.category.setCurrentIndex(index)
            self.category.setEnabled(False)
        super().__init__(
            "Edit Category Budget" if existing else "Add Category Budget",
            content,
            parent,
            submit_label="Save Budget",
            subtitle="Set this category's spending target for the selected month.",
            icon_name="fa6s.chart-pie",
            info_text=(
                "This budget carries forward until you change or remove it. "
                "Only expense transactions in this category count toward it."
            ),
        )
        self.resize(640, 500)


class SavingsGoalDialog(GenericDialog):
    def __init__(self, existing: SavingsGoalRecord | None = None, parent=None) -> None:
        content = QWidget()
        form = QFormLayout(content)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.name = QLineEdit(existing.name if existing else "")
        self.name.setMaxLength(120)
        self.target = _money_editor(existing.target_amount if existing else Decimal())
        self.current = _money_editor(existing.current_amount if existing else Decimal())
        self.has_date = QCheckBox("Set a target date")
        self.date = DatePickerEdit()
        self.date.setDate(QDate.currentDate().addYears(1))
        if existing and existing.target_date:
            self.has_date.setChecked(True)
            self.date.setDate(QDate(existing.target_date.year, existing.target_date.month, existing.target_date.day))
        self.date.setEnabled(self.has_date.isChecked())
        self.has_date.toggled.connect(self.date.setEnabled)
        date_box = QWidget()
        date_layout = QVBoxLayout(date_box)
        date_layout.setContentsMargins(0, 0, 0, 0)
        date_layout.setSpacing(6)
        date_layout.addWidget(self.has_date)
        date_layout.addWidget(self.date)
        self.notes = QTextEdit(existing.notes or "" if existing else "")
        self.notes.setMaximumHeight(78)
        self.notes.setPlaceholderText("Optional notes")
        form.addRow("Name", self.name)
        form.addRow("Target amount", self.target)
        form.addRow("Current amount", self.current)
        form.addRow("Target date", date_box)
        form.addRow("Notes", self.notes)
        _style_form_labels(
            form,
            (self.name, self.target, self.current, date_box, self.notes),
        )
        super().__init__(
            "Edit Savings Goal" if existing else "Add Savings Goal",
            content,
            parent,
            submit_label="Save Goal",
            subtitle="Track a longer-term goal independently from your monthly target.",
            icon_name="fa6s.flag",
        )
        self.resize(680, 650)

    def selected_date(self) -> date | None:
        return self.date.date().toPython() if self.has_date.isChecked() else None


class GoalsPage(QWidget):
    TOP_STACK_WIDTH = 880
    COMPACT_BUDGET_WIDTH = 760
    DENSE_HEIGHT = 720

    def __init__(self, session_factory=SessionLocal) -> None:
        super().__init__()
        self.setObjectName("goalsPage")
        self.session_factory = session_factory
        self.user_id: str | None = None
        self.group_id: int | None = None
        self._budget_items: tuple[CategoryBudgetProgress, ...] = ()
        self._goal_items: tuple[SavingsGoalRecord, ...] = ()
        self._header_stacked: bool | None = None
        self._top_stacked: bool | None = None
        self._budget_compact: bool | None = None
        self._goal_columns = 0
        self._dense: bool | None = None

        self.page_layout = QVBoxLayout(self)
        self.page_layout.setContentsMargins(28, 24, 28, 20)
        self.page_layout.setSpacing(16)
        self.header_container = QWidget()
        self.header_layout = QGridLayout(self.header_container)
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        self.header_layout.setSpacing(10)
        self.header = PageHeader(
            "Goals",
            "Set your savings target, manage category limits, and track your progress.",
        )
        self.month_navigator = MonthNavigator()
        self.month_navigator.month_changed.connect(lambda _y, _m: self.reload())
        self.header_layout.addWidget(self.header, 0, 0)
        self.header_layout.addWidget(self.month_navigator, 0, 1, alignment=Qt.AlignmentFlag.AlignTop)
        self.header_layout.setColumnStretch(0, 1)
        self.page_layout.addWidget(self.header_container)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("goalsScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.content.setObjectName("goalsContent")
        self.content.setMinimumWidth(0)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(16)

        self.top = QWidget()
        self.top.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.top_layout = QGridLayout(self.top)
        self.top_layout.setContentsMargins(0, 0, 0, 0)
        self.top_layout.setSpacing(16)
        self.monthly_card = MonthlySavingsCard()
        self.quick_stats = QuickStatsCard()
        for card in (self.monthly_card, self.quick_stats):
            card.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
        self.monthly_card.edit_requested.connect(self._edit_monthly_goal)
        self.content_layout.addWidget(self.top)

        self.budget_section = SectionCard("categoryBudgetsCard")
        self.budget_section.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.budget_layout = QVBoxLayout(self.budget_section)
        self.budget_layout.setContentsMargins(18, 16, 18, 16)
        self.budget_layout.setSpacing(12)
        budget_heading = QHBoxLayout()
        budget_heading.setSpacing(8)
        budget_icon = QLabel()
        budget_icon.setPixmap(awesome_icon("fa6s.chart-pie", color="#49a4ff").pixmap(21, 21))
        budget_titles = QVBoxLayout()
        budget_title = QLabel("Category Budgets")
        budget_title.setObjectName("goalsSectionTitle")
        self.budget_subtitle = QLabel("Set monthly limits for your spending categories.")
        self.budget_subtitle.setObjectName("goalsMuted")
        budget_titles.addWidget(budget_title)
        budget_titles.addWidget(self.budget_subtitle)
        self.add_budget_button = QPushButton("Add Budget")
        self.add_budget_button.setObjectName("secondaryActionButton")
        set_button_icon(self.add_budget_button, "fa6s.plus", color="#61adff", active_color="#ffffff")
        self.add_budget_button.clicked.connect(lambda: self._edit_budget(None))
        budget_heading.addWidget(budget_icon, alignment=Qt.AlignmentFlag.AlignTop)
        budget_heading.addLayout(budget_titles, 1)
        budget_heading.addWidget(self.add_budget_button, alignment=Qt.AlignmentFlag.AlignTop)
        self.budget_layout.addLayout(budget_heading)
        self.budget_header = QWidget()
        self.budget_header.setObjectName("goalsBudgetHeader")
        self.budget_header_layout = QGridLayout(self.budget_header)
        self.budget_header_layout.setContentsMargins(11, 8, 9, 7)
        self.budget_header_layout.setHorizontalSpacing(12)
        headers = (
            (0, "Category"), (1, "Spent"), (2, "Budget"),
            (3, "Remaining"), (4, "Progress"),
        )
        for column, text in headers:
            label = QLabel(text)
            label.setObjectName("goalsTableHeader")
            self.budget_header_layout.addWidget(label, 0, column, 1, 2 if column == 4 else 1)
        for column, stretch in enumerate((3, 1, 1, 1, 3, 0, 0)):
            self.budget_header_layout.setColumnStretch(column, stretch)
        self.budget_layout.addWidget(self.budget_header)
        self.budget_rows = QWidget()
        self.budget_rows.setObjectName("goalsBudgetTable")
        self.budget_rows_layout = QVBoxLayout(self.budget_rows)
        self.budget_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.budget_rows_layout.setSpacing(0)
        self.budget_layout.addWidget(self.budget_rows)
        self.content_layout.addWidget(self.budget_section)

        self.goals_section = SectionCard("longTermGoalsCard")
        self.goals_section.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.goals_layout = QVBoxLayout(self.goals_section)
        self.goals_layout.setContentsMargins(18, 16, 18, 16)
        self.goals_layout.setSpacing(12)
        goals_heading = QHBoxLayout()
        goals_heading.setSpacing(8)
        goals_icon = QLabel()
        goals_icon.setPixmap(awesome_icon("fa6s.flag", color="#49a4ff").pixmap(21, 21))
        goals_titles = QVBoxLayout()
        goals_title = QLabel("Savings Goals")
        goals_title.setObjectName("goalsSectionTitle")
        self.goals_subtitle = QLabel("Create and track specific longer-term savings goals.")
        self.goals_subtitle.setObjectName("goalsMuted")
        goals_titles.addWidget(goals_title)
        goals_titles.addWidget(self.goals_subtitle)
        self.add_goal_button = QPushButton("Add Goal")
        self.add_goal_button.setObjectName("secondaryActionButton")
        set_button_icon(self.add_goal_button, "fa6s.plus", color="#61adff", active_color="#ffffff")
        self.add_goal_button.clicked.connect(lambda: self._edit_long_term_goal(None))
        goals_heading.addWidget(goals_icon, alignment=Qt.AlignmentFlag.AlignTop)
        goals_heading.addLayout(goals_titles, 1)
        goals_heading.addWidget(self.add_goal_button, alignment=Qt.AlignmentFlag.AlignTop)
        self.goals_layout.addLayout(goals_heading)
        self.goals_grid_widget = QWidget()
        self.goals_grid = QGridLayout(self.goals_grid_widget)
        self.goals_grid.setContentsMargins(0, 0, 0, 0)
        self.goals_grid.setSpacing(10)
        self.goals_layout.addWidget(self.goals_grid_widget)
        self.content_layout.addWidget(self.goals_section)
        # On tall windows, distribute spare height across the actual sections
        # instead of leaving a large empty band below the page. When the
        # viewport is short, each section keeps its size hint and the scroll
        # area continues to provide vertical overflow normally.
        self.content_layout.setStretch(0, 5)
        self.content_layout.setStretch(1, 4)
        self.content_layout.setStretch(2, 4)
        self.scroll.setWidget(self.content)
        self.page_layout.addWidget(self.scroll, 1)

        self.setStyleSheet("""
            QScrollArea#goalsScroll, QWidget#goalsContent { background: transparent; border: none; }
            QFrame#monthlySavingsCard, QFrame#quickStatsCard,
            QFrame#categoryBudgetsCard, QFrame#longTermGoalsCard,
            QFrame#savingsGoalCard {
                background: #151b21;
                border: 1px solid #303b46;
                border-radius: 14px;
            }
            QFrame#goalsMetricTile, QFrame#goalsBreakdown {
                background: #111820;
                border: 1px solid #293641;
                border-radius: 10px;
            }
            QWidget#goalsBudgetHeader {
                background: #171e26;
                border: 1px solid #25313c;
                border-bottom: none;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
            QWidget#goalsBudgetTable {
                background: #10171d;
                border: 1px solid #25313c;
                border-bottom-left-radius: 10px;
                border-bottom-right-radius: 10px;
            }
            QFrame#budgetRow {
                background: transparent;
                border: none;
                border-bottom: 1px solid #25313c;
                border-radius: 0;
            }
            QLabel#goalsSectionTitle { color: #f4f6f8; font-size: 16px; font-weight: 650; }
            QLabel#goalsMuted { color: #9ca9b8; font-size: 11px; }
            QLabel#goalsValue { color: #eef2f6; font-weight: 600; }
            QLabel#monthlySavingsValue { color: #4fd594; font-size: 31px; font-weight: 700; }
            QLabel#goalsTarget { color: #aeb8c5; font-size: 13px; }
            QLabel#goalsRemaining { color: #d4dbe4; font-size: 11px; }
            QLabel#goalsMetricTitle { color: #b9c3cf; font-size: 11px; }
            QLabel#goalsMetricValue { color: #f4f6f8; font-size: 18px; font-weight: 650; }
            QLabel#goalsMetricDetail { color: #91a0b1; font-size: 9px; }
            QLabel#goalsSmallHeading { color: #e4e9ef; font-size: 10px; font-weight: 650; }
            QLabel#goalsTableHeader { color: #b8c3cf; font-size: 10px; font-weight: 550; }
            QLabel#goalsBreakdownName { font-size: 10px; }
            QLabel#goalsBreakdownValue { color: #e7ebef; }
            QLabel#goalsBreakdownNet { color: #4fd594; font-size: 13px; font-weight: 700; }
            QFrame#goalsBreakdownDivider { color: #33404c; border-top: 1px solid #33404c; max-height: 1px; }
            QLabel#goalsStatus { background:#1b2930; color:#c8d1dc; border-radius:7px; padding:8px 10px; }
            QLabel#goalsStatus[state="positive"] { background:#14332b; color:#57de9b; border:1px solid #20513f; }
            QLabel#goalsStatus[state="warning"] { background:#35291a; color:#efb958; border:1px solid #5b4320; }
            QLabel#savingsGoalTitle { color:#f2f5f8; font-size:11px; font-weight:650; }
            QLabel#savingsGoalAmount { color: #f4f6f8; font-size: 16px; font-weight: 700; }
            QLabel#goalsPercent { color:#dce3ea; font-size:10px; }
            QLabel#goalsBudgetCompactAmount { color:#e4e9ef; font-weight:600; }
            QFrame#goalsMonthDisplay { background:#151b21; border-top:1px solid #34404d; border-bottom:1px solid #34404d; }
            QComboBox#goalsMonthSelector, QComboBox#goalsYearSelector {
                color:#edf2f7;
                background:transparent;
                border:none;
                padding:7px 22px 7px 8px;
                font-size:12px;
            }
            QComboBox#goalsMonthSelector:hover, QComboBox#goalsYearSelector:hover {
                background:#222b35;
            }
            QComboBox#goalsMonthSelector::drop-down, QComboBox#goalsYearSelector::drop-down {
                width:20px;
                border:none;
            }
            QComboBox#goalsMonthSelector::down-arrow, QComboBox#goalsYearSelector::down-arrow {
                image:none;
            }
            QComboBox#goalsMonthSelector QAbstractItemView,
            QComboBox#goalsYearSelector QAbstractItemView {
                color:#e5e8ee;
                background:#171b21;
                border:1px solid #343c48;
                selection-color:#ffffff;
                selection-background-color:#4468f2;
                padding:0;
                margin:0;
                outline:none;
            }
            QFrame#goalsMonthDivider { background:#34404d; border:none; }
            QToolButton#goalsMonthButton, QToolButton#goalsMenuButton { background:#151b21; border:1px solid #34404d; padding:5px; }
            QToolButton#goalsMonthButton:hover, QToolButton#goalsMenuButton:hover { background:#27313c; }
            QProgressBar#goalsProgress { background:#293440; border:none; border-radius:5px; min-height:10px; max-height:10px; }
            QProgressBar#goalsProgress::chunk { background:#4fd594; border-radius:5px; }
        """)
        QTimer.singleShot(0, self._reflow)

    @property
    def selected_month(self) -> tuple[int, int]:
        return self.month_navigator.selected_month

    def set_profile(self, *, user_id: str | None = None, group_id: int | None = None) -> None:
        self.user_id = user_id
        self.group_id = group_id
        enabled = user_id is not None or group_id is not None
        self.add_budget_button.setEnabled(enabled)
        self.add_goal_button.setEnabled(enabled)
        self.monthly_card.edit_button.setEnabled(enabled)
        self.reload()

    def reload(self) -> None:
        if self.user_id is None and self.group_id is None:
            return
        year, month = self.selected_month
        month_label = date(year, month, 1).strftime("%B %Y")
        data = get_monthly_savings_breakdown(
            year, month, user_id=self.user_id, group_id=self.group_id,
            session_factory=self.session_factory,
        )
        self.monthly_card.set_data(data, month_label)
        self.quick_stats.set_data(data, month_label)
        self._budget_items = get_category_budgets(
            year, month, user_id=self.user_id, group_id=self.group_id,
            session_factory=self.session_factory,
        )
        self._goal_items = get_savings_goals(
            user_id=self.user_id, group_id=self.group_id,
            session_factory=self.session_factory,
        )
        self._render_budget_rows()
        self._render_goal_cards()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reflow()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API spelling
        # A stacked page can be resized while hidden, so refresh the breakpoints
        # before it paints, then verify once Qt has finalized the viewport.
        self._reflow()
        super().showEvent(event)
        QTimer.singleShot(0, self._reflow)

    def _reflow(self) -> None:
        width = max(0, self.scroll.viewport().width())
        dense = self.height() <= self.DENSE_HEIGHT
        if dense != self._dense:
            self._dense = dense
            page_horizontal = 18 if dense else 28
            self.page_layout.setContentsMargins(
                page_horizontal,
                12 if dense else 24,
                page_horizontal,
                12 if dense else 20,
            )
            self.page_layout.setSpacing(10 if dense else 16)
            self.content_layout.setSpacing(10 if dense else 16)
            self.top_layout.setSpacing(10 if dense else 16)
            section_margin = 12 if dense else 18
            section_vertical = 8 if dense else 16
            for section_layout in (self.budget_layout, self.goals_layout):
                section_layout.setContentsMargins(
                    section_margin,
                    section_vertical,
                    section_margin,
                    section_vertical,
                )
                section_layout.setSpacing(7 if dense else 12)
            self.budget_header_layout.setContentsMargins(
                8 if dense else 11,
                4 if dense else 8,
                7 if dense else 9,
                4 if dense else 7,
            )
            self.budget_subtitle.setVisible(not dense)
            self.goals_subtitle.setVisible(not dense)
            self.monthly_card.set_dense(dense)
            self.quick_stats.set_dense(dense)
            self._render_budget_rows()
            self._render_goal_cards()
        header_stacked = width < 900
        if header_stacked != self._header_stacked:
            self._header_stacked = header_stacked
            self.header_layout.removeWidget(self.header)
            self.header_layout.removeWidget(self.month_navigator)
            self.header_layout.addWidget(self.header, 0, 0)
            self.header_layout.addWidget(
                self.month_navigator,
                1 if header_stacked else 0,
                0 if header_stacked else 1,
                alignment=Qt.AlignmentFlag.AlignLeft if header_stacked else Qt.AlignmentFlag.AlignTop,
            )
            self.header_layout.setColumnStretch(0, 1)
            self.header_layout.setColumnStretch(1, 0)
        stacked = width < self.TOP_STACK_WIDTH
        self.top.setMaximumHeight(
            172 if dense and not stacked else 16_777_215
        )
        if stacked != self._top_stacked:
            self._top_stacked = stacked
            self.top_layout.removeWidget(self.monthly_card)
            self.top_layout.removeWidget(self.quick_stats)
            self.top_layout.addWidget(self.monthly_card, 0, 0)
            self.top_layout.addWidget(self.quick_stats, 1 if stacked else 0, 0 if stacked else 1)
            self.top_layout.setColumnStretch(0, 2)
            self.top_layout.setColumnStretch(1, 1 if not stacked else 0)
            self.top_layout.setRowStretch(0, 1)
            self.top_layout.setRowStretch(1, 1 if stacked else 0)
        self.monthly_card.set_compact(stacked and width < 780)
        self.quick_stats.set_compact(stacked and width < 480)
        compact = width < self.COMPACT_BUDGET_WIDTH
        if compact != self._budget_compact:
            self._budget_compact = compact
            self.budget_header.setVisible(not compact)
            self._render_budget_rows()
        if dense:
            columns = 1 if width < 540 else 2 if width < 700 else 3 if width < 860 else 4
        else:
            columns = 1 if width < 610 else 2 if width < 900 else 3 if width < 1220 else 4
        if columns != self._goal_columns:
            self._goal_columns = columns
            self._render_goal_cards()
        content_policy = self.content.sizePolicy()
        content_policy.setHorizontalPolicy(QSizePolicy.Policy.Expanding)
        content_policy.setVerticalPolicy(
            QSizePolicy.Policy.Ignored if dense else QSizePolicy.Policy.Preferred
        )
        self.content.setSizePolicy(content_policy)
        self.content.setMinimumHeight(0)
        if dense:
            section_heights = (
                min(self.top.minimumSizeHint().height(), self.top.maximumHeight()),
                self.budget_section.minimumSizeHint().height(),
                self.goals_section.minimumSizeHint().height(),
            )
            self.content.setMinimumHeight(
                sum(section_heights) + self.content_layout.spacing() * 2
            )

    def _render_budget_rows(self) -> None:
        _clear_layout(self.budget_rows_layout)
        if not self._budget_items:
            empty = QLabel("No category budgets set for this month.")
            empty.setObjectName("goalsMuted")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(34 if self._dense else 70)
            self.budget_rows_layout.addWidget(empty)
            return
        for item in self._budget_items:
            row = BudgetRow(item, bool(self._budget_compact), bool(self._dense))
            row.edit_requested.connect(self._edit_budget)
            row.delete_requested.connect(self._delete_budget)
            self.budget_rows_layout.addWidget(row)

    def _render_goal_cards(self) -> None:
        _clear_layout(self.goals_grid)
        if not self._goal_items:
            empty = QLabel("No savings goals yet.")
            empty.setObjectName("goalsMuted")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(42 if self._dense else 80)
            self.goals_grid.addWidget(empty, 0, 0)
            return
        columns = max(1, self._goal_columns)
        for index, item in enumerate(self._goal_items):
            card = SavingsGoalCard(item, bool(self._dense))
            card.edit_requested.connect(self._edit_long_term_goal)
            card.delete_requested.connect(self._delete_long_term_goal)
            self.goals_grid.addWidget(card, index // columns, index % columns)
        for column in range(columns):
            self.goals_grid.setColumnStretch(column, 1)

    def _edit_monthly_goal(self) -> None:
        year, month = self.selected_month
        current = get_monthly_savings_breakdown(
            year, month, user_id=self.user_id, group_id=self.group_id,
            session_factory=self.session_factory,
        ).target or Decimal()
        dialog = MonthlySavingsGoalDialog(year, month, current, self)
        def save() -> None:
            try:
                set_monthly_savings_goal(
                    year, month, Decimal(str(dialog.amount.value())),
                    user_id=self.user_id, group_id=self.group_id,
                    session_factory=self.session_factory,
                )
            except ValueError as exc:
                QMessageBox.warning(dialog, "Invalid Goal", str(exc))
                return
            dialog.accept()
            self.reload()
        dialog.submitted.connect(save)
        dialog.exec()

    def _edit_budget(self, category_id: int | None) -> None:
        existing = next((item for item in self._budget_items if item.category_id == category_id), None)
        categories = list_budget_categories(session_factory=self.session_factory)
        if not categories:
            QMessageBox.information(self, "Category Budgets", "Create a category before adding a budget.")
            return
        year, month = self.selected_month
        dialog = BudgetDialog(categories, year, month, existing, self)
        def save() -> None:
            selected_category = dialog.category.currentData()
            if selected_category is None:
                QMessageBox.warning(dialog, "Invalid Budget", "Choose a category.")
                return
            try:
                create_or_update_category_budget(
                    selected_category, year, month, Decimal(str(dialog.amount.value())),
                    user_id=self.user_id, group_id=self.group_id,
                    session_factory=self.session_factory,
                )
            except ValueError as exc:
                QMessageBox.warning(dialog, "Invalid Budget", str(exc))
                return
            dialog.accept()
            self.reload()
        dialog.submitted.connect(save)
        dialog.exec()

    def _delete_budget(self, category_id: int) -> None:
        item = next((value for value in self._budget_items if value.category_id == category_id), None)
        if item is None:
            return
        year, month = self.selected_month
        month_label = date(year, month, 1).strftime("%B %Y")
        answer = QMessageBox.question(
            self,
            "Remove Budget",
            (
                f"Remove the {item.category_name} budget from {month_label} onward? "
                "Earlier months will not change."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        delete_category_budget(
            category_id, year, month, user_id=self.user_id, group_id=self.group_id,
            session_factory=self.session_factory,
        )
        self.reload()

    def _edit_long_term_goal(self, goal_id: int | None) -> None:
        existing = next((item for item in self._goal_items if item.id == goal_id), None)
        dialog = SavingsGoalDialog(existing, self)
        def save() -> None:
            try:
                values = dict(
                    name=dialog.name.text(),
                    target_amount=Decimal(str(dialog.target.value())),
                    current_amount=Decimal(str(dialog.current.value())),
                    target_date=dialog.selected_date(),
                    notes=dialog.notes.toPlainText(),
                    user_id=self.user_id,
                    group_id=self.group_id,
                    session_factory=self.session_factory,
                )
                if existing is None:
                    create_savings_goal(**values)
                else:
                    update_savings_goal(existing.id, **values)
            except ValueError as exc:
                QMessageBox.warning(dialog, "Invalid Savings Goal", str(exc))
                return
            dialog.accept()
            self.reload()
        dialog.submitted.connect(save)
        dialog.exec()

    def _delete_long_term_goal(self, goal_id: int) -> None:
        item = next((value for value in self._goal_items if value.id == goal_id), None)
        if item is None:
            return
        answer = QMessageBox.question(
            self, "Delete Savings Goal", f"Delete “{item.name}”? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        delete_savings_goal(
            goal_id, user_id=self.user_id, group_id=self.group_id,
            session_factory=self.session_factory,
        )
        self.reload()
