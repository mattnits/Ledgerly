import unittest
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models.models import (
    Account,
    Category,
    InvestmentAccount,
    InvestmentSnapshot,
    Transaction,
    User,
)
from app.services.dashboard import get_dashboard_data
from app.services.investments import (
    get_account_summaries,
    get_owner_work_rrsp_summary,
)
from app.services.summary_cache import clear_summary_cache
from app.services.transactions import TransactionQueryParams, fetch_transactions
from app.utils.constants import TransactionType


class PerformanceArchitectureTest(unittest.TestCase):
    def setUp(self):
        clear_summary_cache()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions.begin() as session:
            user = User(id="user", name="User", color="#123456")
            salary = Category(name="Salary", color="#10b981")
            food = Category(name="Food", color="#f97316")
            session.add_all((user, salary, food))
            session.flush()
            account = Account(
                user_id=user.id,
                name="Checking",
                institution="Test",
                account_type="debit",
            )
            session.add(account)
            session.flush()
            session.add_all((
                Transaction(
                    account_id=account.id,
                    category_id=salary.id,
                    transaction_date=date(2026, 7, 15),
                    description="July salary",
                    amount=Decimal("900.00"),
                    transaction_type=TransactionType.INCOME,
                ),
                Transaction(
                    account_id=account.id,
                    category_id=salary.id,
                    transaction_date=date(2026, 8, 15),
                    description="August salary",
                    amount=Decimal("1000.00"),
                    transaction_type=TransactionType.INCOME,
                ),
                Transaction(
                    account_id=account.id,
                    category_id=food.id,
                    transaction_date=date(2026, 8, 16),
                    description="Groceries",
                    amount=Decimal("-25.00"),
                    transaction_type=TransactionType.EXPENSE,
                ),
            ))
            investment = InvestmentAccount(
                user_id=user.id,
                institution="Broker",
                account_name="Portfolio",
            )
            session.add(investment)
            session.flush()
            session.add_all((
                InvestmentSnapshot(
                    investment_account_id=investment.id,
                    snapshot_datetime=datetime(2026, 7, 31),
                    total_value=Decimal("100.00"),
                ),
                InvestmentSnapshot(
                    investment_account_id=investment.id,
                    snapshot_datetime=datetime(2026, 8, 31),
                    total_value=Decimal("125.00"),
                ),
            ))

    def tearDown(self):
        clear_summary_cache()
        self.engine.dispose()

    def _capture_statements(self, operation):
        statements = []

        def capture(_connection, _cursor, statement, parameters, _context, _many):
            statements.append((statement, parameters))

        event.listen(self.engine, "before_cursor_execute", capture)
        try:
            result = operation()
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)
        return result, statements

    def test_dashboard_month_query_uses_half_open_sql_date_range(self):
        result, statements = self._capture_statements(lambda: get_dashboard_data(
            "user", "monthly", (2026, 8), self.sessions
        ))

        aggregate_sql = next(
            statement
            for statement, _parameters in statements
            if "sum(CASE" in statement and "FROM transactions" in statement
        )
        self.assertIn("transactions.transaction_date >=", aggregate_sql)
        self.assertIn("transactions.transaction_date <", aggregate_sql)
        self.assertEqual(result.total_income, Decimal("1000.00"))
        self.assertEqual(result.total_spending, Decimal("25.00"))
        self.assertEqual(result.previous_income, Decimal("900.00"))

    def test_dashboard_cache_hits_and_invalidates_after_commit(self):
        first, first_statements = self._capture_statements(lambda: get_dashboard_data(
            "user", "monthly", (2026, 8), self.sessions
        ))
        second, second_statements = self._capture_statements(lambda: get_dashboard_data(
            "user", "monthly", (2026, 8), self.sessions
        ))
        self.assertGreater(len(first_statements), 0)
        self.assertEqual(second_statements, [])
        self.assertIs(first, second)

        with self.sessions.begin() as session:
            account_id = session.query(Account.id).filter_by(user_id="user").scalar()
            food_id = session.query(Category.id).filter_by(name="Food").scalar()
            session.add(Transaction(
                account_id=account_id,
                category_id=food_id,
                transaction_date=date(2026, 8, 20),
                description="More groceries",
                amount=Decimal("-5.00"),
                transaction_type=TransactionType.EXPENSE,
            ))

        refreshed, refreshed_statements = self._capture_statements(
            lambda: get_dashboard_data(
                "user", "monthly", (2026, 8), self.sessions
            )
        )
        self.assertGreater(len(refreshed_statements), 0)
        self.assertEqual(refreshed.total_spending, Decimal("30.00"))

    def test_latest_investment_values_are_loaded_with_one_query(self):
        accounts, statements = self._capture_statements(lambda: get_account_summaries(
            user_id="user", session_factory=self.sessions
        ))

        self.assertEqual(len(statements), 1)
        self.assertEqual(accounts[0].current_value, Decimal("125.00"))
        self.assertEqual(accounts[0].last_updated, datetime(2026, 8, 31))

    def test_multiple_work_accounts_share_one_salary_query(self):
        with self.sessions.begin() as session:
            session.add_all((
                InvestmentAccount(
                    user_id="user",
                    institution="Employer One",
                    account_name="Work RRSP One",
                    account_type="RRSP",
                    is_work_related=True,
                    auto_track_from_payroll=True,
                    employee_contribution_percent=Decimal("5.00"),
                    created_at=datetime(2026, 1, 1),
                ),
                InvestmentAccount(
                    user_id="user",
                    institution="Employer Two",
                    account_name="Work RRSP Two",
                    account_type="RRSP",
                    is_work_related=True,
                    auto_track_from_payroll=True,
                    employee_contribution_percent=Decimal("3.00"),
                    created_at=datetime(2026, 1, 1),
                ),
            ))

        summary, statements = self._capture_statements(
            lambda: get_owner_work_rrsp_summary(
                2026,
                8,
                user_id="user",
                session_factory=self.sessions,
            )
        )

        self.assertEqual(len(statements), 2)
        self.assertEqual(summary.salary_count, 2)

    def test_unfiltered_transaction_page_avoids_duplicate_count_query(self):
        result, statements = self._capture_statements(lambda: fetch_transactions(
            TransactionQueryParams(
                user_id="user",
                selected_month=(2026, 8),
                limit=1,
            ),
            self.sessions,
        ))

        count_statements = [
            statement for statement, _parameters in statements
            if "count(" in statement.casefold()
        ]
        self.assertEqual(len(count_statements), 1)
        self.assertEqual(len(result.rows), 1)
        self.assertEqual(result.total_count, 2)
        self.assertEqual(result.filtered_count, 2)

    def test_month_query_plan_uses_scope_and_date_indexes(self):
        with self.engine.connect() as connection:
            plan = connection.exec_driver_sql(
                "EXPLAIN QUERY PLAN "
                "SELECT t.id FROM transactions t "
                "JOIN accounts a ON t.account_id = a.id "
                "WHERE a.user_id = ? AND t.is_deleted = 0 "
                "AND t.transaction_date >= ? AND t.transaction_date < ?",
                ("user", "2026-08-01", "2026-09-01"),
            ).fetchall()
        detail = " ".join(row[-1] for row in plan)
        self.assertIn("ix_accounts_user_id", detail)
        self.assertIn("ix_transactions_account_deleted_date", detail)


if __name__ == "__main__":
    unittest.main()
