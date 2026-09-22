from __future__ import annotations

import math
from decimal import Decimal

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from database.dashboard import (
    CategorySpending,
    ChartSeries,
    RecentTransaction,
)


def format_currency(value: Decimal, *, cents: bool = False) -> str:
    precision = 2 if cents else 0
    return f"${value:,.{precision}f}"


class DashboardCard(QFrame):
    def __init__(
        self,
        title: str,
        icon: str,
        accent: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setMinimumWidth(275)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(18, 16, 18, 16)
        self.layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)
        icon_label = QLabel(icon)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedSize(38, 38)
        icon_label.setStyleSheet(
            f"color: {accent}; background: {QColor(accent).darker(260).name()};"
            "border-radius: 19px; font-size: 20px; font-weight: 700;"
        )
        header.addWidget(icon_label)

        heading = QVBoxLayout()
        heading.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("cardSubtitle")
        heading.addWidget(title_label)
        heading.addWidget(self.subtitle_label)
        header.addLayout(heading, 1)

        more_label = QLabel("•••")
        more_label.setObjectName("moreLabel")
        header.addWidget(more_label, alignment=Qt.AlignmentFlag.AlignTop)
        self.layout.addLayout(header)

        self.setStyleSheet("""
            QFrame#dashboardCard {
                background: #1c2128;
                border: 1px solid #303844;
                border-radius: 12px;
            }
            QLabel { background: transparent; border: none; }
            QLabel#cardTitle {
                color: #f4f6fa;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#cardSubtitle, QLabel#moreLabel {
                color: #8e9bad;
                font-size: 11px;
            }
        """)


