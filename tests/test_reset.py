import unittest
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models.models import (
    Account,
    Category,
    CategoryRule,
    Import,
    InvestmentAccount,
    InvestmentSnapshot,
    Transaction,
    User,
)
from app.services.reset import reset_financial_data
from app.utils.constants import MatchType, TransactionType


class ResetFinancialDataTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.sessions = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_only_transactions_and_import_history_are_deleted(self):
        with self.sessions.begin() as session:
            user = User(id="owner", name="Owner", color="#123456")
            category = Category(name="Groceries", color="#22c55e")
            account = Account(
                user_id=user.id,
                name="Chequing",
                institution="TD",
                account_type="debit",
            )
            investment = InvestmentAccount(
                user_id=user.id,
                institution="Broker",
                account_name="TFSA",
                account_number_last7="ABC1234",
            )
            session.add_all((user, category, account, investment))
            session.flush()

            import_record = Import(
                account_id=account.id,
                file_name="statement.csv",
                content_hash="test-hash",
            )
            rule = CategoryRule(
                user_id=user.id,
                account_id=account.id,
                description_key="grocery store",
                description_example="Grocery Store",
                match_type=MatchType.EXACT,
                transaction_type=TransactionType.EXPENSE,
                category_id=category.id,
            )
            snapshot = InvestmentSnapshot(
                investment_account_id=investment.id,
                snapshot_datetime=datetime(2026, 9, 30),
                total_value=Decimal("1000.00"),
            )
            session.add_all((import_record, rule, snapshot))
            session.flush()
            session.add(Transaction(
                account_id=account.id,
                category_id=category.id,
                import_id=import_record.id,
                transaction_date=date(2026, 9, 30),
                description="Grocery Store",
                amount=Decimal("-25.00"),
                transaction_type=TransactionType.EXPENSE,
            ))

        reset_financial_data(session_factory=self.sessions)

        with self.sessions() as session:
            self.assertEqual(session.scalar(select(func.count(Transaction.id))), 0)
            self.assertEqual(session.scalar(select(func.count(Import.id))), 0)
            for model in (
                User,
                Account,
                Category,
                CategoryRule,
                InvestmentAccount,
                InvestmentSnapshot,
            ):
                self.assertEqual(session.scalar(select(func.count(model.id))), 1)


if __name__ == "__main__":
    unittest.main()
