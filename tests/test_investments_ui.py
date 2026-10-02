import os
import unittest
from datetime import date, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QScrollArea
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.db import Base
from database.investments import (
    create_investment_account,
    create_investment_snapshot,
)
from database.models import User
from ui.investments import InvestmentsPage
from ui.theme import APP_STYLESHEET


class InvestmentsPageUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.sessions = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        with self.sessions.begin() as session:
            session.add(User(id="owner", name="Owner", color="#123456"))
        self.account_id = create_investment_account(
            "TD",
            "TFSA",
            account_number="ABC1234",
            user_id="owner",
            session_factory=self.sessions,
        )

    def tearDown(self):
        self.engine.dispose()

    def test_page_scrolls_and_reflows_panels_at_compact_sizes(self):
        page = InvestmentsPage(session_factory=self.sessions)
        self.assertEqual(
            [scroll.objectName() for scroll in page.findChildren(QScrollArea)],
            ["investmentsScroll", "investmentRecentScroll"],
        )

        page.resize(600, 500)
        page.show()
        self.app.processEvents()
        self.assertEqual(page.size().width(), 600)
        self.assertEqual(
            page.middle_grid.getItemPosition(
                page.middle_grid.indexOf(page.entry_panel)
            )[:2],
            (1, 0),
        )
        self.assertEqual(
            page.bottom_grid.getItemPosition(
                page.bottom_grid.indexOf(page.recent_panel)
            )[:2],
            (1, 0),
        )
        self.assertGreater(page.page_scroll.horizontalScrollBar().maximum(), 0)
        self.assertGreater(page.page_scroll.verticalScrollBar().maximum(), 0)

        page.resize(1600, 1100)
        self.app.processEvents()
        self.assertEqual(
            page.middle_grid.getItemPosition(
                page.middle_grid.indexOf(page.entry_panel)
            )[:2],
            (0, 2),
        )
        self.assertEqual(
            page.bottom_grid.getItemPosition(
                page.bottom_grid.indexOf(page.recent_panel)
            )[:2],
            (0, 2),
        )
        page.close()

    def test_account_edit_and_delete_actions_are_icon_only(self):
        page = InvestmentsPage(session_factory=self.sessions)
        page.set_user_id("owner")

        actions = page.accounts_table.cellWidget(0, 5)
        buttons = actions.findChildren(QPushButton)
        edit_button = next(
            button for button in buttons
            if button.objectName() == "tableIconButton"
        )
        delete_button = next(
            button for button in buttons
            if button.objectName() == "dangerButton"
        )

        self.assertEqual(len(buttons), 2)
        self.assertNotIn("Add Entry", (button.text() for button in buttons))
        self.assertEqual(edit_button.text(), "")
        self.assertEqual(edit_button.toolTip(), "Edit investment account")
        self.assertFalse(edit_button.icon().isNull())
        self.assertEqual(delete_button.text(), "")
        self.assertEqual(delete_button.toolTip(), "Delete investment account")
        self.assertFalse(delete_button.icon().isNull())
        page.show()
        self.app.processEvents()
        button_group_left = min(button.geometry().left() for button in buttons)
        button_group_right = max(button.geometry().right() for button in buttons)
        left_margin = button_group_left
        right_margin = actions.width() - button_group_right - 1
        self.assertLessEqual(abs(left_margin - right_margin), 1)
        self.assertEqual(
            page.accounts_table.horizontalHeaderItem(5).textAlignment(),
            Qt.AlignmentFlag.AlignCenter,
        )
        page.close()

    def test_account_actions_are_centered_in_the_rendered_column(self):
        previous_stylesheet = self.app.styleSheet()
        self.app.setStyleSheet(APP_STYLESHEET)
        page = InvestmentsPage(session_factory=self.sessions)
        try:
            page.set_user_id("owner")
            page.resize(1400, 950)
            page.show()
            self.app.processEvents()

            table = page.accounts_table
            actions = table.cellWidget(0, 5)
            buttons = actions.findChildren(QPushButton)
            column_left = table.columnViewportPosition(5)
            column_center = column_left + table.columnWidth(5) / 2
            actions_center = actions.x() + actions.width() / 2
            button_group_left = actions.x() + min(
                button.x() for button in buttons
            )
            button_group_right = actions.x() + max(
                button.x() + button.width() for button in buttons
            )
            button_group_center = (
                button_group_left + button_group_right
            ) / 2

            self.assertEqual(
                table.columnWidth(5),
                InvestmentsPage.ACCOUNT_ACTION_COLUMN_WIDTH,
            )
            self.assertEqual(actions_center, column_center)
            self.assertEqual(button_group_center, column_center)
        finally:
            page.close()
            self.app.setStyleSheet(previous_stylesheet)

    def test_entry_form_wraps_without_overlap_and_masks_account_number(self):
        page = InvestmentsPage(session_factory=self.sessions)
        page.set_user_id("owner")
        page.setMinimumSize(0, 0)
        page.resize(800, 760)
        page.show()
        self.app.processEvents()

        self.assertEqual(
            page.entry_form.rowWrapPolicy(),
            page.entry_form.RowWrapPolicy.WrapAllRows,
        )
        for field in (
            page.entry_account,
            page.entry_date,
            page.entry_total,
            page.entry_contribution,
        ):
            label = page.entry_form.labelForField(field)
            self.assertFalse(label.geometry().intersects(field.geometry()))

        self.assertIn("***1234", page.entry_account.currentText())
        self.assertNotIn("ABC1234", page.entry_account.currentText())
        page.close()

    def test_account_number_reveals_on_hover_and_can_be_pinned(self):
        page = InvestmentsPage(session_factory=self.sessions)
        page.set_user_id("owner")
        page.show()
        self.app.processEvents()
        account_number = page.accounts_table.cellWidget(0, 2)

        self.assertEqual(account_number.text(), "*******")
        QApplication.sendEvent(account_number, QEvent(QEvent.Type.Enter))
        self.assertEqual(account_number.text(), "ABC1234")
        QApplication.sendEvent(account_number, QEvent(QEvent.Type.Leave))
        self.assertEqual(account_number.text(), "*******")

        QApplication.sendEvent(account_number, QEvent(QEvent.Type.Enter))
        QTest.mouseClick(account_number, Qt.MouseButton.LeftButton)
        QApplication.sendEvent(account_number, QEvent(QEvent.Type.Leave))
        self.assertEqual(account_number.text(), "ABC1234")
        page.close()

    def test_chart_history_runs_from_earliest_entry_to_period_end(self):
        today = date.today()
        first_of_current_month = date(today.year, today.month, 1)
        previous_month = first_of_current_month - timedelta(days=1)
        earliest = date(today.year - 1, 1, 1)
        selected_date = date(previous_month.year, previous_month.month, 15)
        for snapshot_date, value in (
            (earliest, "100"),
            (selected_date, "200"),
            (today, "300"),
            (today + timedelta(days=1), "400"),
        ):
            create_investment_snapshot(
                self.account_id,
                snapshot_date,
                value,
                session_factory=self.sessions,
            )

        page = InvestmentsPage(session_factory=self.sessions)
        page.set_user_id("owner")
        page.period_selector.set_selected_month(
            (previous_month.year, previous_month.month), emit=False
        )
        page.reload()
        self.assertEqual(
            [point.snapshot_datetime.date() for point in page.chart.points],
            [earliest, selected_date],
        )
        self.assertEqual(page.chart.range_start, earliest)
        self.assertEqual(page.chart.range_end, previous_month)

        page.period_selector.set_period("all", emit=False)
        page.reload()
        self.assertEqual(
            [point.snapshot_datetime.date() for point in page.chart.points],
            [earliest, selected_date, today],
        )
        self.assertEqual(page.chart.range_start, earliest)
        self.assertEqual(page.chart.range_end, today)

    def test_recent_entries_scroll_after_four_visible_items(self):
        today = date.today()
        for offset in range(1, 7):
            create_investment_snapshot(
                self.account_id,
                today - timedelta(days=offset),
                str(100 + offset),
                session_factory=self.sessions,
            )

        page = InvestmentsPage(session_factory=self.sessions)
        page.set_user_id("owner")
        page.period_selector.set_period("all", emit=False)
        page.reload()
        page.show()
        self.app.processEvents()

        self.assertEqual(page.recent_layout.count(), 6)
        self.assertEqual(
            page.recent_scroll.height(),
            page.VISIBLE_RECENT_ENTRIES * page.RECENT_ENTRY_HEIGHT
            + (page.VISIBLE_RECENT_ENTRIES - 1) * 8,
        )
        self.assertGreater(page.recent_scroll.verticalScrollBar().maximum(), 0)
        page.close()


if __name__ == "__main__":
    unittest.main()
