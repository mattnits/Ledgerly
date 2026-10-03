import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from ui.sidebar import Sidebar
from utils.constants import DASHBOARD_PAGE, USER_MANAGEMENT_PAGE


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
        self.assertTrue(self.sidebar.current_user_name.isHidden())
        self.assertTrue(self.sidebar.current_user_subtitle.isHidden())
        self.assertTrue(self.sidebar.add_user_button.isHidden())
        self.assertTrue(self.sidebar.switch_user_button.isHidden())
        self.assertTrue(self.sidebar.transactions_button.isChecked())
        for button in self.sidebar.navigation_buttons:
            self.assertEqual(button.text(), "")
            self.assertTrue(button.toolTip())

        self.sidebar.set_collapsed(False)
        self.app.processEvents()

        self.assertFalse(self.sidebar.is_collapsed)
        self.assertEqual(self.sidebar.width(), Sidebar.EXPANDED_WIDTH)
        self.assertFalse(self.sidebar.brand_title.isHidden())
        self.assertFalse(self.sidebar.current_user_name.isHidden())
        self.assertEqual(self.sidebar.current_user_name.fullText(), "Matt")
        self.assertEqual(self.sidebar.current_user_subtitle.fullText(), "Personal")
        self.assertFalse(self.sidebar.add_user_button.isHidden())
        self.assertFalse(self.sidebar.switch_user_button.isHidden())
        self.assertEqual(
            self.sidebar.transactions_button.text(),
            self.sidebar.transactions_button.property("sidebarLabel"),
        )
        self.assertTrue(self.sidebar.transactions_button.isChecked())

    def test_user_icon_expands_sidebar_before_opening_switch_dialog(self):
        switched = QSignalSpy(self.sidebar.switch_user_clicked)
        self.sidebar.set_collapsed(True)
        self.sidebar.toggle_user_dropdown()
        self.app.processEvents()

        self.assertFalse(self.sidebar.is_collapsed)
        self.assertEqual(switched.count(), 1)

    def test_user_bar_fills_expanded_sidebar_width(self):
        margins = self.sidebar.sidebar_layout.contentsMargins()
        expected_width = (
            self.sidebar.width() - margins.left() - margins.right()
        )
        self.assertLessEqual(abs(self.sidebar.user_bar.width() - expected_width), 1)

    def test_user_row_is_centered_between_divider_and_sidebar_bottom(self):
        self.sidebar.resize(Sidebar.EXPANDED_WIDTH, 900)
        self.app.processEvents()

        avatar_top = self.sidebar.current_user_avatar.mapTo(
            self.sidebar,
            self.sidebar.current_user_avatar.rect().topLeft(),
        ).y()
        avatar_center = avatar_top + self.sidebar.current_user_avatar.height() / 2
        available_center = (
            self.sidebar.user_bar.geometry().top() + self.sidebar.height()
        ) / 2
        self.assertLessEqual(abs(avatar_center - available_center), 2)

    def test_management_section_is_divided_and_user_bar_is_at_bottom(self):
        layout = self.sidebar.sidebar_layout
        self.assertLess(
            layout.indexOf(self.sidebar.categories_button),
            layout.indexOf(self.sidebar.management_divider),
        )
        self.assertLess(
            layout.indexOf(self.sidebar.management_divider),
            layout.indexOf(self.sidebar.user_management_button),
        )
        self.assertLess(
            layout.indexOf(self.sidebar.settings_button),
            layout.indexOf(self.sidebar.user_bar),
        )
        self.assertIs(layout.itemAt(layout.count() - 1).widget(), self.sidebar.user_bar)

    def test_long_user_name_is_elided_and_has_tooltip(self):
        long_name = "A very long profile name that cannot fit in the sidebar"
        self.sidebar.set_users(
            [{"id": "user-1", "name": long_name, "color": "#3b9de2"}],
            "user-1",
        )
        self.app.processEvents()

        self.assertIn("…", self.sidebar.current_user_name.text())
        self.assertEqual(self.sidebar.current_user_name.toolTip(), long_name)

    def test_user_display_has_no_dropdown_indicator(self):
        self.assertNotIn("▼", self.sidebar.current_user_name.text())
        self.assertEqual(self.sidebar.current_user_name.fullText(), "Matt")

    def test_programmatic_page_change_updates_checked_navigation(self):
        self.sidebar.set_current_page(USER_MANAGEMENT_PAGE)
        self.assertTrue(self.sidebar.user_management_button.isChecked())
        self.assertFalse(self.sidebar.dashboard_button.isChecked())

        self.sidebar.set_current_page(DASHBOARD_PAGE)
        self.assertTrue(self.sidebar.dashboard_button.isChecked())
        self.assertFalse(self.sidebar.user_management_button.isChecked())


if __name__ == "__main__":
    unittest.main()
