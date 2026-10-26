from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.services.dashboard import CategorySpending
from app.services.finance_services import BudgetProgress
from app.ui.theme import COLORS, set_button_icon, set_label_icon


def format_currency(value: Decimal, *, cents: bool = False) -> str:
    precision = 2 if cents else 0
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.{precision}f}"


class _ElidedLabel(QLabel):
    """Keep dense dashboard rows readable when their card becomes narrow."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.full_text = text
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        available = max(self.contentsRect().width(), 0)
        clipped = self.fontMetrics().horizontalAdvance(self.full_text) > available
        self.setText(
            self.fontMetrics().elidedText(
                self.full_text,
                Qt.TextElideMode.ElideRight,
                available,
            )
        )
        self.setToolTip(self.full_text if clipped else "")


class DashboardCard(QFrame):
    """Common card shell used by every dashboard panel."""

    def __init__(
        self,
        title: str,
        icon: str,
        accent: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setMinimumWidth(280)
        self.setMinimumHeight(250)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 18, 20, 18)
        self.layout.setSpacing(12)

        self.header_layout = QHBoxLayout()
        self.header_layout.setSpacing(8)
        icon_container = QFrame()
        icon_container.setObjectName("dashboardIcon")
        icon_container.setFixedSize(36, 36)
        icon_layout = QHBoxLayout(icon_container)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_label = QLabel()
        set_label_icon(icon_label, icon, color=accent, size=17)
        icon_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignCenter)
        icon_container.setStyleSheet(
            f"QFrame#dashboardIcon {{ background: {QColor(accent).darker(300).name()};"
            f" border: 1px solid {QColor(accent).darker(190).name()};"
            " border-radius: 10px; }"
        )
        self.header_layout.addWidget(icon_container)

        heading = QVBoxLayout()
        heading.setSpacing(1)
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("cardSubtitle")
        heading.addWidget(title_label)
        heading.addWidget(self.subtitle_label)
        self.header_layout.addLayout(heading, 1)
        self.layout.addLayout(self.header_layout)

        self.setStyleSheet(f"""
            QFrame#dashboardCard {{
                background: {COLORS['surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 14px;
            }}
            QFrame#dashboardCard QLabel {{ background: transparent; border: none; }}
            QLabel#cardTitle {{
                color: {COLORS['text']};
                font-size: 15px;
                font-weight: 700;
            }}
            QLabel#cardSubtitle {{
                color: {COLORS['text_dim']};
                font-size: 11px;
            }}
        """)

    def add_header_action(self, tooltip: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName("dashboardHeaderAction")
        button.setFixedSize(30, 30)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        set_button_icon(
            button,
            "fa6s.arrow-right",
            color="#8fc5ff",
            active_color="#ffffff",
            size=13,
        )
        button.setStyleSheet("""
            QToolButton#dashboardHeaderAction {
                background: #172433;
                border: 1px solid #315a82;
                border-radius: 8px;
            }
            QToolButton#dashboardHeaderAction:hover {
                background: #1e5f9f;
                border-color: #4aa3ff;
            }
        """)
        self.header_layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignTop)
        return button


class SummaryRow(QWidget):
    def __init__(self, label: str, value: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(10)
        self.label_widget = QLabel(label)
        self.label_widget.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px;"
        )
        self.value_widget = QLabel(value)
        self.value_widget.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 11px; font-weight: 650;"
        )
        self.value_widget.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self.label_widget, 1)
        layout.addWidget(self.value_widget)

    def set_values(self, label: str, value: str) -> None:
        self.label_widget.setText(label)
        self.value_widget.setText(value)


class SparklineChart(QWidget):
    def __init__(self, accent: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.accent = accent
        self.values: tuple[Decimal, ...] = ()
        self.setMinimumHeight(50)

    def set_data(self, values: tuple[Decimal, ...]) -> None:
        self.values = values
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.values:
            return

        plot = self.rect().adjusted(3, 7, -3, -7)
        minimum = min(float(value) for value in self.values)
        maximum = max(float(value) for value in self.values)
        spread = max(maximum - minimum, 1.0)
        step = plot.width() / max(len(self.values) - 1, 1)
        points = [
            QPointF(
                plot.left() + index * step,
                plot.bottom()
                - ((float(value) - minimum) / spread) * plot.height(),
            )
            for index, value in enumerate(self.values)
        ]
        line = QPainterPath(points[0])
        for point in points[1:]:
            line.lineTo(point)

        fill = QPainterPath(line)
        fill.lineTo(points[-1].x(), plot.bottom())
        fill.lineTo(points[0].x(), plot.bottom())
        fill.closeSubpath()
        gradient = QLinearGradient(0, plot.top(), 0, plot.bottom())
        top_color = QColor(self.accent)
        top_color.setAlpha(80)
        bottom_color = QColor(self.accent)
        bottom_color.setAlpha(5)
        gradient.setColorAt(0, top_color)
        gradient.setColorAt(1, bottom_color)
        painter.fillPath(fill, gradient)
        painter.setPen(QPen(QColor(self.accent), 2.0))
        painter.drawPath(line)


class MetricCard(DashboardCard):
    def __init__(
        self,
        title: str,
        icon: str,
        accent: str,
        improvement_when_down: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, icon, accent, parent)
        self.accent = accent
        self.improvement_when_down = improvement_when_down
        self.total_value = QLabel("$0")
        self.total_value.setStyleSheet(
            f"color: {accent}; font-size: 32px; font-weight: 800;"
        )
        self.total_caption = QLabel()
        self.total_caption.setWordWrap(True)
        self.total_caption.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; font-weight: 600;"
        )

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"color: {COLORS['border_soft']};")

        self.rows = QWidget()
        self.rows_layout = QVBoxLayout(self.rows)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(4)
        self.person_rows: list[SummaryRow] = []
        self.rows_scroll = _transparent_scroll(self.rows)

        self.trend_frame = QFrame()
        self.trend_frame.setObjectName("metricTrend")
        trend_layout = QHBoxLayout(self.trend_frame)
        trend_layout.setContentsMargins(9, 5, 9, 5)
        trend_layout.setSpacing(10)
        self.chart = SparklineChart(accent)
        self.change_label = QLabel()
        self.change_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        trend_layout.addWidget(self.chart, 1)
        trend_layout.addWidget(self.change_label)
        tint = QColor(accent)
        tint.setAlpha(22)
        self.trend_frame.setStyleSheet(f"""
            QFrame#metricTrend {{
                background: rgba({tint.red()}, {tint.green()}, {tint.blue()}, 22);
                border: 1px solid {QColor(accent).darker(260).name()};
                border-radius: 9px;
            }}
        """)

        self.layout.addWidget(self.total_value)
        self.layout.addWidget(self.total_caption)
        self.layout.addWidget(divider)
        self.layout.addWidget(self.rows_scroll, 1)
        self.layout.addWidget(self.trend_frame)

    def set_data(
        self,
        period_label: str,
        total_caption: str,
        total: Decimal,
        previous: Decimal | None,
        rows: tuple[tuple[str, Decimal], ...],
        trend_values: tuple[Decimal, ...],
        person_rows: tuple[tuple[str, Decimal], ...] = (),
    ) -> None:
        self.subtitle_label.setText(period_label)
        self.total_caption.setText(total_caption)
        self.total_value.setText(format_currency(total))
        _clear_layout(self.rows_layout)
        self.person_rows = []
        for label, value in rows:
            self.rows_layout.addWidget(SummaryRow(label, format_currency(value)))
        if person_rows:
            section_divider = QFrame()
            section_divider.setFrameShape(QFrame.Shape.HLine)
            section_divider.setStyleSheet(f"color: {COLORS['border_soft']};")
            self.rows_layout.addWidget(section_divider)
            section_title = QLabel("By person")
            section_title.setObjectName("metricSectionTitle")
            section_title.setStyleSheet(
                f"color: {COLORS['text_dim']}; font-size: 10px; font-weight: 700;"
            )
            self.rows_layout.addWidget(section_title)
            for label, value in person_rows:
                row = SummaryRow(label, format_currency(value))
                self.person_rows.append(row)
                self.rows_layout.addWidget(row)
        self.rows_layout.addStretch()

        if previous is None:
            self.change_label.setText("All history")
            color = self.accent
            weight = 400
        elif previous == 0:
            self.change_label.setText("No prior\nactivity")
            color = self.accent
            weight = 400
        else:
            change = (total - previous) / previous * 100
            is_up = change >= 0
            color = self.accent
            weight = 650
            direction = "↑" if is_up else "↓"
            self.change_label.setText(
                f"{direction} {abs(change):.0f}%\nvs. last month"
            )
        self.change_label.setStyleSheet(
            f"color: {color}; font-size: 10px; font-weight: {weight};"
        )
        self.chart.set_data(trend_values)


class SavingsCard(DashboardCard):
    goals_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Savings", "fa6s.piggy-bank", "#56c596", parent)
        self.open_goals_button = self.add_header_action("Open Goals")
        self.open_goals_button.clicked.connect(self.goals_requested.emit)
        self.goal_caption = QLabel("Monthly goal")
        self.goal_caption.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px;"
        )
        self.goal_value = QLabel("Not set")
        self.goal_value.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 29px; font-weight: 800;"
        )
        self.cash_saved_row = SummaryRow("Cash saved", "$0")
        self.work_rrsp_row = SummaryRow("Work RRSP", "$0")
        self.actual_row = SummaryRow("Personal savings total", "$0")
        self.employer_match_row = SummaryRow("Employer match", "+$0")
        self.balance_row = SummaryRow("Savings balance", "Not recorded")
        self.progress = QProgressBar()
        self.progress.setObjectName("savingsProgress")
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress_label = QLabel("Set a goal to track progress")
        self.progress_label.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 10px;"
        )
        self.layout.addWidget(self.goal_caption)
        self.layout.addWidget(self.goal_value)
        self.layout.addWidget(self.cash_saved_row)
        self.layout.addWidget(self.work_rrsp_row)
        self.layout.addWidget(self.actual_row)
        self.layout.addWidget(self.employer_match_row)
        self.layout.addWidget(self.balance_row)
        self.layout.addStretch()
        self.layout.addWidget(self.progress)
        self.layout.addWidget(self.progress_label)
        self.progress.setStyleSheet(f"""
            QProgressBar#savingsProgress {{
                background: {COLORS['surface_alt']}; border: none; border-radius: 4px;
            }}
            QProgressBar#savingsProgress::chunk {{
                background: #56c596; border-radius: 4px;
            }}
        """)

    def set_data(
        self,
        period_label: str,
        goal: Decimal | None,
        actual: Decimal,
        balance: Decimal | None,
        cash_actual: Decimal | None = None,
        work_rrsp_employee: Decimal = Decimal(),
        employer_match: Decimal = Decimal(),
    ) -> None:
        self.subtitle_label.setText(period_label)
        self.goal_caption.setText(
            "Total savings goals" if period_label == "All time" else "Monthly goal"
        )
        self.goal_value.setText(
            format_currency(goal) if goal is not None else "Not set"
        )
        cash = actual if cash_actual is None else cash_actual
        self.cash_saved_row.set_values("Cash saved", format_currency(cash))
        self.work_rrsp_row.set_values(
            "Work RRSP", format_currency(work_rrsp_employee)
        )
        self.actual_row.set_values(
            "Net savings toward goal", format_currency(actual)
        )
        match_text = format_currency(employer_match)
        if employer_match >= 0:
            match_text = f"+{match_text}"
        self.employer_match_row.set_values("Employer match", match_text)
        self.balance_row.set_values(
            "Savings balance",
            format_currency(balance) if balance is not None else "Not recorded",
        )
        if goal is None or goal <= 0:
            self.progress.setValue(0)
            self.progress_label.setText("Set a monthly goal to track progress")
            color = COLORS["text_dim"]
            weight = 400
        else:
            percentage = float(actual / goal * 100)
            self.progress.setValue(min(round(percentage), 100))
            met = actual >= goal
            remaining = format_currency(goal - actual)
            self.progress_label.setText(
                f"{percentage:.0f}% complete - {'goal met' if met else remaining + ' to go'}"
            )
            color = COLORS["positive"] if met else COLORS["text_muted"]
            weight = 650
        self.progress_label.setStyleSheet(
            f"color: {color}; font-size: 10px; font-weight: {weight};"
        )

class DonutChart(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.items: tuple[CategorySpending, ...] = ()
        self.total = Decimal()
        self.setMinimumSize(135, 135)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

    def set_data(self, items: tuple[CategorySpending, ...]) -> None:
        self.items = items
        self.total = sum((item.amount for item in items), Decimal())
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ring, pen_width = self._ring_geometry(self.width(), self.height())
        pen = QPen(QColor(COLORS["surface_hover"]), pen_width)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.drawArc(ring, 0, 360 * 16)
        if self.total > 0:
            start = 90 * 16
            for item in self.items:
                span = -float(item.amount / self.total) * 360 * 16
                pen.setColor(QColor(item.color))
                painter.setPen(pen)
                painter.drawArc(ring, int(start), int(span))
                start += span
        painter.setPen(QColor(COLORS["text"]))
        painter.setFont(QFont(self.font().family(), 11, QFont.Weight.Bold))
        painter.drawText(
            self.rect().adjusted(0, -6, 0, 0),
            Qt.AlignmentFlag.AlignCenter,
            format_currency(self.total),
        )
        painter.setPen(QColor(COLORS["text_dim"]))
        painter.setFont(QFont(self.font().family(), 8))
        painter.drawText(
            self.rect().adjusted(0, 20, 0, 0),
            Qt.AlignmentFlag.AlignCenter,
            "Total",
        )

    @staticmethod
    def _ring_geometry(width: int, height: int) -> tuple[QRectF, int]:
        """Keep the full antialiased stroke inside the chart's paint bounds."""
        available = max(min(width, height), 1)
        pen_width = max(13, min(46, int(available * 0.14)))
        inset = pen_width / 2 + 3
        diameter = max(1.0, available - inset * 2)
        return (
            QRectF(
                (width - diameter) / 2,
                (height - diameter) / 2,
                diameter,
                diameter,
            ),
            pen_width,
        )


