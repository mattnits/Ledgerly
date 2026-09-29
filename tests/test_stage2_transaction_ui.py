import os
import unittest
from datetime import date
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.db import Base
from database.models import Account, Category, Transaction, User
from ui.components.statements_table import StatementsTable
from utils.constants import TransactionType


class Stage2TransactionUiTest(unittest.TestCase):
    def test_review_search_selection_and_rule_prefill_work_together(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine)
        with sessions.begin() as session:
            user = User(id="test-user", name="Test", color="#123456")
            food = Category(name="Food", color="#f97316")
            session.add_all((user, food))
            session.flush()
            account = Account(
                user_id=user.id,
                name="Checking",
                institution="Test",
                account_type="debit",
            )
            session.add(account)
            session.flush()
            rows = (
                Transaction(
                    account_id=account.id,
                    transaction_date=date.today(),
                    description="Tim-Hortons Aurora",
                    amount=Decimal("-5.00"),
                    transaction_type=TransactionType.EXPENSE,
                ),
                Transaction(
                    account_id=account.id,
                    transaction_date=date.today(),
                    description="E-TRANSFER Jane",
                    amount=Decimal("25.00"),
                    transaction_type=TransactionType.E_TRANSFER,
                ),
                Transaction(
                    account_id=account.id,
                    transaction_date=date.today(),
                    description="TIM HORTONS MARKHAM",
                    amount=Decimal("-7.00"),
                    transaction_type=TransactionType.EXPENSE,
                    category_id=food.id,
                ),
            )
            session.add_all(rows)
            session.flush()
            aurora_id = rows[0].id

        app = QApplication.instance() or QApplication([])
        table = StatementsTable(session_factory=sessions)
        table.resize(1150, 520)
        table.show()
        table.set_user_id("test-user")
        app.processEvents()
        self.assertGreaterEqual(table.table.columnWidth(7), 76)
        self.assertGreaterEqual(
            table.table.columnWidth(StatementsTable.DESCRIPTION_COLUMN),
            StatementsTable.MINIMUM_DESCRIPTION_WIDTH,
        )
        self.assertGreaterEqual(
            table.table.columnWidth(4),
            StatementsTable.BASE_COLUMN_WIDTHS[4],
        )
        self.assertGreaterEqual(
            table.transaction_type_selector.width(),
            table.transaction_type_selector.fontMetrics().horizontalAdvance(
                "All Transaction Types"
            ) + 60,
        )

        narrow_description_width = table.table.columnWidth(
            StatementsTable.DESCRIPTION_COLUMN
        )
        table.resize(1500, 520)
        app.processEvents()
        self.assertGreater(
            table.table.columnWidth(StatementsTable.DESCRIPTION_COLUMN),
            narrow_description_width,
        )

        table.needs_review_checkbox.setChecked(True)
        app.processEvents()
        self.assertEqual(table.filtered_count, 1)
        self.assertFalse(table.review_mode_label.isHidden())
        self.assertEqual(table.rows[0].description, "Tim-Hortons Aurora")

        table.needs_review_checkbox.setChecked(False)
        table.search.setText("TIM HORTONS")
        app.processEvents()
        self.assertEqual(table.filtered_count, 2)

        description_label = table.rows[0].description_label
        description_label.setSelection(0, 3)
        description_label.setFocus()
        QTest.keyClick(
            description_label,
            Qt.Key.Key_C,
            Qt.KeyboardModifier.ControlModifier,
        )
        self.assertEqual(
            QApplication.clipboard().text(),
            description_label.selectedText(),
        )

        prefills = []
        table.create_rule_requested.connect(prefills.append)
        table._request_rule(aurora_id)
        self.assertEqual(prefills[0].pattern, "tim hortons aurora")
        self.assertEqual(prefills[0].transaction_type, TransactionType.EXPENSE)

        table.close()
        engine.dispose()

    def test_inline_dropdowns_ignore_mouse_wheel_changes(self):
        class WheelEventStub:
            ignored = False

            def ignore(self):
                self.ignored = True

        from ui.components.transaction_row import WheelSafeComboBox

        app = QApplication.instance() or QApplication([])
        combo = WheelSafeComboBox()
        combo.addItems(("First", "Second"))
        combo.setCurrentIndex(0)
        event = WheelEventStub()

        combo.wheelEvent(event)

        self.assertTrue(event.ignored)
        self.assertEqual(combo.currentIndex(), 0)
        combo.close()


if __name__ == "__main__":
    unittest.main()
