import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.db import Base
from database.models import Account, Category, Transaction, User
from database.transactions import bulk_classify_transactions
from utils.constants import ClassificationSource, TransactionType


class BulkClassificationTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.sessions = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        with self.sessions.begin() as session:
            user = User(id="test-user", name="Test", color="#123456")
            category = Category(name="Food", color="#f97316")
            session.add_all((user, category))
            session.flush()
            account = Account(
                user_id=user.id,
                name="Checking",
                institution="Test",
                account_type="debit",
            )
            session.add(account)
            session.flush()
            self.category_id = category.id
            transactions = [
                Transaction(
                    account_id=account.id,
                    transaction_date=date.today(),
                    description=f"Raw description #{index}",
                    amount=Decimal("-5.00"),
                    transaction_type=None,
                    classification_source=ClassificationSource.DEFAULT.value,
                )
                for index in range(3)
            ]
            session.add_all(transactions)
            session.flush()
            self.transaction_ids = [transaction.id for transaction in transactions]

    def tearDown(self):
        self.engine.dispose()

    def test_bulk_classification_updates_only_selected_rows_as_manual(self):
        with self.sessions.begin() as session:
            updated = bulk_classify_transactions(
                session,
                "test-user",
                self.transaction_ids[:2],
                transaction_type=TransactionType.EXPENSE,
                category_id=self.category_id,
            )
        self.assertEqual(updated, 2)

        with self.sessions() as session:
            rows = session.scalars(
                select(Transaction).order_by(Transaction.id)
            ).all()
        for row in rows[:2]:
            self.assertEqual(row.transaction_type, TransactionType.EXPENSE)
            self.assertEqual(row.category_id, self.category_id)
            self.assertEqual(
                row.classification_source,
                ClassificationSource.MANUAL.value,
            )
        self.assertIsNone(rows[2].transaction_type)
        self.assertIsNone(rows[2].category_id)
        self.assertEqual(
            rows[2].classification_source,
            ClassificationSource.DEFAULT.value,
        )
        self.assertEqual(
            [row.description for row in rows],
            ["Raw description #0", "Raw description #1", "Raw description #2"],
        )

    def test_bulk_transaction_type_preserves_category_unless_type_is_category_free(self):
        with self.sessions.begin() as session:
            row = session.get(Transaction, self.transaction_ids[0])
            row.category_id = self.category_id

        with self.sessions.begin() as session:
            bulk_classify_transactions(
                session,
                "test-user",
                [self.transaction_ids[0]],
                transaction_type=TransactionType.INCOME,
            )
        with self.sessions() as session:
            row = session.get(Transaction, self.transaction_ids[0])
            self.assertEqual(row.category_id, self.category_id)

        with self.sessions.begin() as session:
            bulk_classify_transactions(
                session,
                "test-user",
                [self.transaction_ids[0]],
                transaction_type=TransactionType.E_TRANSFER,
            )
        with self.sessions() as session:
            row = session.get(Transaction, self.transaction_ids[0])
            self.assertIsNone(row.category_id)


if __name__ == "__main__":
    unittest.main()