class CategoryCard(DashboardCard):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            "Spending by Category", "fa6s.chart-pie", "#9a83e8", parent
        )
        content = QHBoxLayout()
        content.setSpacing(14)
        self.donut = DonutChart()
        content.addWidget(self.donut, 1)
        self.legend = QWidget()
        self.legend_layout = QVBoxLayout(self.legend)
        self.legend_layout.setContentsMargins(0, 0, 4, 0)
        self.legend_layout.setSpacing(6)
        self.legend_scroll = _transparent_scroll(self.legend)
        content.addWidget(self.legend_scroll, 1)
        self.layout.addLayout(content, 1)
        self.amount_labels: list[QLabel] = []
        self._amounts_visible: bool | None = None
        self._legend_required_width = 0

    def set_data(
        self, period_label: str, items: tuple[CategorySpending, ...]
    ) -> None:
        self.subtitle_label.setText(period_label)
        self.donut.set_data(items)
        _clear_layout(self.legend_layout)
        self.amount_labels = []
        self._amounts_visible = None
        self._legend_required_width = 0
        total = sum((item.amount for item in items), Decimal())
        if not items:
            self.legend_layout.addWidget(_empty_label("No spending for this period"))
        for item in items:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 1, 0, 1)
            row_layout.setSpacing(8)
            dot = QFrame()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"background: {item.color}; border-radius: 4px;")
            name = _ElidedLabel(item.name)
            name.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 10px;"
            )
            amount = QLabel(format_currency(item.amount))
            amount.setStyleSheet(
                f"color: {COLORS['text']}; font-size: 10px; font-weight: 650;"
            )
            row_layout.addWidget(dot)
            row_layout.addWidget(name, 1)
            share = None
            if total:
                share = QLabel(f"{float(item.amount / total * 100):.0f}%")
                share.setStyleSheet(
                    f"color: {COLORS['text_dim']}; font-size: 9px;"
                )
                row_layout.addWidget(share)
            row_layout.addWidget(amount)
            self.amount_labels.append(amount)
            spacing_width = row_layout.spacing() * (3 if share else 2)
            required_width = (
                dot.width()
                + name.fontMetrics().horizontalAdvance(item.name)
                + amount.sizeHint().width()
                + (share.sizeHint().width() if share else 0)
                + spacing_width
                + 16
            )
            self._legend_required_width = max(
                self._legend_required_width,
                required_width,
            )
            self.legend_layout.addWidget(row)
        self.legend_layout.addStretch()
        QTimer.singleShot(0, self._update_legend_density)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._update_legend_density)

    def _update_legend_density(self) -> None:
        """Hide amounts exactly when the legend no longer has room for them."""
        if not self.amount_labels:
            return
        available_width = self.legend_scroll.viewport().width()
        show_amounts = available_width >= self._legend_required_width
        if show_amounts == self._amounts_visible:
            return
        self._amounts_visible = show_amounts
        for amount in self.amount_labels:
            amount.setVisible(show_amounts)


