import os
import time
import unittest
from datetime import date, datetime
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox

from app.services.transactions import TransactionRowData
from app.ui.widgets.transaction_table import (
    TransactionTableModel,
    TransactionTableView,
)
from app.utils.constants import TransactionType


class TransactionTablePerformanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_two_hundred_rows_render_without_persistent_editors(self):
        categories = [
            (category_id, f"Category {category_id}", "#3b82f6")
            for category_id in range(1, 21)
        ]
        rows = tuple(
            TransactionRowData(
                id=transaction_id,
                transaction_date=date(2026, 11, transaction_id % 28 + 1),
                description=f"Synthetic transaction {transaction_id}",
                amount=Decimal("-12.50"),
                transaction_type=TransactionType.EXPENSE,
                imported_at=datetime(2026, 11, 1, 12, 30),
                category_id=transaction_id % len(categories) + 1,
                account_name="Checking",
                institution="TD",
                is_deleted=False,
            )
            for transaction_id in range(1, 201)
        )
        model = TransactionTableModel()
        model.set_categories(categories)
        view = TransactionTableView(model)
        view.resize(1200, 620)

        started = time.perf_counter()
        model.replace_rows(rows)
        view.show()
        self.app.processEvents()
        elapsed = time.perf_counter() - started

        self.assertEqual(model.rowCount(), 200)
        self.assertEqual(view.findChildren(QComboBox), [])
        self.assertLess(
            elapsed,
            1.0,
            f"200 transaction rows took {elapsed:.3f}s to render",
        )
        view.close()


if __name__ == "__main__":
    unittest.main()
