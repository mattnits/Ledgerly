from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDate, QPointF, QRectF, QSignalBlocker, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QHeaderView,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.db import SessionLocal
from app.services.investments import (
    InvestmentAccountSummary,
    PortfolioPoint,
    create_investment_account,
    create_investment_snapshot,
    delete_investment_account,
    get_account_summaries,
    get_account_history,
    get_all_time_work_rrsp_summary,
    get_investment_months,
    get_monthly_work_rrsp_summary,
    get_monthly_contribution_comparison,
    get_portfolio_history,
    get_recent_snapshots,
    get_total_contributions,
    get_work_rrsp_monthly_history,
    update_investment_account,
)
from app.ui.widgets.account_badge import AccountBadge
from app.ui.widgets.combo_box import AppComboBox, FramelessPopupComboBox
from app.ui.widgets.date_picker import DatePickerEdit
from app.ui.dialogs.generic_dialog import GenericDialog
from app.ui.widgets.generic_table import GenericTable
from app.ui.widgets.page_header import PageHeader
from app.ui.widgets.period_selector import PeriodSelector
from app.ui.theme import (
    COLORS,
    brand_icon,
    set_button_icon,
    set_delete_button_icon,
    set_icon_only_button,
    set_label_icon,
)


def _currency(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def _signed_currency(value: Decimal) -> str:
    if value > 0:
        return f"+${value:,.2f}"
    return _currency(value)


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


class FlexiblePercentSpinBox(QDoubleSpinBox):
    """Display whole percentages compactly while retaining decimal precision."""

    def textFromValue(self, value: float) -> str:
        return f"{value:.4f}".rstrip("0").rstrip(".")


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
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        line_color: str = "#2791ff",
        empty_text: str = "No portfolio history yet",
    ) -> None:
        super().__init__(parent)
        self.points: tuple[PortfolioPoint, ...] = ()
        self.range_start: date | None = None
        self.range_end: date | None = None
        self.line_color = line_color
        self.empty_text = empty_text
        self.setMinimumHeight(175)
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
                self.empty_text,
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
        painter.setPen(QPen(QColor(self.line_color), 2.5))
        painter.drawPath(path)
        painter.setBrush(QColor(self.line_color))
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
        self.setMinimumHeight(104)
        self.setMaximumHeight(122)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(9)
        self.icon_frame = QFrame()
        self.icon_frame.setObjectName("investmentSummaryIcon")
        self.icon_frame.setFixedSize(34, 34)
        icon_layout = QVBoxLayout(self.icon_frame)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_label = QLabel()
        set_label_icon(icon_label, icon, color="#42a0ff", size=18)
        icon_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignCenter)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 12px; font-weight: 650;"
        )
        self.title_label.setWordWrap(False)
        title_row.addWidget(self.icon_frame)
        title_row.addWidget(self.title_label)
        title_row.addStretch()
        layout.addLayout(title_row)

        self.value_label = QLabel("$0.00")
        self.value_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 24px; font-weight: 750;"
        )
        layout.addWidget(self.value_label, alignment=Qt.AlignmentFlag.AlignBottom)
        self.detail_label = QLabel()
        self.detail_label.setWordWrap(False)
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

        self.scroll = QScrollArea()
        self.scroll.setObjectName("investmentAccountScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        content = QWidget()
        content.setObjectName("investmentAccountDialogContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(14)
        self.scroll.setWidget(content)

        def section(
            title: str,
            subtitle: str,
            icon_name: str,
        ) -> tuple[QFrame, QVBoxLayout]:
            card = QFrame()
            card.setObjectName("investmentDialogSection")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 14, 16, 16)
            card_layout.setSpacing(12)
            header = QHBoxLayout()
            header.setSpacing(8)
            icon = QLabel()
            icon.setObjectName("investmentDialogSectionIcon")
            set_label_icon(icon, icon_name, color="#6c8cff", size=18)
            icon.setFixedSize(34, 34)
            icon.setStyleSheet(
                "background: #17233f; border-radius: 9px; padding: 0;"
            )
            heading = QVBoxLayout()
            heading.setSpacing(2)
            title_label = QLabel(title)
            title_label.setObjectName("investmentDialogSectionTitle")
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("investmentDialogSectionSubtitle")
            subtitle_label.setWordWrap(True)
            heading.addWidget(title_label)
            heading.addWidget(subtitle_label)
            header.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
            header.addLayout(heading, 1)
            card_layout.addLayout(header)
            return card, card_layout

        def configure_form(form: QFormLayout) -> None:
            form.setHorizontalSpacing(18)
            form.setVerticalSpacing(10)
            form.setFieldGrowthPolicy(
                QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
            )
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setLabelAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )

        details_card, details_layout = section(
            "Account Details",
            "Enter the basic information for this investment account.",
            "fa6s.building-columns",
        )
        details_form = QFormLayout()
        configure_form(details_form)

        self.institution = QLineEdit(account.institution if account else "")
        self.institution.setPlaceholderText("e.g. Wealthsimple")
        self.account_name = QLineEdit(account.account_name if account else "")
        self.account_name.setPlaceholderText("e.g. TFSA")
        self.account_type = AppComboBox()
        existing_type = (account.account_type or "").strip() if account else ""
        supported_types = {"tfsa": "TFSA", "fhsa": "FHSA", "rrsp": "RRSP"}
        selected_type = supported_types.get(existing_type.casefold())
        general_value = existing_type if existing_type and not selected_type else "General"
        self.account_type.addItem("General Investment", general_value)
        self.account_type.addItem("TFSA", "TFSA")
        self.account_type.addItem("FHSA", "FHSA")
        self.account_type.addItem("RRSP", "RRSP")
        if selected_type:
            self.account_type.setCurrentText(selected_type)
        self.account_number = QLineEdit(
            account.account_number_last7 or "" if account else ""
        )
        self.account_number.setPlaceholderText(
            "Optional — only the last 7 letters/numbers are stored"
        )
        self.account_number.setMaxLength(64)
        details_form.addRow("Institution", self.institution)
        details_form.addRow("Account name", self.account_name)
        details_form.addRow("Account type", self.account_type)
        details_form.addRow("Account number (last 7)", self.account_number)
        details_layout.addLayout(details_form)

        self.work_related = QCheckBox("Work / employer-related RRSP")
        self.work_related.setChecked(bool(account and account.is_work_related))
        self.work_toggle_card = QFrame()
        self.work_toggle_card.setObjectName("workRrspToggleCard")
        toggle_layout = QVBoxLayout(self.work_toggle_card)
        toggle_layout.setContentsMargins(12, 10, 12, 10)
        toggle_layout.setSpacing(3)
        toggle_layout.addWidget(self.work_related)
        toggle_help = QLabel(
            "Enable this if the RRSP is through your employer and contributions "
            "are deducted automatically from your paycheque."
        )
        toggle_help.setObjectName("investmentDialogSectionSubtitle")
        toggle_help.setWordWrap(True)
        toggle_help.setContentsMargins(27, 0, 0, 0)
        toggle_layout.addWidget(toggle_help)
        details_layout.addWidget(self.work_toggle_card)
        content_layout.addWidget(details_card)

        self.initial_value = QLineEdit()
        self.initial_value.setPlaceholderText("$    e.g. 10,000.00")
        self.initial_date = DatePickerEdit(_qdate(date.today()))
        self.initial_section, initial_layout = section(
            "Initial Setup",
            "Set the account start date and optional initial value.",
            "fa6s.chart-line",
        )
        initial_form = QFormLayout()
        configure_form(initial_form)
        if account is None:
            initial_form.addRow("Initial value", self.initial_value)
            initial_form.addRow("Initial date", self.initial_date)
        initial_layout.addLayout(initial_form)
        self.initial_section.setVisible(account is None)
        content_layout.addWidget(self.initial_section)

        self.work_section = QFrame()
        self.work_section.setObjectName("investmentDialogSection")
        work_layout = QVBoxLayout(self.work_section)
        work_layout.setContentsMargins(16, 14, 16, 16)
        work_layout.setSpacing(12)
        work_header = QHBoxLayout()
        work_header.setSpacing(8)
        work_icon = QLabel()
        set_label_icon(work_icon, "fa6s.coins", color="#6c8cff", size=18)
        work_icon.setFixedSize(34, 34)
        work_icon.setStyleSheet(
            "background: #17233f; border-radius: 9px; padding: 0;"
        )
        work_heading = QVBoxLayout()
        work_heading.setSpacing(2)
        work_title = QLabel("Work RRSP / Payroll Tracking")
        work_title.setObjectName("investmentDialogSectionTitle")
        work_subtitle = QLabel(
            "Automatically calculate your contributions from Salary transactions."
        )
        work_subtitle.setObjectName("investmentDialogSectionSubtitle")
        work_subtitle.setWordWrap(True)
        work_heading.addWidget(work_title)
        work_heading.addWidget(work_subtitle)
        work_header.addWidget(work_icon, 0, Qt.AlignmentFlag.AlignTop)
        work_header.addLayout(work_heading, 1)
        work_layout.addLayout(work_header)
        work_form = QFormLayout()
        configure_form(work_form)
        self.employee_percent = FlexiblePercentSpinBox()
        self.employee_percent.setRange(0, 99.9999)
        self.employee_percent.setDecimals(4)
        self.employee_percent.setSuffix(" %")
        self.employee_percent.setValue(float(
            account.employee_contribution_percent
            if account and account.employee_contribution_percent is not None
            else Decimal("5.00")
        ))
        self.employer_matching = QCheckBox("Enabled")
        self.employer_matching.setChecked(
            account.employer_matching_enabled if account else True
        )
        self.employer_match_percent = FlexiblePercentSpinBox()
        self.employer_match_percent.setRange(0, 999.9999)
        self.employer_match_percent.setDecimals(4)
        self.employer_match_percent.setSuffix(" %")
        self.employer_match_percent.setValue(float(
            account.employer_match_percent
            if account and account.employer_match_percent is not None
            else Decimal("50.00")
        ))
        match_field = QWidget()
        match_layout = QHBoxLayout(match_field)
        match_layout.setContentsMargins(0, 0, 0, 0)
        match_layout.setSpacing(8)
        match_layout.addWidget(self.employer_match_percent, 1)
        match_description = QLabel("of employee contribution")
        match_description.setObjectName("investmentDialogSectionSubtitle")
        match_layout.addWidget(match_description)
        self.auto_track = QCheckBox("Enabled")
        self.auto_track.setChecked(
            account.auto_track_from_payroll if account else True
        )
        work_form.addRow("Employee contribution", self.employee_percent)
        work_form.addRow("Employer matching", self.employer_matching)
        work_form.addRow("Employer match", match_field)
        work_form.addRow("Auto-track from Salary transactions", self.auto_track)
        work_layout.addLayout(work_form)
        note = QLabel(
            "Salary deposits are treated as take-home pay after the configured "
            "RRSP deduction. The app estimates your employee contribution by "
            "reversing that deduction. Tracking starts on the Initial date and "
            "includes them once each month is complete; the current month is excluded."
        )
        note.setObjectName("workRrspInfoNote")
        note.setWordWrap(True)
        note.setContentsMargins(12, 9, 12, 9)
        work_layout.addWidget(note)
        content_layout.addWidget(self.work_section)

        self.account_type.currentIndexChanged.connect(self._refresh_work_controls)
        self.work_related.toggled.connect(self._refresh_work_controls)
        self.employer_matching.toggled.connect(
            self.employer_match_percent.setEnabled
        )
        self._refresh_work_controls()
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(f"color: {COLORS['negative']};")
        content_layout.addWidget(self.error_label)
        content_layout.addStretch()

        super().__init__(
            "Edit Investment Account" if account else "Add Investment Account",
            self.scroll,
            parent,
            submit_label="Save Account" if account else "Add Account",
            subtitle=(
                "Update account details and payroll tracking settings."
                if account
                else "Create an account and optionally add payroll tracking for work RRSPs."
            ),
            icon_name="fa6s.chart-line",
        )
        self.setMinimumSize(520, 430)
        self.resize(660, 700 if account is None else 650)
        self.scroll.setStyleSheet(
            "QScrollArea#investmentAccountScroll { background: transparent; border: none; }"
            "QScrollArea#investmentAccountScroll > QWidget > QWidget "
            "{ background: transparent; }"
        )

    def _refresh_work_controls(self, *_args) -> None:
        is_rrsp = self.selected_account_type().casefold() == "rrsp"
        self.work_toggle_card.setVisible(is_rrsp)
        if not is_rrsp:
            self.work_related.setChecked(False)
        self.work_section.setVisible(is_rrsp and self.work_related.isChecked())
        self.work_toggle_card.setProperty(
            "selected", self.work_related.isChecked()
        )
        self.work_toggle_card.style().unpolish(self.work_toggle_card)
        self.work_toggle_card.style().polish(self.work_toggle_card)
        self.employer_match_percent.setEnabled(
            self.employer_matching.isChecked()
        )

    def work_settings(self) -> dict[str, object]:
        enabled = (
            self.selected_account_type().casefold() == "rrsp"
            and self.work_related.isChecked()
        )
        return {
            "is_work_related": enabled,
            "auto_track_from_payroll": enabled and self.auto_track.isChecked(),
            "employee_contribution_percent": (
                Decimal(str(self.employee_percent.value())) if enabled else None
            ),
            "employer_matching_enabled": (
                enabled and self.employer_matching.isChecked()
            ),
            "employer_match_percent": (
                Decimal(str(self.employer_match_percent.value()))
                if enabled and self.employer_matching.isChecked()
                else None
            ),
        }

    def selected_account_type(self) -> str:
        return str(self.account_type.currentData() or "General")


