from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDate, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QHeaderView,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from database.db import SessionLocal
from database.investments import (
    InvestmentAccountSummary,
    PortfolioPoint,
    create_investment_account,
    create_investment_snapshot,
    delete_investment_account,
    get_account_summaries,
    get_investment_months,
    get_monthly_contribution_comparison,
    get_portfolio_history,
    get_recent_snapshots,
    get_total_contributions,
    get_total_portfolio_value,
    update_investment_account,
)
from ui.components.account_badge import AccountBadge
from ui.components.generic_dialog import GenericDialog
from ui.components.generic_table import GenericTable
from ui.components.page_header import PageHeader
from ui.components.period_selector import PeriodSelector
from ui.theme import (
    COLORS,
    set_button_icon,
    set_delete_button_icon,
    set_icon_only_button,
)


def _currency(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def _month_dates(month: tuple[int, int]) -> tuple[date, date]:
    year, month_number = month
    return (
        date(year, month_number, 1),
        date(year, month_number, calendar.monthrange(year, month_number)[1]),
    )


def _previous_month(month: tuple[int, int]) -> tuple[int, int]:
    year, month_number = month
    return year - (month_number == 1), (month_number - 2) % 12 + 1


def _qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


def _date_from_editor(editor: QDateEdit) -> date:
    value = editor.date()
    return date(value.year(), value.month(), value.day())


def _masked_account_number(account_number: str | None) -> str:
    value = account_number or ""
    if len(value) <= 4:
        return value
    return f"{'*' * (len(value) - 4)}{value[-4:]}"


def _parse_optional_money(text: str, label: str) -> Decimal | None:
    cleaned = text.strip().replace("$", "").replace(",", "")
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"{label} must be a valid amount") from exc
    if not value.is_finite():
        raise ValueError(f"{label} must be a valid amount")
    return value


class AccountNumberReveal(QLabel):
    """Mask an account number until it is hovered or pinned with a click."""

    def __init__(self, account_number: str | None, parent=None) -> None:
        super().__init__(parent)
        self.account_number = account_number or ""
        self._hovered = False
        self._pinned = False
        self.setObjectName("investmentAccountNumber")
        self.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        if self.account_number:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip("Hover to reveal; click to keep the account number visible")
            self.setAccessibleName("Hidden investment account number")
        self._refresh_text()

    @property
    def is_revealed(self) -> bool:
        return bool(self.account_number and (self._hovered or self._pinned))

    def enterEvent(self, event) -> None:
        if not self._pinned:
            self._hovered = True
            self._refresh_text()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if not self._pinned:
            self._hovered = False
            self._refresh_text()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.account_number and event.button() == Qt.MouseButton.LeftButton:
            self._pinned = not self._pinned
            self._refresh_text()
        super().mouseReleaseEvent(event)

    def _refresh_text(self) -> None:
        if not self.account_number:
            self.setText("—")
        elif self.is_revealed:
            self.setText(self.account_number)
        else:
            self.setText("*" * len(self.account_number))


