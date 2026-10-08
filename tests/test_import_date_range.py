import os
import unittest
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication

from app.parsers.generic_parser import GenericParser
from app.ui.widgets.file_selection import FileSelection, previous_month_bounds


class ImportDateRangeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_range_is_optional_and_defaults_to_previous_calendar_month(self):
        selection = FileSelection()
        self.assertEqual(selection.get_date_range(), (None, None))

        selection.limit_date_range.setChecked(True)
        start, end = selection.get_date_range()
        self.assertEqual((start, end), previous_month_bounds(date.today()))

    def test_previous_month_bounds_handle_year_rollover(self):
        self.assertEqual(
            previous_month_bounds(date(2026, 1, 15)),
            (date(2025, 12, 1), date(2025, 12, 31)),
        )

    def test_invalid_range_is_rejected(self):
        selection = FileSelection()
        selection.limit_date_range.setChecked(True)
        selection.start_date.setDate(QDate(2026, 9, 30))
        selection.end_date.setDate(QDate(2026, 9, 1))
        with self.assertRaisesRegex(ValueError, "start date"):
            selection.get_date_range()

    def test_parser_range_is_inclusive(self):
        parser = GenericParser(
            [],
            start_date=date(2026, 9, 5),
            end_date=date(2026, 9, 10),
        )
        self.assertFalse(parser._date_is_selected(date(2026, 9, 4)))
        self.assertTrue(parser._date_is_selected(date(2026, 9, 5)))
        self.assertTrue(parser._date_is_selected(date(2026, 9, 10)))
        self.assertFalse(parser._date_is_selected(date(2026, 9, 11)))

    def test_parser_rejects_reverse_range(self):
        with self.assertRaisesRegex(ValueError, "start date"):
            GenericParser(
                [],
                start_date=date(2026, 9, 10),
                end_date=date(2026, 9, 5),
            )


if __name__ == "__main__":
    unittest.main()