class BudgetGoalsCard(DashboardCard):
    goals_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            "Budget / Category Goals", "fa6s.bullseye", "#f2b84b", parent
        )
        self.open_goals_button = self.add_header_action("Open Goals")
        self.open_goals_button.clicked.connect(self.goals_requested.emit)
        self.summary_label = QLabel("No category goals set")
        self.summary_label.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 12px; font-weight: 650;"
        )
        self.layout.addWidget(self.summary_label)
        self.rows = QWidget()
        self.rows_layout = QVBoxLayout(self.rows)
        self.rows_layout.setContentsMargins(0, 0, 4, 0)
        self.rows_layout.setSpacing(10)
        self.layout.addWidget(_transparent_scroll(self.rows), 1)

    def set_data(
        self, period_label: str, goals: tuple[BudgetProgress, ...]
    ) -> None:
        self.subtitle_label.setText(period_label)
        _clear_layout(self.rows_layout)
        if not goals:
            self.summary_label.setText("No category goals set")
            self.rows_layout.addWidget(
                _empty_label("Add monthly category targets to see progress here.")
            )
            self.rows_layout.addStretch()
            return

        goals_met = sum(goal.spent <= goal.target for goal in goals)
        self.summary_label.setText(f"{goals_met} of {len(goals)} goals met")
        summary_color = (
            COLORS["positive"]
            if goals_met == len(goals)
            else COLORS["text_muted"]
        )
        self.summary_label.setStyleSheet(
            f"color: {summary_color}; font-size: 12px; font-weight: 700;"
        )
        for goal in goals:
            wrapper = QWidget()
            wrapper_layout = QVBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(0, 0, 0, 0)
            wrapper_layout.setSpacing(4)
            line = QHBoxLayout()
            name = QLabel(goal.category_name)
            name.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 10px;"
            )
            amount = QLabel(
                f"{format_currency(goal.spent)} / {format_currency(goal.target)}"
            )
            amount_color = (
                COLORS["negative"] if goal.spent > goal.target else COLORS["text"]
            )
            amount.setStyleSheet(
                f"color: {amount_color}; font-size: 10px; font-weight: 650;"
            )
            line.addWidget(name, 1)
            line.addWidget(amount)
            progress = QProgressBar()
            progress.setRange(0, 100)
            percentage = (
                float(goal.spent / goal.target * 100) if goal.target else 100.0
            )
            progress.setValue(min(round(percentage), 100))
            progress.setTextVisible(False)
            progress.setFixedHeight(6)
            bar_color = (
                COLORS["negative"] if goal.spent > goal.target else "#f2b84b"
            )
            progress.setStyleSheet(
                f"QProgressBar {{ background: {COLORS['surface_hover']}; border: none; border-radius: 3px; }}"
                f"QProgressBar::chunk {{ background: {bar_color}; border-radius: 3px; }}"
            )
            wrapper_layout.addLayout(line)
            wrapper_layout.addWidget(progress)
            self.rows_layout.addWidget(wrapper)
        self.rows_layout.addStretch()


