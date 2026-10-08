import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication

from app.__main__ import create_splash


class SplashScreenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_rounded_splash_has_transparent_window_corners(self):
        splash = create_splash()
        image = splash.pixmap().toImage()

        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
        self.assertEqual(image.pixelColor(image.width() - 1, 0).alpha(), 0)
        self.assertEqual(image.pixelColor(0, image.height() - 1).alpha(), 0)
        self.assertEqual(
            image.pixelColor(image.width() - 1, image.height() - 1).alpha(),
            0,
        )
        self.assertGreater(image.pixelColor(image.width() // 2, 1).alpha(), 0)
        self.assertTrue(
            splash.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        )
        self.assertTrue(
            splash.testAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        )
        self.assertFalse(splash.autoFillBackground())
        self.assertFalse(splash.mask().contains(QPoint(0, 0)))
        self.assertTrue(
            splash.mask().contains(
                QPoint(image.width() // 2, image.height() // 2)
            )
        )


if __name__ == "__main__":
    unittest.main()
