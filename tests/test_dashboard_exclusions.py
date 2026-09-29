import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.dashboard import get_dashboard_data
from database.db import Base
from database.models import (
    Account,
    Category,
    InvestmentSnapshot,
    MonthlyCategoryBudget,
    SavingsGoal,
    SavingsSnapshot,
    Transaction,
    User,
)
from database.transactions import get_transaction_months
from utils.constants import TransactionType


class DashboardTransactionTypesTest(unittest.TestCase):
    def test_dashboard_uses_transaction_type_for_every_total(self):
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
                for name in ("Salary", "Other Income", "Food")
            }
            session.add_all((user, *categories.values()))
            session.flush()
            account = Account(
                user_id=user.id,
                name="Checking",
                institution="Test",
                account_type="debit",
            )
            unused_account = Account(
                user_id=user.id,
                name="Credit Card",
                institution="Test",
                account_type="credit",
            )
            session.add_all((account, unused_account))
            session.flush()

            def add(
                day,
                description,
                amount,
                transaction_type,
                category=None,
                deleted=False,
            ):
                session.add(Transaction(
                    account_id=account.id,
                    transaction_date=day,
                    description=description,
                    amount=Decimal(amount),
                    transaction_type=transaction_type,
                    category_id=categories[category].id if category else None,
                    is_deleted=deleted,
                ))

            add(date(2026, 7, 1), "Salary", "80.00", TransactionType.INCOME, "Salary")
            add(date(2026, 7, 2), "Food", "-8.00", TransactionType.EXPENSE, "Food")
            add(date(2026, 7, 3), "Transfer", "20.00", TransactionType.TRANSFER)
            add(date(2026, 8, 1), "Salary", "100.00", TransactionType.INCOME, "Salary")
            add(date(2026, 8, 1), "Grant", "40.00", TransactionType.INCOME, "Other Income")
            add(date(2026, 8, 2), "Transfer", "30.00", TransactionType.TRANSFER)
            add(date(2026, 8, 3), "Food", "-20.00", TransactionType.EXPENSE, "Food")
            add(date(2026, 8, 4), "Card payment", "-50.00", TransactionType.CREDIT_CARD_PAYMENT)
            add(date(2026, 8, 5), "Investment", "-10.00", TransactionType.INVESTMENT)
            add(
                date(2026, 8, 6), "Food reimbursement", "3.00",
                TransactionType.REFUND_REIMBURSEMENT, "Food",
            )
            add(
                date(2026, 8, 7), "Income adjustment", "-5.00",
                TransactionType.INCOME, "Other Income",
            )
            add(
                date(2026, 6, 1), "Removed", "900.00",
                TransactionType.INCOME, "Other Income", deleted=True,
            )
            session.add_all((
                InvestmentSnapshot(
                    user_id=user.id,
                    account_name="Brokerage",
                    snapshot_date=date(2026, 7, 31),
                    monthly_contribution=Decimal("20.00"),
                    portfolio_value=Decimal("800.00"),
                ),
                InvestmentSnapshot(
                    user_id=user.id,
                    account_name="Brokerage",
                    snapshot_date=date(2026, 8, 31),
                    monthly_contribution=Decimal("10.00"),
                    portfolio_value=Decimal("1000.00"),
                ),
                SavingsGoal(
                    user_id=user.id,
                    year=2026,
                    month=8,
                    target_amount=Decimal("200.00"),
                ),
                SavingsSnapshot(
                    user_id=user.id,
                    snapshot_date=date(2026, 8, 31),
                    amount_saved_this_month=Decimal("150.00"),
                    total_savings_balance=Decimal("750.00"),
                ),
                MonthlyCategoryBudget(
                    user_id=user.id,
                    category_id=categories["Food"].id,
                    year=2026,
                    month=8,
                    target_amount=Decimal("25.00"),
                ),
            ))

        monthly = get_dashboard_data("test-user", "monthly", (2026, 8), sessions)
        self.assertEqual(monthly.regular_income, Decimal("100.00"))
        self.assertEqual(monthly.additional_income, Decimal("35.00"))
        self.assertEqual(monthly.income_total, Decimal("135.00"))
        self.assertEqual(monthly.gross_spending, Decimal("20.00"))
        self.assertEqual(monthly.reimbursements, Decimal("3.00"))
        self.assertEqual(monthly.spending_total, Decimal("17.00"))
        self.assertEqual(
            [(item.name, item.amount) for item in monthly.account_spending],
            [
                ("Checking", Decimal("20.00")),
                ("Credit Card", Decimal("0")),
            ],
        )
        self.assertEqual(monthly.investing_total, Decimal("10.00"))
        self.assertEqual(monthly.savings_goal, Decimal("200.00"))
        self.assertEqual(monthly.savings_actual, Decimal("150.00"))
        self.assertEqual(monthly.savings_balance, Decimal("750.00"))
        self.assertEqual(monthly.budget_progress[0].spent, Decimal("17.00"))
        self.assertEqual(monthly.budget_progress[0].target, Decimal("25.00"))
        self.assertEqual(monthly.portfolio_value, Decimal("1000.00"))
        self.assertEqual(monthly.previous_portfolio_value, Decimal("800.00"))
        self.assertEqual(
            monthly.investment_value_series,
            (Decimal("800.00"), Decimal("1000.00")),
        )
        self.assertEqual(monthly.previous_income, Decimal("80.00"))
        self.assertEqual(monthly.previous_spending, Decimal("8.00"))
        self.assertEqual(monthly.cash_flow_income[-1], Decimal("135.00"))
        self.assertEqual(monthly.cash_flow_spending[-1], Decimal("17.00"))
        self.assertEqual(
            {item.name: item.amount for item in monthly.category_spending},
            {"Food": Decimal("17.00")},
        )
        self.assertTrue(all(
            item.description != "Removed" for item in monthly.recent_transactions
        ))

        all_time = get_dashboard_data("test-user", "all", (2026, 8), sessions)
        self.assertEqual(all_time.income_total, Decimal("215.00"))
        self.assertEqual(all_time.spending_total, Decimal("25.00"))
        self.assertEqual(all_time.investing_total, Decimal("30.00"))
        self.assertEqual(len(all_time.month_labels), 2)
        self.assertEqual(
            get_transaction_months("test-user", sessions),
            {(2026, 7), (2026, 8)},
        )
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