class PortfolioChart(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.points: tuple[PortfolioPoint, ...] = ()
        self.range_start: date | None = None
        self.range_end: date | None = None
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(
        self,
        points: tuple[PortfolioPoint, ...],
        *,
        end_date: date | None = None,
    ) -> None:
        self.points = points
        self.range_start = points[0].snapshot_datetime.date() if points else None
        self.range_end = end_date if points else None
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.points:
            painter.setPen(QColor(COLORS["text_dim"]))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "No portfolio history yet",
            )
            return

        plot = self.rect().adjusted(64, 18, -18, -38)
        values = [float(point.total_value) for point in self.points]
        minimum = min(values)
        maximum = max(values)
        padding = max((maximum - minimum) * 0.12, maximum * 0.03, 1.0)
        lower = max(0.0, minimum - padding)
        upper = maximum + padding
        spread = max(upper - lower, 1.0)

        painter.setFont(QFont(self.font().family(), 8))
        for line in range(5):
            ratio = line / 4
            y = plot.bottom() - ratio * plot.height()
            painter.setPen(QPen(QColor(COLORS["border_soft"]), 1))
            painter.drawLine(plot.left(), int(y), plot.right(), int(y))
            painter.setPen(QColor(COLORS["text_dim"]))
            label_value = lower + ratio * spread
            painter.drawText(
                QRectF(0, y - 8, plot.left() - 8, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"${label_value / 1000:.0f}k" if label_value >= 1000 else f"${label_value:.0f}",
            )

        range_start = self.range_start or self.points[0].snapshot_datetime.date()
        range_end = max(
            self.range_end or self.points[-1].snapshot_datetime.date(),
            range_start,
        )
        day_span = max((range_end - range_start).days, 1)
        coordinates = [
            QPointF(
                plot.left()
                + (
                    (point.snapshot_datetime.date() - range_start).days
                    / day_span
                )
                * plot.width(),
                plot.bottom() - ((value - lower) / spread) * plot.height(),
            )
            for point, value in zip(self.points, values)
        ]
        path = QPainterPath(coordinates[0])
        for point in coordinates[1:]:
            path.lineTo(point)
        painter.setPen(QPen(QColor("#6c9fff"), 2.5))
        painter.drawPath(path)
        painter.setBrush(QColor("#6c9fff"))
        painter.setPen(Qt.PenStyle.NoPen)
        for point in coordinates:
            painter.drawEllipse(point, 3.5, 3.5)

        painter.setPen(QColor(COLORS["text_dim"]))
        painter.drawText(
            QRectF(plot.left(), plot.bottom() + 9, plot.width() / 2, 18),
            Qt.AlignmentFlag.AlignLeft,
            range_start.strftime("%b %d, %Y"),
        )
        painter.drawText(
            QRectF(plot.center().x(), plot.bottom() + 9, plot.width() / 2, 18),
            Qt.AlignmentFlag.AlignRight,
            range_end.strftime("%b %d, %Y"),
        )


class SummaryCard(QFrame):
    def __init__(self, title: str, icon: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("investmentSummaryCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(7)

        title_row = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 12px; font-weight: 650;"
        )
        icon_label = QLabel()
        from ui.theme import set_label_icon

        set_label_icon(icon_label, icon, color="#6c9fff", size=16)
        title_row.addWidget(self.title_label)
        title_row.addStretch()
        title_row.addWidget(icon_label)
        layout.addLayout(title_row)

        self.value_label = QLabel("$0.00")
        self.value_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 27px; font-weight: 750;"
        )
        layout.addWidget(self.value_label)
        self.detail_label = QLabel()
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 11px;"
        )
        layout.addWidget(self.detail_label)

    def set_data(self, value: str, detail: str, color: str | None = None) -> None:
        self.value_label.setText(value)
        self.detail_label.setText(detail)
        self.detail_label.setStyleSheet(
            f"color: {color or COLORS['text_dim']}; font-size: 11px;"
        )

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)


class InvestmentAccountDialog(GenericDialog):
    def __init__(
        self,
        parent=None,
        *,
        account: InvestmentAccountSummary | None = None,
    ) -> None:
        self.account = account
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)

        self.institution = QLineEdit(account.institution if account else "")
        self.institution.setPlaceholderText("e.g. Wealthsimple")
        self.account_name = QLineEdit(account.account_name if account else "")
        self.account_name.setPlaceholderText("e.g. TFSA")
        self.account_type = QLineEdit(account.account_type or "" if account else "")
        self.account_type.setPlaceholderText("Optional")
        self.account_number = QLineEdit(
            account.account_number_last7 or "" if account else ""
        )
        self.account_number.setPlaceholderText(
            "Optional — only the last 7 letters/numbers are stored"
        )
        self.account_number.setMaxLength(64)
        form.addRow("Institution", self.institution)
        form.addRow("Account name", self.account_name)
        form.addRow("Account type", self.account_type)
        form.addRow("Account number (last 7)", self.account_number)

        self.initial_value = QLineEdit()
        self.initial_value.setPlaceholderText("Optional")
        self.initial_date = QDateEdit(_qdate(date.today()))
        self.initial_date.setCalendarPopup(True)
        self.initial_date.setDisplayFormat("MMM d, yyyy")
        if account is None:
            form.addRow("Initial value", self.initial_value)
            form.addRow("Initial date", self.initial_date)

        content_layout.addLayout(form)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(f"color: {COLORS['negative']};")
        content_layout.addWidget(self.error_label)

        super().__init__(
            "Edit Investment Account" if account else "Add Investment Account",
            content,
            parent,
            submit_label="Save Account" if account else "Add Account",
        )
        self.resize(570, 430 if account is None else 350)


