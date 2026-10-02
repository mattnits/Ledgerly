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

from database.db import Base
from database.models import Account, Category, Transaction, User
from ui.components.statements_table import StatementsTable
from utils.constants import ClassificationSource, TransactionType


class TransactionScrollTest(unittest.TestCase):
    @staticmethod
    def _wait_for(predicate, timeout=3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            QApplication.processEvents()
            if predicate():
                return
            QTest.qWait(10)
        raise AssertionError("Timed out waiting for background transaction query")

    def test_category_change_keeps_scroll_after_paginated_reload(self):
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
                for index in range(250)
            )

        app = QApplication.instance() or QApplication([])
        table = StatementsTable(session_factory=sessions)
        table.resize(1150, 520)
        table.show()
        table.set_user_id("test-user")
        self._wait_for(lambda: not table._loading and table.loaded_count == 200)
        table._load_more()
        self._wait_for(lambda: not table._loading and table.loaded_count == 250)
        self.assertEqual(table.loaded_count, 250)

        scrollbar = table.table.verticalScrollBar()
        self.assertGreater(scrollbar.maximum(), 150)
        scrollbar.setValue(150)
        original_position = scrollbar.value()
        row = table.rows[160]
        transaction_id = row.transaction_id
        generation = table._query_generation
        row.category_combo.setCurrentIndex(row.category_combo.findData(category_id))
        self._wait_for(
            lambda: table._query_generation > generation
            and not table._loading
            and table.loaded_count == 250
        )

        self.assertEqual(table.loaded_count, 250)
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
