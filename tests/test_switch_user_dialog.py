import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QDialog

from ui.switch_user import SwitchUserDialog


class SwitchUserDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.users = [
            {"id": "one", "name": "Matt", "color": "#3397f5"},
            {"id": "two", "name": "Alyssa", "color": "#ef4a8b"},
            {"id": "three", "name": "House", "color": "#57c978"},
        ]

    def test_is_modal_and_marks_current_user(self):
        dialog = SwitchUserDialog(self.users, "one")

        self.assertTrue(dialog.isModal())
        self.assertTrue(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
        self.assertEqual(len(dialog.user_rows), 3)
        self.assertTrue(dialog.user_rows[0].property("selected"))
        self.assertFalse(dialog.user_rows[1].property("selected"))

    def test_clicking_user_emits_id_and_accepts(self):
        dialog = SwitchUserDialog(self.users, "one")
        selected = QSignalSpy(dialog.user_selected)
        dialog.show()
        self.app.processEvents()

        QTest.mouseClick(dialog.user_rows[1], Qt.MouseButton.LeftButton)

        self.assertEqual(selected.count(), 1)
        self.assertEqual(selected.at(0)[0], "two")
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_close_rejects_without_selecting(self):
        dialog = SwitchUserDialog(self.users, "one")
        selected = QSignalSpy(dialog.user_selected)

        dialog.close_button.click()

        self.assertEqual(selected.count(), 0)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)


if __name__ == "__main__":
    unittest.main()