class MiniLineChart(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.labels: tuple[str, ...] = ()
        self.values: tuple[Decimal, ...] = ()
        self.setMinimumHeight(72)

    def set_data(
        self, labels: tuple[str, ...], values: tuple[Decimal, ...]
    ) -> None:
        self.labels = labels
        self.values = values
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.values:
            painter.setPen(QColor(COLORS["text_dim"]))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "No portfolio history"
            )
            return
        plot = self.rect().adjusted(5, 5, -5, -18)
        minimum = min(float(value) for value in self.values)
        maximum = max(float(value) for value in self.values)
        spread = max(maximum - minimum, 1.0)
        step = plot.width() / max(len(self.values) - 1, 1)
        points = [
            QPointF(
                plot.left() + index * step,
                plot.bottom()
                - ((float(value) - minimum) / spread) * plot.height(),
            )
            for index, value in enumerate(self.values)
        ]
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        painter.setPen(QPen(QColor("#6c9fff"), 2.2))
        painter.drawPath(path)
        painter.setPen(QColor(COLORS["text_dim"]))
        painter.setFont(QFont(self.font().family(), 7))
        if self.labels:
            painter.drawText(
                QRectF(plot.left(), plot.bottom() + 4, plot.width() / 2, 13),
                Qt.AlignmentFlag.AlignLeft,
                self.labels[0],
            )
            painter.drawText(
                QRectF(plot.center().x(), plot.bottom() + 4, plot.width() / 2, 13),
                Qt.AlignmentFlag.AlignRight,
                self.labels[-1],
            )