class PortfolioEntryDialog(GenericDialog):
    """Compact modal used to record a portfolio value or contribution."""

    def __init__(
        self,
        accounts: tuple[InvestmentAccountSummary, ...],
        parent=None,
        *,
        selected_account_id: int | None = None,
    ) -> None:
        content = QWidget()
        form = QFormLayout(content)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self.account = FramelessPopupComboBox()
        self.account.setObjectName("investmentEntryAccount")
        self.account.setMaxVisibleItems(8)
        for account in accounts:
            masked_number = _masked_account_number(account.account_number_last7)
            suffix = f" ({masked_number})" if masked_number else ""
            self.account.addItem(
                brand_icon(account.institution, size=18),
                f"{account.account_name} — {account.institution}{suffix}",
                account.id,
            )
        if selected_account_id is not None:
            selected_index = self.account.findData(selected_account_id)
            if selected_index >= 0:
                self.account.setCurrentIndex(selected_index)

        self.entry_date = DatePickerEdit(_qdate(date.today()))
        self.total = QLineEdit()
        self.total.setPlaceholderText("0.00")
        self.contribution = QLineEdit()
        self.contribution.setPlaceholderText("Optional")
        for field in (
            self.account,
            self.entry_date,
            self.total,
            self.contribution,
        ):
            field.setMinimumWidth(0)
            field.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
        form.addRow("Investment account", self.account)
        form.addRow("Date", self.entry_date)
        form.addRow("Total amount", self.total)
        form.addRow("Contribution", self.contribution)

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(f"color: {COLORS['negative']};")
        form.addRow("", self.error_label)

        super().__init__(
            "Add Portfolio Entry",
            content,
            parent,
            submit_label="Add Entry",
            subtitle="Record an account value and optional contribution.",
            icon_name="fa6s.chart-line",
        )
        self.setMinimumSize(520, 430)
        self.resize(620, 500)


