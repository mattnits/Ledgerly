import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMessageBox, QWidget

from app.ui.shell import ShellWindow
from app.ui.sidebar import Sidebar, avatar_icon
from app.utils.constants import DASHBOARD_PAGE, USER_MANAGEMENT_PAGE


class SidebarTest(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.sidebar = Sidebar()
        self.sidebar.set_users(
            [{"id": "user-1", "name": "Matt", "color": "#3b9de2"}],
            "user-1",
        )
        self.host = QWidget()
        self.host.resize(900, 760)
        layout = QHBoxLayout(self.host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.sidebar)
        layout.addStretch()
        self.host.show()
        self.app.processEvents()

    def tearDown(self):
        self.sidebar.close_profile_menu()
        self.host.close()

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
        self.assertEqual(self.sidebar.exit_button.text(), "")
        self.assertEqual(self.sidebar.exit_button.toolTip(), "Exit Ledgerly")

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
        self.assertEqual(self.sidebar.exit_button.text(), "Exit")

    def test_exit_button_emits_request(self):
        requests = QSignalSpy(self.sidebar.exit_requested)
        QTest.mouseClick(self.sidebar.exit_button, Qt.MouseButton.LeftButton)
        self.assertEqual(requests.count(), 1)

    def test_exit_confirmation_only_closes_after_yes(self):
        shell = Mock()
        with patch(
            "app.ui.shell.QMessageBox.question",
            side_effect=(
                QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            ),
        ):
            ShellWindow.confirm_exit(shell)
            shell.close.assert_not_called()
            ShellWindow.confirm_exit(shell)
            shell.close.assert_called_once_with()

    def test_collapsed_profile_click_opens_menu_without_expanding(self):
        self.sidebar.set_collapsed(True)
        QTest.mouseClick(
            self.sidebar.current_user_panel,
            Qt.MouseButton.LeftButton,
            pos=self.sidebar.current_user_panel.rect().center(),
        )
        self.app.processEvents()

        self.assertTrue(self.sidebar.is_collapsed)
        self.assertIsNotNone(self.sidebar.profile_menu)
        self.assertTrue(self.sidebar.profile_menu.isVisible())

    def test_expanded_profile_click_is_informational(self):
        added = QSignalSpy(self.sidebar.create_user_clicked)
        switched = QSignalSpy(self.sidebar.switch_user_clicked)
        QTest.mouseClick(
            self.sidebar.current_user_panel,
            Qt.MouseButton.LeftButton,
            pos=self.sidebar.current_user_panel.rect().center(),
        )
        self.app.processEvents()

        self.assertIsNone(self.sidebar.profile_menu)
        self.assertEqual(added.count(), 0)
        self.assertEqual(switched.count(), 0)

    def test_profile_panel_cursor_tracks_collapse_state(self):
        self.assertEqual(
            self.sidebar.current_user_panel.cursor().shape(),
            Qt.CursorShape.ArrowCursor,
        )
        self.sidebar.set_collapsed(True)
        self.assertEqual(
            self.sidebar.current_user_panel.cursor().shape(),
            Qt.CursorShape.PointingHandCursor,
        )
        self.assertEqual(
            self.sidebar.current_user_avatar.cursor().shape(),
            Qt.CursorShape.PointingHandCursor,
        )
        self.sidebar.set_collapsed(False)
        self.assertEqual(
            self.sidebar.current_user_panel.cursor().shape(),
            Qt.CursorShape.ArrowCursor,
        )
        self.assertEqual(
            self.sidebar.current_user_avatar.cursor().shape(),
            Qt.CursorShape.ArrowCursor,
        )

    def test_popup_actions_reuse_sidebar_dialog_signals(self):
        added = QSignalSpy(self.sidebar.create_user_clicked)
        switched = QSignalSpy(self.sidebar.switch_user_clicked)
        self.sidebar.set_collapsed(True)
        self.sidebar.toggle_profile_menu()
        self.app.processEvents()
        QTest.mouseClick(
            self.sidebar.profile_menu.add_user_button,
            Qt.MouseButton.LeftButton,
        )
        self.app.processEvents()
        self.assertEqual(added.count(), 1)
        self.assertIsNone(self.sidebar.profile_menu)

        self.sidebar.toggle_profile_menu()
        self.app.processEvents()
        QTest.mouseClick(
            self.sidebar.profile_menu.change_user_button,
            Qt.MouseButton.LeftButton,
        )
        self.app.processEvents()
        self.assertEqual(switched.count(), 1)
        self.assertIsNone(self.sidebar.profile_menu)

    def test_popup_closes_when_sidebar_expands(self):
        self.sidebar.set_collapsed(True)
        self.sidebar.toggle_profile_menu()
        self.app.processEvents()
        menu = self.sidebar.profile_menu
        self.assertTrue(menu.isVisible())

        self.sidebar.set_collapsed(False)
        self.app.processEvents()
        self.assertIsNone(self.sidebar.profile_menu)

    def test_popup_closes_when_active_profile_changes(self):
        self.sidebar.set_profiles(
            [
                {
                    "key": "user:user-1", "type": "user", "id": "user-1",
                    "name": "Matt", "color": "#3b9de2", "subtitle": "Personal",
                },
                {
                    "key": "group:7", "type": "group", "id": 7,
                    "name": "Household", "color": "#8844ff",
                    "subtitle": "Group • 2 members", "member_count": 2,
                },
            ],
            "user:user-1",
        )
        self.sidebar.set_collapsed(True)
        self.sidebar.toggle_profile_menu()
        self.app.processEvents()
        self.assertIsNotNone(self.sidebar.profile_menu)

        self.sidebar.select_profile("group:7")
        self.app.processEvents()
        self.assertIsNone(self.sidebar.profile_menu)
        self.assertEqual(self.sidebar.current_profile_key, "group:7")

    def test_popup_closes_on_outside_click(self):
        self.sidebar.set_collapsed(True)
        self.sidebar.toggle_profile_menu()
        self.app.processEvents()
        self.assertIsNotNone(self.sidebar.profile_menu)

        QTest.mouseClick(
            self.host,
            Qt.MouseButton.LeftButton,
            pos=QPoint(self.host.width() - 20, 20),
        )
        self.app.processEvents()
        self.assertIsNone(self.sidebar.profile_menu)

    def test_popup_shows_personal_profile_and_stays_inside_window(self):
        self.sidebar.set_collapsed(True)
        self.sidebar.toggle_profile_menu()
        self.app.processEvents()
        menu = self.sidebar.profile_menu
        self.assertEqual(menu.name_label.fullText(), "Matt")
        self.assertEqual(menu.subtitle_label.fullText(), "Personal")

        host_top_left = self.host.mapToGlobal(QPoint(0, 0))
        host_right = host_top_left.x() + self.host.width()
        host_bottom = host_top_left.y() + self.host.height()
        menu_rect = menu.frameGeometry()
        self.assertGreaterEqual(menu_rect.left(), host_top_left.x())
        self.assertGreaterEqual(menu_rect.top(), host_top_left.y())
        self.assertLessEqual(menu_rect.right(), host_right)
        self.assertLessEqual(menu_rect.bottom(), host_bottom)

    def test_group_popup_uses_group_subtitle_and_avatar_shape(self):
        self.sidebar.set_profiles(
            [{
                "key": "group:7",
                "type": "group",
                "id": 7,
                "name": "Household",
                "color": "#8844ff",
                "subtitle": "Group • 3 members",
                "member_count": 3,
            }],
            "group:7",
        )
        self.sidebar.set_collapsed(True)
        self.sidebar.toggle_profile_menu()
        self.app.processEvents()
        self.assertEqual(self.sidebar.profile_menu.name_label.fullText(), "Household")
        self.assertEqual(
            self.sidebar.profile_menu.subtitle_label.fullText(),
            "Group • 3 members",
        )
        self.assertEqual(
            self.sidebar.current_user_avatar.property("profileType"), "group"
        )

    def test_user_avatar_is_circular_and_group_avatar_is_squircle(self):
        user_image = avatar_icon(
            "M", "#8844ff", 36, profile_type="user"
        ).pixmap(36, 36).toImage()
        group_image = avatar_icon(
            "H", "#8844ff", 36, profile_type="group"
        ).pixmap(36, 36).toImage()
        self.assertEqual(user_image.pixelColor(4, 4).alpha(), 0)
        self.assertGreater(group_image.pixelColor(4, 4).alpha(), 0)

        text_pixels = [
            (x, y)
            for y in range(user_image.height())
            for x in range(user_image.width())
            if (
                user_image.pixelColor(x, y).alpha() > 0
                and user_image.pixelColor(x, y).red() > 220
                and user_image.pixelColor(x, y).green() > 220
                and user_image.pixelColor(x, y).blue() > 220
            )
        ]
        self.assertTrue(text_pixels)
        text_bounds = (
            min(x for x, _ in text_pixels),
            min(y for _, y in text_pixels),
            max(x for x, _ in text_pixels),
            max(y for _, y in text_pixels),
        )
        self.assertGreaterEqual(text_bounds[0], 8)
        self.assertGreaterEqual(text_bounds[1], 8)
        self.assertLessEqual(text_bounds[2], 27)
        self.assertLessEqual(text_bounds[3], 27)

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
            layout.indexOf(self.sidebar.exit_button),
        )
        self.assertLess(
            layout.indexOf(self.sidebar.exit_button),
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
