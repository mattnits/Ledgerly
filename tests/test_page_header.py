import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from ui.components.page_header import PageHeader


class PageHeaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_missing_subtitle_reserves_subtitle_row(self):
        without_subtitle = PageHeader("Dashboard", action_button=QPushButton("Add"))
        with_subtitle = PageHeader(
            "Investments",
            "Subtitle",
            action_button=QPushButton("Add"),
        )

        self.assertGreater(without_subtitle.subtitle_label.sizeHint().height(), 0)
        self.assertEqual(
            without_subtitle.subtitle_label.sizeHint().height(),
            with_subtitle.subtitle_label.sizeHint().height(),
        )

    def test_subtitle_can_be_added_after_construction(self):
        header = PageHeader("Dashboard")

        header.set_subtitle("A dashboard summary.")

        self.assertEqual(header.subtitle_label.text(), "A dashboard summary.")


if __name__ == "__main__":
    unittest.main()
