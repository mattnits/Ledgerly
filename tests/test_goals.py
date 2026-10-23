import os
import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtWidgets import QApplication, QLabel, QWidget
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.services.goals import (
    CategoryBudgetProgress,
    MonthlySavingsBreakdown,
    create_or_update_category_budget,
    create_savings_goal,
    delete_category_budget,
    delete_savings_goal,
    get_category_budgets,
    get_monthly_savings_breakdown,
    get_savings_goals,
    SavingsGoalRecord,
    set_monthly_savings_goal,
    update_savings_goal,
)
from app.services.investments import (
    create_investment_account,
    create_work_rrsp_contribution,
)
from app.models.models import (
    Account,
    Category,
    Group,
    GroupMembership,
    InvestmentAccount,
    LongTermSavingsGoal,
    MonthlyCategoryBudget,
    SavingsGoal,
    SavingsSnapshot,
    Transaction,
    User,
)
from app.ui.pages.goals import (
    BudgetDialog,
    BudgetRow,
    GoalsPage,
    MonthNavigator,
    MonthlySavingsCard,
    MonthlySavingsGoalDialog,
    ProgressRing,
    QuickStatsCard,
    SavingsGoalCard,
    SavingsGoalDialog,
)
from app.ui.theme import COLORS, apply_theme
from app.ui.widgets.date_picker import DatePickerCalendar, DatePickerEdit
from app.ui.widgets.month_year_picker import MonthYearPicker
from app.utils.constants import TransactionType


class GoalsServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.sessions = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        with self.sessions.begin() as session:
            self.user = User(id="owner", name="Owner", color="#111111")
            self.member = User(id="member", name="Member", color="#222222")
            self.group = Group(name="Household", color="#333333")
            self.salary = Category(name="Salary", color="#10b981")
            self.food = Category(name="Food", color="#f97316")
            session.add_all((self.user, self.member, self.group, self.salary, self.food))
            session.flush()
            session.add(GroupMembership(user_id=self.member.id, group_id=self.group.id))
            self.user_account = Account(
                user_id=self.user.id, name="Owner debit", institution="Test", account_type="debit"
            )
            self.member_account = Account(
                user_id=self.member.id, name="Member debit", institution="Test", account_type="debit"
            )
            session.add_all((self.user_account, self.member_account))
            session.flush()
            self.user_account_id = self.user_account.id
            self.member_account_id = self.member_account.id
            self.food_id = self.food.id
            self.group_id = self.group.id

    def tearDown(self):
        self.engine.dispose()

    def test_monthly_goal_uses_saved_rrsp_contributions_not_savings_snapshot(self):
        with self.sessions.begin() as session:
            session.add_all((
                Transaction(
                    account_id=self.user_account_id,
                    transaction_date=date(2026, 9, 2),
                    description="Pay",
                    amount=Decimal("900.00"),
                    transaction_type=TransactionType.INCOME,
                    category_id=session.scalar(select(Category.id).where(Category.name == "Salary")),
                ),
                Transaction(
                    account_id=self.user_account_id,
                    transaction_date=date(2026, 9, 5),
                    description="Food",
                    amount=Decimal("-300.00"),
                    transaction_type=TransactionType.EXPENSE,
                    category_id=self.food_id,
                ),
                SavingsSnapshot(
                    user_id="owner",
                    snapshot_date=date(2026, 9, 30),
                    amount_saved_this_month=Decimal("9999.00"),
                ),
            ))
        work_id = create_investment_account(
            "Work",
            "Work RRSP",
            account_type="RRSP",
            user_id="owner",
            is_work_related=True,
            employer_matching_enabled=True,
            employer_match_percent=Decimal("100"),
            session_factory=self.sessions,
        )
        create_work_rrsp_contribution(
            work_id,
            date(2026, 9, 15),
            Decimal("100"),
            session_factory=self.sessions,
        )
        set_monthly_savings_goal(
            2026, 9, Decimal("750"), user_id="owner", session_factory=self.sessions
        )
        result = get_monthly_savings_breakdown(
            2026, 9, user_id="owner", session_factory=self.sessions
        )
        self.assertEqual(result.income, Decimal("900.00"))
        self.assertEqual(result.spending, Decimal("300.00"))
        self.assertEqual(result.work_rrsp_employee, Decimal("100.00"))
        self.assertEqual(result.work_rrsp_employer, Decimal("100.00"))
        self.assertEqual(result.net_savings, Decimal("800.00"))
        self.assertEqual(result.target, Decimal("750.00"))

    def test_monthly_goal_carries_forward_until_a_later_change(self):
        set_monthly_savings_goal(
            2026, 10, Decimal("750"), user_id="owner", session_factory=self.sessions
        )

        september = get_monthly_savings_breakdown(
            2026, 9, user_id="owner", session_factory=self.sessions
        )
        november = get_monthly_savings_breakdown(
            2026, 11, user_id="owner", session_factory=self.sessions
        )
        january = get_monthly_savings_breakdown(
            2027, 1, user_id="owner", session_factory=self.sessions
        )

        self.assertIsNone(september.target)
        self.assertEqual(november.target, Decimal("750.00"))
        self.assertEqual(january.target, Decimal("750.00"))

        set_monthly_savings_goal(
            2026, 12, Decimal("900"), user_id="owner", session_factory=self.sessions
        )

        unchanged_november = get_monthly_savings_breakdown(
            2026, 11, user_id="owner", session_factory=self.sessions
        )
        changed_december = get_monthly_savings_breakdown(
            2026, 12, user_id="owner", session_factory=self.sessions
        )
        changed_january = get_monthly_savings_breakdown(
            2027, 1, user_id="owner", session_factory=self.sessions
        )

        self.assertEqual(unchanged_november.target, Decimal("750.00"))
        self.assertEqual(changed_december.target, Decimal("900.00"))
        self.assertEqual(changed_january.target, Decimal("900.00"))

    def test_carried_monthly_goals_remain_isolated_by_owner(self):
        set_monthly_savings_goal(
            2026, 10, Decimal("500"), user_id="owner", session_factory=self.sessions
        )
        set_monthly_savings_goal(
            2026, 11, Decimal("800"), group_id=self.group_id,
            session_factory=self.sessions,
        )

        user = get_monthly_savings_breakdown(
            2027, 2, user_id="owner", session_factory=self.sessions
        )
        group = get_monthly_savings_breakdown(
            2027, 2, group_id=self.group_id, session_factory=self.sessions
        )

        self.assertEqual(user.target, Decimal("500.00"))
        self.assertEqual(group.target, Decimal("800.00"))

    def test_budget_upsert_scope_progress_and_expense_only_filter(self):
        with self.sessions.begin() as session:
            session.add_all((
                Transaction(
                    account_id=self.user_account_id,
                    transaction_date=date(2026, 10, 5),
                    description="Food", amount=Decimal("-125"),
                    transaction_type=TransactionType.EXPENSE, category_id=self.food_id,
                ),
                Transaction(
                    account_id=self.user_account_id,
                    transaction_date=date(2026, 10, 7),
                    description="Payment", amount=Decimal("-500"),
                    transaction_type=TransactionType.CREDIT_CARD_PAYMENT, category_id=self.food_id,
                ),
                Transaction(
                    account_id=self.user_account_id,
                    transaction_date=date(2026, 10, 8),
                    description="Refund", amount=Decimal("25"),
                    transaction_type=TransactionType.REFUND_REIMBURSEMENT, category_id=self.food_id,
                ),
            ))
        create_or_update_category_budget(
            self.food_id, 2026, 10, Decimal("100"),
            user_id="owner", session_factory=self.sessions,
        )
        create_or_update_category_budget(
            self.food_id, 2026, 10, Decimal("120"),
            user_id="owner", session_factory=self.sessions,
        )
        result = get_category_budgets(
            2026, 10, user_id="owner", session_factory=self.sessions
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].spent, Decimal("125.00"))
        self.assertEqual(result[0].target, Decimal("120.00"))
        self.assertEqual(result[0].remaining, Decimal("-5.00"))
        with self.sessions() as session:
            self.assertEqual(session.query(MonthlyCategoryBudget).count(), 1)

    def test_budget_progress_normalizes_sqlite_float_aggregates(self):
        progress = CategoryBudgetProgress(
            category_id=1,
            category_name="Bills",
            category_color="#398cff",
            spent=125.5,
            target=Decimal("200.00"),
        )

        self.assertIsInstance(progress.spent, Decimal)
        self.assertEqual(progress.remaining, Decimal("74.50"))
        self.assertEqual(progress.percent, Decimal("62.7500"))

    def test_category_budgets_carry_forward_until_changed_or_removed(self):
        with self.sessions.begin() as session:
            transport = Category(name="Transportation", color="#398cff")
            session.add(transport)
            session.flush()
            transport_id = transport.id

        create_or_update_category_budget(
            self.food_id, 2026, 10, Decimal("100"),
            user_id="owner", session_factory=self.sessions,
        )
        create_or_update_category_budget(
            transport_id, 2026, 11, Decimal("200"),
            user_id="owner", session_factory=self.sessions,
        )

        self.assertEqual(
            get_category_budgets(
                2026, 9, user_id="owner", session_factory=self.sessions
            ),
            (),
        )
        october = get_category_budgets(
            2026, 10, user_id="owner", session_factory=self.sessions
        )
        november = get_category_budgets(
            2026, 11, user_id="owner", session_factory=self.sessions
        )
        self.assertEqual(
            [(item.category_name, item.target) for item in october],
            [("Food", Decimal("100.00"))],
        )
        self.assertEqual(
            [(item.category_name, item.target) for item in november],
            [
                ("Food", Decimal("100.00")),
                ("Transportation", Decimal("200.00")),
            ],
        )

        create_or_update_category_budget(
            self.food_id, 2026, 12, Decimal("150"),
            user_id="owner", session_factory=self.sessions,
        )
        january = get_category_budgets(
            2027, 1, user_id="owner", session_factory=self.sessions
        )
        self.assertEqual(
            {item.category_name: item.target for item in january},
            {
                "Food": Decimal("150.00"),
                "Transportation": Decimal("200.00"),
            },
        )

        delete_category_budget(
            self.food_id, 2027, 1,
            user_id="owner", session_factory=self.sessions,
        )
        december = get_category_budgets(
            2026, 12, user_id="owner", session_factory=self.sessions
        )
        february = get_category_budgets(
            2027, 2, user_id="owner", session_factory=self.sessions
        )
        self.assertEqual(
            {item.category_name: item.target for item in december},
            {
                "Food": Decimal("150.00"),
                "Transportation": Decimal("200.00"),
            },
        )
        self.assertEqual(
            [(item.category_name, item.target) for item in february],
            [("Transportation", Decimal("200.00"))],
        )

    def test_recurring_budget_resumes_after_existing_single_month_budget(self):
        create_or_update_category_budget(
            self.food_id,
            2026,
            9,
            Decimal("225"),
            applies_to_future=False,
            user_id="owner",
            session_factory=self.sessions,
        )

        result = create_or_update_category_budget(
            self.food_id,
            2026,
            7,
            Decimal("100"),
            applies_to_future=True,
            user_id="owner",
            session_factory=self.sessions,
        )

        self.assertEqual(result.preserved_months, ((2026, 9),))
        self.assertEqual(
            get_category_budgets(
                2026, 8, user_id="owner", session_factory=self.sessions
            )[0].target,
            Decimal("100.00"),
        )
        self.assertEqual(
            get_category_budgets(
                2026, 9, user_id="owner", session_factory=self.sessions
            )[0].target,
            Decimal("225.00"),
        )
        self.assertEqual(
            get_category_budgets(
                2026, 10, user_id="owner", session_factory=self.sessions
            )[0].target,
            Decimal("100.00"),
        )

    def test_month_only_budget_does_not_carry_forward(self):
        create_or_update_category_budget(
            self.food_id,
            2026,
            7,
            Decimal("100"),
            applies_to_future=False,
            user_id="owner",
            session_factory=self.sessions,
        )

        self.assertEqual(
            len(get_category_budgets(
                2026, 7, user_id="owner", session_factory=self.sessions
            )),
            1,
        )
        self.assertEqual(
            get_category_budgets(
                2026, 8, user_id="owner", session_factory=self.sessions
            ),
            (),
        )

    def test_database_indexes_enforce_owner_month_uniqueness(self):
        with self.sessions.begin() as session:
            session.add_all((
                SavingsGoal(
                    user_id="owner", year=2026, month=10,
                    target_amount=Decimal("100"),
                ),
                MonthlyCategoryBudget(
                    user_id="owner", category_id=self.food_id,
                    year=2026, month=10, target_amount=Decimal("100"),
                ),
            ))
        with self.assertRaises(IntegrityError):
            with self.sessions.begin() as session:
                session.add(SavingsGoal(
                    user_id="owner", year=2026, month=10,
                    target_amount=Decimal("200"),
                ))
        with self.assertRaises(IntegrityError):
            with self.sessions.begin() as session:
                session.add(MonthlyCategoryBudget(
                    user_id="owner", category_id=self.food_id,
                    year=2026, month=10, target_amount=Decimal("200"),
                ))

    def test_user_and_group_ownership_are_isolated_and_group_is_aggregated(self):
        with self.sessions.begin() as session:
            session.add(Transaction(
                account_id=self.member_account_id,
                transaction_date=date(2026, 10, 5),
                description="Food", amount=Decimal("-40"),
                transaction_type=TransactionType.EXPENSE, category_id=self.food_id,
            ))
        set_monthly_savings_goal(
            2026, 10, Decimal("50"), user_id="owner", session_factory=self.sessions
        )
        set_monthly_savings_goal(
            2026, 10, Decimal("90"), group_id=self.group_id, session_factory=self.sessions
        )
        create_or_update_category_budget(
            self.food_id, 2026, 10, Decimal("80"),
            group_id=self.group_id, session_factory=self.sessions,
        )
        user = get_monthly_savings_breakdown(
            2026, 10, user_id="owner", session_factory=self.sessions
        )
        group = get_monthly_savings_breakdown(
            2026, 10, group_id=self.group_id, session_factory=self.sessions
        )
        self.assertEqual(user.target, Decimal("50.00"))
        self.assertEqual(group.target, Decimal("90.00"))
        self.assertEqual(group.spending, Decimal("40.00"))

    def test_long_term_goal_create_edit_delete_and_owner_scope(self):
        goal_id = create_savings_goal(
            "Emergency Fund", Decimal("10000"), Decimal("2500"),
            date(2027, 12, 31), "Six months of expenses",
            user_id="owner", session_factory=self.sessions,
        )
        self.assertEqual(len(get_savings_goals(user_id="owner", session_factory=self.sessions)), 1)
        self.assertEqual(len(get_savings_goals(group_id=self.group_id, session_factory=self.sessions)), 0)
        update_savings_goal(
            goal_id, "Emergency Fund", Decimal("12000"), Decimal("3000"),
            user_id="owner", session_factory=self.sessions,
        )
        updated = get_savings_goals(user_id="owner", session_factory=self.sessions)[0]
        self.assertEqual(updated.target_amount, Decimal("12000.00"))
        self.assertEqual(updated.percent, Decimal("25.00"))
        delete_savings_goal(goal_id, user_id="owner", session_factory=self.sessions)
        with self.sessions() as session:
            self.assertIsNone(session.get(LongTermSavingsGoal, goal_id))


class GoalsPageLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_month_navigator_has_independent_month_and_year_dropdowns(self):
        navigator = MonthNavigator()
        self.assertIsInstance(navigator, MonthYearPicker)
        navigator.set_month(2026, 10)
        changes = []
        navigator.month_changed.connect(
            lambda year, month: changes.append((year, month))
        )

        self.assertEqual(navigator.month_selector.currentData(), 10)
        self.assertEqual(navigator.year_selector.currentData(), 2026)
        self.assertEqual(navigator.month_selector.accessibleName(), "Month")
        self.assertEqual(navigator.year_selector.accessibleName(), "Year")

        navigator.month_selector.setCurrentIndex(
            navigator.month_selector.findData(11)
        )
        self.assertEqual(navigator.selected_month, (2026, 11))
        self.assertEqual(changes[-1], (2026, 11))

        navigator.year_selector.setCurrentIndex(
            navigator.year_selector.findData(2027)
        )
        self.assertEqual(navigator.selected_month, (2027, 11))
        self.assertEqual(changes[-1], (2027, 11))
        navigator.close()

    def test_negative_net_savings_is_red_in_every_summary(self):
        data = MonthlySavingsBreakdown(
            income=Decimal("15"),
            spending=Decimal("9088.56"),
            work_rrsp_employee=Decimal(),
            work_rrsp_employer=Decimal(),
            net_savings=Decimal("-9073.56"),
            target=None,
        )
        monthly = MonthlySavingsCard()
        quick = QuickStatsCard()

        monthly.set_data(data, "August 2026")
        quick.set_data(data, "August 2026")

        for label in (
            monthly.actual_label,
            monthly.breakdown_values["net"],
            quick.net.value_label,
        ):
            self.assertEqual(label.property("signState"), "negative")
            self.assertIn(COLORS["negative"], label.styleSheet())

        positive = MonthlySavingsBreakdown(
            income=Decimal("1000"),
            spending=Decimal("250"),
            work_rrsp_employee=Decimal(),
            work_rrsp_employer=Decimal(),
            net_savings=Decimal("750"),
            target=None,
        )
        monthly.set_data(positive, "September 2026")
        quick.set_data(positive, "September 2026")
        for label in (
            monthly.actual_label,
            monthly.breakdown_values["net"],
            quick.net.value_label,
        ):
            self.assertEqual(label.property("signState"), "nonnegative")
            self.assertNotIn(COLORS["negative"], label.styleSheet())

        monthly.close()
        quick.close()

    def test_quick_stats_tiles_keep_icons_and_text_aligned_when_resized(self):
        quick = QuickStatsCard()
        quick.set_data(
            MonthlySavingsBreakdown(
                income=Decimal("5755"),
                spending=Decimal("2970.79"),
                work_rrsp_employee=Decimal("300"),
                work_rrsp_employer=Decimal("150"),
                net_savings=Decimal("2784.21"),
                target=Decimal("2000"),
            ),
            "September 2026",
        )

        try:
            quick.show()
            for compact, width in ((False, 560), (True, 320)):
                with self.subTest(compact=compact):
                    quick.set_compact(compact)
                    quick.resize(width, quick.sizeHint().height())
                    self.app.processEvents()

                    tiles = (
                        quick.income,
                        quick.spending,
                        quick.rrsp,
                        quick.net,
                    )
                    self.assertLessEqual(
                        max(tile.height() for tile in tiles)
                        - min(tile.height() for tile in tiles),
                        1,
                    )

                    for tile in tiles:
                        icon_position = tile.icon_label.mapTo(tile, QPoint())
                        title_position = tile.title_label.mapTo(tile, QPoint())
                        value_position = tile.value_label.mapTo(tile, QPoint())
                        detail_position = tile.detail_label.mapTo(tile, QPoint())

                        self.assertAlmostEqual(
                            icon_position.y() + tile.icon_label.height() / 2,
                            title_position.y() + tile.title_label.height() / 2,
                            delta=1.0,
                        )
                        self.assertEqual(icon_position.x(), value_position.x())
                        self.assertEqual(value_position.x(), detail_position.x())
                        self.assertEqual(
                            title_position.x(),
                            icon_position.x()
                            + tile.icon_label.width()
                            + tile.header_layout.spacing(),
                        )
                        self.assertLessEqual(
                            value_position.y()
                            - (
                                icon_position.y()
                                + tile.icon_label.height()
                            ),
                            tile.tile_layout.spacing() + 2,
                        )
                        self.assertLessEqual(
                            value_position.x() + tile.value_label.width(),
                            tile.contentsRect().right() + 1,
                        )
                        self.assertEqual(
                            tile.cursor().shape(), Qt.CursorShape.ArrowCursor
                        )

                    if not compact:
                        self.assertEqual(
                            quick.income.value_label.mapTo(quick, QPoint()).y(),
                            quick.spending.value_label.mapTo(quick, QPoint()).y(),
                        )
                        self.assertEqual(
                            quick.rrsp.value_label.mapTo(quick, QPoint()).y(),
                            quick.net.value_label.mapTo(quick, QPoint()).y(),
                        )
                        for tile in tiles:
                            for label in (
                                tile.title_label,
                                tile.value_label,
                                tile.detail_label,
                            ):
                                self.assertLessEqual(
                                    label.fontMetrics().horizontalAdvance(
                                        label.text()
                                    ),
                                    label.width(),
                                )

            self.assertEqual(quick.income.detail_label.text(), "Total income")
            self.assertEqual(quick.spending.detail_label.text(), "Total spending")
            self.assertEqual(
                quick.rrsp.detail_label.text(), "$300 you • $150 employer"
            )
            self.assertEqual(quick.net.detail_label.text(), "48% of income")
            self.assertFalse(quick.rrsp.detail_label.wordWrap())
        finally:
            quick.close()

    def test_month_change_refreshes_every_quick_stat(self):
        october = MonthlySavingsBreakdown(
            income=Decimal("1000"),
            spending=Decimal("250"),
            work_rrsp_employee=Decimal("50"),
            work_rrsp_employer=Decimal("25"),
            net_savings=Decimal("750"),
            target=None,
        )
        september = MonthlySavingsBreakdown(
            income=Decimal("5755"),
            spending=Decimal("2970.79"),
            work_rrsp_employee=Decimal("300"),
            work_rrsp_employer=Decimal("150"),
            net_savings=Decimal("2784.21"),
            target=None,
        )

        def breakdown_for_month(year, month, **_scope):
            return september if (year, month) == (2026, 9) else october

        page = GoalsPage(session_factory=self.sessions)
        try:
            with patch(
                "app.ui.pages.goals.get_monthly_savings_breakdown",
                side_effect=breakdown_for_month,
            ):
                page.month_navigator.set_month(2026, 10)
                page.set_profile(user_id="owner")
                page.month_navigator.month_selector.setCurrentIndex(
                    page.month_navigator.month_selector.findData(9)
                )
                self.app.processEvents()

            self.assertEqual(page.quick_stats.month_label.text(), "September 2026")
            self.assertEqual(page.quick_stats.income.value_label.text(), "$5,755")
            self.assertEqual(page.quick_stats.spending.value_label.text(), "$2,970.79")
            self.assertEqual(page.quick_stats.rrsp.value_label.text(), "$450")
            self.assertEqual(page.quick_stats.net.value_label.text(), "$2,784.21")
        finally:
            page.close()

    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        self.sessions = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        with self.sessions.begin() as session:
            session.add(User(id="owner", name="Owner", color="#111111"))

    def tearDown(self):
        self.engine.dispose()

    def test_monthly_goal_dialog_uses_shared_modal_structure(self):
        dialog = MonthlySavingsGoalDialog(2026, 10, Decimal("1450"))

        self.assertEqual(dialog.windowTitle(), "Monthly Savings Goal")
        self.assertEqual(dialog.title_label.text(), "Monthly Savings Goal")
        self.assertEqual(dialog.submit_button.text(), "Save Goal")
        self.assertIsNotNone(dialog.info_panel)
        self.assertEqual(dialog.amount.objectName(), "dialogMoneyInput")
        self.assertEqual(dialog.amount.value(), 1450.0)
        self.assertTrue(
            dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
        )
        dialog.close()

    def test_budget_dialog_applies_to_future_months_by_default(self):
        dialog = BudgetDialog(
            [(1, "Bills", "#398cff")],
            2026,
            7,
        )

        self.assertTrue(dialog.apply_to_future.isChecked())
        self.assertIn("future months", dialog.apply_to_future.text())
        dialog.close()

    def test_saving_goal_from_september_refreshes_page_after_dialog_closes(self):
        page = GoalsPage(session_factory=self.sessions)
        page.month_navigator.set_month(2026, 9)
        page.set_profile(user_id="owner")

        def complete_dialog(dialog):
            dialog.name.setText("September goal")
            dialog.target.setValue(1500)
            dialog.current.setValue(100)
            dialog.submitted.emit()
            return dialog.result()

        with patch.object(
            SavingsGoalDialog,
            "exec",
            new=complete_dialog,
        ):
            page._edit_long_term_goal(None)

        self.assertEqual(len(page._goal_items), 1)
        self.assertEqual(page._goal_items[0].name, "September goal")
        self.assertEqual(page._goal_items[0].target_amount, Decimal("1500.00"))
        page.close()

    def test_saving_budget_from_september_refreshes_and_carries_forward(self):
        with self.sessions.begin() as session:
            category = Category(name="Bills", color="#398cff")
            session.add(category)
            session.flush()
            category_id = category.id

        page = GoalsPage(session_factory=self.sessions)
        page.month_navigator.set_month(2026, 9)
        page.set_profile(user_id="owner")

        def complete_dialog(dialog):
            dialog.category.setCurrentIndex(
                dialog.category.findData(category_id)
            )
            dialog.amount.setValue(450)
            dialog.submitted.emit()
            return dialog.result()

        with patch.object(BudgetDialog, "exec", new=complete_dialog):
            page._edit_budget(None)

        self.assertEqual(len(page._budget_items), 1)
        self.assertEqual(page._budget_items[0].category_name, "Bills")
        self.assertEqual(page._budget_items[0].target, Decimal("450.00"))

        page.month_navigator.set_month(2026, 10)
        page.reload()
        self.assertEqual(page._budget_items[0].target, Decimal("450.00"))
        page.close()

    def test_savings_goal_dialog_uses_shared_calendar_design(self):
        dialog = SavingsGoalDialog()

        self.assertIsInstance(dialog.date, DatePickerEdit)
        self.assertIsInstance(dialog.date.calendarWidget(), DatePickerCalendar)
        self.assertEqual(dialog.date.objectName(), "datePickerEdit")
        self.assertFalse(dialog.date.isEnabled())

        dialog.has_date.setChecked(True)
        self.assertTrue(dialog.date.isEnabled())
        self.assertEqual(dialog.date.calendarWidget().today_button.text(), "Today")
        self.assertEqual(dialog.date.calendarWidget().done_button.text(), "Done")
        dialog.close()

    def test_savings_goal_card_construction_never_shows_child_windows(self):
        shown_windows: list[QWidget] = []

        class ShowFilter(QObject):
            def eventFilter(self, watched, event):  # noqa: N802 - Qt API spelling
                if (
                    event.type() == QEvent.Type.Show
                    and isinstance(watched, QWidget)
                    and watched.isWindow()
                ):
                    shown_windows.append(watched)
                return False

        event_filter = ShowFilter()
        self.app.installEventFilter(event_filter)
        try:
            card = SavingsGoalCard(SavingsGoalRecord(
                1,
                "Emergency Fund",
                Decimal("10000"),
                Decimal("1000"),
                date(2027, 12, 31),
                None,
            ))
        finally:
            self.app.removeEventFilter(event_filter)

        self.assertEqual(shown_windows, [])
        card.close()

    def test_narrow_layout_reflows_and_page_is_vertically_scrollable(self):
        page = GoalsPage(session_factory=self.sessions)
        page.set_profile(user_id="owner")
        page.resize(520, 420)
        page.show()
        self.app.processEvents()
        page._reflow()
        self.assertTrue(page._top_stacked)
        self.assertTrue(page._budget_compact)
        self.assertEqual(page._goal_columns, 1)
        self.assertTrue(page.scroll.widgetResizable())
        self.assertEqual(
            page.scroll.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        visible_text = " ".join(label.text() for label in page.findChildren(QLabel))
        self.assertNotIn("Budget Rules", visible_text)
        page.close()

    def test_summary_cards_fill_wide_row_and_reflow_across_widths(self):
        page = GoalsPage(session_factory=self.sessions)
        page.set_profile(user_id="owner")

        try:
            page.show()

            page.resize(1400, 900)
            self.app.processEvents()
            page._reflow()
            self.app.processEvents()
            self.assertFalse(page._top_stacked)
            self.assertFalse(page.quick_stats._compact)
            self.assertEqual(
                page.quick_stats.geometry().top(),
                page.monthly_card.geometry().top(),
            )
            self.assertEqual(
                page.quick_stats.geometry().bottom(),
                page.monthly_card.geometry().bottom(),
            )
            self.assertLessEqual(
                abs(
                    page.quick_stats.income.height()
                    - page.quick_stats.net.height()
                ),
                1,
            )

            page.resize(800, 900)
            self.app.processEvents()
            page._reflow()
            self.app.processEvents()
            self.assertTrue(page._top_stacked)
            self.assertFalse(page.quick_stats._compact)
            self.assertGreater(
                page.quick_stats.geometry().top(),
                page.monthly_card.geometry().bottom(),
            )
            self.assertEqual(
                page.quick_stats.width(), page.monthly_card.width()
            )

            page.resize(440, 760)
            self.app.processEvents()
            page._reflow()
            self.app.processEvents()
            self.assertTrue(page._top_stacked)
            self.assertTrue(page.quick_stats._compact)
            tile_lefts = {
                tile.mapTo(page.quick_stats, QPoint()).x()
                for tile in (
                    page.quick_stats.income,
                    page.quick_stats.spending,
                    page.quick_stats.rrsp,
                    page.quick_stats.net,
                )
            }
            self.assertEqual(len(tile_lefts), 1)
            self.assertEqual(page.scroll.horizontalScrollBar().maximum(), 0)
        finally:
            page.close()

    def test_wide_layout_matches_reference_structure(self):
        page = GoalsPage(session_factory=self.sessions)
        page.set_profile(user_id="owner")
        page.resize(1400, 900)
        page.show()
        self.app.processEvents()
        page._reflow()

        self.assertFalse(page._top_stacked)
        self.assertFalse(page._budget_compact)
        self.assertEqual(page._goal_columns, 4)
        self.assertIsInstance(page.monthly_card.ring_widget, ProgressRing)
        self.assertEqual(
            page.add_budget_button.objectName(), "secondaryActionButton"
        )
        self.assertEqual(
            page.add_goal_button.objectName(), "secondaryActionButton"
        )
        self.assertEqual(page.quick_stats.height(), page.monthly_card.height())
        self.assertEqual(
            page.quick_stats.income.height(),
            page.quick_stats.spending.height(),
        )
        self.assertEqual(
            page.quick_stats.rrsp.height(),
            page.quick_stats.net.height(),
        )
        header_icon_top = page.quick_stats.header_icon.mapTo(
            page.quick_stats, QPoint()
        ).y()
        header_title_top = page.quick_stats.title_label.mapTo(
            page.quick_stats, QPoint()
        ).y()
        header_month_top = page.quick_stats.month_label.mapTo(
            page.quick_stats, QPoint()
        ).y()
        header_center = header_icon_top + page.quick_stats.header_icon.height() / 2
        self.assertAlmostEqual(
            header_center,
            header_title_top + page.quick_stats.title_label.height() / 2,
            delta=1.0,
        )
        self.assertAlmostEqual(
            header_center,
            header_month_top + page.quick_stats.month_label.height() / 2,
            delta=1.0,
        )
        page.close()

    def test_budget_values_remain_centered_under_headers_when_resized(self):
        page = GoalsPage(session_factory=self.sessions)
        page._budget_items = tuple(
            CategoryBudgetProgress(
                category_id=index,
                category_name=name,
                category_color=color,
                spent=Decimal("210.59"),
                target=Decimal("200"),
            )
            for index, (name, color) in enumerate(
                (
                    ("Food", "#d66a1f"),
                    ("Groceries", "#18b86f"),
                    ("Household Shopping", "#9b45d4"),
                ),
                start=1,
            )
        )

        def center_x(widget: QWidget) -> float:
            left = widget.mapTo(page, QPoint(0, 0)).x()
            return left + widget.width() / 2

        try:
            page.show()
            for width, height in ((950, 650), (1400, 900)):
                page.resize(width, height)
                self.app.processEvents()
                page._reflow()
                self.app.processEvents()

                self.assertFalse(page._budget_compact)
                rows = [
                    page.budget_rows_layout.itemAt(index).widget()
                    for index in range(page.budget_rows_layout.count())
                ]
                self.assertTrue(all(isinstance(row, BudgetRow) for row in rows))
                row = rows[0]
                pairs = (
                    ("category", row.category_cell),
                    ("spent", row.spent),
                    ("budget", row.target),
                    ("remaining", row.remaining),
                )
                for name, value in pairs:
                    with self.subTest(width=width, height=height, column=name):
                        self.assertAlmostEqual(
                            center_x(page.budget_header_labels[name]),
                            center_x(value),
                            delta=1.0,
                        )

                self.assertAlmostEqual(
                    center_x(page.budget_header_labels["progress"]),
                    center_x(row.progress),
                    delta=1.0,
                )
                category_header = page.budget_header_labels["category"]
                category_header_text_left = (
                    category_header.mapTo(page, QPoint()).x()
                    + category_header.contentsMargins().left()
                )
                category_icon_left = row.category_icon.mapTo(page, QPoint()).x()
                self.assertEqual(category_header_text_left, category_icon_left)
                self.assertTrue(
                    category_header.alignment() & Qt.AlignmentFlag.AlignLeft
                )
                self.assertGreaterEqual(
                    category_header.contentsRect().width(),
                    category_header.fontMetrics().horizontalAdvance(
                        category_header.text()
                    ),
                )
                self.assertEqual(
                    row.category_icon.mapTo(page, QPoint()).x(),
                    row.mapTo(page, QPoint()).x() + BudgetRow.LEFT_MARGIN,
                )
                icon_lefts = {
                    row.category_icon.mapTo(page, QPoint(0, 0)).x()
                    for row in rows
                }
                text_lefts = {
                    row.category.mapTo(page, QPoint(0, 0)).x()
                    for row in rows
                }
                self.assertEqual(len(icon_lefts), 1)
                self.assertEqual(len(text_lefts), 1)
                self.assertTrue(
                    all(row.category.text() == row.item.category_name for row in rows)
                )
                self.assertTrue(all(not row.category.toolTip() for row in rows))
        finally:
            page.close()

    def test_budget_category_elides_and_adds_tooltip_only_on_overflow(self):
        name = "Professional Development and Continuing Education"
        row = BudgetRow(
            CategoryBudgetProgress(
                category_id=1,
                category_name=name,
                category_color="#398cff",
                spent=Decimal("0"),
                target=Decimal("200"),
            ),
            compact=False,
        )
        try:
            row.resize(620, 46)
            row.show()
            self.app.processEvents()
            self.assertTrue(row.category.text().endswith("…"))
            self.assertEqual(row.category.toolTip(), name)

            row.resize(1800, 46)
            self.app.processEvents()
            self.assertEqual(row.category.text(), name)
            self.assertEqual(row.category.toolTip(), "")
        finally:
            row.close()

    def test_fullscreen_720p_layout_fits_populated_sections_without_scrolling(self):
        with self.sessions.begin() as session:
            categories = [
                Category(name=f"Budget {index}", color="#398cff")
                for index in range(5)
            ]
            session.add_all(categories)
            session.flush()
            for category in categories:
                session.add(MonthlyCategoryBudget(
                    user_id="owner",
                    category_id=category.id,
                    year=2026,
                    month=10,
                    target_amount=Decimal("500"),
                ))
            for index in range(4):
                session.add(LongTermSavingsGoal(
                    user_id="owner",
                    name=f"Goal {index}",
                    target_amount=Decimal("1000"),
                    current_amount=Decimal("100"),
                    target_date=date(2027, 1, 1),
                ))

        previous_stylesheet = self.app.styleSheet()
        try:
            apply_theme(self.app)
            page = GoalsPage(session_factory=self.sessions)
            page.month_navigator.set_month(2026, 10)
            page.set_profile(user_id="owner")
            # Approximate the content area remaining in a maximized 1280x720
            # window after the title bar and expanded sidebar are accounted for.
            page.resize(1000, 650)
            page.show()
            self.app.processEvents()
            page._reflow()
            self.app.processEvents()

            self.assertTrue(page._dense)
            self.assertFalse(page._top_stacked)
            self.assertEqual(page._goal_columns, 4)
            self.assertEqual(page.scroll.verticalScrollBar().maximum(), 0)
            self.assertEqual(page.scroll.horizontalScrollBar().maximum(), 0)
            self.assertEqual(
                page.monthly_card.breakdown_names["employee"].text(),
                "RRSP employee",
            )
            self.assertIs(
                page.monthly_card.breakdown_frame.parentWidget(),
                page.monthly_card,
            )
            page.close()
        finally:
            self.app.setStyleSheet(previous_stylesheet)

    def test_tall_viewport_distributes_space_without_bottom_gap(self):
        page = GoalsPage(session_factory=self.sessions)
        page.set_profile(user_id="owner")
        page.resize(1500, 1100)
        page.show()
        self.app.processEvents()
        page._reflow()
        self.app.processEvents()

        bottom_gap = page.content.height() - (
            page.goals_section.geometry().bottom() + 1
        )
        self.assertLessEqual(bottom_gap, 2)
        self.assertEqual(page.content_layout.stretch(0), 5)
        self.assertEqual(page.content_layout.stretch(1), 4)
        self.assertEqual(page.content_layout.stretch(2), 4)

        title_top = page.quick_stats.title_label.mapTo(
            page.quick_stats, QPoint(0, 0)
        ).y()
        self.assertLessEqual(title_top, 26)
        tile_heights = [
            page.quick_stats.income.height(),
            page.quick_stats.spending.height(),
            page.quick_stats.rrsp.height(),
            page.quick_stats.net.height(),
        ]
        self.assertLessEqual(max(tile_heights) - min(tile_heights), 1)
        page.close()


if __name__ == "__main__":
    unittest.main()