class InvestmentsPage(QWidget):
    RECENT_ENTRY_HEIGHT = 72
    VISIBLE_RECENT_ENTRIES = 4

    def __init__(self, session_factory=SessionLocal):
        super().__init__()
        self.session_factory = session_factory
        self.user_id: str | None = None
        self._accounts: tuple[InvestmentAccountSummary, ...] = ()
        self.setObjectName("investmentsPage")
        self.setMinimumSize(980, 760)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        content.setObjectName("investmentsContent")
        content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        root_layout.addWidget(content)

        add_account_button = QPushButton("Add Investment Account")
        add_account_button.setObjectName("pageActionButton")
        set_button_icon(
            add_account_button,
            "fa6s.plus",
            color="#ffffff",
            active_color="#ffffff",
        )
        add_account_button.clicked.connect(self._open_add_account)
        layout.addWidget(PageHeader(
            "Investments",
            "Track your investment accounts and portfolio snapshots.",
            add_account_button,
        ))

        self.period_selector = PeriodSelector()
        self.period_selector.selection_changed.connect(lambda *_: self.reload())
        layout.addWidget(self.period_selector)

        summary_grid = QGridLayout()
        summary_grid.setSpacing(16)
        self.portfolio_card = SummaryCard(
            "Total Portfolio Value", "fa6s.chart-line"
        )
        self.contribution_card = SummaryCard(
            "Monthly Contributions", "fa6s.coins"
        )
        self.accounts_card = SummaryCard(
            "Investment Accounts", "fa6s.building-columns"
        )
        summary_grid.addWidget(self.portfolio_card, 0, 0)
        summary_grid.addWidget(self.contribution_card, 0, 1)
        summary_grid.addWidget(self.accounts_card, 0, 2)
        for column in range(3):
            summary_grid.setColumnStretch(column, 1)
        layout.addLayout(summary_grid)

        middle = QGridLayout()
        middle.setHorizontalSpacing(16)
        middle.setVerticalSpacing(16)
        chart_card = QFrame()
        chart_card.setObjectName("contentCard")
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(18, 16, 18, 14)
        chart_title = QLabel("Portfolio Value Over Time")
        chart_title.setObjectName("sectionTitle")
        chart_layout.addWidget(chart_title)
        self.chart = PortfolioChart()
        chart_layout.addWidget(self.chart, 1)
        middle.addWidget(chart_card, 0, 0, 1, 2)
        self.entry_panel = self._build_entry_panel()
        middle.addWidget(self.entry_panel, 0, 2)
        middle.setColumnStretch(0, 1)
        middle.setColumnStretch(1, 1)
        middle.setColumnStretch(2, 1)
        layout.addLayout(middle, 5)

        bottom = QGridLayout()
        bottom.setHorizontalSpacing(16)
        bottom.setVerticalSpacing(16)
        bottom.addWidget(self._build_accounts_panel(), 0, 0, 1, 2)
        bottom.addWidget(self._build_recent_panel(), 0, 2)
        bottom.setColumnStretch(0, 1)
        bottom.setColumnStretch(1, 1)
        bottom.setColumnStretch(2, 1)
        layout.addLayout(bottom, 5)

    def _build_entry_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentCard")
        panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 16, 18, 18)
        panel_layout.setSpacing(12)
        title = QLabel("Add Portfolio Entry")
        title.setObjectName("sectionTitle")
        panel_layout.addWidget(title)

        form = QFormLayout()
        self.entry_form = form
        form.setSpacing(10)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.entry_account = QComboBox()
        self.entry_date = QDateEdit(_qdate(date.today()))
        self.entry_date.setCalendarPopup(True)
        self.entry_date.setDisplayFormat("MMM d, yyyy")
        self.entry_total = QLineEdit()
        self.entry_total.setPlaceholderText("0.00")
        self.entry_contribution = QLineEdit()
        self.entry_contribution.setPlaceholderText("Optional")
        for field in (
            self.entry_account,
            self.entry_date,
            self.entry_total,
            self.entry_contribution,
        ):
            field.setMinimumWidth(0)
            field.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
        form.addRow("Investment account", self.entry_account)
        form.addRow("Date", self.entry_date)
        form.addRow("Total amount", self.entry_total)
        form.addRow("Contribution", self.entry_contribution)
        panel_layout.addLayout(form)
        self.entry_error = QLabel()
        self.entry_error.setWordWrap(True)
        self.entry_error.setStyleSheet(f"color: {COLORS['negative']};")
        panel_layout.addWidget(self.entry_error)
        self.save_entry_button = QPushButton("Save Entry")
        self.save_entry_button.setObjectName("primaryButton")
        set_button_icon(
            self.save_entry_button,
            "fa6s.plus",
            color="#ffffff",
            active_color="#ffffff",
        )
        self.save_entry_button.clicked.connect(self._save_entry)
        panel_layout.addWidget(self.save_entry_button)
        panel_layout.addStretch()
        return panel

    def _build_accounts_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentCard")
        panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        heading = QLabel("Investment Accounts")
        heading.setObjectName("sectionTitle")
        heading.setContentsMargins(18, 14, 18, 4)
        panel_layout.addWidget(heading)
        self.accounts_empty = QLabel("No investment accounts yet")
        self.accounts_empty.setObjectName("emptyLabel")
        self.accounts_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.accounts_empty.setContentsMargins(18, 20, 18, 20)
        panel_layout.addWidget(self.accounts_empty)
        self.accounts_table = GenericTable((
            "Account",
            "Institution",
            "Account #",
            "Current Value",
            "Last Updated",
            "Action",
        ))
        self.accounts_table.setMinimumHeight(200)
        self.accounts_table.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeMode.ResizeToContents
        )
        panel_layout.addWidget(self.accounts_table)
        return panel

    def _build_recent_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentCard")
        panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 16, 18, 18)
        panel_layout.setSpacing(10)
        title = QLabel("Recent Portfolio Entries")
        title.setObjectName("sectionTitle")
        panel_layout.addWidget(title)

        self.recent_scroll = QScrollArea()
        self.recent_scroll.setObjectName("investmentRecentScroll")
        self.recent_scroll.setWidgetResizable(True)
        self.recent_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.recent_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.recent_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        viewport_height = (
            self.VISIBLE_RECENT_ENTRIES * self.RECENT_ENTRY_HEIGHT
            + (self.VISIBLE_RECENT_ENTRIES - 1) * 8
        )
        self.recent_scroll.setFixedHeight(viewport_height)
        self.recent_scroll.setStyleSheet(
            "QScrollArea#investmentRecentScroll { background: transparent; border: none; }"
            "QScrollArea#investmentRecentScroll > QWidget > QWidget "
            "{ background: transparent; }"
        )

        self.recent_entries = QWidget()
        self.recent_entries.setObjectName("investmentRecentEntries")
        self.recent_layout = QVBoxLayout(self.recent_entries)
        self.recent_layout.setContentsMargins(0, 0, 4, 0)
        self.recent_layout.setSpacing(8)
        self.recent_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.recent_scroll.setWidget(self.recent_entries)
        panel_layout.addWidget(self.recent_scroll)
        panel_layout.addStretch()
        return panel

    def set_user_id(self, user_id: str | None) -> None:
        self.user_id = user_id
        self.period_selector.reset(emit=False)
        self.reload()

    def reload(self) -> None:
        if self.user_id is None:
            self.period_selector.set_available_months(())
            self._accounts = ()
            self._render_empty()
            return

        months = get_investment_months(
            user_id=self.user_id, session_factory=self.session_factory
        )
        self.period_selector.set_available_months(months)
        self._accounts = get_account_summaries(
            user_id=self.user_id, session_factory=self.session_factory
        )
        total_value = get_total_portfolio_value(
            user_id=self.user_id, session_factory=self.session_factory
        )

        selected_month = self.period_selector.selected_month
        start_date = end_date = None
        if self.period_selector.period == "monthly":
            self.contribution_card.set_title("Monthly Contributions")
            start_date, end_date = _month_dates(selected_month)
            comparison = get_monthly_contribution_comparison(
                *selected_month,
                user_id=self.user_id,
                session_factory=self.session_factory,
            )
            contributions = comparison.current
            previous_contributions = comparison.previous
            contribution_label = date(*selected_month, 1).strftime("%B %Y")
        else:
            self.contribution_card.set_title("All-Time Contributions")
            contributions = get_total_contributions(
                user_id=self.user_id, session_factory=self.session_factory
            )
            previous_contributions = None
            contribution_label = "All-time contributions"

        history_end = end_date if end_date is not None else date.today()
        history = get_portfolio_history(
            user_id=self.user_id,
            end_date=history_end,
            session_factory=self.session_factory,
        )
        previous_portfolio = self._portfolio_before_month(selected_month)
        self._update_cards(
            total_value,
            previous_portfolio,
            contributions,
            previous_contributions,
            contribution_label,
        )
        self.chart.set_data(history, end_date=history_end)
        self._render_accounts()
        self._render_recent(start_date, history_end)
        self._refresh_entry_accounts()

    def _portfolio_before_month(self, month: tuple[int, int]) -> Decimal | None:
        previous = _previous_month(month)
        _, last_day = _month_dates(previous)
        points = get_portfolio_history(
            user_id=self.user_id,
            end_date=last_day,
            session_factory=self.session_factory,
        )
        return points[-1].total_value if points else None

    def _update_cards(
        self,
        total_value: Decimal,
        previous_value: Decimal | None,
        contributions: Decimal,
        previous_contributions: Decimal | None,
        contribution_label: str,
    ) -> None:
        if previous_value is None:
            portfolio_detail = "No previous-month value available"
            portfolio_color = COLORS["text_dim"]
        elif previous_value == 0:
            portfolio_detail = "First recorded portfolio value"
            portfolio_color = COLORS["text_dim"]
        else:
            change = (total_value - previous_value) / previous_value * 100
            portfolio_detail = f"{abs(change):.1f}% {'up' if change >= 0 else 'down'} vs previous month"
            portfolio_color = COLORS["positive"] if change >= 0 else COLORS["negative"]
        self.portfolio_card.set_data(
            _currency(total_value), portfolio_detail, portfolio_color
        )

        if previous_contributions is None:
            contribution_detail = contribution_label
            contribution_color = COLORS["text_dim"]
        elif previous_contributions == 0:
            contribution_detail = f"{contribution_label} · no prior contributions"
            contribution_color = COLORS["text_dim"]
        else:
            change = (
                (contributions - previous_contributions)
                / abs(previous_contributions)
                * 100
            )
            contribution_detail = f"{abs(change):.1f}% {'up' if change >= 0 else 'down'} vs previous month"
            contribution_color = (
                COLORS["positive"] if change >= 0 else COLORS["negative"]
            )
        self.contribution_card.set_data(
            _currency(contributions), contribution_detail, contribution_color
        )

        institutions = len({account.institution.casefold() for account in self._accounts})
        self.accounts_card.set_data(
            str(len(self._accounts)),
            f"{institutions} institution{'s' if institutions != 1 else ''}",
        )

    def _render_empty(self) -> None:
        self.portfolio_card.set_data("$0.00", "No portfolio history")
        self.contribution_card.set_data("$0.00", "No contributions recorded")
        self.accounts_card.set_data("0", "0 institutions")
        self.chart.set_data(())
        self.accounts_table.set_rows(())
        self.accounts_empty.show()
        self._clear_layout(self.recent_layout)
        self.recent_entries.setMinimumHeight(0)
        empty = QLabel("No portfolio entries yet")
        empty.setObjectName("emptyLabel")
        self.recent_layout.addWidget(empty)
        self.entry_account.clear()
        self.save_entry_button.setEnabled(False)

    def _render_accounts(self) -> None:
        rows = []
        for account in self._accounts:
            actions = QWidget()
            actions.setObjectName("tableCell")
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(3, 3, 3, 3)
            action_layout.setSpacing(5)
            add_button = QPushButton("Add Entry")
            set_button_icon(add_button, "fa6s.plus", size=14)
            edit_button = QPushButton()
            edit_button.setObjectName("tableIconButton")
            set_icon_only_button(
                edit_button,
                "fa6s.gear",
                tooltip="Edit investment account",
            )
            delete_button = QPushButton()
            delete_button.setObjectName("dangerButton")
            delete_button.setToolTip("Delete investment account")
            set_delete_button_icon(delete_button)
            actions.setMinimumWidth(190)
            add_button.clicked.connect(
                lambda checked=False, account_id=account.id: self._select_entry_account(account_id)
            )
            edit_button.clicked.connect(
                lambda checked=False, selected=account: self._open_edit_account(selected)
            )
            delete_button.clicked.connect(
                lambda checked=False, selected=account: self._delete_account(selected)
            )
            action_layout.addWidget(add_button)
            action_layout.addWidget(edit_button)
            action_layout.addWidget(delete_button)
            rows.append((
                AccountBadge(account.account_name, account.institution),
                account.institution,
                AccountNumberReveal(account.account_number_last7),
                _currency(account.current_value),
                account.last_updated.strftime("%b %d, %Y") if account.last_updated else "No data",
                actions,
            ))
        self.accounts_table.set_rows(rows)
        self.accounts_empty.setVisible(not rows)
        self.accounts_table.setVisible(bool(rows))

    def _render_recent(self, start_date: date | None, end_date: date | None) -> None:
        self._clear_layout(self.recent_layout)
        entries = get_recent_snapshots(
            user_id=self.user_id,
            limit=50,
            start_date=start_date,
            end_date=end_date,
            session_factory=self.session_factory,
        )
        if not entries:
            self.recent_entries.setMinimumHeight(0)
            empty = QLabel("No portfolio entries for this period")
            empty.setObjectName("emptyLabel")
            empty.setWordWrap(True)
            self.recent_layout.addWidget(empty)
            return
        for entry in entries:
            item = QFrame()
            item.setObjectName("recentInvestmentEntry")
            item.setFixedHeight(self.RECENT_ENTRY_HEIGHT)
            item_layout = QVBoxLayout(item)
            item_layout.setContentsMargins(10, 7, 10, 7)
            item_layout.setSpacing(2)
            name = QLabel(f"{entry.account_name} — {entry.institution}")
            name.setStyleSheet(f"color: {COLORS['text']}; font-weight: 650;")
            recorded = QLabel(entry.snapshot_datetime.strftime("%b %d, %Y"))
            recorded.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
            value_text = f"Value: {_currency(entry.total_value)}"
            if entry.contribution_amount is not None:
                value_text += (
                    "  ·  Contribution: "
                    f"{'+' if entry.contribution_amount >= 0 else ''}"
                    f"{_currency(entry.contribution_amount)}"
                )
            value = QLabel(value_text)
            value.setStyleSheet(f"color: {COLORS['text_muted']};")
            item_layout.addWidget(name)
            item_layout.addWidget(recorded)
            item_layout.addWidget(value)
            self.recent_layout.addWidget(item)
        content_height = (
            len(entries) * self.RECENT_ENTRY_HEIGHT
            + max(len(entries) - 1, 0) * self.recent_layout.spacing()
        )
        self.recent_entries.setMinimumHeight(content_height)

    def _refresh_entry_accounts(self) -> None:
        selected_id = self.entry_account.currentData()
        self.entry_account.clear()
        for account in self._accounts:
            masked_number = _masked_account_number(
                account.account_number_last7
            )
            suffix = f" ({masked_number})" if masked_number else ""
            self.entry_account.addItem(
                f"{account.account_name} — {account.institution}{suffix}",
                account.id,
            )
        if selected_id is not None:
            index = self.entry_account.findData(selected_id)
            if index >= 0:
                self.entry_account.setCurrentIndex(index)
        self.save_entry_button.setEnabled(bool(self._accounts))

    def _open_add_account(self) -> None:
        if self.user_id is None:
            return
        dialog = InvestmentAccountDialog(self.window())

        def submit() -> None:
            try:
                initial_value = _parse_optional_money(
                    dialog.initial_value.text(), "Initial value"
                )
                create_investment_account(
                    dialog.institution.text(),
                    dialog.account_name.text(),
                    account_number=dialog.account_number.text(),
                    account_type=dialog.account_type.text(),
                    initial_value=initial_value,
                    initial_date=_date_from_editor(dialog.initial_date),
                    user_id=self.user_id,
                    session_factory=self.session_factory,
                )
            except ValueError as exc:
                dialog.error_label.setText(str(exc))
                return
            dialog.accept()
            self.reload()

        dialog.submitted.connect(submit)
        dialog.exec()

    def _open_edit_account(self, account: InvestmentAccountSummary) -> None:
        dialog = InvestmentAccountDialog(self.window(), account=account)

        def submit() -> None:
            try:
                update_investment_account(
                    account.id,
                    institution=dialog.institution.text(),
                    account_name=dialog.account_name.text(),
                    account_number=dialog.account_number.text(),
                    account_type=dialog.account_type.text(),
                    session_factory=self.session_factory,
                )
            except ValueError as exc:
                dialog.error_label.setText(str(exc))
                return
            dialog.accept()
            self.reload()

        dialog.submitted.connect(submit)
        dialog.exec()

    def _delete_account(self, account: InvestmentAccountSummary) -> None:
        answer = QMessageBox.warning(
            self.window(),
            "Delete Investment Account",
            f"Delete {account.account_name} — {account.institution}?\n\n"
            "This permanently deletes the account and all portfolio history "
            "for this account. This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_investment_account(
                account.id, session_factory=self.session_factory
            )
        except ValueError as exc:
            QMessageBox.warning(self.window(), "Unable to Delete Account", str(exc))
            return
        self.reload()

    def _select_entry_account(self, account_id: int) -> None:
        index = self.entry_account.findData(account_id)
        if index >= 0:
            self.entry_account.setCurrentIndex(index)
        self.entry_total.setFocus()

    def _save_entry(self) -> None:
        self.entry_error.clear()
        account_id = self.entry_account.currentData()
        if account_id is None:
            self.entry_error.setText("Add an investment account first")
            return
        try:
            total_value = _parse_optional_money(
                self.entry_total.text(), "Total amount"
            )
            if total_value is None:
                raise ValueError("Total amount is required")
            contribution = _parse_optional_money(
                self.entry_contribution.text(), "Contribution amount"
            )
            create_investment_snapshot(
                account_id,
                _date_from_editor(self.entry_date),
                total_value,
                contribution,
                session_factory=self.session_factory,
            )
        except ValueError as exc:
            self.entry_error.setText(str(exc))
            return
        self.entry_total.clear()
        self.entry_contribution.clear()
        self.entry_date.setDate(_qdate(date.today()))
        self.reload()

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
