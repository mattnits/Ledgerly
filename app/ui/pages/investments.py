from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDate, QPointF, QRectF, Qt
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
    get_all_time_work_rrsp_summary,
    get_investment_months,
    get_monthly_work_rrsp_summary,
    get_monthly_contribution_comparison,
    get_portfolio_history,
    get_recent_snapshots,
    get_total_contributions,
    get_total_portfolio_value,
    get_work_rrsp_monthly_history,
    update_investment_account,
)
from app.ui.widgets.account_badge import AccountBadge
from app.ui.widgets.combo_box import AppComboBox
from app.ui.widgets.date_picker import DatePickerEdit
from app.ui.dialogs.generic_dialog import GenericDialog
from app.ui.widgets.generic_table import GenericTable
from app.ui.widgets.page_header import PageHeader
from app.ui.widgets.period_selector import PeriodSelector
from app.ui.theme import (
    COLORS,
    set_button_icon,
    set_delete_button_icon,
    set_icon_only_button,
    set_label_icon,
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
        from app.ui.theme import set_label_icon

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
            "includes Salary transactions from that date onward, even for past months."
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


class WorkRrspDetailDialog(GenericDialog):
    def __init__(
        self,
        account: InvestmentAccountSummary,
        parent=None,
        *,
        session_factory=SessionLocal,
    ) -> None:
        current_month = (date.today().year, date.today().month)
        current = get_monthly_work_rrsp_summary(
            account.id, *current_month, session_factory=session_factory
        )
        all_time = get_all_time_work_rrsp_summary(
            account.id, session_factory=session_factory
        )
        history = get_work_rrsp_monthly_history(
            account.id, session_factory=session_factory
        )
        self.current_summary = current
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
        totals.addWidget(QLabel("Current Month"), 0, 1)
        totals.addWidget(QLabel("All Time"), 0, 2)
        for row, (caption, current_amount, all_time_amount) in enumerate((
            (
                "You contributed",
                current.employee_contribution,
                all_time.employee_contribution,
            ),
            ("Employer matched", current.employer_match, all_time.employer_match),
            (
                "Total contributed",
                current.total_contribution,
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
    RECENT_ENTRY_HEIGHT = 72
    VISIBLE_RECENT_ENTRIES = 4
    COMPACT_LAYOUT_WIDTH = 1050
    NARROW_LAYOUT_WIDTH = 760
    ACCOUNT_ACTION_COLUMN_WIDTH = 120

    def __init__(self, session_factory=SessionLocal):
        super().__init__()
        self.session_factory = session_factory
        self.user_id: str | None = None
        self.group_id: int | None = None
        self._accounts: tuple[InvestmentAccountSummary, ...] = ()
        self.setObjectName("investmentsPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.page_scroll = QScrollArea()
        self.page_scroll.setObjectName("investmentsScroll")
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.page_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
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
        content.setMinimumWidth(720)
        content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        self.page_scroll.setWidget(content)

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

        self.summary_grid = QGridLayout()
        self.summary_grid.setSpacing(16)
        self.portfolio_card = SummaryCard(
            "Total Portfolio Value", "fa6s.chart-line"
        )
        self.contribution_card = SummaryCard(
            "Monthly Contributions", "fa6s.coins"
        )
        self.accounts_card = SummaryCard(
            "Investment Accounts", "fa6s.building-columns"
        )
        self.summary_grid.addWidget(self.portfolio_card, 0, 0)
        self.summary_grid.addWidget(self.contribution_card, 0, 1)
        self.summary_grid.addWidget(self.accounts_card, 0, 2)
        for column in range(3):
            self.summary_grid.setColumnStretch(column, 1)
        layout.addLayout(self.summary_grid)

        self.middle_grid = QGridLayout()
        self.middle_grid.setHorizontalSpacing(16)
        self.middle_grid.setVerticalSpacing(16)
        self.chart_card = QFrame()
        self.chart_card.setObjectName("contentCard")
        chart_layout = QVBoxLayout(self.chart_card)
        chart_layout.setContentsMargins(18, 16, 18, 14)
        chart_title = QLabel("Portfolio Value Over Time")
        chart_title.setObjectName("sectionTitle")
        chart_layout.addWidget(chart_title)
        self.chart = PortfolioChart()
        chart_layout.addWidget(self.chart, 1)
        self.middle_grid.addWidget(self.chart_card, 0, 0, 1, 2)
        self.entry_panel = self._build_entry_panel()
        self.middle_grid.addWidget(self.entry_panel, 0, 2)
        self.middle_grid.setColumnStretch(0, 1)
        self.middle_grid.setColumnStretch(1, 1)
        self.middle_grid.setColumnStretch(2, 1)
        layout.addLayout(self.middle_grid, 5)

        self.bottom_grid = QGridLayout()
        self.bottom_grid.setHorizontalSpacing(16)
        self.bottom_grid.setVerticalSpacing(16)
        self.accounts_panel = self._build_accounts_panel()
        self.recent_panel = self._build_recent_panel()
        self.bottom_grid.addWidget(self.accounts_panel, 0, 0, 1, 2)
        self.bottom_grid.addWidget(self.recent_panel, 0, 2)
        self.bottom_grid.setColumnStretch(0, 1)
        self.bottom_grid.setColumnStretch(1, 1)
        self.bottom_grid.setColumnStretch(2, 1)
        layout.addLayout(self.bottom_grid, 5)

        self.work_rrsp_panel = self._build_work_rrsp_panel()
        layout.addWidget(self.work_rrsp_panel)

        self._layout_mode: tuple[bool, bool] | None = None
        self._update_responsive_layout(self.width())

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
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.entry_account = AppComboBox()
        self.entry_date = DatePickerEdit(_qdate(date.today()))
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

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_responsive_layout(event.size().width())

    def _update_responsive_layout(self, width: int) -> None:
        compact = width < self.COMPACT_LAYOUT_WIDTH
        narrow = width < self.NARROW_LAYOUT_WIDTH
        mode = (compact, narrow)
        if mode == self._layout_mode:
            return
        self._layout_mode = mode

        for card in (
            self.portfolio_card,
            self.contribution_card,
            self.accounts_card,
        ):
            self.summary_grid.removeWidget(card)
        if narrow:
            self.summary_grid.setColumnStretch(0, 1)
            self.summary_grid.setColumnStretch(1, 0)
            self.summary_grid.setColumnStretch(2, 0)
            self.summary_grid.addWidget(self.portfolio_card, 0, 0)
            self.summary_grid.addWidget(self.contribution_card, 1, 0)
            self.summary_grid.addWidget(self.accounts_card, 2, 0)
        else:
            for column in range(3):
                self.summary_grid.setColumnStretch(column, 1)
            self.summary_grid.addWidget(self.portfolio_card, 0, 0)
            self.summary_grid.addWidget(self.contribution_card, 0, 1)
            self.summary_grid.addWidget(self.accounts_card, 0, 2)

        self.middle_grid.removeWidget(self.chart_card)
        self.middle_grid.removeWidget(self.entry_panel)
        self.bottom_grid.removeWidget(self.accounts_panel)
        self.bottom_grid.removeWidget(self.recent_panel)
        if compact:
            for grid in (self.middle_grid, self.bottom_grid):
                grid.setColumnStretch(0, 1)
                grid.setColumnStretch(1, 0)
                grid.setColumnStretch(2, 0)
            self.middle_grid.addWidget(self.chart_card, 0, 0)
            self.middle_grid.addWidget(self.entry_panel, 1, 0)
            self.bottom_grid.addWidget(self.accounts_panel, 0, 0)
            self.bottom_grid.addWidget(self.recent_panel, 1, 0)
        else:
            for grid in (self.middle_grid, self.bottom_grid):
                for column in range(3):
                    grid.setColumnStretch(column, 1)
            self.middle_grid.addWidget(self.chart_card, 0, 0, 1, 2)
            self.middle_grid.addWidget(self.entry_panel, 0, 2)
            self.bottom_grid.addWidget(self.accounts_panel, 0, 0, 1, 2)
            self.bottom_grid.addWidget(self.recent_panel, 0, 2)

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

    def _build_work_rrsp_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentCard")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 16, 18, 18)
        panel_layout.setSpacing(12)
        title = QLabel("Work RRSP Contributions")
        title.setObjectName("sectionTitle")
        panel_layout.addWidget(title)
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
    ) -> None:
        self.user_id = user_id
        self.group_id = group_id
        self.period_selector.reset(emit=False)
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
        total_value = get_total_portfolio_value(
            user_id=self.user_id,
            group_id=self.group_id,
            session_factory=self.session_factory,
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
        self._render_work_rrsp_accounts()
        self._render_recent(start_date, history_end)
        self._refresh_entry_accounts()

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
        self._clear_layout(self.work_rrsp_layout)
        self.work_rrsp_empty.show()
        self.work_rrsp_content.hide()
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
            actions.setMinimumWidth(92)
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
        accounts = tuple(
            account for account in self._accounts if account.is_work_related
        )
        self.work_rrsp_empty.setVisible(not accounts)
        self.work_rrsp_content.setVisible(bool(accounts))
        current_month = (date.today().year, date.today().month)
        for account in accounts:
            monthly = get_monthly_work_rrsp_summary(
                account.id, *current_month, session_factory=self.session_factory
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
                month_value = QLabel(f"+{_currency(this_month)} this month")
                month_value.setStyleSheet(
                    f"color: {COLORS['text_dim']}; font-size: 10px;"
                )
                card_layout.addWidget(title)
                card_layout.addWidget(amount)
                card_layout.addWidget(month_value)
                cards.addWidget(card, 0, column)
                cards.setColumnStretch(column, 1)
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

    def _open_work_rrsp_details(
        self, account: InvestmentAccountSummary
    ) -> None:
        WorkRrspDetailDialog(
            account,
            self.window(),
            session_factory=self.session_factory,
        ).exec()

    def _render_recent(self, start_date: date | None, end_date: date | None) -> None:
        self._clear_layout(self.recent_layout)
        entries = get_recent_snapshots(
            user_id=self.user_id,
            group_id=self.group_id,
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
            item.setMinimumHeight(self.RECENT_ENTRY_HEIGHT)
            item_layout = QVBoxLayout(item)
            item_layout.setContentsMargins(10, 7, 10, 7)
            item_layout.setSpacing(2)
            name = QLabel(f"{entry.account_name} — {entry.institution}")
            name.setStyleSheet(f"color: {COLORS['text']}; font-weight: 650;")
            name.setWordWrap(True)
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
            value.setWordWrap(True)
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
