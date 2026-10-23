import os
import unittest
from datetime import date
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.services.investments as investment_services
from app.core.db import Base
from app.models.models import Account, Category, Transaction, User, WorkRRSPContribution
from app.services.dashboard import get_dashboard_data
from app.services.goals import get_monthly_savings_breakdown
from app.services.investments import (
    calculate_employer_match,
    create_investment_account,
    create_investment_snapshot,
    create_work_rrsp_contribution,
    delete_work_rrsp_contribution,
    get_account_current_value,
    get_account_history,
    get_account_summaries,
    get_all_time_work_rrsp_summary,
    get_monthly_contribution_summary,
    get_monthly_work_rrsp_summary,
    get_owner_work_rrsp_summary,
    get_total_portfolio_value,
    get_work_rrsp_contribution_history,
    update_investment_account,
    update_work_rrsp_contribution,
)
from app.ui.pages.investments import (
    InvestmentAccountDialog,
    InvestmentsPage,
    WorkRrspContributionDialog,
    WorkRrspDetailDialog,
)
from app.utils.constants import TransactionType


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
            spending = Category(name="Food", color="#ef4444")
            session.add_all((salary, spending))
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
            self.spending_id = spending.id

        self.work_id = create_investment_account(
            "Canada Life",
            "Work RRSP",
            account_type="RRSP",
            user_id="owner",
            is_work_related=True,
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

    def tearDown(self):
        self.engine.dispose()

    def add_transaction(self, day, amount, transaction_type, category_id):
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
    def test_create_contribution_calculates_and_saves_match_snapshot(self):
        contribution_id = create_work_rrsp_contribution(
            self.work_id, date(2026, 9, 15), "300", session_factory=self.sessions
        )
        with self.sessions() as session:
            row = session.get(WorkRRSPContribution, contribution_id)
            self.assertEqual(row.employee_contribution, Decimal("300.00"))
            self.assertEqual(row.employer_match, Decimal("150.00"))
            self.assertEqual(row.total_contribution, Decimal("450.00"))
            self.assertEqual((row.year, row.month), (2026, 9))

    def test_calculate_employer_match_allows_fifty_and_one_hundred_percent(self):
        self.assertEqual(calculate_employer_match("300", "50"), Decimal("150.00"))
        self.assertEqual(calculate_employer_match("300", "100"), Decimal("300.00"))

    def test_matching_disabled_saves_zero_match(self):
        update_investment_account(
            self.work_id,
            institution="Canada Life",
            account_name="Work RRSP",
            account_type="RRSP",
            is_work_related=True,
            employer_matching_enabled=False,
            session_factory=self.sessions,
        )
        contribution_id = create_work_rrsp_contribution(
            self.work_id, date(2026, 9, 15), "300", session_factory=self.sessions
        )
        with self.sessions() as session:
            row = session.get(WorkRRSPContribution, contribution_id)
            self.assertEqual(row.employer_match, Decimal("0.00"))
            self.assertEqual(row.total_contribution, Decimal("300.00"))

    def test_multiple_entries_in_same_month_aggregate(self):
        create_work_rrsp_contribution(
            self.work_id, date(2026, 9, 15), "150", session_factory=self.sessions
        )
        create_work_rrsp_contribution(
            self.work_id, date(2026, 9, 30), "150", session_factory=self.sessions
        )
        summary = get_monthly_work_rrsp_summary(
            self.work_id, 2026, 9, session_factory=self.sessions
        )
        self.assertEqual(summary.contribution_count, 2)
        self.assertEqual(summary.employee_contribution, Decimal("300.00"))
        self.assertEqual(summary.employer_match, Decimal("150.00"))
        self.assertEqual(summary.total_contribution, Decimal("450.00"))

    def test_different_months_and_all_time_aggregate_separately(self):
        create_work_rrsp_contribution(
            self.work_id, date(2026, 8, 31), "100", session_factory=self.sessions
        )
        create_work_rrsp_contribution(
            self.work_id, date(2026, 9, 15), "200", session_factory=self.sessions
        )
        august = get_monthly_work_rrsp_summary(
            self.work_id, 2026, 8, session_factory=self.sessions
        )
        september = get_monthly_work_rrsp_summary(
            self.work_id, 2026, 9, session_factory=self.sessions
        )
        all_time = get_all_time_work_rrsp_summary(
            self.work_id, session_factory=self.sessions
        )
        self.assertEqual(august.total_contribution, Decimal("150.00"))
        self.assertEqual(september.total_contribution, Decimal("300.00"))
        self.assertEqual(all_time.total_contribution, Decimal("450.00"))

    def test_history_contains_each_paycheque_not_monthly_synthetic_rows(self):
        first = create_work_rrsp_contribution(
            self.work_id, date(2026, 9, 15), "150", session_factory=self.sessions
        )
        second = create_work_rrsp_contribution(
            self.work_id, date(2026, 9, 30), "150", session_factory=self.sessions
        )
        history = get_work_rrsp_contribution_history(
            self.work_id, session_factory=self.sessions
        )
        self.assertEqual([item.id for item in history], [second, first])

    def test_editing_contribution_updates_summary(self):
        contribution_id = create_work_rrsp_contribution(
            self.work_id, date(2026, 9, 15), "100", session_factory=self.sessions
        )
        update_work_rrsp_contribution(
            contribution_id,
            date(2026, 10, 1),
            "300",
            session_factory=self.sessions,
        )
        september = get_monthly_work_rrsp_summary(
            self.work_id, 2026, 9, session_factory=self.sessions
        )
        october = get_monthly_work_rrsp_summary(
            self.work_id, 2026, 10, session_factory=self.sessions
        )
        self.assertEqual(september.total_contribution, Decimal("0.00"))
        self.assertEqual(october.total_contribution, Decimal("450.00"))

    def test_deleting_contribution_updates_summary_only(self):
        create_investment_snapshot(
            self.work_id, date(2026, 9, 30), "2500", session_factory=self.sessions
        )
        contribution_id = create_work_rrsp_contribution(
            self.work_id, date(2026, 9, 15), "300", session_factory=self.sessions
        )
        delete_work_rrsp_contribution(contribution_id, session_factory=self.sessions)
        summary = get_monthly_work_rrsp_summary(
            self.work_id, 2026, 9, session_factory=self.sessions
        )
        self.assertEqual(summary.total_contribution, Decimal("0.00"))
        self.assertEqual(
            get_account_current_value(self.work_id, session_factory=self.sessions),
            Decimal("2500.00"),
        )

    def test_saved_match_is_not_recalculated_when_plan_changes(self):
        create_work_rrsp_contribution(
            self.work_id, date(2026, 9, 15), "300", session_factory=self.sessions
        )
        update_investment_account(
            self.work_id,
            institution="Canada Life",
            account_name="Work RRSP",
            account_type="RRSP",
            is_work_related=True,
            employer_matching_enabled=True,
            employer_match_percent="100",
            session_factory=self.sessions,
        )
        summary = get_all_time_work_rrsp_summary(
            self.work_id, session_factory=self.sessions
        )
        self.assertEqual(summary.employer_match, Decimal("150.00"))

    def test_salary_transactions_do_not_affect_rrsp_totals(self):
        self.add_transaction(
            date(2026, 9, 1), "950", TransactionType.INCOME, self.salary_id
        )
        summary = get_owner_work_rrsp_summary(
            2026, 9, user_id="owner", session_factory=self.sessions
        )
        self.assertEqual(summary.contribution_count, 0)
        self.assertEqual(summary.total_contribution, Decimal("0.00"))

    def test_dashboard_and_goals_use_saved_contributions(self):
        self.add_transaction(
            date(2026, 9, 1), "1000", TransactionType.INCOME, self.salary_id
        )
        self.add_transaction(
            date(2026, 9, 2), "-400", TransactionType.EXPENSE, self.spending_id
        )
        create_work_rrsp_contribution(
            self.work_id, date(2026, 9, 15), "300", session_factory=self.sessions
        )
        dashboard = get_dashboard_data(
            "owner", "monthly", (2026, 9), self.sessions
        )
        goals = get_monthly_savings_breakdown(
            2026, 9, user_id="owner", session_factory=self.sessions
        )
        self.assertEqual(dashboard.work_rrsp_employee, Decimal("300.00"))
        self.assertEqual(dashboard.employer_rrsp_match, Decimal("150.00"))
        self.assertEqual(dashboard.savings_actual, Decimal("1050.00"))
        self.assertEqual(goals.net_savings, Decimal("1050.00"))

    def test_manual_portfolio_contribution_is_separate_and_not_double_counted(self):
        create_investment_snapshot(
            self.personal_id,
            date(2026, 9, 30),
            "1000",
            "800",
            session_factory=self.sessions,
        )
        create_work_rrsp_contribution(
            self.work_id, date(2026, 9, 15), "300", session_factory=self.sessions
        )
        summary = get_monthly_contribution_summary(
            2026, 9, user_id="owner", session_factory=self.sessions
        )
        self.assertEqual(summary.manual, Decimal("800.00"))
        self.assertEqual(summary.work_rrsp_employee, Decimal("300.00"))
        self.assertEqual(summary.work_rrsp_employer, Decimal("150.00"))
        self.assertEqual(summary.total, Decimal("1250.00"))

    def test_portfolio_value_and_history_come_only_from_snapshots(self):
        create_investment_snapshot(
            self.work_id, date(2026, 9, 30), "2500", session_factory=self.sessions
        )
        create_work_rrsp_contribution(
            self.work_id, date(2026, 10, 1), "300", session_factory=self.sessions
        )
        self.assertEqual(
            get_account_current_value(self.work_id, session_factory=self.sessions),
            Decimal("2500.00"),
        )
        self.assertEqual(
            get_total_portfolio_value(user_id="owner", session_factory=self.sessions),
            Decimal("2500.00"),
        )
        history = get_account_history(self.work_id, session_factory=self.sessions)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].total_value, Decimal("2500.00"))

    def test_personal_rrsp_rejects_work_contribution(self):
        with self.assertRaisesRegex(ValueError, "Work RRSP"):
            create_work_rrsp_contribution(
                self.personal_id,
                date(2026, 9, 15),
                "300",
                session_factory=self.sessions,
            )

    def test_old_salary_reverse_engineering_function_is_removed(self):
        self.assertFalse(hasattr(investment_services, "calculate_work_rrsp_for_salary"))


