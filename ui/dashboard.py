from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from database.dashboard import get_dashboard_data
from database.db import SessionLocal
from database.transactions import get_transaction_months
from parsers.generic_parser import GenericParser
from ui.components.dashboard_cards import (
    BudgetGoalsCard,
    CategoryCard,
    InvestingCard,
    MetricCard,
    SavingsCard,
)
from ui.components.file_upload_dialog import FileUploadDialog
from ui.components.page_header import PageHeader
from ui.components.period_selector import PeriodSelector
from ui.theme import set_button_icon
from utils.constants import ADD_STATMENT_LABEL


class DashboardPage(QWidget):
    def __init__(self, session_factory=SessionLocal):
        super().__init__()
        self.session_factory = session_factory
        self.user_id: str | None = None
        self.group_id: int | None = None
        self.setObjectName("dashboardPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(18)

        self.files_to_parse = []
        add_files_button = QPushButton(ADD_STATMENT_LABEL)
        self.add_files_button = add_files_button
        add_files_button.setObjectName("primaryButton")
        set_button_icon(
            add_files_button,
            "fa6s.plus",
            color="#ffffff",
            active_color="#ffffff",
        )
        add_files_button.clicked.connect(self.open_file_selection)
        layout.addWidget(PageHeader("Dashboard", action_button=add_files_button))

        self.period_selector = PeriodSelector()
        self.period_selector.selection_changed.connect(self._period_changed)
        layout.addWidget(self.period_selector)

        cards = QWidget()
        cards.setObjectName("dashboardCards")
        cards.setMinimumHeight(545)
        cards_layout = QGridLayout(cards)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setHorizontalSpacing(16)
        cards_layout.setVerticalSpacing(16)

        self.income_card = MetricCard(
            "Income", "fa6s.briefcase", "#18d98b", False
        )
        self.spending_card = MetricCard(
            "Spending", "fa6s.credit-card", "#ff5b63", True
        )
        self.savings_card = SavingsCard()
        self.category_card = CategoryCard()
        self.budget_card = BudgetGoalsCard()
        self.investing_card = InvestingCard()

        cards_layout.addWidget(self.income_card, 0, 0)
        cards_layout.addWidget(self.spending_card, 0, 1)
        cards_layout.addWidget(self.savings_card, 0, 2)
        cards_layout.addWidget(self.category_card, 1, 0)
        cards_layout.addWidget(self.budget_card, 1, 1)
        cards_layout.addWidget(self.investing_card, 1, 2)
        for column in range(3):
            cards_layout.setColumnStretch(column, 1)
        cards_layout.setRowStretch(0, 1)
        cards_layout.setRowStretch(1, 1)

        scroll = QScrollArea()
        scroll.setObjectName("dashboardScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(cards)
        scroll.setStyleSheet("""
            QScrollArea#dashboardScroll { background: transparent; border: none; }
            QScrollArea#dashboardScroll > QWidget > QWidget { background: transparent; }
            QScrollBar:vertical { background: #15171a; width: 8px; }
            QScrollBar::handle:vertical {
                background: #4d535b;
                border-radius: 4px;
                min-height: 28px;
            }
        """)
        layout.addWidget(scroll, 1)

    @property
    def period_filter(self) -> str:
        return self.period_selector.period

    @property
    def selected_month(self) -> tuple[int, int]:
        return self.period_selector.selected_month

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
        self.add_files_button.setEnabled(user_id is not None)
        self.add_files_button.setToolTip(
            "" if user_id is not None else "Switch to a user to import statements"
        )
        self.period_selector.reset(emit=False)
        self.reload()

    def reload(self) -> None:
        self.period_selector.set_available_months(
            get_transaction_months(
                self.user_id,
                self.session_factory,
                group_id=self.group_id,
            )
        )
        self._load_dashboard_data()

    def _period_changed(
        self,
        period: str,
        selected_month: tuple[int, int],
    ) -> None:
        self._load_dashboard_data()

    def _load_dashboard_data(self) -> None:
        data = get_dashboard_data(
            self.user_id,
            self.period_filter,
            self.selected_month,
            self.session_factory,
            group_id=self.group_id,
        )
        self.income_card.set_data(
            data.period_label,
            "Total income",
            data.total_income,
            data.previous_income,
            (
                ("Regular income", data.regular_income),
                ("Other income", data.other_income),
                ("Positive e-transfers", data.e_transfer_income_adjustment),
            ),
            data.cash_flow_income,
        )
        self.spending_card.set_data(
            data.period_label,
            "Total spending (after adjustments)",
            data.total_spending,
            data.previous_spending,
            tuple(
                (item.name, item.amount)
                for item in data.account_spending
            ) + (
                ("Refunds / reimbursements", -data.reimbursements),
                ("Net negative e-transfers", data.e_transfer_spending_adjustment),
            ),
            data.cash_flow_spending,
        )
        self.savings_card.set_data(
            data.period_label,
            data.savings_goal,
            data.savings_actual,
            data.savings_balance,
            data.cash_savings_actual,
            data.work_rrsp_employee,
            data.employer_rrsp_match,
        )
        self.category_card.set_data(data.period_label, data.category_spending)
        self.budget_card.set_data(data.period_label, data.budget_progress)
        self.investing_card.set_data(
            data.period_label,
            data.investing_total,
            data.portfolio_value,
            data.portfolio_baseline_value,
            data.investment_month_labels,
            data.investment_value_series,
            data.manual_investing_total,
            data.work_rrsp_employee,
            data.employer_rrsp_match,
        )

    def open_file_selection(self):
        if self.user_id is None:
            return
        dialog = FileUploadDialog(self.window())
        dialog.submitted.connect(lambda: self._parse_selected_files(dialog))
        dialog.exec()

    def _parse_selected_files(self, dialog: FileUploadDialog) -> None:
        file_data = dialog.get_file_parse_types()
        if not file_data:
            dialog.file_selection.show_general_error("Select at least one file")
            return

        try:
            start_date, end_date = dialog.get_date_range()
        except ValueError as exc:
            dialog.file_selection.show_general_error(str(exc))
            return

        parser = GenericParser(
            file_data,
            self.user_id,
            start_date=start_date,
            end_date=end_date,
        )
        parser.parse()
        errors = parser.get_results()

        if errors:
            dialog.show_errors(errors)
            return

        self.files_to_parse = dialog.get_files()
        self.window().transactions_page.reload()
        self.reload()
        dialog.accept()