class GroupedBarChart(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.labels: tuple[str, ...] = ()
        self.series: tuple[ChartSeries, ...] = ()
        self.setMinimumHeight(105)

    def set_data(
        self,
        labels: tuple[str, ...],
        series: tuple[ChartSeries, ...],
    ) -> None:
        self.labels = labels
        self.series = series
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self.labels or not self.series:
            painter.setPen(QColor("#778396"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data for this period")
            return

        legend_height = 19 if len(self.series) > 1 else 0
        plot = QRectF(5, 5 + legend_height, self.width() - 10, self.height() - 28 - legend_height)
        baseline = plot.bottom()
        painter.setPen(QPen(QColor("#35404d"), 1))
        painter.drawLine(plot.left(), baseline, plot.right(), baseline)

        maximum = max(
            (float(value) for item in self.series for value in item.values),
            default=0.0,
        )
        if maximum <= 0:
            maximum = 1.0

        group_width = plot.width() / max(1, len(self.labels))
        usable_width = min(group_width * 0.72, 34.0)
        bar_width = max(2.0, usable_width / max(1, len(self.series)))

        for group_index in range(len(self.labels)):
            group_left = plot.left() + group_index * group_width
            bars_left = group_left + (group_width - bar_width * len(self.series)) / 2
            for series_index, item in enumerate(self.series):
                value = float(item.values[group_index])
                height = (value / maximum) * max(1.0, plot.height() - 3)
                bar = QRectF(
                    bars_left + series_index * bar_width,
                    baseline - height,
                    max(1.5, bar_width - 1.5),
                    height,
                )
                gradient = QLinearGradient(bar.topLeft(), bar.bottomLeft())
                color = QColor(item.color)
                gradient.setColorAt(0, color.lighter(125))
                gradient.setColorAt(1, color.darker(135))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(gradient)
                painter.drawRoundedRect(bar, 2, 2)

        if len(self.series) > 1:
            self._draw_legend(painter)
        self._draw_month_labels(painter, plot)

    def _draw_legend(self, painter: QPainter) -> None:
        painter.setFont(QFont(self.font().family(), 7))
        x = 5.0
        for item in self.series:
            if x > self.width() - 65:
                break
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(item.color))
            painter.drawEllipse(QRectF(x, 5, 7, 7))
            painter.setPen(QColor("#9eabba"))
            name = painter.fontMetrics().elidedText(
                item.name, Qt.TextElideMode.ElideRight, 72
            )
            painter.drawText(QRectF(x + 11, 0, 74, 16), Qt.AlignmentFlag.AlignVCenter, name)
            x += 88

    def _draw_month_labels(self, painter: QPainter, plot: QRectF) -> None:
        painter.setPen(QColor("#7f8a9c"))
        painter.setFont(QFont(self.font().family(), 7))
        group_width = plot.width() / max(1, len(self.labels))
        step = max(1, math.ceil(len(self.labels) / 7))
        visible = set(range(0, len(self.labels), step)) | {len(self.labels) - 1}
        for index, label in enumerate(self.labels):
            if index not in visible:
                continue
            painter.drawText(
                QRectF(plot.left() + index * group_width, plot.bottom() + 4, group_width, 16),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                label,
            )


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
        self.improvement_when_down = improvement_when_down
        self.value_label = QLabel("$0")
        self.value_label.setStyleSheet(
            "color: #f7f8fb; font-size: 32px; font-weight: 800;"
        )
        self.change_label = QLabel()
        self.change_label.setStyleSheet("color: #8e9bad; font-size: 11px;")
        self.chart = GroupedBarChart()
        self.layout.addWidget(self.value_label)
        self.layout.addWidget(self.change_label)
        self.layout.addWidget(self.chart, 1)

    def set_data(
        self,
        period_label: str,
        total: Decimal,
        previous: Decimal | None,
        labels: tuple[str, ...],
        series: tuple[ChartSeries, ...],
    ) -> None:
        self.subtitle_label.setText(period_label)
        self.value_label.setText(format_currency(total))
        if previous is None:
            self.change_label.setText("Full transaction history")
            self.change_label.setStyleSheet("color: #8e9bad; font-size: 11px;")
        elif previous == 0:
            self.change_label.setText("No activity last month")
            self.change_label.setStyleSheet("color: #8e9bad; font-size: 11px;")
        else:
            change = (total - previous) / previous * 100
            up = change >= 0
            good = (not up) if self.improvement_when_down else up
            color = "#63dba0" if good else "#f16f88"
            arrow = "↑" if up else "↓"
            self.change_label.setText(f"{arrow} {abs(change):.0f}%   vs. last month")
            self.change_label.setStyleSheet(
                f"color: {color}; font-size: 11px; font-weight: 700;"
            )
        self.chart.set_data(labels, series)


class ProgressRing(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.percentage = 0.0
        self.setFixedSize(104, 104)

    def set_percentage(self, value: float) -> None:
        self.percentage = max(0.0, value)
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ring = QRectF(10, 10, self.width() - 20, self.height() - 20)
        pen = QPen(QColor("#2e3746"), 10)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(ring, 0, 360 * 16)
        pen.setColor(QColor("#5f6cff"))
        painter.setPen(pen)
        painter.drawArc(ring, 90 * 16, -min(self.percentage, 100.0) / 100 * 360 * 16)
        painter.setPen(QColor("#f1f4f9"))
        painter.setFont(QFont(self.font().family(), 12, QFont.Weight.Bold))
        painter.drawText(self.rect().adjusted(0, -5, 0, 0), Qt.AlignmentFlag.AlignCenter, f"{self.percentage:.0f}%")
        painter.setPen(QColor("#8d99aa"))
        painter.setFont(QFont(self.font().family(), 7))
        painter.drawText(self.rect().adjusted(0, 24, 0, 0), Qt.AlignmentFlag.AlignCenter, "of income")


class InvestingCard(DashboardCard):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Saved / Investing", "↗", "#7293ff", parent)
        content = QHBoxLayout()
        content.setSpacing(8)
        value_column = QVBoxLayout()
        self.value_label = QLabel("$0")
        self.value_label.setStyleSheet(
            "color: #f7f8fb; font-size: 32px; font-weight: 800;"
        )
        self.detail_label = QLabel("No investing transactions")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet("color: #8e9bad; font-size: 11px;")
        value_column.addWidget(self.value_label)
        value_column.addWidget(self.detail_label)
        value_column.addStretch()
        content.addLayout(value_column, 1)
        self.ring = ProgressRing()
        content.addWidget(self.ring, alignment=Qt.AlignmentFlag.AlignRight)
        self.layout.addLayout(content, 1)

        note = QLabel("Investing is included in spending totals")
        note.setWordWrap(True)
        note.setStyleSheet(
            "color: #afbdd0; background: #202733; border: 1px solid #303b4b;"
            "border-radius: 8px; padding: 9px; font-size: 10px;"
        )
        self.layout.addWidget(note)

    def set_data(
        self,
        period_label: str,
        investing: Decimal,
        income: Decimal,
    ) -> None:
        self.subtitle_label.setText(period_label)
        self.value_label.setText(format_currency(investing))
        percentage = float(investing / income * 100) if income else 0.0
        self.ring.set_percentage(percentage)
        self.detail_label.setText(
            f"{percentage:.0f}% of income invested"
            if income
            else "No debit income for this period"
        )


class DonutChart(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.items: tuple[CategorySpending, ...] = ()
        self.total = Decimal()
        self.setMinimumSize(145, 145)

    def set_data(self, items: tuple[CategorySpending, ...]) -> None:
        self.items = items
        self.total = sum((item.amount for item in items), Decimal())
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.width(), self.height()) - 16
        ring = QRectF(
            (self.width() - size) / 2,
            (self.height() - size) / 2,
            size,
            size,
        )
        pen = QPen(QColor("#313a47"), max(14, int(size * 0.18)))
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.drawArc(ring, 0, 360 * 16)

        if self.total:
            start = 90 * 16
            for item in self.items:
                span = -float(item.amount / self.total) * 360 * 16
                pen.setColor(QColor(item.color))
                painter.setPen(pen)
                painter.drawArc(ring, int(start), int(span))
                start += span

        painter.setPen(QColor("#f2f5f9"))
        painter.setFont(QFont(self.font().family(), 11, QFont.Weight.Bold))
        painter.drawText(self.rect().adjusted(0, -7, 0, 0), Qt.AlignmentFlag.AlignCenter, format_currency(self.total))
        painter.setPen(QColor("#8d99aa"))
        painter.setFont(QFont(self.font().family(), 8))
        painter.drawText(self.rect().adjusted(0, 22, 0, 0), Qt.AlignmentFlag.AlignCenter, "Total")


class CategoryCard(DashboardCard):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Spending by Category", "◔", "#a67cff", parent)
        content = QHBoxLayout()
        content.setSpacing(14)
        self.donut = DonutChart()
        content.addWidget(self.donut, 1)

        self.legend = QWidget()
        self.legend_layout = QVBoxLayout(self.legend)
        self.legend_layout.setContentsMargins(0, 0, 4, 0)
        self.legend_layout.setSpacing(5)
        self.legend.setStyleSheet("background: transparent;")
        legend_scroll = QScrollArea()
        legend_scroll.setWidgetResizable(True)
        legend_scroll.setFrameShape(QFrame.Shape.NoFrame)
        legend_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        legend_scroll.setWidget(self.legend)
        legend_scroll.viewport().setStyleSheet("background: transparent;")
        legend_scroll.setStyleSheet("""
            QScrollArea, QScrollArea > QWidget > QWidget {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical { background: transparent; width: 5px; }
            QScrollBar::handle:vertical { background: #465164; border-radius: 2px; }
        """)
        content.addWidget(legend_scroll, 1)
        self.layout.addLayout(content, 1)

    def set_data(
        self,
        period_label: str,
        items: tuple[CategorySpending, ...],
    ) -> None:
        self.subtitle_label.setText(period_label)
        self.donut.set_data(items)
        while self.legend_layout.count():
            child = self.legend_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        total = sum((item.amount for item in items), Decimal())
        if not items:
            empty = QLabel("No spending for this period")
            empty.setStyleSheet("color: #7f8a9c; font-size: 10px;")
            empty.setWordWrap(True)
            self.legend_layout.addWidget(empty)
        for item in items:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {item.color}; font-size: 12px;")
            name = QLabel(item.name)
            name.setStyleSheet("color: #d8deea; font-size: 10px;")
            amount = QLabel(format_currency(item.amount))
            amount.setStyleSheet("color: #9aa6b8; font-size: 9px;")
            percentage = QLabel(
                f"{float(item.amount / total * 100):.0f}%" if total else "0%"
            )
            percentage.setStyleSheet("color: #7e899a; font-size: 9px;")
            row_layout.addWidget(dot)
            row_layout.addWidget(name, 1)
            row_layout.addWidget(percentage)
            row_layout.addWidget(amount)
            self.legend_layout.addWidget(row)
        self.legend_layout.addStretch()


class CashFlowChart(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.labels: tuple[str, ...] = ()
        self.income: tuple[Decimal, ...] = ()
        self.spending: tuple[Decimal, ...] = ()
        self.setMinimumHeight(165)

    def set_data(
        self,
        labels: tuple[str, ...],
        income: tuple[Decimal, ...],
        spending: tuple[Decimal, ...],
    ) -> None:
        self.labels = labels
        self.income = income
        self.spending = spending
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.labels:
            return

        plot = QRectF(7, 25, self.width() - 14, self.height() - 48)
        zero = plot.center().y()
        maximum = max(
            [float(value) for value in self.income + self.spending] or [1.0]
        )
        maximum = max(maximum, 1.0)
        painter.setPen(QPen(QColor("#35404d"), 1))
        painter.drawLine(plot.left(), zero, plot.right(), zero)

        group_width = plot.width() / max(1, len(self.labels))
        bar_width = min(9.0, group_width * 0.28)
        half_height = plot.height() / 2 - 3
        for index in range(len(self.labels)):
            center = plot.left() + (index + 0.5) * group_width
            income_height = float(self.income[index]) / maximum * half_height
            spending_height = float(self.spending[index]) / maximum * half_height
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#63dba0"))
            painter.drawRoundedRect(
                QRectF(center - bar_width - 1, zero - income_height, bar_width, income_height),
                2,
                2,
            )
            painter.setBrush(QColor("#f16f88"))
            painter.drawRoundedRect(
                QRectF(center + 1, zero, bar_width, spending_height), 2, 2
            )

        painter.setFont(QFont(self.font().family(), 8))
        painter.setPen(QColor("#63dba0"))
        painter.drawText(QRectF(5, 1, 75, 18), Qt.AlignmentFlag.AlignVCenter, "●  Income")
        painter.setPen(QColor("#f16f88"))
        painter.drawText(QRectF(82, 1, 85, 18), Qt.AlignmentFlag.AlignVCenter, "●  Spending")
        painter.setPen(QColor("#7f8a9c"))
        painter.setFont(QFont(self.font().family(), 7))
        step = max(1, math.ceil(len(self.labels) / 6))
        visible = set(range(0, len(self.labels), step)) | {len(self.labels) - 1}
        for index, label in enumerate(self.labels):
            if index in visible:
                painter.drawText(
                    QRectF(plot.left() + index * group_width, plot.bottom() + 5, group_width, 15),
                    Qt.AlignmentFlag.AlignHCenter,
                    label,
                )


class CashFlowCard(DashboardCard):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Cash Flow", "▥", "#7392ff", parent)
        self.chart = CashFlowChart()
        self.layout.addWidget(self.chart, 1)

    def set_data(
        self,
        period_label: str,
        labels: tuple[str, ...],
        income: tuple[Decimal, ...],
        spending: tuple[Decimal, ...],
    ) -> None:
        self.subtitle_label.setText(f"Income vs. spending · {period_label}")
        self.chart.set_data(labels, income, spending)


class RecentTransactionsCard(DashboardCard):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Recent Transactions", "▤", "#7392ff", parent)
        self.rows = QWidget()
        self.rows_layout = QVBoxLayout(self.rows)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(4)
        self.layout.addWidget(self.rows, 1)

    def set_data(
        self,
        period_label: str,
        transactions: tuple[RecentTransaction, ...],
    ) -> None:
        self.subtitle_label.setText(period_label)
        while self.rows_layout.count():
            child = self.rows_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not transactions:
            empty = QLabel("No transactions for this period")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #7f8a9c; font-size: 11px;")
            self.rows_layout.addWidget(empty, 1)
            return

        for item in transactions:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 3, 0, 3)
            row_layout.setSpacing(8)
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {item.category_color}; font-size: 18px;")
            row_layout.addWidget(dot)

            details = QVBoxLayout()
            details.setSpacing(1)
            description = QLabel(item.description)
            description.setStyleSheet("color: #e4e9f1; font-size: 10px;")
            description.setToolTip(item.description)
            meta = QLabel(f"{item.transaction_date:%b %d, %Y} · {item.account_name}")
            meta.setStyleSheet("color: #7f8a9c; font-size: 8px;")
            details.addWidget(description)
            details.addWidget(meta)
            row_layout.addLayout(details, 1)

            sign = "-" if item.amount < 0 else "+"
            amount = QLabel(f"{sign}{format_currency(abs(item.amount), cents=True)}")
            amount.setStyleSheet(
                f"color: {'#f16f88' if item.amount < 0 else '#63dba0'};"
                "font-size: 10px; font-weight: 700;"
            )
            row_layout.addWidget(amount)
            self.rows_layout.addWidget(row)
        self.rows_layout.addStretch()
