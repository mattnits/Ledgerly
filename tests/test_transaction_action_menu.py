import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from app.ui.widgets.statements_table import (
    TransactionActionMenu,
    prepare_transaction_action_menu,
)


class TransactionActionMenuTest(unittest.TestCase):
    def test_action_menu_hover_covers_outer_padding(self):
        app = QApplication.instance() or QApplication([])
        parent = QWidget()
        menu = prepare_transaction_action_menu(parent)

        self.assertIsInstance(menu, TransactionActionMenu)
        self.assertEqual(menu.ICON_LEFT_INSET, 16)
        self.assertEqual(menu.objectName(), "transactionActionMenu")
        self.assertIn("padding: 0", menu.styleSheet())
        self.assertIn("padding: 9px 24px 9px 20px", menu.styleSheet())
        self.assertIn("QMenu#transactionActionMenu::item:selected", menu.styleSheet())
        self.assertIn("background: #315f94", menu.styleSheet())

        first_action = menu.addAction("First action")
        menu.addAction("Second action")
        menu.popup(QPoint(20, 20))
        app.processEvents()
        first_rect = menu.actionGeometry(first_action)
        QTest.mouseMove(menu, first_rect.center())
        app.processEvents()
        rendered = menu.grab().toImage()
        self.assertEqual(
            rendered.pixelColor(first_rect.left() + 2, first_rect.center().y()).name(),
            "#315f94",
        )

        menu.close()
        parent.close()


if __name__ == "__main__":
    unittest.main()
