import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.sidebar import Sidebar


class SidebarTest(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.sidebar = Sidebar()
        self.sidebar.set_users(
            [{"id": "user-1", "name": "Matt", "color": "#3b9de2"}],
            "user-1",
        )
        self.sidebar.show()
        self.app.processEvents()

    def tearDown(self):
        self.sidebar.close()

    def test_sidebar_collapses_to_icons_and_restores_labels(self):
        self.sidebar.transactions_button.setChecked(True)
        self.sidebar.dashboard_button.setChecked(False)

        self.sidebar.set_collapsed(True)
        self.app.processEvents()

        self.assertTrue(self.sidebar.is_collapsed)
        self.assertEqual(self.sidebar.width(), Sidebar.COLLAPSED_WIDTH)
        self.assertTrue(self.sidebar.brand_title.isHidden())
        self.assertEqual(self.sidebar.current_user_button.text(), "")
        self.assertEqual(self.sidebar.create_user_button.text(), "")
        self.assertTrue(self.sidebar.transactions_button.isChecked())
        for button in self.sidebar.navigation_buttons:
            self.assertEqual(button.text(), "")
            self.assertTrue(button.toolTip())

        self.sidebar.set_collapsed(False)
        self.app.processEvents()

        self.assertFalse(self.sidebar.is_collapsed)
        self.assertEqual(self.sidebar.width(), Sidebar.EXPANDED_WIDTH)
        self.assertFalse(self.sidebar.brand_title.isHidden())
        self.assertIn("Matt", self.sidebar.current_user_button.text())
        self.assertEqual(self.sidebar.create_user_button.text(), "Create User")
        self.assertEqual(
            self.sidebar.transactions_button.text(),
            self.sidebar.transactions_button.property("sidebarLabel"),
        )
        self.assertTrue(self.sidebar.transactions_button.isChecked())

    def test_user_icon_expands_sidebar_before_opening_selector(self):
        self.sidebar.set_collapsed(True)
        self.sidebar.toggle_user_dropdown()
        self.app.processEvents()

        self.assertFalse(self.sidebar.is_collapsed)
        self.assertTrue(self.sidebar.user_dropdown.isVisible())


if __name__ == "__main__":
    unittest.main()
