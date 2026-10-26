import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCalendarWidget, QToolButton

from app.ui.widgets.date_picker import DatePickerCalendar, DatePickerEdit
from app.ui.widgets.file_selection import FileSelection
from app.ui.pages.investments import InvestmentAccountDialog, PortfolioEntryDialog
from app.ui.theme import DROPDOWN_MENU_STYLE


class DatePickerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_editor_and_calendar_use_the_shared_date_picker_style(self):
        editor = DatePickerEdit(QDate(2026, 10, 2))
        calendar = editor.calendarWidget()

        self.assertTrue(editor.calendarPopup())
        self.assertEqual(editor.displayFormat(), "MMM d, yyyy")
        self.assertEqual(editor.objectName(), "datePickerEdit")
        self.assertIsInstance(calendar, DatePickerCalendar)
        self.assertEqual(calendar.objectName(), "financeDatePickerCalendar")
        self.assertFalse(calendar.isGridVisible())
        self.assertEqual(calendar.firstDayOfWeek(), Qt.DayOfWeek.Sunday)
        self.assertEqual(
            calendar.verticalHeaderFormat(),
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader,
        )
        self.assertGreaterEqual(calendar.minimumWidth(), 420)
        self.assertGreaterEqual(calendar.minimumHeight(), 404)
        self.assertEqual(calendar.today_button.text(), "Today")
        self.assertEqual(calendar.done_button.text(), "Done")

        for object_name in (
            "qt_calendar_prevmonth",
            "qt_calendar_nextmonth",
        ):
            button = calendar.findChild(QToolButton, object_name)
            self.assertIsNotNone(button)
            self.assertFalse(button.icon().isNull())

    def test_calendar_selection_updates_the_editor(self):
        editor = DatePickerEdit(QDate(2026, 10, 2))
        selected = QDate(2026, 10, 15)

        editor.calendarWidget().setSelectedDate(selected)

        self.assertEqual(editor.date(), selected)

    def test_popup_renders_with_the_custom_calendar(self):
        editor = DatePickerEdit(QDate(2026, 10, 2))
        editor.resize(300, 44)
        editor.show()
        self.app.processEvents()

        QTest.mouseClick(
            editor,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(editor.width() - 20, editor.height() // 2),
        )
        self.app.processEvents()

        calendar = editor.calendarWidget()
        self.assertTrue(calendar.isVisible())
        self.assertFalse(calendar.grab().isNull())
        popup = calendar.window()
        self.assertTrue(popup.windowFlags() & Qt.WindowType.NoDropShadowWindowHint)
        self.assertTrue(popup.contentsMargins().isNull())
        self.assertEqual(calendar.geometry().top(), 0)
        self.assertEqual(calendar.geometry().bottom(), popup.height() - 1)
        calendar.today_button.click()
        self.assertEqual(editor.date(), QDate.currentDate())
        calendar.done_button.click()
        self.app.processEvents()
        self.assertFalse(calendar.isVisible())
        editor.close()

    def test_calendar_month_menu_uses_shared_flat_style(self):
        editor = DatePickerEdit(QDate(2026, 10, 2))
        menu = editor.calendarWidget().findChild(QToolButton, "qt_calendar_monthbutton").menu()
        self.assertEqual(menu.styleSheet(), DROPDOWN_MENU_STYLE)
        self.assertTrue(menu.windowFlags() & Qt.WindowType.NoDropShadowWindowHint)
        self.assertEqual(len(menu.actions()), 12)
        editor.close()

    def test_import_and_investment_forms_use_the_shared_component(self):
        selection = FileSelection()
        account_dialog = InvestmentAccountDialog()
        entry_dialog = PortfolioEntryDialog(())
        try:
            self.assertIsInstance(selection.start_date, DatePickerEdit)
            self.assertIsInstance(selection.end_date, DatePickerEdit)
            self.assertIsInstance(account_dialog.initial_date, DatePickerEdit)
            self.assertIsInstance(entry_dialog.entry_date, DatePickerEdit)
        finally:
            selection.close()
            account_dialog.close()
            entry_dialog.close()


if __name__ == "__main__":
    unittest.main()