class WorkRrspDetailDialog(GenericDialog):
    def __init__(
        self,
        account: InvestmentAccountSummary,
        parent=None,
        *,
        session_factory=SessionLocal,
    ) -> None:
        current_month = (date.today().year, date.today().month)
        completed_month = _previous_month(current_month)
        current = get_monthly_work_rrsp_summary(
            account.id, *current_month, session_factory=session_factory
        )
        completed = get_monthly_work_rrsp_summary(
            account.id, *completed_month, session_factory=session_factory
        )
        all_time = get_all_time_work_rrsp_summary(
            account.id, session_factory=session_factory
        )
        history = get_work_rrsp_monthly_history(
            account.id, session_factory=session_factory
        )
        self.current_summary = current
        self.completed_summary = completed
        self.all_time_summary = all_time
        self.history = history

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        account_info = QLabel(
            f"{account.institution} · {account.account_name}"
            + (
                f" · {_masked_account_number(account.account_number_last7)}"
                if account.account_number_last7
                else ""
            )
        )
        account_info.setStyleSheet(f"color: {COLORS['text_muted']};")
        layout.addWidget(account_info)
        current_value = QLabel(
            "Current Value: "
            + (_currency(account.current_value) if account.last_updated else "No data")
        )
        current_value.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 20px; font-weight: 750;"
        )
        layout.addWidget(current_value)

        totals = QGridLayout()
        totals.setHorizontalSpacing(20)
        totals.setVerticalSpacing(7)
        totals.addWidget(QLabel(""), 0, 0)
        totals.addWidget(
            QLabel(date(*completed_month, 1).strftime("%B %Y")), 0, 1
        )
        totals.addWidget(QLabel("All Time"), 0, 2)
        for row, (caption, current_amount, all_time_amount) in enumerate((
            (
                "You contributed",
                completed.employee_contribution,
                all_time.employee_contribution,
            ),
            (
                "Employer matched",
                completed.employer_match,
                all_time.employer_match,
            ),
            (
                "Total contributed",
                completed.total_contribution,
                all_time.total_contribution,
            ),
        ), start=1):
            totals.addWidget(QLabel(caption), row, 0)
            current_label = QLabel(_currency(current_amount))
            all_time_label = QLabel(_currency(all_time_amount))
            current_label.setStyleSheet(f"color: {COLORS['positive']};")
            all_time_label.setStyleSheet(f"color: {COLORS['positive']};")
            totals.addWidget(current_label, row, 1)
            totals.addWidget(all_time_label, row, 2)
        layout.addLayout(totals)

        history_title = QLabel("Contribution History")
        history_title.setObjectName("sectionTitle")
        layout.addWidget(history_title)
        self.history_table = GenericTable((
            "Month",
            "Employee Contribution",
            "Employer Match",
            "Total Contribution",
        ))
        self.history_table.setMinimumHeight(220)
        self.history_table.set_rows(tuple(
            (
                date(item.year, item.month, 1).strftime("%b %Y"),
                _currency(item.summary.employee_contribution),
                _currency(item.summary.employer_match),
                _currency(item.summary.total_contribution),
            )
            for item in history
        ))
        self.history_table.setVisible(bool(history))
        layout.addWidget(self.history_table)
        self.history_empty = QLabel(
            "No Salary data is available for contribution history."
        )
        self.history_empty.setObjectName("emptyLabel")
        self.history_empty.setVisible(not history)
        layout.addWidget(self.history_empty)

        super().__init__(
            "Work RRSP",
            content,
            parent,
            submit_label="Close",
            subtitle="Payroll-derived contributions are separate from portfolio snapshots.",
            icon_name="fa6s.piggy-bank",
        )
        self.cancel_button.hide()
        self.submitted.connect(self.accept)
        self.resize(760, 620)


