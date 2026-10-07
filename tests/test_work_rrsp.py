import os
import unittest
from datetime import date, datetime
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.dashboard import get_dashboard_data
from database.db import Base
from database.investments import (
    calculate_work_rrsp_for_salary,
    create_investment_account,
    create_investment_snapshot,
    get_account_summaries,
    get_all_time_work_rrsp_summary,
    get_monthly_contribution_summary,
    get_monthly_work_rrsp_summary,
    get_owner_work_rrsp_summary,
    get_total_portfolio_value,
    get_work_rrsp_monthly_history,
    update_investment_account,
)
from database.models import (
    Account,
    Category,
    InvestmentAccount,
    SavingsSnapshot,
    Transaction,
    User,
)
from ui.investments import (
    InvestmentAccountDialog,
    InvestmentsPage,
    WorkRrspDetailDialog,
)
from utils.constants import TransactionType


class WorkRrspFixture:
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.sessions = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        with self.sessions.begin() as session:
            session.add(User(id="owner", name="Owner", color="#123456"))
            salary = Category(name="Salary", color="#10b981")
            other_income = Category(name="Other Income", color="#64748b")
            session.add_all((salary, other_income))
            session.flush()
            bank = Account(
                user_id="owner",
                name="Chequing",
                institution="Test",
                account_type="debit",
            )
            session.add(bank)
            session.flush()
            self.bank_id = bank.id
            self.salary_id = salary.id
            self.other_income_id = other_income.id

        self.work_id = create_investment_account(
            "Canada Life",
            "Work RRSP",
            account_type="RRSP",
            user_id="owner",
            is_work_related=True,
            auto_track_from_payroll=True,
            employee_contribution_percent="5",
            employer_matching_enabled=True,
            employer_match_percent="50",
            session_factory=self.sessions,
        )
        self.personal_id = create_investment_account(
            "Bank",
            "Personal RRSP",
            account_type="RRSP",
            user_id="owner",
            session_factory=self.sessions,
        )
        # Most service tests exercise historical fixtures. Individual start-date
        # tests override this value explicitly.
        with self.sessions.begin() as session:
            session.get(InvestmentAccount, self.work_id).created_at = datetime(
                2026, 1, 1
            )

    def tearDown(self):
        self.engine.dispose()

    def add_transaction(
        self,
        day,
        amount,
        transaction_type=TransactionType.INCOME,
        category="salary",
    ):
        category_id = {
            "salary": self.salary_id,
            "other": self.other_income_id,
            None: None,
        }[category]
        with self.sessions.begin() as session:
            session.add(Transaction(
                account_id=self.bank_id,
                transaction_date=day,
                description="Imported transaction",
                amount=Decimal(amount),
                transaction_type=transaction_type,
                category_id=category_id,
            ))


