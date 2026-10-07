import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.db import Base
from database.finance_services import (
    investment_contribution_totals,
    monthly_budget_progress,
    monthly_financial_summary,
    savings_goal_progress,
)
from database.models import (
    Account,
    Category,
    Group,
    GroupMembership,
    InvestmentSnapshot,
    MonthlyCategoryBudget,
    SavingsGoal,
    SavingsSnapshot,
    Transaction,
    User,
)
from utils.constants import TransactionType


class FinanceServicesTest(unittest.TestCase):
    def test_group_scope_combines_member_and_joint_accounts_without_duplication(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        sessions = sessionmaker(bind=engine)
        Base.metadata.create_all(engine)

        with sessions.begin() as session:
            first = User(id="first", name="First", color="#111111")
            second = User(id="second", name="Second", color="#222222")
            outsider = User(id="outside", name="Outside", color="#333333")
            group = Group(name="Household")
            food = Category(name="Food", color="#f97316")
            salary = Category(name="Salary", color="#10b981")
            session.add_all((first, second, outsider, group, food, salary))
            session.flush()
            session.add_all((
                GroupMembership(user_id=first.id, group_id=group.id),
                GroupMembership(user_id=second.id, group_id=group.id),
            ))
            first_account = Account(
                user_id=first.id, name="First", institution="Test", account_type="debit"
            )
            second_account = Account(
                user_id=second.id, name="Second", institution="Test", account_type="debit"
            )
            joint_account = Account(
                group_id=group.id, name="Joint", institution="Test", account_type="debit"
            )
            outside_account = Account(
                user_id=outsider.id, name="Outside", institution="Test", account_type="debit"
            )
            session.add_all((first_account, second_account, joint_account, outside_account))
            session.flush()

            def add(account, amount, transaction_type, category=None):
                session.add(Transaction(
                    account_id=account.id,
                    transaction_date=date(2026, 9, 15),
                    description="Test",
                    amount=Decimal(amount),
                    transaction_type=transaction_type,
                    category_id=category.id if category else None,
                ))

            add(first_account, "100.00", TransactionType.INCOME, salary)
            add(first_account, "-20.00", TransactionType.EXPENSE, food)
            add(second_account, "-10.00", TransactionType.EXPENSE, food)
            add(joint_account, "5.00", TransactionType.REFUND_REIMBURSEMENT, food)
            add(outside_account, "-999.00", TransactionType.EXPENSE, food)
            session.add_all((
                MonthlyCategoryBudget(
                    group_id=group.id, category_id=food.id,
                    year=2026, month=9, target_amount=Decimal("50.00"),
                ),
                SavingsGoal(
                    group_id=group.id, year=2026, month=9,
                    target_amount=Decimal("200.00"),
                ),
                SavingsSnapshot(
                    group_id=group.id, snapshot_date=date(2026, 9, 30),
                    amount_saved_this_month=Decimal("175.00"),
                ),
                InvestmentSnapshot(
                    group_id=group.id, account_name="Joint brokerage",
                    snapshot_date=date(2026, 9, 30),
                    monthly_contribution=Decimal("75.00"),
                    portfolio_value=Decimal("1200.00"),
                ),
            ))
            group_id = group.id

        summary = monthly_financial_summary(
            2026, 9, group_id=group_id, session_factory=sessions
        )
        self.assertEqual(summary.total_income, Decimal("100.00"))
        self.assertEqual(summary.gross_spending, Decimal("30.00"))
        self.assertEqual(summary.reimbursements, Decimal("5.00"))
        self.assertEqual(summary.net_spending, Decimal("25.00"))
        self.assertEqual(
            monthly_budget_progress(
                2026, 9, group_id=group_id, session_factory=sessions
            )[0].spent,
            Decimal("25.00"),
        )
        self.assertEqual(
            savings_goal_progress(
                2026, 9, group_id=group_id, session_factory=sessions
            ).actual,
            Decimal("175.00"),
        )
        self.assertEqual(
            investment_contribution_totals(
                2026, 9, group_id=group_id, session_factory=sessions
            ),
            Decimal("75.00"),
        )
        carried_budget = monthly_budget_progress(
            2026, 10, group_id=group_id, session_factory=sessions
        )
        self.assertEqual(carried_budget[0].target, Decimal("50.00"))
        self.assertEqual(carried_budget[0].spent, Decimal("0"))
        self.assertEqual(
            savings_goal_progress(
                2026, 10, group_id=group_id, session_factory=sessions
            ).target,
            Decimal("200.00"),
        )
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
