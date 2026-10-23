import os
import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QScrollArea
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models.models import User
from app.services.investments import (
    create_investment_account,
    create_investment_snapshot,
)
from app.ui.pages.investments import InvestmentsPage, PortfolioEntryDialog
from app.ui.theme import APP_STYLESHEET
from app.ui.widgets.account_badge import AccountBadge
from app.ui.widgets.combo_box import FramelessPopupComboBox
from app.ui.widgets.date_picker import DatePickerEdit


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
            session.add_all((
                User(id="owner", name="Owner", color="#123456"),
                User(id="empty", name="Empty", color="#654321"),
            ))
        self.account_id = create_investment_account(
            "TD",
            "TFSA",
            account_number="ABC1234",
            user_id="owner",
            session_factory=self.sessions,
        )

    def tearDown(self):
        self.engine.dispose()

    @staticmethod
    def _grid_position(grid, widget):
        return grid.getItemPosition(grid.indexOf(widget))[:2]

    def _assert_vertically_ordered(self, parent, *widgets):
        spans = []
        for widget in widgets:
            top = widget.mapTo(parent, QPoint()).y()
            spans.append((top, top + widget.height()))
        for earlier, later in zip(spans, spans[1:]):
            self.assertLessEqual(earlier[1], later[0])

    def test_page_has_one_scroll_area_and_reflows_at_all_breakpoints(self):
        page = InvestmentsPage(session_factory=self.sessions)
        page.set_user_id("owner")
        self.assertEqual(
            [scroll.objectName() for scroll in page.findChildren(QScrollArea)],
            ["investmentsScroll"],
        )

        page.resize(480, 520)
        page.show()
        self.app.processEvents()
        self.assertEqual(page._layout_mode, "narrow")
        self.assertEqual(self._grid_position(page.summary_grid, page.gain_card), (3, 0))
        self.assertEqual(
            self._grid_position(page.chart_grid, page.account_chart_card),
            (1, 0),
        )
        self.assertEqual(
            self._grid_position(page.activity_grid, page.recent_panel),
            (1, 0),
        )
        self.assertEqual(
            self._grid_position(
                page.account_chart_card.header_grid,
                page.account_selector,
            ),
            (1, 0),
        )
        self.assertEqual(page.page_scroll.horizontalScrollBar().maximum(), 0)
        self.assertGreater(page.page_scroll.verticalScrollBar().maximum(), 0)

        page.resize(900, 700)
        self.app.processEvents()
        self.assertEqual(page._layout_mode, "medium")
        self.assertEqual(self._grid_position(page.summary_grid, page.gain_card), (1, 1))
        self.assertEqual(
            self._grid_position(page.chart_grid, page.account_chart_card),
            (1, 0),
        )
        self.assertEqual(page.page_scroll.horizontalScrollBar().maximum(), 0)

        page.resize(1600, 1000)
        self.app.processEvents()
        self.assertEqual(page._layout_mode, "wide")
        self.assertEqual(self._grid_position(page.summary_grid, page.gain_card), (0, 3))
        self.assertEqual(
            self._grid_position(page.chart_grid, page.account_chart_card),
            (0, 1),
        )
        self.assertEqual(
            self._grid_position(page.activity_grid, page.recent_panel),
            (0, 1),
        )
        self.assertEqual(page.page_scroll.horizontalScrollBar().maximum(), 0)
        page.close()

    def test_account_edit_and_delete_actions_are_icon_only_and_centered(self):
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
            edit_button = next(
                button for button in buttons
                if button.objectName() == "tableIconButton"
            )
            delete_button = next(
                button for button in buttons
                if button.objectName() == "dangerButton"
            )
            self.assertEqual(len(buttons), 2)
            self.assertEqual(edit_button.text(), "")
            self.assertEqual(edit_button.toolTip(), "Edit investment account")
            self.assertFalse(edit_button.icon().isNull())
            self.assertEqual(delete_button.text(), "")
            self.assertEqual(delete_button.toolTip(), "Delete investment account")
            self.assertFalse(delete_button.icon().isNull())

            column_center = (
                table.columnViewportPosition(5) + table.columnWidth(5) / 2
            )
            actions_center = actions.x() + actions.width() / 2
            button_left = actions.x() + min(button.x() for button in buttons)
            button_right = actions.x() + max(
                button.x() + button.width() for button in buttons
            )
            self.assertEqual(actions_center, column_center)
            self.assertEqual((button_left + button_right) / 2, column_center)
            self.assertEqual(
                table.horizontalHeaderItem(5).textAlignment(),
                Qt.AlignmentFlag.AlignCenter,
            )
        finally:
            page.close()
            self.app.setStyleSheet(previous_stylesheet)

    def test_add_entry_uses_a_modal_with_masked_account_number(self):
        page = InvestmentsPage(session_factory=self.sessions)
        page.set_user_id("owner")
        dialog = PortfolioEntryDialog(page._accounts)
        try:
            self.assertIsInstance(dialog.account, FramelessPopupComboBox)
            self.assertIsInstance(dialog.entry_date, DatePickerEdit)
            self.assertIn("***1234", dialog.account.currentText())
            self.assertNotIn("ABC1234", dialog.account.currentText())
            self.assertFalse(hasattr(page, "entry_panel"))
            dialog.total.setText("450.00")
            dialog.contribution.setText("50.00")
            dialog.exec = MagicMock(side_effect=dialog.submitted.emit)
            with patch(
                "app.ui.pages.investments.PortfolioEntryDialog",
                return_value=dialog,
            ) as dialog_class:
                page.add_entry_button.click()
            dialog_class.assert_called_once()
            dialog.exec.assert_called_once()
            self.assertEqual(page.recent_table.rowCount(), 1)
            self.assertEqual(page.recent_table.item(0, 2).text(), "$450.00")
            self.assertEqual(page.recent_table.item(0, 3).text(), "+$50.00")
        finally:
            dialog.close()
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

    def test_selected_month_drives_card_and_both_chart_end_dates(self):
        today = date.today()
        selected_month_end = date(today.year, today.month, 1) - timedelta(days=1)
        selected_date = selected_month_end.replace(day=15)
        earlier = selected_date - timedelta(days=40)
        for snapshot_date, value in (
            (earlier, "100"),
            (selected_date, "200"),
            (today, "300"),
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
            (selected_date.year, selected_date.month), emit=False
        )
        page.reload()

        expected_dates = [earlier, selected_date]
        self.assertEqual(
            [point.snapshot_datetime.date() for point in page.chart.points],
            expected_dates,
        )
        self.assertEqual(
            [point.snapshot_datetime.date() for point in page.account_chart.points],
            expected_dates,
        )
        self.assertEqual(page.chart.range_end, selected_month_end)
        self.assertEqual(page.account_chart.range_end, selected_month_end)
        self.assertEqual(page.portfolio_card.value_label.text(), "$200.00")

    def test_account_selector_filters_the_account_chart(self):
        second_id = create_investment_account(
            "Wealthsimple",
            "Long-Term Growth Account",
            account_number="XYZ5678",
            user_id="owner",
            session_factory=self.sessions,
        )
        today = date.today()
        create_investment_snapshot(
            self.account_id, today - timedelta(days=2), "100",
            session_factory=self.sessions,
        )
        create_investment_snapshot(
            second_id, today - timedelta(days=1), "250",
            session_factory=self.sessions,
        )

        page = InvestmentsPage(session_factory=self.sessions)
        page.set_user_id("owner")
        page.period_selector.set_period("all", emit=False)
        page.reload()
        second_index = page.account_selector.findData(second_id)
        page.account_selector.setCurrentIndex(second_index)
        self.app.processEvents()

        self.assertEqual(page.account_selector.currentData(), second_id)
        self.assertEqual(
            [point.total_value for point in page.account_chart.points],
            [250],
        )
        self.assertEqual(page.chart.points[-1].total_value, 350)

    def test_recent_entries_are_compact_and_do_not_add_nested_scrolling(self):
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

        self.assertEqual(page.recent_table.rowCount(), page.MAX_RECENT_ENTRIES)
        self.assertEqual(page.recent_table.verticalScrollBar().maximum(), 0)
        self.assertEqual(
            [scroll.objectName() for scroll in page.findChildren(QScrollArea)],
            ["investmentsScroll"],
        )
        page.close()

    def test_activity_tables_use_intended_padding_and_clear_rounded_bottom_corners(self):
        create_investment_snapshot(
            self.account_id,
            date.today(),
            "2500.00",
            session_factory=self.sessions,
        )
        page = InvestmentsPage(session_factory=self.sessions)
        page.set_user_id("owner")
        page.resize(1400, 900)
        page.show()
        self.app.processEvents()

        for panel, body, table, expected_margins in (
            (
                page.accounts_panel,
                page.accounts_table_body,
                page.accounts_table,
                (14, 0, 14, 10),
            ),
            (
                page.recent_panel,
                page.recent_table_body,
                page.recent_table,
                (14, 8, 14, 10),
            ),
        ):
            margins = body.layout().contentsMargins()
            self.assertEqual(
                (margins.left(), margins.top(), margins.right(), margins.bottom()),
                expected_margins,
            )
            table_top_left = table.mapTo(panel, QPoint())
            self.assertEqual(table_top_left.x(), expected_margins[0])
            self.assertGreaterEqual(
                table_top_left.y()
                - body.mapTo(panel, QPoint()).y(),
                expected_margins[1],
            )
            self.assertEqual(
                panel.width() - table_top_left.x() - table.width(),
                expected_margins[2],
            )
            self.assertGreaterEqual(
                panel.height() - table_top_left.y() - table.height(),
                expected_margins[3],
            )
        page.close()

    def test_recent_empty_state_keeps_heading_compact_and_uses_remaining_space(self):
        page = InvestmentsPage(session_factory=self.sessions)
        page.set_user_id("owner")
        page.resize(1400, 900)
        page.show()
        self.app.processEvents()

        heading = page.recent_panel.layout().itemAt(0).widget()
        title = next(
            label for label in heading.findChildren(QLabel)
            if label.text() == "Recent Portfolio Entries"
        )
        subtitle = next(
            label for label in heading.findChildren(QLabel)
            if label.text() == "Latest values and contributions for this period."
        )

        self.assertLessEqual(heading.height(), heading.sizeHint().height())
        self.assertLessEqual(subtitle.geometry().top() - title.geometry().bottom(), 2)
        self.assertEqual(
            page.recent_empty.mapTo(page.recent_panel, QPoint()).y(),
            heading.geometry().bottom()
            + 1
            + page.recent_table_body.layout().contentsMargins().top(),
        )
        self.assertGreater(page.recent_empty.height(), heading.height())
        page.close()

    def test_empty_state_has_clear_call_to_action(self):
        page = InvestmentsPage(session_factory=self.sessions)
        page.set_user_id("empty")
        page.resize(1400, 900)
        page.show()
        self.app.processEvents()

        self.assertTrue(page.empty_panel.isVisible())
        self.assertTrue(page.empty_add_account_button.isEnabled())
        self.assertFalse(page.add_entry_button.isEnabled())
        self.assertFalse(page.chart_container.isVisible())
        self.assertFalse(page.activity_container.isVisible())
        self.assertFalse(page.work_rrsp_panel.isVisible())
        self.assertEqual(len(page.empty_steps), 3)
        self.assertTrue(all(arrow.isVisible() for arrow in page.empty_step_arrows))
        self.assertEqual(
            [self._grid_position(page.empty_steps_grid, step) for step in page.empty_steps],
            [(0, 0), (0, 2), (0, 4)],
        )
        self.assertEqual(page.empty_title.text(), "No investment accounts yet")
        self.assertGreaterEqual(
            page.empty_title.height(),
            page.empty_title.fontMetrics().height(),
        )
        self._assert_vertically_ordered(
            page.empty_panel,
            page.empty_hero_icon,
            page.empty_title,
            page.empty_message,
            page.empty_add_account_button,
            page.empty_divider,
            page.empty_steps[0],
        )
        self.assertLessEqual(
            page.period_selector.geometry().top()
            - page.header.geometry().bottom(),
            page.SECTION_GAP + 2,
        )
        self.assertLessEqual(
            page.portfolio_card.geometry().top()
            - page.period_selector.geometry().bottom(),
            page.SECTION_GAP + 2,
        )
        self.assertLessEqual(
            page.empty_panel.geometry().top()
            - page.portfolio_card.geometry().bottom(),
            page.SECTION_GAP + 2,
        )
        self.assertEqual(page.page_scroll.horizontalScrollBar().maximum(), 0)

        page.resize(480, 700)
        self.app.processEvents()
        self.assertEqual(
            [self._grid_position(page.empty_steps_grid, step) for step in page.empty_steps],
            [(0, 0), (1, 0), (2, 0)],
        )
        self.assertTrue(all(arrow.isHidden() for arrow in page.empty_step_arrows))
        self.assertEqual(page.page_scroll.horizontalScrollBar().maximum(), 0)

        page.resize(360, 520)
        self.app.processEvents()
        self.assertTrue(page.empty_title.wordWrap())
        self.assertEqual(page.page_scroll.horizontalScrollBar().maximum(), 0)
        self.assertGreater(page.page_scroll.verticalScrollBar().maximum(), 0)
        self._assert_vertically_ordered(
            page.empty_panel,
            page.empty_hero_icon,
            page.empty_title,
            page.empty_message,
            page.empty_add_account_button,
            page.empty_divider,
            *page.empty_steps,
        )
        page.close()

    def test_account_selector_popup_has_no_shadow_or_padding_bands(self):
        page = InvestmentsPage(session_factory=self.sessions)
        page.set_user_id("owner")
        selector = page.account_selector
        selector.show()
        selector.showPopup()
        self.app.processEvents()

        popup = selector._popup_window
        self.assertTrue(
            popup.windowFlags() & Qt.WindowType.NoDropShadowWindowHint
        )
        self.assertTrue(popup.layout().contentsMargins().isNull())
        self.assertEqual(popup.layout().spacing(), 0)
        self.assertEqual(selector.view().geometry().top(), 0)
        self.assertEqual(selector.view().geometry().bottom(), popup.height() - 1)
        selector.hidePopup()
        page.close()

    def test_multiple_work_rrsp_accounts_render_independently_and_reflow(self):
        for index in range(2):
            create_investment_account(
                f"Employer {index}",
                f"Work RRSP {index}",
                account_number=f"RRSP{index}",
                account_type="RRSP",
                initial_date=date.today() - timedelta(days=90),
                user_id="owner",
                is_work_related=True,
                employer_matching_enabled=True,
                employer_match_percent="50",
                session_factory=self.sessions,
            )

        page = InvestmentsPage(session_factory=self.sessions)
        page.set_user_id("owner")
        page.resize(600, 700)
        page.show()
        self.app.processEvents()
        self.assertEqual(page.work_rrsp_layout.count(), 2)
        self.assertEqual(len(page._rrsp_card_grids), 2)
        for grid, cards in page._rrsp_card_grids:
            self.assertEqual(len(cards), 3)
            self.assertEqual(
                [self._grid_position(grid, card) for card in cards],
                [(0, 0), (1, 0), (2, 0)],
            )

        page.resize(1400, 900)
        self.app.processEvents()
        for grid, cards in page._rrsp_card_grids:
            self.assertEqual(
                [self._grid_position(grid, card) for card in cards],
                [(0, 0), (0, 1), (0, 2)],
            )
        page.close()

    def test_long_account_name_stays_inside_its_table_cell(self):
        create_investment_account(
            "RBC Dominion Securities",
            "A Very Long Retirement Investment Account Name",
            account_number="LONG999",
            user_id="owner",
            session_factory=self.sessions,
        )
        page = InvestmentsPage(session_factory=self.sessions)
        page.set_user_id("owner")
        page.resize(850, 700)
        page.show()
        self.app.processEvents()

        badge = next(
            page.accounts_table.cellWidget(row, 0)
            for row in range(page.accounts_table.rowCount())
            if "A Very Long Retirement"
            in page.accounts_table.cellWidget(row, 0).name_label.toolTip()
        )
        self.assertIsInstance(badge, AccountBadge)
        row = page.accounts_table.indexAt(badge.geometry().center()).row()
        cell = page.accounts_table.visualRect(page.accounts_table.model().index(row, 0))
        self.assertLessEqual(badge.geometry().right(), cell.right())
        self.assertIn("A Very Long Retirement", badge.name_label.toolTip())
        self.assertEqual(page.page_scroll.horizontalScrollBar().maximum(), 0)
        page.close()


if __name__ == "__main__":
    unittest.main()