class WorkRrspServiceTest(WorkRrspFixture, unittest.TestCase):
    def test_personal_rrsp_does_not_auto_track_payroll(self):
        self.add_transaction(date(2026, 8, 1), "950")
        summary = get_monthly_work_rrsp_summary(
            self.personal_id, 2026, 8, session_factory=self.sessions
        )
        self.assertEqual(summary.salary_count, 0)
        self.assertEqual(summary.total_contribution, Decimal("0.00"))

    def test_salary_reversal_and_employer_match_formula(self):
        result = calculate_work_rrsp_for_salary("950", "5", "50")
        self.assertEqual(result.pre_rrsp_take_home, Decimal("1000.00"))
        self.assertEqual(result.employee_contribution, Decimal("50.00"))
        self.assertEqual(result.employer_match, Decimal("25.00"))
        self.assertEqual(result.total_contribution, Decimal("75.00"))

    def test_employee_rate_must_be_below_100_and_full_match_is_allowed(self):
        with self.assertRaisesRegex(ValueError, "less than 100"):
            calculate_work_rrsp_for_salary("950", "100", "50")
        result = calculate_work_rrsp_for_salary("950", "5", "100")
        self.assertEqual(result.employee_contribution, Decimal("50.00"))
        self.assertEqual(result.employer_match, Decimal("50.00"))

    def test_multiple_salary_transactions_aggregate_independently(self):
        self.add_transaction(date(2026, 8, 1), "950")
        self.add_transaction(date(2026, 8, 15), "1900")
        summary = get_monthly_work_rrsp_summary(
            self.work_id, 2026, 8, session_factory=self.sessions
        )
        self.assertEqual(summary.salary_count, 2)
        self.assertEqual(summary.deposited_salary_total, Decimal("2850.00"))
        self.assertEqual(summary.pre_rrsp_take_home_total, Decimal("3000.00"))
        self.assertEqual(summary.employee_contribution, Decimal("150.00"))
        self.assertEqual(summary.employer_match, Decimal("75.00"))
        self.assertEqual(summary.total_contribution, Decimal("225.00"))

    def test_salary_before_account_creation_date_is_ignored(self):
        with self.sessions.begin() as session:
            session.get(InvestmentAccount, self.work_id).created_at = datetime(
                2026, 8, 10, 14, 30
            )
        self.add_transaction(date(2026, 8, 9), "950")
        self.add_transaction(date(2026, 8, 10), "950")
        self.add_transaction(date(2026, 8, 20), "950")
        summary = get_monthly_work_rrsp_summary(
            self.work_id, 2026, 8, session_factory=self.sessions
        )
        self.assertEqual(summary.salary_count, 2)
        self.assertEqual(summary.employee_contribution, Decimal("100.00"))

    def test_other_income_and_e_transfer_are_ignored(self):
        self.add_transaction(date(2026, 8, 1), "950")
        self.add_transaction(date(2026, 8, 2), "1000", category="other")
        self.add_transaction(
            date(2026, 8, 3),
            "1000",
            transaction_type=TransactionType.E_TRANSFER,
        )
        summary = get_monthly_work_rrsp_summary(
            self.work_id, 2026, 8, session_factory=self.sessions
        )
        self.assertEqual(summary.salary_count, 1)
        self.assertEqual(summary.employee_contribution, Decimal("50.00"))

    def test_contribution_history_groups_by_month(self):
        self.add_transaction(date(2026, 7, 15), "950")
        self.add_transaction(date(2026, 8, 1), "950")
        self.add_transaction(date(2026, 8, 15), "950")
        history = get_work_rrsp_monthly_history(
            self.work_id, session_factory=self.sessions
        )
        self.assertEqual([(item.year, item.month) for item in history], [
            (2026, 8),
            (2026, 7),
        ])
        self.assertEqual(
            history[0].summary.employee_contribution, Decimal("100.00")
        )
        self.assertEqual(history[1].summary.employer_match, Decimal("25.00"))

    def test_multiple_work_accounts_use_their_own_rates(self):
        self.add_transaction(date(2026, 8, 1), "950")
        second_work_id = create_investment_account(
            "Second",
            "Second Work RRSP",
            account_type="RRSP",
            user_id="owner",
            is_work_related=True,
            auto_track_from_payroll=True,
            employee_contribution_percent="10",
            employer_matching_enabled=False,
            session_factory=self.sessions,
        )
        with self.sessions.begin() as session:
            session.get(InvestmentAccount, second_work_id).created_at = datetime(
                2026, 1, 1
            )
        summary = get_owner_work_rrsp_summary(
            2026, 8, user_id="owner", session_factory=self.sessions
        )
        self.assertEqual(summary.salary_count, 2)
        self.assertEqual(summary.employee_contribution, Decimal("155.56"))
        self.assertEqual(summary.employer_match, Decimal("25.00"))

    def test_snapshot_controls_current_value_and_total_portfolio_value(self):
        create_investment_snapshot(
            self.work_id,
            date(2026, 8, 31),
            "4120",
            session_factory=self.sessions,
        )
        create_investment_snapshot(
            self.personal_id,
            date(2026, 8, 31),
            "1000",
            session_factory=self.sessions,
        )
        self.add_transaction(date(2026, 8, 1), "950")
        summaries = {
            item.id: item
            for item in get_account_summaries(
                user_id="owner", session_factory=self.sessions
            )
        }
        self.assertEqual(summaries[self.work_id].current_value, Decimal("4120.00"))
        self.assertEqual(
            get_total_portfolio_value(
                user_id="owner", session_factory=self.sessions
            ),
            Decimal("5120.00"),
        )

    def test_dashboard_savings_and_investment_breakdowns(self):
        self.add_transaction(date(2026, 8, 1), "950")
        create_investment_snapshot(
            self.personal_id,
            date(2026, 8, 31),
            "1000",
            "800",
            session_factory=self.sessions,
        )
        with self.sessions.begin() as session:
            session.add(SavingsSnapshot(
                user_id="owner",
                snapshot_date=date(2026, 8, 31),
                amount_saved_this_month=Decimal("1000"),
            ))
        data = get_dashboard_data("owner", "monthly", (2026, 8), self.sessions)
        self.assertEqual(data.cash_savings_actual, Decimal("1000.00"))
        self.assertEqual(data.work_rrsp_employee, Decimal("50.00"))
        self.assertEqual(data.savings_actual, Decimal("1025.00"))
        self.assertEqual(data.employer_rrsp_match, Decimal("25.00"))
        self.assertEqual(data.manual_investing_total, Decimal("800.00"))
        self.assertEqual(data.investing_total, Decimal("875.00"))
        self.assertEqual(data.total_spending, Decimal("0"))
        self.assertEqual(data.total_income, Decimal("950.00"))

    def test_editing_rates_recalculates_without_changing_transactions(self):
        self.add_transaction(date(2026, 8, 1), "950")
        with self.sessions() as session:
            before = tuple(session.execute(
                select(Transaction.id, Transaction.amount)
            ).all())
        update_investment_account(
            self.work_id,
            institution="Canada Life",
            account_name="Work RRSP",
            account_type="RRSP",
            is_work_related=True,
            auto_track_from_payroll=True,
            employee_contribution_percent="10",
            employer_matching_enabled=False,
            session_factory=self.sessions,
        )
        summary = get_all_time_work_rrsp_summary(
            self.work_id, session_factory=self.sessions
        )
        with self.sessions() as session:
            after = tuple(session.execute(
                select(Transaction.id, Transaction.amount)
            ).all())
        self.assertEqual(summary.employee_contribution, Decimal("105.56"))
        self.assertEqual(before, after)
        self.assertEqual(len(after), 1)

    def test_personal_accounts_and_manual_contributions_remain_unaffected(self):
        create_investment_snapshot(
            self.personal_id,
            date(2026, 8, 31),
            "1000",
            "200",
            session_factory=self.sessions,
        )
        contribution = get_monthly_contribution_summary(
            2026, 8, user_id="owner", session_factory=self.sessions
        )
        self.assertEqual(contribution.manual, Decimal("200.00"))
        self.assertEqual(contribution.work_rrsp_employee, Decimal("0.00"))
        self.assertEqual(contribution.total, Decimal("200.00"))


