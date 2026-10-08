import os
import unittest
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QSignalSpy

from app.services.dashboard import CategorySpending
from app.ui.widgets.dashboard_cards import (
    BudgetGoalsCard,
    CategoryCard,
    DonutChart,
    InvestingCard,
    MetricCard,
    SavingsCard,
)


class DashboardUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_donut_stroke_stays_inside_paint_bounds(self):
        width, height = 220, 160
        ring, pen_width = DonutChart._ring_geometry(width, height)
        half_stroke = pen_width / 2

        self.assertGreaterEqual(ring.left() - half_stroke, 0)
        self.assertGreaterEqual(ring.top() - half_stroke, 0)
        self.assertLessEqual(ring.right() + half_stroke, width)
        self.assertLessEqual(ring.bottom() + half_stroke, height)

    def test_savings_and_budget_cards_link_to_goals(self):
        for card in (SavingsCard(), BudgetGoalsCard()):
            spy = QSignalSpy(card.goals_requested)
            card.open_goals_button.click()

            self.assertEqual(spy.count(), 1)
            self.assertEqual(
                card.open_goals_button.accessibleName(),
                "Open Goals",
            )
            card.close()

    def test_investment_change_shows_dollars_and_percentage(self):
        card = InvestingCard()
        card.set_data(
            "All time",
            Decimal("0"),
            Decimal("1250"),
            Decimal("1000"),
            (),
            (),
        )
        self.assertEqual(card.change_label.text(), "+$250 (+25.0%)")

        card.set_data(
            "September 2026",
            Decimal("0"),
            Decimal("750"),
            Decimal("1000"),
            (),
            (),
        )
        self.assertEqual(card.change_label.text(), "-$250 (-25.0%)")

    def test_category_amounts_hide_and_restore_with_available_width(self):
        card = CategoryCard()
        card.set_data(
            "September 2026",
            (
                CategorySpending(
                    "Transportation",
                    "#3d82f0",
                    Decimal("1688"),
                ),
                CategorySpending(
                    "Net negative e-transfers",
                    "#9349ee",
                    Decimal("188"),
                ),
            ),
        )
        card.resize(800, 420)
        card.show()
        self.app.processEvents()

        self.assertTrue(card._amounts_visible)
        self.assertTrue(all(not amount.isHidden() for amount in card.amount_labels))

        card.resize(360, 420)
        self.app.processEvents()

        self.assertFalse(card._amounts_visible)
        self.assertTrue(all(amount.isHidden() for amount in card.amount_labels))

        card.resize(800, 420)
        self.app.processEvents()

        self.assertTrue(card._amounts_visible)
        self.assertTrue(all(not amount.isHidden() for amount in card.amount_labels))
        card.close()

    def test_metric_card_only_adds_person_rows_when_provided(self):
        card = MetricCard("Income", "fa6s.briefcase", "#18d98b", False)
        common_args = (
            "September 2026",
            "Total income",
            Decimal("1000"),
            Decimal("900"),
            (("Regular income", Decimal("1000")),),
            (Decimal("900"), Decimal("1000")),
        )

        card.set_data(*common_args)
        self.assertEqual(card.person_rows, [])

        card.set_data(
            *common_args,
            (("Alyssa", Decimal("400")), ("Matt", Decimal("600"))),
        )
        self.assertEqual(
            [
                (row.label_widget.text(), row.value_widget.text())
                for row in card.person_rows
            ],
            [("Alyssa", "$400"), ("Matt", "$600")],
        )
        card.close()

    def test_metric_person_breakdown_scrolls_without_growing_the_card(self):
        card = MetricCard("Spending", "fa6s.credit-card", "#ff5b63", True)
        card.resize(360, 360)
        card.set_data(
            "September 2026",
            "Total spending (after adjustments)",
            Decimal("2000"),
            Decimal("1800"),
            (("TD Credit", Decimal("2000")),),
            (Decimal("1800"), Decimal("2000")),
            tuple(
                (f"Person {index}", Decimal("100"))
                for index in range(20)
            ),
        )
        card.show()
        self.app.processEvents()

        self.assertEqual(card.height(), 360)
        self.assertGreater(card.rows_scroll.verticalScrollBar().maximum(), 0)
        card.close()


if __name__ == "__main__":
    unittest.main()
