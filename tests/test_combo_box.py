import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QHelpEvent, QStandardItem, QStandardItemModel
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QScrollArea, QToolTip, QVBoxLayout, QWidget

from app.ui.theme import APP_STYLESHEET, DROPDOWN_MAX_ROWS
from app.ui.widgets.combo_box import AppComboBox
from app.ui.widgets.dropdown import _dismiss_filter
from app.ui.widgets.date_dropdown import DateDropdown


class AppComboBoxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.old_style = self.app.styleSheet()
        self.app.setStyleSheet(APP_STYLESHEET)
        self.combo = AppComboBox()
        self.combo.resize(260, 42)
        self.combo.move(100, 100)

    def tearDown(self):
        self.combo.hidePopup()
        self.combo.close()
        self.app.setStyleSheet(self.old_style)

    def open_combo(self, count):
        for index in range(count):
            self.combo.addItem(f"Choice {index}", index * 10)
        self.combo.show()
        self.app.processEvents()
        self.combo.showPopup()
        self.app.processEvents()
        return self.combo.view(), self.combo.view().window()

    def test_small_lists_show_every_row_and_long_lists_scroll_without_bands(self):
        for count in (1, 3, 6, 8, 20):
            with self.subTest(count=count):
                self.combo.clear()
                view, popup = self.open_combo(count)
                rows = min(count, DROPDOWN_MAX_ROWS)
                self.assertEqual(view.viewport().height(), rows * self.combo.popup_row_height())
                self.assertEqual(popup.height(), view.viewport().height() + 2)
                self.assertEqual(view.geometry(), popup.rect())
                self.assertTrue(popup.layout().contentsMargins().isNull())
                self.assertEqual(view.viewport().geometry().top(), 1)
                self.assertEqual(view.verticalScrollBar().isVisible(), count > rows)
                self.assertTrue(popup.windowFlags() & Qt.WindowType.NoDropShadowWindowHint)
                self.assertIsNone(popup.graphicsEffect())
                self.assertFalse(any(
                    child.metaObject().className() == "QComboBoxPrivateScroller"
                    for child in popup.findChildren(QWidget)
                ))
                self.combo.hidePopup()

    def test_keyboard_commit_cancel_and_signals_preserve_values(self):
        self.combo.addItem("First", "first")
        self.combo.addItem("Second", "second")
        self.combo.show()
        self.app.processEvents()
        changes = QSignalSpy(self.combo.currentIndexChanged)
        activated = QSignalSpy(self.combo.activated)
        text_activated = QSignalSpy(self.combo.textActivated)
        highlighted = QSignalSpy(self.combo.textHighlighted)
        QTest.keyClick(self.combo, Qt.Key.Key_Space)
        QTest.keyClick(self.combo.view(), Qt.Key.Key_End)
        self.assertEqual(highlighted.at(highlighted.count() - 1)[0], "Second")
        self.assertEqual(self.combo.currentData(), "first")
        QTest.keyClick(self.combo.view(), Qt.Key.Key_Escape)
        self.assertEqual(changes.count(), 0)
        QTest.keyClick(self.combo, Qt.Key.Key_Return)
        QTest.keyClick(self.combo.view(), Qt.Key.Key_Down)
        QTest.keyClick(self.combo.view(), Qt.Key.Key_Return)
        self.assertEqual(self.combo.currentData(), "second")
        self.assertEqual(changes.count(), 1)
        self.assertEqual(activated.count(), 1)
        self.assertEqual(text_activated.at(0)[0], "Second")
        self.combo.showPopup()
        QTest.keyClick(self.combo.view(), Qt.Key.Key_Return)
        self.assertEqual(changes.count(), 1)
        self.assertEqual(activated.count(), 2)

    def test_mouse_selection_and_disabled_items(self):
        view, popup = self.open_combo(6)
        self.combo.model().item(2).setEnabled(False)
        self.combo._activate_popup_index(self.combo.model().index(2, 0))
        self.assertEqual(self.combo.currentIndex(), 0)
        self.assertTrue(popup.isVisible())
        index = self.combo.model().index(3, 0)
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=view.visualRect(index).center())
        self.assertEqual(self.combo.currentData(), 30)
        self.assertFalse(popup.isVisible())
        self.combo.setEnabled(False)
        self.combo.showPopup()
        self.assertFalse(popup.isVisible())
        self.assertEqual(self.combo.cursor().shape(), Qt.CursorShape.ArrowCursor)
        self.combo.setEnabled(True)
        self.assertEqual(self.combo.cursor().shape(), Qt.CursorShape.PointingHandCursor)

    def test_closed_control_opens_with_mouse_without_changing_value(self):
        self.combo.addItems(["First", "Second"])
        self.combo.show()
        self.app.processEvents()
        QTest.mouseClick(self.combo, Qt.MouseButton.LeftButton,
                         pos=QPoint(self.combo.width() - 12, self.combo.height() // 2))
        self.app.processEvents()
        self.assertTrue(self.combo.view().window().isVisible())
        self.assertEqual(self.combo.currentIndex(), 0)

    def test_popup_in_scroll_area_does_not_change_layout_or_scroll_position(self):
        dialog = QDialog()
        layout = QVBoxLayout(dialog)
        scroll = QScrollArea()
        layout.addWidget(scroll)
        content = QWidget()
        content.setMinimumHeight(700)
        fields = QVBoxLayout(content)
        fields.addWidget(self.combo)
        fields.addStretch()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        self.combo.addItems(["First", "Second", "Third", "Fourth", "Fifth", "Sixth"])
        dialog.resize(400, 300)
        dialog.show()
        self.app.processEvents()
        geometry = dialog.geometry(), self.combo.geometry(), content.geometry()
        scroll_position = scroll.verticalScrollBar().value()
        self.combo.showPopup()
        self.app.processEvents()
        self.assertEqual((dialog.geometry(), self.combo.geometry(), content.geometry()), geometry)
        self.assertEqual(scroll.verticalScrollBar().value(), scroll_position)
        self.assertTrue(self.combo.view().window().isWindow())
        self.assertEqual(self.combo.view().viewport().height(), 6 * self.combo.popup_row_height())
        self.combo.hidePopup()
        self.combo.setParent(None)
        dialog.close()

    def test_popup_stays_on_screen_and_opens_above_bottom_edge(self):
        self.combo.addItems([f"Choice {i}" for i in range(20)])
        screen = self.combo.screen().availableGeometry()
        self.combo.move(screen.right() - 270, screen.bottom() - 65)
        self.combo.show()
        self.app.processEvents()
        self.combo.showPopup()
        self.app.processEvents()
        popup = self.combo.view().window()
        self.assertTrue(screen.contains(popup.geometry()))
        self.assertLess(popup.y(), self.combo.mapToGlobal(QPoint()).y())
        current = self.combo.currentIndex()
        self.combo.hidePopup()
        self.combo.setCurrentIndex(19)
        self.combo.showPopup()
        self.app.processEvents()
        view = self.combo.view()
        self.assertTrue(view.viewport().rect().contains(view.visualRect(view.currentIndex())))
        self.assertEqual(current, 0)

    def test_popup_reduces_rows_when_neither_side_fits_the_preferred_height(self):
        screen = QRect(0, 0, 400, 220)
        self.combo.addItems([f"Choice {i}" for i in range(20)])
        self.combo.move(20, 80)
        self.combo.show()
        with patch.object(self.combo, "screen", return_value=SimpleNamespace(availableGeometry=lambda: screen)):
            self.combo.showPopup()
        self.app.processEvents()
        popup = self.combo.view().window()
        self.assertTrue(screen.contains(popup.geometry()))
        self.assertLess(popup.height(), DROPDOWN_MAX_ROWS * self.combo.popup_row_height())
        self.assertEqual((popup.height() - 2) % self.combo.popup_row_height(), 0)
        self.assertTrue(self.combo.view().verticalScrollBar().isVisible())

    def test_outside_click_and_tab_close_without_committing(self):
        dialog = QDialog()
        layout = QVBoxLayout(dialog)
        layout.addWidget(self.combo)
        after = QLineEdit()
        layout.addWidget(after)
        layout.addStretch()
        dialog.resize(400, 300)
        self.combo.addItems(["First", "Second"])
        try:
            dialog.show()
            dialog.activateWindow()
            self.app.processEvents()
            self.combo.showPopup()
            self.app.processEvents()
            QTest.keyClick(self.combo.view(), Qt.Key.Key_End)
            QTest.mouseClick(dialog, Qt.MouseButton.LeftButton, pos=QPoint(380, 280))
            self.assertFalse(self.combo.view().window().isVisible())
            self.assertEqual(self.combo.currentIndex(), 0)
            self.combo.showPopup()
            self.app.processEvents()
            QTest.keyClick(self.combo.view(), Qt.Key.Key_Tab)
            self.app.processEvents()
            self.assertFalse(self.combo.view().window().isVisible())
            self.assertIs(self.app.focusWidget(), after)
        finally:
            self.combo.hidePopup()
            self.combo.setParent(None)
            dialog.close()

    def test_popup_dismiss_filter_releases_closed_combo(self):
        self.combo.addItems(["First", "Second"])
        self.combo.show()
        self.combo.showPopup()
        self.app.processEvents()
        self.assertIs(_dismiss_filter().active_combo(), self.combo)

        self.combo.hidePopup()
        self.app.processEvents()

        self.assertIsNone(_dismiss_filter().active_combo())

    def test_replaced_model_and_long_names_use_bounded_popup_width(self):
        model = QStandardItemModel(self.combo)
        model.appendRow(QStandardItem("An unusually long account name " * 30))
        self.combo.setModel(model)
        self.combo.show()
        self.combo.showPopup()
        self.app.processEvents()
        self.assertIs(self.combo.view().model(), model)
        self.assertGreaterEqual(self.combo.view().window().width(), self.combo.width())
        self.assertLessEqual(self.combo.view().window().width(), 420)
        self.assertEqual(self.combo.view().horizontalScrollBar().maximum(), 0)
        view = self.combo.view()
        point = view.visualRect(model.index(0, 0)).center()
        event = QHelpEvent(QEvent.Type.ToolTip, point, view.viewport().mapToGlobal(point))
        QApplication.sendEvent(view.viewport(), event)
        self.assertEqual(QToolTip.text(), model.item(0).text())
        QToolTip.hideText()

    def test_account_type_keeps_options_signals_and_dialog_geometry(self):
        from app.ui.pages.investments import InvestmentAccountDialog

        dialog = InvestmentAccountDialog()
        try:
            dialog.show()
            self.app.processEvents()
            combo = dialog.account_type
            self.assertEqual(
                [(combo.itemText(i), combo.itemData(i)) for i in range(combo.count())],
                [("General Investment", "General"), ("TFSA", "TFSA"),
                 ("FHSA", "FHSA"), ("RRSP", "RRSP")],
            )
            before = dialog.geometry(), combo.geometry()
            scrolls = dialog.findChildren(QScrollArea)
            scroll_positions = [scroll.verticalScrollBar().value() for scroll in scrolls]
            changes = QSignalSpy(combo.currentIndexChanged)
            combo.showPopup()
            self.app.processEvents()
            self.assertEqual(combo.view().viewport().height(), 4 * combo.popup_row_height())
            self.assertEqual((dialog.geometry(), combo.geometry()), before)
            self.assertEqual([s.verticalScrollBar().value() for s in scrolls], scroll_positions)
            QTest.keyClick(combo.view(), Qt.Key.Key_End)
            QTest.keyClick(combo.view(), Qt.Key.Key_Return)
            self.assertEqual(combo.currentData(), "RRSP")
            self.assertEqual(changes.count(), 1)
        finally:
            dialog.close()

    def test_date_dropdown_uses_the_same_popup(self):
        combo = DateDropdown()
        try:
            combo.addItems(["All time", "Last month", "This month"])
            combo.show()
            combo.showPopup()
            self.app.processEvents()
            self.assertEqual(combo.view().window().objectName(), "ledgerlyDropdownPopup")
            self.assertEqual(combo.view().viewport().height(), 3 * combo.popup_row_height())
        finally:
            combo.hidePopup()
            combo.close()


if __name__ == "__main__":
    unittest.main()