class WorkRrspUiTest(WorkRrspFixture, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _work_account(self):
        return next(
            item
            for item in get_account_summaries(
                user_id="owner", session_factory=self.sessions
            )
            if item.id == self.work_id
        )

    def test_account_dialog_has_matching_but_no_obsolete_auto_fields(self):
        dialog = InvestmentAccountDialog()
        dialog.account_type.setCurrentText("RRSP")
        dialog.work_related.setChecked(True)
        settings = dialog.work_settings()
        self.assertTrue(settings["is_work_related"])
        self.assertIn("employer_matching_enabled", settings)
        self.assertFalse(hasattr(dialog, "employee_percent"))
        self.assertFalse(hasattr(dialog, "auto_track"))
        labels = " ".join(child.text() for child in dialog.findChildren(QLabel))
        self.assertNotIn("Salary transactions", labels)
        dialog.close()

    def test_contribution_dialog_updates_match_live(self):
        dialog = WorkRrspContributionDialog(
            (self._work_account(),), session_factory=self.sessions
        )
        dialog.employee_contribution.setText("300")
        self.app.processEvents()
        self.assertEqual(dialog.match_amount_label.text(), "$150.00")
        self.assertEqual(dialog.total_amount_label.text(), "$450.00")
        dialog.close()

    def test_detail_dialog_empty_state_and_individual_history_rows(self):
        account = self._work_account()
        empty_dialog = WorkRrspDetailDialog(account, session_factory=self.sessions)
        self.assertEqual(empty_dialog.history_table.rowCount(), 0)
        self.assertFalse(empty_dialog.history_empty.isHidden())
        empty_dialog.close()
        create_work_rrsp_contribution(
            self.work_id, date.today(), "300", session_factory=self.sessions
        )
        dialog = WorkRrspDetailDialog(account, session_factory=self.sessions)
        self.assertEqual(dialog.history_table.rowCount(), 1)
        self.assertEqual(dialog.history_table.columnCount(), 5)
        dialog.close()

    def test_investments_page_shows_only_work_rrsp_contribution_block(self):
        page = InvestmentsPage(session_factory=self.sessions)
        page.set_user_id("owner")
        self.assertEqual(page.work_rrsp_layout.count(), 1)
        self.assertTrue(page.work_rrsp_empty.isHidden())
        page.close()


if __name__ == "__main__":
    unittest.main()
