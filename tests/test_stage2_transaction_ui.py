import os
import time
import unittest
from datetime import date
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models.models import Account, Category, Transaction, User
from app.ui.widgets.statements_table import StatementsTable
from app.utils.constants import TransactionType


class Stage2TransactionUiTest(unittest.TestCase):
    @staticmethod
    def _wait_for(predicate, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            QApplication.processEvents()
            if predicate():
                return
            QTest.qWait(10)
        raise AssertionError("Timed out waiting for background transaction query")

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
        self._wait_for(lambda: not table._loading)
        review_center = table.needs_review_checkbox.mapTo(
            table,
            table.needs_review_checkbox.rect().center(),
        ).y()
        date_range_center = table.date_range_selector.mapTo(
            table,
            table.date_range_selector.rect().center(),
        ).y()
        self.assertLessEqual(abs(review_center - date_range_center), 1)
        for index in range(table.category_selector.count()):
            self.assertEqual(
                table.category_selector.itemData(
                    index,
                    Qt.ItemDataRole.ForegroundRole,
                ),
                QColor("#ffffff"),
            )
        category_filter_longest = max(
            table.category_selector.fontMetrics().horizontalAdvance(
                table.category_selector.itemText(index)
            )
            for index in range(table.category_selector.count())
        )
        self.assertGreaterEqual(
            table.category_selector.view().minimumWidth(),
            category_filter_longest + 64,
        )
        for row in table.rows:
            for index in range(row.category_combo.count()):
                self.assertEqual(
                    row.category_combo.itemData(
                        index,
                        Qt.ItemDataRole.ForegroundRole,
                    ),
                    QColor("#ffffff"),
                )
            longest_category = max(
                row.category_combo.fontMetrics().horizontalAdvance(
                    row.category_combo.itemText(index)
                )
                for index in range(row.category_combo.count())
            )
            self.assertGreaterEqual(
                row.category_combo.view().minimumWidth(),
                longest_category + 64,
            )
        self.assertEqual(
            table.table.columnWidth(StatementsTable.ACTION_COLUMN),
            80,
        )
        action_button = table.rows[0].action_button
        action_cell = table.rows[0].action_cell
        self.assertGreaterEqual(action_button.geometry().left(), 8)
        self.assertGreaterEqual(
            action_cell.width() - action_button.geometry().right() - 1,
            8,
        )
        imported_text_width = max(
            table.table.fontMetrics().horizontalAdvance(text)
            for text in StatementsTable.IMPORTED_AT_WIDTH_SAMPLES
        )
        self.assertEqual(
            table.table.columnWidth(StatementsTable.IMPORTED_AT_COLUMN),
            imported_text_width + 16,
        )
        imported_margins = table.rows[0].imported_label.contentsMargins()
        self.assertEqual(imported_margins.left(), 8)
        self.assertEqual(imported_margins.right(), 8)
        self.assertEqual(
            sum(
                table.table.columnWidth(column)
                for column in range(table.table.columnCount())
            ),
            table.table.viewport().width(),
        )
        self.assertLessEqual(
            action_cell.geometry().right(),
            table.table.viewport().width() - 1,
        )
        self.assertGreaterEqual(
            table.table.columnWidth(StatementsTable.DESCRIPTION_COLUMN),
            StatementsTable.MINIMUM_COLUMN_WIDTHS[
                StatementsTable.DESCRIPTION_COLUMN
            ],
        )
        self.assertGreaterEqual(
            table.table.columnWidth(4),
            StatementsTable.MINIMUM_COLUMN_WIDTHS[4],
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
        self.assertEqual(
            sum(
                table.table.columnWidth(column)
                for column in range(table.table.columnCount())
            ),
            table.table.viewport().width(),
        )
        self.assertGreater(
            table.table.columnWidth(StatementsTable.DESCRIPTION_COLUMN),
            StatementsTable.MAXIMUM_COLUMN_WIDTHS[
                StatementsTable.DESCRIPTION_COLUMN
            ],
        )

        table.needs_review_checkbox.setChecked(True)
        self._wait_for(lambda: not table._loading and table.filtered_count == 1)
        self.assertEqual(table.filtered_count, 1)
        self.assertFalse(table.review_mode_label.isHidden())
        self.assertEqual(table.rows[0].description, "Tim-Hortons Aurora")

        table.needs_review_checkbox.setChecked(False)
        table.search.setText("TIM HORTONS")
        self._wait_for(lambda: not table._loading and table.filtered_count == 2)
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

        from app.ui.widgets.transaction_row import WheelSafeComboBox

        app = QApplication.instance() or QApplication([])
        combo = WheelSafeComboBox()
        combo.addItems(("First", "Second"))
        combo.setCurrentIndex(0)
        event = WheelEventStub()

        combo.wheelEvent(event)

        self.assertTrue(event.ignored)
        self.assertEqual(combo.currentIndex(), 0)

        combo.resize(220, 34)
        combo.show()
        combo.showPopup()
        app.processEvents()
        popup = combo.view().window()
        native_scrollers = [
            child
            for child in popup.findChildren(QWidget)
            if child.metaObject().className() == "QComboBoxPrivateScroller"
        ]
        self.assertEqual(popup.objectName(), "framelessComboPopup")
        self.assertEqual(native_scrollers, [])
        self.assertEqual(popup.height(), combo.view().height())
        self.assertEqual(combo.view().geometry().top(), 0)
        viewport = combo.view().viewport().rect()
        for row in range(combo.count()):
            item = combo.model().index(row, 0)
            self.assertTrue(viewport.contains(combo.view().visualRect(item)))

        combo.hidePopup()
        combo.close()

    def test_empty_selected_month_does_not_show_latest_month_rows(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine)
        with sessions.begin() as session:
            user = User(id="test-user", name="Test", color="#123456")
            session.add(user)
            session.flush()
            account = Account(
                user_id=user.id,
                name="TD Debit",
                institution="TD",
                account_type="debit",
            )
            session.add(account)
            session.flush()
            session.add(Transaction(
                account_id=account.id,
                transaction_date=date(2026, 9, 1),
                description="September transaction",
                amount=Decimal("5700.00"),
                transaction_type=TransactionType.INCOME,
            ))

        app = QApplication.instance() or QApplication([])
        table = StatementsTable(session_factory=sessions)
        table.show()
        table.set_user_id("test-user")
        self._wait_for(
            lambda: not table._loading
            and table.selected_month == (2026, 9)
            and table.loaded_count == 1
        )

        table.period_selector.month_picker.set_period(2026, 6, emit=True)
        self._wait_for(
            lambda: not table._loading
            and table.selected_month == (2026, 6)
            and table.filtered_count == 0
        )

        self.assertEqual(
            table.period_selector.month_picker.selected_period,
            (2026, 6),
        )
        self.assertEqual(table.rows, [])
        self.assertEqual(table.date_range_filter, "selected_month")

        table.period_selector.month_picker.set_period(2026, 9, emit=True)
        self._wait_for(
            lambda: not table._loading
            and table.selected_month == (2026, 9)
            and table.loaded_count == 1
        )
        self.assertEqual(table.rows[0].description, "September transaction")
        table.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
