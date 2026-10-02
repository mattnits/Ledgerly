import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from ui.theme import ICON_ROOT, brand_icon


class BrandIconTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def assert_uses_asset(self, institution: str, filename: str) -> None:
        null_pixmap = QPixmap()
        with patch("ui.theme.QPixmap", return_value=null_pixmap) as loader:
            brand_icon(institution)
        loader.assert_called_once_with(str(ICON_ROOT / filename))

    def test_rbc_names_use_rbc_icon(self):
        for institution in ("RBC", "RBC Royal Bank", "Royal Bank of Canada"):
            with self.subTest(institution=institution):
                self.assert_uses_asset(institution, "rbc.png")

    def test_wealthsimple_names_use_wealthsimple_icon(self):
        for institution in ("Wealthsimple", "Wealthsimple Investments Inc."):
            with self.subTest(institution=institution):
                self.assert_uses_asset(institution, "wealthsimple.png")

    def test_canada_life_names_use_canada_life_icon(self):
        for institution in (
            "Canada Life",
            "Canada-Life",
            "The Canada Life Assurance Company",
        ):
            with self.subTest(institution=institution):
                self.assert_uses_asset(institution, "canada-life.png")


if __name__ == "__main__":
    unittest.main()
