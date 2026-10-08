import os
import unittest
from datetime import date, datetime
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMenu

from app.ui.theme import APP_STYLESHEET, prepare_popup_menu
from app.ui.widgets.transaction_row import TransactionRow
from app.utils.constants import TransactionType


class ActionMenuStyleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_popup_menu_disables_native_shadow(self):
        menu = prepare_popup_menu(QMenu())

        self.assertTrue(
            menu.windowFlags() & Qt.WindowType.NoDropShadowWindowHint
        )
        self.assertTrue(
            menu.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        )
        self.assertFalse(
            menu.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        )
        menu.close()

    def test_transaction_action_uses_shared_transparent_button_style(self):
        row = TransactionRow(
            transaction_id=1,
            transaction_date=date(2026, 10, 8),
            description="Test transaction",
            amount=Decimal("-10"),
            transaction_type=TransactionType.EXPENSE,
            imported_at=datetime(2026, 10, 8),
            category_id=None,
            account_name="Checking",
            institution="Test Bank",
            is_deleted=False,
            categories=[],
        )

        self.assertEqual(row.action_button.objectName(), "transactionActionButton")
        self.assertEqual(row.action_button.styleSheet(), "")
        self.assertIn(
            "QPushButton#transactionActionButton,\nQToolButton#goalsMenuButton",
            APP_STYLESHEET,
        )
        row.action_button.close()


if __name__ == "__main__":
    unittest.main()
