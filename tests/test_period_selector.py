import os
import unittest
from datetime import date, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.ui.widgets.date_dropdown import DateDropdown, DateDropdownItemDelegate
from app.ui.widgets.period_selector import PeriodSelector


class PeriodSelectorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_uses_latest_data_month_instead_of_empty_current_month(self):
        today = date.today()
        current_month = (today.year, today.month)
        previous_date = date(today.year, today.month, 1) - timedelta(days=1)
        previous_month = (previous_date.year, previous_date.month)
        older_month = (
            previous_date.year - (previous_date.month == 1),
            (previous_date.month - 2) % 12 + 1,
        )

        selector = PeriodSelector()
        selector.set_available_months({older_month, previous_month})

        choices = {
            selector.month_selector.itemData(index)
            for index in range(selector.month_selector.count())
        }
        self.assertEqual(selector.selected_month, previous_month)
        self.assertEqual(choices, {older_month, previous_month})
        self.assertNotIn(current_month, choices)

    def test_current_month_is_shown_when_it_has_data(self):
        today = date.today()
        current_month = (today.year, today.month)

        selector = PeriodSelector()
        selector.set_available_months({current_month})

        self.assertEqual(selector.selected_month, current_month)
        self.assertEqual(selector.month_selector.count(), 1)
        self.assertEqual(selector.month_selector.currentData(), current_month)

    def test_month_picker_uses_checkmark_free_date_dropdown(self):
        selector = PeriodSelector()
        selector.set_available_months({(2026, 9), (2026, 10)})

        self.assertIsInstance(selector.month_selector, DateDropdown)
        self.assertIsInstance(
            selector.month_selector.view().itemDelegate(),
            DateDropdownItemDelegate,
        )
        self.assertFalse(selector.month_selector.itemIcon(0).isNull())

    def test_no_data_does_not_create_a_phantom_month(self):
        selector = PeriodSelector()
        selector.set_available_months(set())

        self.assertEqual(selector.month_selector.count(), 0)
        self.assertFalse(selector.month_selector.isEnabled())
        self.assertEqual(selector.period, "all")
        self.assertTrue(selector.month_selector.isHidden())

    def test_monthly_view_returns_when_data_becomes_available(self):
        today = date.today()
        previous_date = date(today.year, today.month, 1) - timedelta(days=1)
        previous_month = (previous_date.year, previous_date.month)
        selector = PeriodSelector()
        selector.set_available_months(set())

        selector.set_available_months({previous_month})

        self.assertEqual(selector.period, "monthly")
        self.assertEqual(selector.selected_month, previous_month)
        self.assertFalse(selector.month_selector.isHidden())


if __name__ == "__main__":
    unittest.main()
