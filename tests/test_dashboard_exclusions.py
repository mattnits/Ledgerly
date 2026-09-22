import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.dashboard import get_dashboard_data
from database.db import Base
from database.models import Account, Category, Transaction, User
from database.transactions import get_transaction_months


class DashboardExclusionsTest(unittest.TestCase):
    def test_deleted_and_excluded_are_absent_from_every_dashboard_result(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine)

        with sessions.begin() as session:
            user = User(id="test-user", name="Test", color="#123456")
            categories = {
                name: Category(name=name, color="#123456")
                for name in (
                    "Income", "E-Transfer", "Food", "Investing",
                    "Exclude", "Excluded", "Deleted",
                )
            }
            session.add_all((user, *categories.values()))
            session.flush()
            account = Account(
                user_id=user.id,
                name="Checking",
                institution="Test",
                account_type="debit",
            )
            session.add(account)
            credit_account = Account(
                user_id=user.id,
                name="Card",
                institution="Test",
                account_type="credit",
            )
            session.add(credit_account)
            session.flush()

            def add(day, description, amount, category=None, account_id=None):
                session.add(Transaction(
                    account_id=account.id if account_id is None else account_id,
                    transaction_date=day,
                    description=description,
                    amount=Decimal(amount),
                    category_id=categories[category].id if category else None,
                ))

            add(date(2026, 7, 1), "Previous income", "80.00", "Income")
            add(date(2026, 7, 2), "Previous food", "-8.00", "Food")
            add(date(2026, 7, 3), "Previous incoming transfer", "20.00", "E-Transfer")
            add(date(2026, 7, 4), "Previous outgoing transfer", "-5.00", "E-Transfer")
            add(date(2026, 8, 1), "Income", "100.00", "Income")
            add(date(2026, 8, 1), "Card income", "40.00", "Income", credit_account.id)
            add(date(2026, 8, 2), "Incoming transfer", "30.00", "E-Transfer")
            add(date(2026, 8, 3), "Food", "-20.00", "Food")
            add(date(2026, 8, 4), "Outgoing transfer", "-7.00", "E-Transfer")
            add(date(2026, 8, 5), "Investing", "-10.00", "Investing")
            add(date(2026, 8, 6), "Food refund", "3.00", "Food")
            add(date(2026, 8, 7), "Income adjustment", "-5.00", "Income")
            add(date(2026, 8, 8), "Excluded income", "1000.00", "Exclude")
            add(date(2026, 8, 9), "Excluded spending", "-300.00", "Exclude")
            add(date(2026, 8, 10), "Excluded alias", "77.00", "Excluded")
            add(date(2026, 8, 11), "Deleted income", "2000.00", "Deleted")
            add(date(2026, 8, 12), "Deleted spending", "-400.00", "Deleted")
            add(date(2026, 6, 1), "Hidden month", "900.00", "Exclude")

        monthly = get_dashboard_data("test-user", "monthly", (2026, 8), sessions)
        self.assertEqual(monthly.income_total, Decimal("165.00"))
        self.assertEqual(monthly.spending_total, Decimal("34.00"))
        self.assertEqual(monthly.investing_total, Decimal("10.00"))
        self.assertEqual(monthly.previous_income, Decimal("100.00"))
        self.assertEqual(monthly.previous_spending, Decimal("13.00"))
        self.assertEqual(monthly.cash_flow_income[-1], Decimal("165.00"))
        self.assertEqual(monthly.cash_flow_spending[-1], Decimal("34.00"))
        self.assertEqual(
            sum((series.values[-1] for series in monthly.income_series), Decimal()),
            Decimal("165.00"),
        )
        self.assertEqual(monthly.spending_series[0].values[-1], Decimal("34.00"))
        self.assertEqual(
            {item.name: item.amount for item in monthly.category_spending},
            {
                "Food": Decimal("17.00"),
                "Investing": Decimal("10.00"),
                "E-Transfer": Decimal("7.00"),
            },
        )
        self.assertTrue(all(
            "Excluded" not in item.description and "Deleted" not in item.description
            for item in monthly.recent_transactions
        ))

        all_time = get_dashboard_data("test-user", "all", (2026, 8), sessions)
        self.assertEqual(all_time.income_total, Decimal("265.00"))
        self.assertEqual(all_time.spending_total, Decimal("47.00"))
        self.assertEqual(len(all_time.month_labels), 2)
        self.assertEqual(
            get_transaction_months("test-user", sessions),
            {(2026, 7), (2026, 8)},
        )
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