class WorkRrspUiTest(WorkRrspFixture, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_add_dialog_reveals_work_controls_only_for_rrsp(self):
        dialog = InvestmentAccountDialog()
        self.assertEqual(dialog.account_type.currentText(), "General Investment")
        self.assertEqual(dialog.selected_account_type(), "General")
        self.assertEqual(
            [dialog.account_type.itemText(index) for index in range(
                dialog.account_type.count()
            )],
            ["General Investment", "TFSA", "FHSA", "RRSP"],
        )
        self.assertFalse(dialog.work_related.isVisible())
        dialog.account_type.setCurrentText("RRSP")
        dialog.show()
        self.app.processEvents()
        self.assertFalse(dialog.work_related.isHidden())
        dialog.work_related.setChecked(True)
        self.assertFalse(dialog.work_section.isHidden())
        settings = dialog.work_settings()
        self.assertTrue(settings["is_work_related"])
        self.assertTrue(settings["auto_track_from_payroll"])
        self.assertNotIn(".0000", dialog.employee_percent.text())
        self.assertNotIn(".0000", dialog.employer_match_percent.text())
        dialog.employee_percent.setValue(5.25)
        self.assertIn("5.25", dialog.employee_percent.text())
        dialog.close()

    def test_account_dialog_scrollbar_only_appears_when_content_needs_it(self):
        dialog = InvestmentAccountDialog()
        dialog.resize(660, 700)
        dialog.show()
        self.app.processEvents()
        self.assertEqual(dialog.scroll.verticalScrollBar().maximum(), 0)

        dialog.account_type.setCurrentText("RRSP")
        dialog.work_related.setChecked(True)
        self.app.processEvents()
        self.assertGreater(dialog.scroll.verticalScrollBar().maximum(), 0)

        dialog.resize(700, 1050)
        self.app.processEvents()
        self.assertEqual(dialog.scroll.verticalScrollBar().maximum(), 0)
        dialog.close()

    def test_detail_dialog_receives_monthly_all_time_and_history_totals(self):
        today = date.today()
        self.add_transaction(date(today.year, today.month, 1), "950")
        self.add_transaction(
            date(today.year - (today.month == 1), (today.month - 2) % 12 + 1, 1),
            "950",
        )
        account = next(
            item for item in get_account_summaries(
                user_id="owner", session_factory=self.sessions
            )
            if item.id == self.work_id
        )
        dialog = WorkRrspDetailDialog(
            account, session_factory=self.sessions
        )
        self.assertEqual(
            dialog.current_summary.total_contribution, Decimal("75.00")
        )
        self.assertEqual(
            dialog.all_time_summary.total_contribution, Decimal("150.00")
        )
        self.assertEqual(dialog.history_table.rowCount(), 2)
        dialog.close()

    def test_investments_page_keeps_generic_table_and_adds_work_summary(self):
        today = date.today()
        self.add_transaction(date(today.year, today.month, 1), "950")
        page = InvestmentsPage(session_factory=self.sessions)
        page.set_user_id("owner")
        headers = [
            page.accounts_table.horizontalHeaderItem(column).text()
            for column in range(page.accounts_table.columnCount())
        ]
        self.assertEqual(headers, [
            "Account",
            "Institution",
            "Account #",
            "Current Value",
            "Last Updated",
            "Action",
        ])
        self.assertEqual(page.work_rrsp_layout.count(), 1)
        self.assertTrue(page.work_rrsp_empty.isHidden())
        page.close()


if __name__ == "__main__":
    unittest.main()
