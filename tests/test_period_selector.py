import os
import unittest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.ui.widgets.combo_box import AppComboBox
from app.ui.widgets.month_year_picker import (
    MonthYearItemDelegate,
    MonthYearPicker,
)
from app.ui.widgets.period_selector import PeriodSelector
from app.ui.widgets.statements_table import StatementsTable
from app.ui.pages.dashboard import DashboardPage
from app.ui.pages.goals import GoalsPage
from app.ui.pages.investments import InvestmentsPage
from app.ui.shell import ShellWindow


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
        self.assertEqual(choices, set(range(1, 13)))
        self.assertEqual(selector.year_selector.currentData(), previous_month[0])

    def test_current_month_is_shown_when_it_has_data(self):
        today = date.today()
        current_month = (today.year, today.month)

        selector = PeriodSelector()
        selector.set_available_months({current_month})

        self.assertEqual(selector.selected_month, current_month)
        self.assertEqual(selector.month_selector.count(), 12)
        self.assertEqual(selector.month_selector.currentData(), current_month[1])
        self.assertEqual(selector.year_selector.currentData(), current_month[0])

    def test_period_selector_uses_shared_month_year_picker(self):
        selector = PeriodSelector()
        selector.set_available_months({(2026, 9), (2026, 10)})

        self.assertIsInstance(selector.month_picker, MonthYearPicker)
        self.assertIsInstance(selector.month_selector, AppComboBox)
        self.assertIsInstance(
            selector.month_selector.view().itemDelegate(),
            MonthYearItemDelegate,
        )

    def test_month_picker_popup_is_flush_to_its_list(self):
        selector = PeriodSelector()
        selector.set_available_months({(2026, 10)})
        selector.show()
        selector.month_selector.showPopup()
        self.app.processEvents()
        popup_container = selector.month_selector.view().window()

        self.assertFalse(
            popup_container.testAttribute(
                Qt.WidgetAttribute.WA_TranslucentBackground
            )
        )
        self.assertTrue(
            popup_container.windowFlags()
            & Qt.WindowType.NoDropShadowWindowHint
        )
        self.assertTrue(
            popup_container.testAttribute(
                Qt.WidgetAttribute.WA_StyledBackground
            )
        )
        self.assertEqual(popup_container.objectName(), "ledgerlyDropdownPopup")
        self.assertEqual(
            popup_container.height(), selector.month_selector.view().height()
        )
        self.assertEqual(selector.month_selector.view().geometry().top(), 0)
        selector.month_selector.hidePopup()
        selector.close()

    def test_no_data_does_not_create_a_phantom_month(self):
        selector = PeriodSelector()
        selector.set_available_months(set())

        self.assertEqual(selector.month_selector.count(), 12)
        self.assertFalse(selector.month_picker.isEnabled())
        self.assertEqual(selector.period, "all")
        self.assertTrue(selector.month_picker.isHidden())

    def test_monthly_view_returns_when_data_becomes_available(self):
        today = date.today()
        previous_date = date(today.year, today.month, 1) - timedelta(days=1)
        previous_month = (previous_date.year, previous_date.month)
        selector = PeriodSelector()
        selector.set_available_months(set())

        selector.set_available_months({previous_month})

        self.assertEqual(selector.period, "monthly")
        self.assertEqual(selector.selected_month, previous_month)
        self.assertFalse(selector.month_picker.isHidden())

    def test_monthly_pages_share_the_month_year_picker(self):
        pages = (
            DashboardPage(),
            StatementsTable(),
            InvestmentsPage(),
            GoalsPage(),
        )
        try:
            self.assertTrue(all(isinstance(
                getattr(page, "month_navigator", None)
                or page.period_selector.month_picker,
                MonthYearPicker,
            ) for page in pages))
        finally:
            for page in pages:
                page.close()

    def test_explicit_month_is_not_replaced_when_months_load_later(self):
        selector = PeriodSelector()
        selector.set_selected_month((2026, 8), emit=False)

        selector.set_available_months({(2026, 9), (2026, 10)})

        self.assertEqual(selector.selected_month, (2026, 8))

    def test_shell_applies_selected_month_to_every_monthly_page(self):
        dashboard = DashboardPage()
        statements = StatementsTable()
        investments = InvestmentsPage()
        goals = GoalsPage()
        class TransactionPage:
            def __init__(self, table):
                self.statements_table = table

        transactions = TransactionPage(statements)
        shell = SimpleNamespace(
            _syncing_month_selection=False,
            _selected_month=None,
            _dirty_monthly_pages=set(),
            dashboard_page=dashboard,
            transactions_page=transactions,
            investments_page=investments,
            goals_page=goals,
            pages=SimpleNamespace(currentWidget=lambda: dashboard),
        )
        try:
            ShellWindow._set_selected_month(shell, (2026, 8))

            self.assertEqual(shell._selected_month, (2026, 8))
            self.assertEqual(dashboard.selected_month, (2026, 8))
            self.assertEqual(statements.selected_month, (2026, 8))
            self.assertEqual(
                statements.period_selector.selected_month,
                (2026, 8),
            )
            self.assertEqual(
                investments.period_selector.selected_month,
                (2026, 8),
            )
            self.assertEqual(goals.selected_month, (2026, 8))
            self.assertNotIn(dashboard, shell._dirty_monthly_pages)
            self.assertEqual(
                shell._dirty_monthly_pages,
                {transactions, investments, goals},
            )
        finally:
            for page in (dashboard, statements, investments, goals):
                page.close()

    def test_profile_application_defers_hidden_page_queries(self):
        dashboard = SimpleNamespace(
            selected_month=(2026, 8),
            set_profile=MagicMock(),
            reload=MagicMock(),
        )
        transactions = SimpleNamespace(set_profile=MagicMock())
        investments = SimpleNamespace(set_profile=MagicMock())
        accounts = SimpleNamespace(set_profile=MagicMock())
        goals = SimpleNamespace(set_profile=MagicMock())
        shell = SimpleNamespace(
            _selected_month=None,
            dashboard_page=dashboard,
            transactions_page=transactions,
            investments_page=investments,
            accounts_page=accounts,
            goals_page=goals,
            _set_selected_month=MagicMock(),
        )

        ShellWindow._apply_profile(shell, "user:test-user")

        dashboard.set_profile.assert_called_once_with(
            user_id="test-user", group_id=None
        )
        for page in (transactions, investments, accounts, goals):
            page.set_profile.assert_called_once_with(
                user_id="test-user",
                group_id=None,
                reload=False,
            )


if __name__ == "__main__":
    unittest.main()
