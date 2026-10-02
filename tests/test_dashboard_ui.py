import os
import unittest
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.components.dashboard_cards import DonutChart, InvestingCard


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


if __name__ == "__main__":
    unittest.main()
