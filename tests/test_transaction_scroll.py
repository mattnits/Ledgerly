import os
import unittest
from datetime import date
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.db import Base
from database.models import Account, Category, Transaction, User
from ui.components.statements_table import StatementsTable


class TransactionScrollTest(unittest.TestCase):
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
                )
                for index in range(250)
            )

        app = QApplication.instance() or QApplication([])
        table = StatementsTable(session_factory=sessions)
        table.resize(1150, 520)
        table.show()
        table.set_user_id("test-user")
        app.processEvents()
        table._load_more()
        self.assertEqual(table.loaded_count, 250)

        scrollbar = table.table.verticalScrollBar()
        self.assertGreater(scrollbar.maximum(), 150)
        scrollbar.setValue(150)
        original_position = scrollbar.value()
        row = table.rows[160]
        transaction_id = row.transaction_id
        row.category_combo.setCurrentIndex(row.category_combo.findData(category_id))
        app.processEvents()

        self.assertEqual(table.loaded_count, 250)
        self.assertEqual(scrollbar.value(), original_position)
        with sessions() as session:
            self.assertEqual(session.get(Transaction, transaction_id).category_id, category_id)

        table.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
