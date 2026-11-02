import os
import time
import unittest
from datetime import date
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models.models import Account, Category, Transaction, User
from app.ui.widgets.statements_table import StatementsTable
from app.utils.constants import ClassificationSource, TransactionType


class TransactionScrollTest(unittest.TestCase):
    TEST_PAGE_SIZE = 20
    TRANSACTION_COUNT = 30

    @staticmethod
    def _wait_for(predicate, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            QApplication.processEvents()
            if predicate():
                return
            QTest.qWait(10)
        raise AssertionError("Timed out waiting for background transaction query")

    def test_category_change_is_saved_without_reloading_or_moving_scroll(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine)
        with sessions.begin() as session:
            user = User(id="test-user", name="Test", color="#123456")
            category = Category(name="Food", color="#f97316")
            session.add_all((user, category))
            session.flush()
            account = Account(
                user_id=user.id, name="Checking", institution="Test",
                account_type="debit",
            )
            session.add(account)
            session.flush()
            account_id, category_id = account.id, category.id
            session.add_all(
                Transaction(
                    account_id=account_id,
                    transaction_date=date.today(),
                    description=f"Unique row {index:03}",
                    amount=Decimal("-1.00"),
                    transaction_type=TransactionType.EXPENSE,
                )
                for index in range(self.TRANSACTION_COUNT)
            )

        app = QApplication.instance() or QApplication([])
        table = StatementsTable(session_factory=sessions)
        # Exercise pagination so an inline edit proves it does not rebuild the
        # already loaded model.
        table.PAGE_SIZE = self.TEST_PAGE_SIZE
        table.resize(1150, 520)
        table.show()
        table.set_user_id("test-user")
        self._wait_for(
            lambda: not table._loading
            and table.loaded_count == self.TEST_PAGE_SIZE
        )
        table._load_more()
        self._wait_for(
            lambda: not table._loading
            and table.loaded_count == self.TRANSACTION_COUNT
        )
        self.assertEqual(table.loaded_count, self.TRANSACTION_COUNT)
        action_rect = table.table.visualRect(
            table.table_model.index(0, StatementsTable.ACTION_COLUMN)
        )
        self.assertLessEqual(
            action_rect.right(),
            table.table.viewport().width() - 1,
        )

        scrollbar = table.table.verticalScrollBar()
        self.assertGreater(scrollbar.maximum(), 0)
        scrollbar.setValue(min(150, scrollbar.maximum()))
        original_position = scrollbar.value()
        self.assertGreater(original_position, 0)
        row = table.rows[self.TEST_PAGE_SIZE + 5]
        transaction_id = row.transaction_id
        generation = table._query_generation
        table.table_model.setData(
            table.table_model.index(
                self.TEST_PAGE_SIZE + 5,
                table.table_model.CATEGORY_COLUMN,
            ),
            category_id,
        )
        self._wait_for(
            lambda: transaction_id not in table._assignment_active
        )

        self.assertEqual(table._query_generation, generation)
        self.assertEqual(table.loaded_count, self.TRANSACTION_COUNT)
        self.assertEqual(scrollbar.value(), original_position)
        with sessions() as session:
            transaction = session.get(Transaction, transaction_id)
            self.assertEqual(transaction.category_id, category_id)
            self.assertEqual(
                transaction.classification_source,
                ClassificationSource.MANUAL.value,
            )

        table.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
