import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QWidget

from app.ui.widgets.month_year_picker import MonthYearItemDelegate, MonthYearPicker


class MonthYearPickerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_previous_and_next_cross_year_boundaries(self):
        picker = MonthYearPicker()
        picker.set_period(2026, 1)

        picker.previous_button.click()
        self.assertEqual(picker.selected_period, (2025, 12))

        picker.set_period(2026, 12)
        picker.next_button.click()
        self.assertEqual(picker.selected_period, (2027, 1))
        picker.close()

    def test_month_and_year_selections_emit_selected_period(self):
        picker = MonthYearPicker()
        picker.set_period(2026, 10)
        changes = QSignalSpy(picker.period_changed)

        picker.month_selector.setCurrentIndex(
            picker.month_selector.findData(11)
        )
        picker.year_selector.setCurrentIndex(
            picker.year_selector.findData(2027)
        )

        self.assertEqual(picker.selected_period, (2027, 11))
        self.assertEqual(list(changes.at(0)), [2026, 11])
        self.assertEqual(list(changes.at(1)), [2027, 11])
        picker.close()

    def test_lists_have_only_real_months_and_years(self):
        picker = MonthYearPicker(minimum_year=2024, maximum_year=2033)

        self.assertEqual(picker.month_selector.count(), 12)
        self.assertEqual(
            [
                picker.month_selector.itemData(index)
                for index in range(picker.month_selector.count())
            ],
            list(range(1, 13)),
        )
        self.assertEqual(picker.year_selector.count(), 10)
        self.assertTrue(all(
            picker.year_selector.itemData(index) is not None
            for index in range(picker.year_selector.count())
        ))
        picker.close()

    def test_interactive_controls_use_pointer_cursor(self):
        picker = MonthYearPicker()

        for control in (
            picker.previous_button,
            picker.month_selector,
            picker.year_selector,
            picker.next_button,
        ):
            self.assertEqual(
                control.cursor().shape(), Qt.CursorShape.PointingHandCursor
            )
        picker.close()

    def test_month_popup_is_flush_and_closes_after_selection(self):
        picker = MonthYearPicker()
        picker.show()
        picker.month_selector.showPopup()
        self.app.processEvents()

        combo = picker.month_selector
        popup = combo.view().window()
        scrollers = [
            child
            for child in popup.findChildren(QWidget)
            if child.metaObject().className() == "QComboBoxPrivateScroller"
        ]
        self.assertEqual(popup.objectName(), "ledgerlyDropdownPopup")
        self.assertEqual(scrollers, [])
        self.assertEqual(popup.height(), combo.view().height())
        self.assertEqual(combo.view().geometry().top(), 0)
        self.assertEqual(
            (popup.height() - 2) % MonthYearItemDelegate.ROW_HEIGHT,
            0,
        )
        self.assertTrue(all(item.height() == 0 for item in scrollers))

        target = combo.model().index(combo.findData(6), 0)
        target_rect = combo.view().visualRect(target)
        QTest.mouseClick(
            combo.view().viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(target_rect.center()),
        )
        self.app.processEvents()
        self.assertEqual(combo.currentData(), 6)
        self.assertFalse(popup.isVisible())

        picker.year_selector.showPopup()
        self.app.processEvents()
        year_popup = picker.year_selector.view().window()
        year_field_bottom = picker.year_selector.mapToGlobal(
            picker.year_selector.rect().bottomLeft()
        ).y()
        self.assertEqual(year_popup.y(), year_field_bottom + 5)
        self.assertLessEqual(
            year_popup.height(),
            10 * MonthYearItemDelegate.ROW_HEIGHT + 2,
        )
        self.assertGreater(
            picker.year_selector.view().verticalScrollBar().maximum(), 0
        )
        current_year = picker.year_selector.model().index(
            picker.year_selector.currentIndex(), 0
        )
        self.assertTrue(
            picker.year_selector.view().viewport().rect().contains(
                picker.year_selector.view().visualRect(current_year)
            )
        )
        viewport_rect = picker.year_selector.view().viewport().rect()
        visible_rows = 0
        for row in range(picker.year_selector.count()):
            item_rect = picker.year_selector.view().visualRect(
                picker.year_selector.model().index(row, 0)
            )
            if item_rect.intersects(viewport_rect):
                visible_rows += 1
                self.assertTrue(viewport_rect.contains(item_rect))
        self.assertEqual(visible_rows, 10)
        picker.year_selector.hidePopup()
        picker.close()

    def test_navigation_controls_have_spacing_and_are_not_clipped(self):
        picker = MonthYearPicker(compact=True)
        picker.show()
        self.app.processEvents()

        self.assertGreaterEqual(picker.layout().spacing(), 6)
        self.assertEqual(
            picker.display.geometry().left()
            - picker.previous_button.geometry().right()
            - 1,
            6,
        )
        self.assertEqual(
            picker.next_button.geometry().left()
            - picker.display.geometry().right()
            - 1,
            6,
        )
        self.assertTrue(
            picker.display.contentsRect().contains(
                picker.year_selector.geometry()
            )
        )
        self.assertEqual(picker.previous_button.size(), picker.next_button.size())
        picker.close()


if __name__ == "__main__":
    unittest.main()
