import os
import unittest
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from database.dashboard import CategorySpending
from ui.components.dashboard_cards import CategoryCard, DonutChart, InvestingCard


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


if __name__ == "__main__":
    unittest.main()
