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

    def test_page_has_no_page_level_scroll_area_and_panels_expand(self):
        page = InvestmentsPage(session_factory=self.sessions)
        self.assertEqual(
            [scroll.objectName() for scroll in page.findChildren(QScrollArea)],
            ["investmentRecentScroll"],
        )

        page.resize(page.minimumSize())
        page.show()
        self.app.processEvents()
        compact_chart_height = page.chart.height()
        compact_table_height = page.accounts_table.height()

        page.resize(1600, 1100)
        self.app.processEvents()

        self.assertGreater(page.chart.height(), compact_chart_height)
        self.assertGreater(page.accounts_table.height(), compact_table_height)
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

        self.assertEqual(edit_button.text(), "")
        self.assertEqual(edit_button.toolTip(), "Edit investment account")
        self.assertFalse(edit_button.icon().isNull())
        self.assertEqual(delete_button.text(), "")
        self.assertEqual(delete_button.toolTip(), "Delete investment account")
        self.assertFalse(delete_button.icon().isNull())

    def test_entry_form_wraps_without_overlap_and_masks_account_number(self):
        page = InvestmentsPage(session_factory=self.sessions)
        page.set_user_id("owner")
        page.setMinimumSize(0, 0)
        page.resize(800, 760)
        page.show()
        self.app.processEvents()

        self.assertEqual(
            page.entry_form.rowWrapPolicy(),
            page.entry_form.RowWrapPolicy.WrapLongRows,
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