class InvestingCard(DashboardCard):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            "Investments", "fa6s.arrow-trend-up", "#6c9fff", parent
        )
        self.portfolio_caption = QLabel("Current portfolio value")
        self.portfolio_caption.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px;"
        )
        self.portfolio_value = QLabel("$0")
        self.portfolio_value.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 29px; font-weight: 800;"
        )
        self.contribution_row = SummaryRow("Monthly contributions", "$0")
        self.manual_contribution_row = SummaryRow("Manual contributions", "$0")
        self.employee_rrsp_row = SummaryRow("Work RRSP - employee", "$0")
        self.employer_rrsp_row = SummaryRow("Work RRSP - employer", "$0")
        self.change_label = QLabel("No portfolio history")
        self.change_label.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 11px;"
        )
        self.change_label.setToolTip(
            "Change from the earliest recorded portfolio value"
        )
        value_row = QHBoxLayout()
        value_row.setContentsMargins(0, 0, 0, 0)
        value_row.setSpacing(10)
        value_row.addWidget(self.portfolio_value)
        value_row.addWidget(self.change_label)
        value_row.addStretch()
        self.chart = MiniLineChart()
        self.layout.addWidget(self.portfolio_caption)
        self.layout.addLayout(value_row)
        self.layout.addWidget(self.manual_contribution_row)
        self.layout.addWidget(self.employee_rrsp_row)
        self.layout.addWidget(self.employer_rrsp_row)
        self.layout.addWidget(self.contribution_row)
        self.layout.addWidget(self.chart, 1)

    def set_data(
        self,
        period_label: str,
        contribution: Decimal,
        portfolio_value: Decimal,
        baseline_value: Decimal | None,
        labels: tuple[str, ...],
        values: tuple[Decimal, ...],
        manual_contribution: Decimal | None = None,
        work_rrsp_employee: Decimal = Decimal(),
        work_rrsp_employer: Decimal = Decimal(),
    ) -> None:
        self.subtitle_label.setText(period_label)
        self.portfolio_caption.setText(
            "Current portfolio value"
            if period_label == "All time"
            else "Portfolio value at month end"
        )
        self.portfolio_value.setText(format_currency(portfolio_value))
        caption = (
            "Total contributions"
            if period_label == "All time"
            else "Monthly contributions"
        )
        manual = contribution if manual_contribution is None else manual_contribution
        self.manual_contribution_row.set_values(
            "Manual contributions", format_currency(manual)
        )
        self.employee_rrsp_row.set_values(
            "Work RRSP - employee", format_currency(work_rrsp_employee)
        )
        self.employer_rrsp_row.set_values(
            "Work RRSP - employer", format_currency(work_rrsp_employer)
        )
        self.contribution_row.set_values(caption, format_currency(contribution))
        if baseline_value is None:
            self.change_label.setText("No portfolio history")
            color = COLORS["text_dim"]
            weight = 400
        elif baseline_value == 0:
            difference = portfolio_value - baseline_value
            sign = "+" if difference > 0 else ""
            self.change_label.setText(
                f"{sign}{format_currency(difference)} (new)"
            )
            color = COLORS["positive"] if difference > 0 else COLORS["text_dim"]
            weight = 650
        else:
            difference = portfolio_value - baseline_value
            change = difference / baseline_value * 100
            sign = "+" if difference > 0 else "-" if difference < 0 else ""
            color = (
                COLORS["positive"]
                if difference > 0
                else COLORS["negative"]
                if difference < 0
                else COLORS["text_dim"]
            )
            weight = 650
            self.change_label.setText(
                f"{sign}{format_currency(abs(difference))} "
                f"({sign}{abs(change):.1f}%)"
            )
        self.change_label.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: {weight};"
        )
        self.chart.set_data(labels, values)


def _transparent_scroll(widget: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(widget)
    scroll.viewport().setStyleSheet("background: transparent;")
    scroll.setStyleSheet(
        "QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }"
        "QScrollBar:vertical { background: transparent; width: 5px; }"
        "QScrollBar::handle:vertical { background: #4d535b; border-radius: 2px; }"
    )
    return scroll


def _empty_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px;")
    return label


def _clear_layout(layout: QVBoxLayout) -> None:
    while layout.count():
        child = layout.takeAt(0)
        if child.widget():
            child.widget().deleteLater()