class InvestmentsPage(QWidget):
    PAGE_MARGIN = 24
    SECTION_GAP = 14
    CARD_GAP = 14
    WIDE_LAYOUT_WIDTH = 1120
    MEDIUM_LAYOUT_WIDTH = 820
    ACCOUNT_ACTION_COLUMN_WIDTH = 128
    MAX_RECENT_ENTRIES = 5

    def __init__(self, session_factory=SessionLocal):
        super().__init__()
        self.session_factory = session_factory
        self.user_id: str | None = None
        self.group_id: int | None = None
        self._accounts: tuple[InvestmentAccountSummary, ...] = ()
        self._rrsp_card_grids: list[tuple[QGridLayout, list[QFrame]]] = []
        self.setObjectName("investmentsPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.page_scroll = QScrollArea()
        self.page_scroll.setObjectName("investmentsScroll")
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.page_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.page_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.page_scroll.setStyleSheet(
            "QScrollArea#investmentsScroll { background: transparent; border: none; }"
            "QScrollArea#investmentsScroll > QWidget > QWidget "
            "{ background: transparent; }"
        )
        root_layout.addWidget(self.page_scroll)

        content = QWidget()
        self.content = content
        content.setObjectName("investmentsContent")
        content.setMinimumWidth(0)
        content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(
            self.PAGE_MARGIN,
            18,
            self.PAGE_MARGIN,
            self.PAGE_MARGIN,
        )
        self.content_layout.setSpacing(self.SECTION_GAP)
        self.page_scroll.setWidget(content)

        self.add_entry_button = QPushButton("Add Portfolio Entry")
        self.add_entry_button.setObjectName("pageActionButton")
        set_button_icon(
            self.add_entry_button,
            "fa6s.plus",
            color="#ffffff",
            active_color="#ffffff",
        )
        self.add_entry_button.clicked.connect(lambda: self._open_add_entry())
        self.add_account_button = QPushButton("Add Investment Account")
        self.add_account_button.setObjectName("pageActionButton")
        set_button_icon(
            self.add_account_button,
            "fa6s.plus",
            color="#ffffff",
            active_color="#ffffff",
        )
        self.add_account_button.clicked.connect(self._open_add_account)

        self.header_actions = QWidget()
        self.header_actions_layout = QGridLayout(self.header_actions)
        self.header_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.header_actions_layout.setHorizontalSpacing(10)
        self.header_actions_layout.setVerticalSpacing(8)
        self.header_actions_layout.addWidget(self.add_entry_button, 0, 0)
        self.header_actions_layout.addWidget(self.add_account_button, 0, 1)
        self.header = PageHeader(
            "Investments",
            "Track your investment accounts and portfolio performance.",
        )
        self.header_grid = QGridLayout()
        self.header_grid.setContentsMargins(0, 0, 0, 0)
        self.header_grid.setHorizontalSpacing(16)
        self.header_grid.setVerticalSpacing(8)
        self.header_grid.addWidget(self.header, 0, 0)
        self.header_grid.addWidget(
            self.header_actions,
            0,
            1,
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        self.header_grid.setColumnStretch(0, 1)
        self.content_layout.addLayout(self.header_grid)

        self.period_selector = PeriodSelector()
        self.period_selector.selection_changed.connect(lambda *_: self.reload())
        self.content_layout.addWidget(self.period_selector)

        self.summary_grid = QGridLayout()
        self.summary_grid.setSpacing(self.CARD_GAP)
        self.portfolio_card = SummaryCard(
            "Total Portfolio Value", "fa6s.chart-line"
        )
        self.contribution_card = SummaryCard(
            "Monthly Contributions", "fa6s.coins"
        )
        self.accounts_card = SummaryCard(
            "Investment Accounts", "fa6s.building-columns"
        )
        self.gain_card = SummaryCard("Total Gain/Loss", "fa6s.chart-column")
        self.summary_cards = (
            self.portfolio_card,
            self.contribution_card,
            self.accounts_card,
            self.gain_card,
        )
        self.content_layout.addLayout(self.summary_grid)

        self.empty_panel = self._build_empty_panel()
        self.content_layout.addWidget(self.empty_panel, 1)

        self.chart_container = QWidget()
        self.chart_grid = QGridLayout()
        self.chart_grid.setContentsMargins(0, 0, 0, 0)
        self.chart_grid.setHorizontalSpacing(self.CARD_GAP)
        self.chart_grid.setVerticalSpacing(self.CARD_GAP)
        self.chart_container.setLayout(self.chart_grid)
        self.chart = PortfolioChart()
        self.portfolio_chart_card = self._build_chart_panel(
            "Portfolio Performance",
            "Total value of all investment accounts over time.",
            self.chart,
        )
        self.account_selector = FramelessPopupComboBox()
        self.account_selector.setObjectName("investmentChartAccountSelector")
        self.account_selector.setMinimumWidth(190)
        self.account_selector.setMaxVisibleItems(8)
        self.account_selector.currentIndexChanged.connect(
            self._account_chart_changed
        )
        self.account_chart = PortfolioChart(
            line_color=COLORS["positive"],
            empty_text="No history for this account yet",
        )
        self.account_chart_card = self._build_chart_panel(
            "Account Performance",
            "Performance of a single investment account.",
            self.account_chart,
            self.account_selector,
        )
        self.content_layout.addWidget(self.chart_container)

        self.activity_container = QWidget()
        self.activity_grid = QGridLayout()
        self.activity_grid.setContentsMargins(0, 0, 0, 0)
        self.activity_grid.setHorizontalSpacing(self.CARD_GAP)
        self.activity_grid.setVerticalSpacing(self.CARD_GAP)
        self.activity_container.setLayout(self.activity_grid)
        self.accounts_panel = self._build_accounts_panel()
        self.recent_panel = self._build_recent_panel()
        self.content_layout.addWidget(self.activity_container)

        self.work_rrsp_panel = self._build_work_rrsp_panel()
        self.content_layout.addWidget(self.work_rrsp_panel)

        self._layout_mode: str | None = None
        self._update_responsive_layout(self.width())

        self.setStyleSheet("""
            QFrame#investmentSummaryIcon, QFrame#investmentSectionIcon {
                background: #13294a;
                border: 1px solid #1d4777;
                border-radius: 9px;
            }
            QLabel#investmentSectionSubtitle {
                color: #8f9baa;
                font-size: 11px;
            }
            QFrame#investmentEmptyPanel {
                background: #151b21;
                border: 1px solid #303b46;
                border-radius: 14px;
            }
            QLabel#investmentEmptyTitle {
                color: #f2f4f7;
                font-size: 24px;
                font-weight: 700;
            }
            QLabel#investmentEmptyMessage {
                color: #aab5c3;
                font-size: 14px;
            }
            QFrame#investmentEmptyHeroIcon, QFrame#investmentEmptyStepIcon {
                background: #152945;
                border: 1px solid #1e416b;
                border-radius: 28px;
            }
            QFrame#investmentEmptyHeroIcon {
                border-radius: 44px;
            }
            QLabel#investmentEmptyStepNumber {
                color: #ffffff;
                background: #2387ff;
                border: 1px solid #59a6ff;
                border-radius: 11px;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#investmentEmptyStepTitle {
                color: #f2f4f7;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#investmentEmptyStepText, QLabel#investmentEmptyDividerLabel {
                color: #98a6b6;
                font-size: 11px;
            }
            QFrame#investmentEmptyDivider {
                color: #33404c;
                background: #33404c;
                border: none;
                max-height: 1px;
            }
            QComboBox#investmentChartAccountSelector {
                min-height: 20px;
                padding-top: 6px;
                padding-bottom: 6px;
            }
            QScrollArea#investmentsScroll QScrollBar:vertical {
                width: 9px;
                margin: 3px 1px;
                background: transparent;
            }
            QScrollArea#investmentsScroll QScrollBar::handle:vertical {
                min-height: 28px;
                background: #4a5058;
                border-radius: 4px;
            }
            QScrollArea#investmentsScroll QScrollBar::add-line:vertical,
            QScrollArea#investmentsScroll QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

    @staticmethod
    def _section_heading(
        title: str,
        subtitle: str,
        icon_name: str,
        trailing: QWidget | None = None,
    ) -> QWidget:
        heading = QWidget()
        layout = QHBoxLayout(heading)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        icon_frame = QFrame()
        icon_frame.setObjectName("investmentSectionIcon")
        icon_frame.setFixedSize(36, 36)
        icon_layout = QVBoxLayout(icon_frame)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon = QLabel()
        set_label_icon(icon, icon_name, color="#42a0ff", size=18)
        icon_layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)
        labels = QVBoxLayout()
        labels.setSpacing(1)
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("investmentSectionSubtitle")
        subtitle_label.setWordWrap(True)
        labels.addWidget(title_label)
        labels.addWidget(subtitle_label)
        layout.addWidget(icon_frame, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(labels, 1)
        if trailing is not None:
            layout.addWidget(trailing, alignment=Qt.AlignmentFlag.AlignTop)
        return heading

    def _build_chart_panel(
        self,
        title: str,
        subtitle: str,
        chart: PortfolioChart,
        selector: QWidget | None = None,
    ) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentCard")
        panel.setMinimumWidth(0)
        panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(6)
        header = QWidget()
        header_grid = QGridLayout(header)
        header_grid.setContentsMargins(0, 0, 0, 0)
        header_grid.setHorizontalSpacing(10)
        header_grid.setVerticalSpacing(6)
        heading = self._section_heading(
            title,
            subtitle,
            "fa6s.chart-line",
        )
        header_grid.addWidget(heading, 0, 0)
        header_grid.setColumnStretch(0, 1)
        if selector is not None:
            header_grid.addWidget(
                selector,
                0,
                1,
                alignment=Qt.AlignmentFlag.AlignRight
                | Qt.AlignmentFlag.AlignTop,
            )
        panel.header_grid = header_grid
        panel.heading = heading
        panel.selector = selector
        layout.addWidget(header)
        layout.addWidget(chart, 1)
        return panel

    def _build_empty_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("investmentEmptyPanel")
        panel.setMinimumHeight(420)
        panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout = QVBoxLayout(panel)
        self.empty_panel_layout = layout
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(42, 24, 42, 28)
        layout.setSpacing(10)

        self.empty_hero = QWidget()
        self.empty_hero.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        hero_layout = QVBoxLayout(self.empty_hero)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        hero_layout.setSpacing(10)

        self.empty_hero_icon = QFrame()
        self.empty_hero_icon.setObjectName("investmentEmptyHeroIcon")
        self.empty_hero_icon.setFixedSize(88, 88)
        hero_icon_layout = QVBoxLayout(self.empty_hero_icon)
        hero_icon_layout.setContentsMargins(0, 0, 0, 0)
        icon = QLabel()
        set_label_icon(icon, "fa6s.chart-column", color="#3597ff", size=40)
        hero_icon_layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)

        self.empty_title = QLabel("No investment accounts yet")
        self.empty_title.setObjectName("investmentEmptyTitle")
        self.empty_title.setTextFormat(Qt.TextFormat.PlainText)
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_title.setWordWrap(False)
        self.empty_title.setMinimumHeight(38)
        self.empty_title.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self.empty_message = QLabel(
            "Add your first investment account to start tracking portfolio "
            "value, contributions, and performance."
        )
        self.empty_message.setObjectName("investmentEmptyMessage")
        self.empty_message.setTextFormat(Qt.TextFormat.PlainText)
        self.empty_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_message.setWordWrap(True)
        self.empty_message.setMaximumWidth(560)
        self.empty_message.setMinimumHeight(38)
        self.empty_message.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Minimum,
        )
        self.empty_add_account_button = QPushButton("Add Investment Account")
        self.empty_add_account_button.setObjectName("pageActionButton")
        set_button_icon(
            self.empty_add_account_button,
            "fa6s.plus",
            color="#ffffff",
            active_color="#ffffff",
        )
        self.empty_add_account_button.clicked.connect(self._open_add_account)
        hero_layout.addWidget(
            self.empty_hero_icon,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        hero_layout.addWidget(self.empty_title)
        message_row = QHBoxLayout()
        message_row.setContentsMargins(0, 0, 0, 0)
        message_row.addStretch(1)
        message_row.addWidget(self.empty_message, 4)
        message_row.addStretch(1)
        hero_layout.addLayout(message_row)
        hero_layout.addWidget(
            self.empty_add_account_button,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        layout.addWidget(self.empty_hero)

        self.empty_divider = QWidget()
        self.empty_divider.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        divider = QHBoxLayout(self.empty_divider)
        divider.setContentsMargins(0, 0, 0, 0)
        divider.setSpacing(12)
        left_line = QFrame()
        left_line.setObjectName("investmentEmptyDivider")
        left_line.setFrameShape(QFrame.Shape.HLine)
        right_line = QFrame()
        right_line.setObjectName("investmentEmptyDivider")
        right_line.setFrameShape(QFrame.Shape.HLine)
        self.empty_divider_label = QLabel("How it works")
        self.empty_divider_label.setObjectName("investmentEmptyDividerLabel")
        divider.addWidget(left_line, 1)
        divider.addWidget(self.empty_divider_label)
        divider.addWidget(right_line, 1)
        layout.addStretch(1)
        layout.addWidget(self.empty_divider)

        self.empty_steps_grid = QGridLayout()
        self.empty_steps_grid.setContentsMargins(0, 4, 0, 0)
        self.empty_steps_grid.setHorizontalSpacing(16)
        self.empty_steps_grid.setVerticalSpacing(12)
        self.empty_steps = (
            self._build_empty_step(
                1,
                "fa6s.building-columns",
                "Add an account",
                "Connect your investment account (e.g. brokerage or retirement).",
            ),
            self._build_empty_step(
                2,
                "fa6s.file-lines",
                "Add portfolio entries",
                "Record purchases, contributions, and other investment activity.",
            ),
            self._build_empty_step(
                3,
                "fa6s.chart-line",
                "Track performance",
                "View portfolio value, contributions, and gain/loss over time.",
            ),
        )
        self.empty_step_arrows = (QLabel(), QLabel())
        for arrow in self.empty_step_arrows:
            set_label_icon(arrow, "fa6s.chevron-right", color="#4aa3ff", size=16)
        layout.addLayout(self.empty_steps_grid)
        layout.addStretch(1)
        return panel

    @staticmethod
    def _build_empty_step(
        number: int,
        icon_name: str,
        title: str,
        description: str,
    ) -> QWidget:
        step = QWidget()
        step.setMinimumWidth(0)
        step.setMinimumHeight(76)
        step.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        step_layout = QHBoxLayout(step)
        step_layout.setContentsMargins(0, 0, 0, 0)
        step_layout.setSpacing(12)

        icon_stack = QWidget()
        icon_stack.setFixedSize(72, 68)
        icon_frame = QFrame(icon_stack)
        icon_frame.setObjectName("investmentEmptyStepIcon")
        icon_frame.setGeometry(0, 8, 56, 56)
        icon_layout = QVBoxLayout(icon_frame)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon = QLabel()
        set_label_icon(icon, icon_name, color="#4aa3ff", size=24)
        icon_layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)
        badge = QLabel(str(number), icon_stack)
        badge.setObjectName("investmentEmptyStepNumber")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setGeometry(48, 0, 24, 24)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 8, 0, 0)
        text_layout.setSpacing(4)
        title_label = QLabel(title)
        title_label.setObjectName("investmentEmptyStepTitle")
        title_label.setWordWrap(True)
        title_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Minimum,
        )
        description_label = QLabel(description)
        description_label.setObjectName("investmentEmptyStepText")
        description_label.setWordWrap(True)
        description_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Minimum,
        )
        text_layout.addWidget(title_label)
        text_layout.addWidget(description_label)
        text_layout.addStretch()
        step_layout.addWidget(icon_stack, alignment=Qt.AlignmentFlag.AlignTop)
        step_layout.addLayout(text_layout, 1)
        return step

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_responsive_layout(self.page_scroll.viewport().width())

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API spelling
        super().showEvent(event)
        self._update_responsive_layout(self.page_scroll.viewport().width())

    def _update_responsive_layout(self, width: int) -> None:
        if width >= self.WIDE_LAYOUT_WIDTH:
            mode = "wide"
        elif width >= self.MEDIUM_LAYOUT_WIDTH:
            mode = "medium"
        else:
            mode = "narrow"
        self._update_empty_panel_metrics(mode)
        if mode == self._layout_mode:
            return
        self._layout_mode = mode

        self.header_grid.removeWidget(self.header)
        self.header_grid.removeWidget(self.header_actions)
        self.header_actions_layout.removeWidget(self.add_entry_button)
        self.header_actions_layout.removeWidget(self.add_account_button)
        if mode == "narrow":
            self.header_actions_layout.addWidget(self.add_entry_button, 0, 0)
            self.header_actions_layout.addWidget(self.add_account_button, 1, 0)
            self.header_grid.addWidget(self.header, 0, 0)
            self.header_grid.addWidget(
                self.header_actions,
                1,
                0,
                alignment=Qt.AlignmentFlag.AlignLeft,
            )
            self.header_grid.setColumnStretch(1, 0)
        else:
            self.header_actions_layout.addWidget(self.add_entry_button, 0, 0)
            self.header_actions_layout.addWidget(self.add_account_button, 0, 1)
            self.header_grid.addWidget(self.header, 0, 0)
            self.header_grid.addWidget(
                self.header_actions,
                0,
                1,
                alignment=(
                    Qt.AlignmentFlag.AlignRight
                    | Qt.AlignmentFlag.AlignVCenter
                ),
            )
            self.header_grid.setColumnStretch(1, 0)

        for card in self.summary_cards:
            self.summary_grid.removeWidget(card)
        summary_columns = 4 if mode == "wide" else 2 if mode == "medium" else 1
        for index, card in enumerate(self.summary_cards):
            self.summary_grid.addWidget(
                card,
                index // summary_columns,
                index % summary_columns,
            )
        for column in range(4):
            self.summary_grid.setColumnStretch(
                column,
                1 if column < summary_columns else 0,
            )

        for grid, widgets in (
            (
                self.chart_grid,
                (self.portfolio_chart_card, self.account_chart_card),
            ),
            (self.activity_grid, (self.accounts_panel, self.recent_panel)),
        ):
            for widget in widgets:
                grid.removeWidget(widget)

        side_by_side = mode == "wide"
        if side_by_side:
            self.chart_grid.addWidget(self.portfolio_chart_card, 0, 0)
            self.chart_grid.addWidget(self.account_chart_card, 0, 1)
            self.chart_grid.setColumnStretch(0, 1)
            self.chart_grid.setColumnStretch(1, 1)
            self.activity_grid.addWidget(self.accounts_panel, 0, 0)
            self.activity_grid.addWidget(self.recent_panel, 0, 1)
            self.activity_grid.setColumnStretch(0, 3)
            self.activity_grid.setColumnStretch(1, 2)
        else:
            self.chart_grid.addWidget(self.portfolio_chart_card, 0, 0)
            self.chart_grid.addWidget(self.account_chart_card, 1, 0)
            self.chart_grid.setColumnStretch(0, 1)
            self.chart_grid.setColumnStretch(1, 0)
            self.activity_grid.addWidget(self.accounts_panel, 0, 0)
            self.activity_grid.addWidget(self.recent_panel, 1, 0)
            self.activity_grid.setColumnStretch(0, 1)
            self.activity_grid.setColumnStretch(1, 0)

        self._reflow_rrsp_cards(stack=mode == "narrow")
        self._reflow_chart_header(
            self.account_chart_card,
            stack=mode == "narrow",
        )
        self._reflow_empty_steps(stack=mode != "wide")

    def _update_empty_panel_metrics(self, mode: str) -> None:
        """Keep empty-state text readable as the scroll viewport changes size."""
        side_margin = 42 if mode == "wide" else 32 if mode == "medium" else 24
        compact_height = self.page_scroll.viewport().height() < 680
        top_margin = 18 if compact_height else 24
        bottom_margin = 20 if compact_height else 28
        self.empty_panel_layout.setContentsMargins(
            side_margin,
            top_margin,
            side_margin,
            bottom_margin,
        )
        self.empty_panel_layout.setSpacing(8 if compact_height else 10)

        wrap_title = mode == "narrow"
        self.empty_title.setWordWrap(wrap_title)
        self.empty_title.setMinimumHeight(64 if wrap_title else 38)
        self.empty_message.setMinimumHeight(58 if mode == "narrow" else 38)
        for step in self.empty_steps:
            step.setMinimumHeight(88 if mode != "wide" else 76)

    def _reflow_empty_steps(self, *, stack: bool) -> None:
        for step in self.empty_steps:
            self.empty_steps_grid.removeWidget(step)
        for arrow in self.empty_step_arrows:
            self.empty_steps_grid.removeWidget(arrow)

        if stack:
            for row, step in enumerate(self.empty_steps):
                self.empty_steps_grid.addWidget(step, row, 0)
            for arrow in self.empty_step_arrows:
                arrow.hide()
            self.empty_steps_grid.setColumnStretch(0, 1)
            for column in range(1, 5):
                self.empty_steps_grid.setColumnStretch(column, 0)
            return

        for index, step in enumerate(self.empty_steps):
            self.empty_steps_grid.addWidget(step, 0, index * 2)
            self.empty_steps_grid.setColumnStretch(index * 2, 1)
            if index < len(self.empty_step_arrows):
                arrow = self.empty_step_arrows[index]
                arrow.show()
                self.empty_steps_grid.addWidget(
                    arrow,
                    0,
                    index * 2 + 1,
                    alignment=Qt.AlignmentFlag.AlignCenter,
                )
                self.empty_steps_grid.setColumnStretch(index * 2 + 1, 0)

    @staticmethod
    def _reflow_chart_header(panel: QFrame, *, stack: bool) -> None:
        selector = panel.selector
        if selector is None:
            return
        panel.header_grid.removeWidget(panel.heading)
        panel.header_grid.removeWidget(selector)
        panel.header_grid.addWidget(panel.heading, 0, 0)
        panel.header_grid.addWidget(
            selector,
            1 if stack else 0,
            0 if stack else 1,
            alignment=(
                Qt.AlignmentFlag.AlignLeft
                if stack
                else Qt.AlignmentFlag.AlignRight
            )
            | Qt.AlignmentFlag.AlignTop,
        )
        panel.header_grid.setColumnStretch(0, 1)
        panel.header_grid.setColumnStretch(1, 0)

    def _build_accounts_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentCard")
        panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        self.accounts_panel_add_button = QPushButton("Add Account")
        self.accounts_panel_add_button.setObjectName("secondaryActionButton")
        set_button_icon(
            self.accounts_panel_add_button,
            "fa6s.plus",
            color="#61adff",
            active_color="#ffffff",
            size=13,
        )
        self.accounts_panel_add_button.clicked.connect(self._open_add_account)
        heading = self._section_heading(
            "Investment Accounts",
            "Linked accounts and their current balances.",
            "fa6s.building-columns",
            self.accounts_panel_add_button,
        )
        heading.setContentsMargins(14, 12, 14, 3)
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
        self.accounts_table.setMinimumHeight(190)
        self.accounts_table.setMaximumHeight(230)
        self.accounts_table.verticalHeader().setDefaultSectionSize(42)
        self.accounts_table.horizontalHeader().setFixedHeight(38)
        self.accounts_table.horizontalHeader().setMinimumSectionSize(82)
        for column in (0, 1):
            self.accounts_table.horizontalHeader().setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Stretch,
            )
        for column in (2, 3, 4):
            self.accounts_table.horizontalHeader().setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )
        self.accounts_table.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeMode.Fixed
        )
        self.accounts_table.setColumnWidth(
            5, self.ACCOUNT_ACTION_COLUMN_WIDTH
        )
        self.accounts_table.horizontalHeaderItem(5).setTextAlignment(
            Qt.AlignmentFlag.AlignCenter
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
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)
        heading = self._section_heading(
            "Recent Portfolio Entries",
            "Latest values and contributions for this period.",
            "fa6s.file-lines",
        )
        heading.setContentsMargins(14, 12, 14, 3)
        panel_layout.addWidget(heading)
        self.recent_table = GenericTable((
            "Date",
            "Account",
            "Value",
            "Contribution",
        ))
        self.recent_table.setMinimumHeight(190)
        self.recent_table.setMaximumHeight(230)
        self.recent_table.verticalHeader().setDefaultSectionSize(30)
        self.recent_table.horizontalHeader().setFixedHeight(38)
        self.recent_table.horizontalHeader().setMinimumSectionSize(76)
        self.recent_table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )
        for column in (0, 2, 3):
            self.recent_table.horizontalHeader().setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )
        self.recent_table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        panel_layout.addWidget(self.recent_table)
        self.recent_empty = QLabel("No portfolio entries for this period")
        self.recent_empty.setObjectName("emptyLabel")
        self.recent_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.recent_empty.setMinimumHeight(120)
        panel_layout.addWidget(self.recent_empty)
        return panel

    def _build_work_rrsp_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentCard")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 12, 14, 14)
        panel_layout.setSpacing(9)
        panel_layout.addWidget(self._section_heading(
            "Work RRSP Contributions",
            "Payroll-derived employee and employer contributions.",
            "fa6s.piggy-bank",
        ))
        self.work_rrsp_empty = QLabel("No work RRSP accounts configured.")
        self.work_rrsp_empty.setObjectName("emptyLabel")
        panel_layout.addWidget(self.work_rrsp_empty)
        self.work_rrsp_content = QWidget()
        self.work_rrsp_layout = QVBoxLayout(self.work_rrsp_content)
        self.work_rrsp_layout.setContentsMargins(0, 0, 0, 0)
        self.work_rrsp_layout.setSpacing(12)
        panel_layout.addWidget(self.work_rrsp_content)
        return panel

    def set_user_id(self, user_id: str | None) -> None:
        self.set_profile(user_id=user_id)

    def set_profile(
        self,
        *,
        user_id: str | None = None,
        group_id: int | None = None,
        reload: bool = True,
    ) -> None:
        self.user_id = user_id
        self.group_id = group_id
        enabled = user_id is not None or group_id is not None
        self.add_account_button.setEnabled(enabled)
        self.accounts_panel_add_button.setEnabled(enabled)
        self.empty_add_account_button.setEnabled(enabled)
        self.period_selector.reset(emit=False)
        if reload:
            self.reload()

    def reload(self) -> None:
        if self.user_id is None and self.group_id is None:
            self.period_selector.set_available_months(())
            self._accounts = ()
            self._render_empty()
            return

        months = get_investment_months(
            user_id=self.user_id,
            group_id=self.group_id,
            session_factory=self.session_factory,
        )
        self.period_selector.set_available_months(months)
        self._accounts = get_account_summaries(
            user_id=self.user_id,
            group_id=self.group_id,
            session_factory=self.session_factory,
        )
        latest_total_value = sum(
            (account.current_value for account in self._accounts),
            Decimal("0.00"),
        )

        selected_month = self.period_selector.selected_month
        start_date = end_date = None
        if self.period_selector.period == "monthly":
            self.contribution_card.set_title("Monthly Contributions")
            start_date, end_date = _month_dates(selected_month)
            comparison = get_monthly_contribution_comparison(
                *selected_month,
                user_id=self.user_id,
                group_id=self.group_id,
                session_factory=self.session_factory,
            )
            contributions = comparison.current
            previous_contributions = comparison.previous
            contribution_label = date(*selected_month, 1).strftime("%B %Y")
        else:
            self.contribution_card.set_title("All-Time Contributions")
            contributions = get_total_contributions(
                user_id=self.user_id,
                group_id=self.group_id,
                session_factory=self.session_factory,
            )
            previous_contributions = None
            contribution_label = "All-time contributions"

        history_end = end_date if end_date is not None else date.today()
        history = get_portfolio_history(
            user_id=self.user_id,
            group_id=self.group_id,
            end_date=history_end,
            session_factory=self.session_factory,
        )
        total_value = (
            history[-1].total_value
            if self.period_selector.period == "monthly" and history
            else latest_total_value
        )
        if self.period_selector.period == "monthly" and not history:
            total_value = Decimal()
        previous_portfolio = self._portfolio_before_month(selected_month)
        self._update_cards(
            total_value,
            previous_portfolio,
            contributions,
            previous_contributions,
            contribution_label,
            history,
        )
        self.chart.set_data(history, end_date=history_end)
        self._populate_account_selector(history_end)
        self._render_accounts()
        self._render_work_rrsp_accounts()
        self._render_recent(start_date, history_end)
        self._set_content_state(bool(self._accounts))

    def _portfolio_before_month(self, month: tuple[int, int]) -> Decimal | None:
        previous = _previous_month(month)
        _, last_day = _month_dates(previous)
        points = get_portfolio_history(
            user_id=self.user_id,
            group_id=self.group_id,
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
        history: tuple[PortfolioPoint, ...],
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

        baseline = previous_value
        baseline_label = "vs previous month"
        if self.period_selector.period == "all":
            baseline = history[0].total_value if history else None
            baseline_label = "since first entry"
        if baseline is None:
            self.gain_card.set_data(
                "$0.00",
                "No comparison history available",
                COLORS["text_dim"],
            )
        else:
            gain = total_value - baseline
            return_percent = (
                gain / abs(baseline) * 100 if baseline else Decimal()
            )
            self.gain_card.set_data(
                _signed_currency(gain),
                f"{return_percent:+.1f}% {baseline_label}",
                COLORS["positive"] if gain >= 0 else COLORS["negative"],
            )

    def _set_content_state(self, has_accounts: bool) -> None:
        self.empty_panel.setVisible(not has_accounts)
        self.add_entry_button.setEnabled(has_accounts)
        self.chart_container.setVisible(has_accounts)
        self.activity_container.setVisible(has_accounts)
        self.work_rrsp_panel.setVisible(has_accounts)

    def _render_empty(self) -> None:
        self.portfolio_card.set_data("$0.00", "No portfolio history")
        self.contribution_card.set_data("$0.00", "No contributions recorded")
        self.accounts_card.set_data("0", "0 institutions")
        self.gain_card.set_data("$0.00", "No comparison history")
        self.chart.set_data(())
        self.account_chart.set_data(())
        with QSignalBlocker(self.account_selector):
            self.account_selector.clear()
        self.accounts_table.set_rows(())
        self.accounts_empty.show()
        self._clear_layout(self.work_rrsp_layout)
        self.work_rrsp_empty.show()
        self.work_rrsp_content.hide()
        self.recent_table.set_rows(())
        self.recent_empty.show()
        self._set_content_state(False)

    def _populate_account_selector(self, history_end: date) -> None:
        selected_id = self.account_selector.currentData()
        available_ids = {account.id for account in self._accounts}
        if selected_id not in available_ids:
            selected_id = self._accounts[0].id if self._accounts else None
        with QSignalBlocker(self.account_selector):
            self.account_selector.clear()
            for account in self._accounts:
                self.account_selector.addItem(
                    brand_icon(account.institution, size=18),
                    f"{account.account_name} — {account.institution}",
                    account.id,
                )
            if selected_id is not None:
                index = self.account_selector.findData(selected_id)
                self.account_selector.setCurrentIndex(max(index, 0))
        self.account_selector.setEnabled(bool(self._accounts))
        self._render_account_chart(history_end)

    def _account_chart_changed(self, _index: int) -> None:
        selected_month = self.period_selector.selected_month
        history_end = (
            _month_dates(selected_month)[1]
            if self.period_selector.period == "monthly"
            else date.today()
        )
        self._render_account_chart(history_end)

    def _render_account_chart(self, history_end: date) -> None:
        account_id = self.account_selector.currentData()
        if account_id is None:
            self.account_chart.set_data(())
            return
        history = tuple(
            snapshot
            for snapshot in get_account_history(
                int(account_id),
                session_factory=self.session_factory,
            )
            if snapshot.snapshot_datetime.date() <= history_end
        )
        self.account_chart.set_data(history, end_date=history_end)

    def _render_accounts(self) -> None:
        rows = []
        for account in self._accounts:
            actions = QWidget()
            actions.setObjectName("tableCell")
            actions.setMinimumWidth(0)
            actions.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(3, 3, 3, 3)
            action_layout.setSpacing(6)
            action_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
            edit_button.clicked.connect(
                lambda checked=False, selected=account: self._open_edit_account(selected)
            )
            delete_button.clicked.connect(
                lambda checked=False, selected=account: self._delete_account(selected)
            )
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

    def _render_work_rrsp_accounts(self) -> None:
        self._clear_layout(self.work_rrsp_layout)
        self._rrsp_card_grids = []
        accounts = tuple(
            account
            for account in self._accounts
            if account.is_work_related
            and (account.account_type or "").strip().casefold() == "rrsp"
        )
        self.work_rrsp_empty.setVisible(not accounts)
        self.work_rrsp_content.setVisible(bool(accounts))
        completed_month = _previous_month((date.today().year, date.today().month))
        completed_month_label = date(*completed_month, 1).strftime("%b %Y")
        for account in accounts:
            monthly = get_monthly_work_rrsp_summary(
                account.id, *completed_month, session_factory=self.session_factory
            )
            all_time = get_all_time_work_rrsp_summary(
                account.id, session_factory=self.session_factory
            )
            block = QFrame()
            block.setObjectName("recentInvestmentEntry")
            block_layout = QVBoxLayout(block)
            block_layout.setContentsMargins(14, 12, 14, 14)
            block_layout.setSpacing(10)

            header = QHBoxLayout()
            name = QLabel(f"{account.institution} · {account.account_name}")
            name.setStyleSheet(
                f"color: {COLORS['text']}; font-size: 14px; font-weight: 700;"
            )
            details = QPushButton("View Details")
            details.setObjectName("tableIconButton")
            set_button_icon(details, "fa6s.list", size=13)
            details.clicked.connect(
                lambda checked=False, selected=account: self._open_work_rrsp_details(selected)
            )
            header.addWidget(name)
            header.addStretch()
            header.addWidget(details)
            block_layout.addLayout(header)

            cards = QGridLayout()
            cards.setSpacing(10)
            metric_cards: list[QFrame] = []
            values = (
                (
                    "You Contributed",
                    all_time.employee_contribution,
                    monthly.employee_contribution,
                ),
                (
                    "Employer Matched",
                    all_time.employer_match,
                    monthly.employer_match,
                ),
                (
                    "Total Contributed",
                    all_time.total_contribution,
                    monthly.total_contribution,
                ),
            )
            for column, (caption, total, this_month) in enumerate(values):
                card = QFrame()
                card.setObjectName("investmentSummaryCard")
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(12, 10, 12, 10)
                card_layout.setSpacing(3)
                title = QLabel(caption)
                title.setStyleSheet(
                    f"color: {COLORS['text_muted']}; font-size: 11px;"
                )
                amount = QLabel(_currency(total))
                amount.setStyleSheet(
                    f"color: {COLORS['positive']}; font-size: 18px; font-weight: 700;"
                )
                month_value = QLabel(
                    f"+{_currency(this_month)} in {completed_month_label}"
                )
                month_value.setStyleSheet(
                    f"color: {COLORS['text_dim']}; font-size: 10px;"
                )
                card_layout.addWidget(title)
                card_layout.addWidget(amount)
                card_layout.addWidget(month_value)
                card.setProperty("rrspMetricIndex", column)
                metric_cards.append(card)
                cards.addWidget(card, 0, column)
                cards.setColumnStretch(column, 1)
            self._rrsp_card_grids.append((cards, metric_cards))
            block_layout.addLayout(cards)

            value_text = (
                _currency(account.current_value)
                if account.last_updated is not None
                else "No data"
            )
            status = "Auto-tracking Salary transactions"
            if not account.auto_track_from_payroll:
                status = "Payroll auto-tracking is disabled"
            footer = QLabel(f"Current Value  {value_text}  ·  {status}")
            footer.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
            block_layout.addWidget(footer)
            self.work_rrsp_layout.addWidget(block)
        self._reflow_rrsp_cards(stack=self._layout_mode == "narrow")

    def _reflow_rrsp_cards(self, *, stack: bool) -> None:
        for grid, cards in self._rrsp_card_grids:
            for card in cards:
                grid.removeWidget(card)
            for index, card in enumerate(cards):
                grid.addWidget(card, index if stack else 0, 0 if stack else index)
            for column in range(3):
                grid.setColumnStretch(column, 1 if not stack else 0)
            grid.setColumnStretch(0, 1)

    def _open_work_rrsp_details(
        self, account: InvestmentAccountSummary
    ) -> None:
        WorkRrspDetailDialog(
            account,
            self.window(),
            session_factory=self.session_factory,
        ).exec()

    def _render_recent(self, start_date: date | None, end_date: date | None) -> None:
        entries = get_recent_snapshots(
            user_id=self.user_id,
            group_id=self.group_id,
            limit=self.MAX_RECENT_ENTRIES,
            start_date=start_date,
            end_date=end_date,
            session_factory=self.session_factory,
        )
        rows = tuple(
            (
                entry.snapshot_datetime.strftime("%b %d, %Y"),
                entry.account_name,
                _currency(entry.total_value),
                (
                    f"{'+' if entry.contribution_amount >= 0 else ''}"
                    f"{_currency(entry.contribution_amount)}"
                    if entry.contribution_amount is not None
                    else "—"
                ),
            )
            for entry in entries
        )
        self.recent_table.set_rows(rows)
        self.recent_table.setVisible(bool(rows))
        self.recent_empty.setVisible(not rows)

    def _open_add_account(self) -> None:
        if self.user_id is None and self.group_id is None:
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
                    account_type=dialog.selected_account_type(),
                    initial_value=initial_value,
                    initial_date=_date_from_editor(dialog.initial_date),
                    user_id=self.user_id,
                    group_id=self.group_id,
                    **dialog.work_settings(),
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
                    account_type=dialog.selected_account_type(),
                    **dialog.work_settings(),
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

    def _open_add_entry(self, selected_account_id: int | None = None) -> None:
        if not self._accounts:
            return
        dialog = PortfolioEntryDialog(
            self._accounts,
            self.window(),
            selected_account_id=selected_account_id,
        )

        def submit() -> None:
            try:
                account_id = dialog.account.currentData()
                if account_id is None:
                    raise ValueError("Choose an investment account")
                total_value = _parse_optional_money(
                    dialog.total.text(),
                    "Total amount",
                )
                if total_value is None:
                    raise ValueError("Total amount is required")
                contribution = _parse_optional_money(
                    dialog.contribution.text(),
                    "Contribution amount",
                )
                create_investment_snapshot(
                    int(account_id),
                    _date_from_editor(dialog.entry_date),
                    total_value,
                    contribution,
                    session_factory=self.session_factory,
                )
            except ValueError as exc:
                dialog.error_label.setText(str(exc))
                return
            dialog.accept()
            self.reload()

        dialog.submitted.connect(submit)
        dialog.exec()

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
