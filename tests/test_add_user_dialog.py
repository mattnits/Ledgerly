import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.db import Base
from database.models import User
from ui.add_user import AddUserDialog


class AddUserDialogTest(unittest.TestCase):
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

    def tearDown(self):
        self.engine.dispose()

    def test_creates_user_emits_id_and_accepts(self):
        dialog = AddUserDialog(session_factory=self.sessions)
        created = QSignalSpy(dialog.user_created)
        dialog.name_input.setText("  Matthew  ")
        dialog.selected_color = QColor("#7654dc")
        dialog.update_color_preview()

        dialog.add_user_button.click()

        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(created.count(), 1)
        with self.sessions() as session:
            user = session.scalar(select(User))
            self.assertIsNotNone(user)
            self.assertEqual(user.id, created.at(0)[0])
            self.assertEqual(user.name, "Matthew")
            self.assertEqual(user.color, "#7654dc")

    def test_missing_name_keeps_dialog_open_without_writing(self):
        dialog = AddUserDialog(session_factory=self.sessions)
        created = QSignalSpy(dialog.user_created)

        with patch.object(QMessageBox, "warning") as warning:
            dialog.add_user_button.click()

        warning.assert_called_once()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)
        self.assertEqual(created.count(), 0)
        with self.sessions() as session:
            self.assertEqual(session.scalar(select(func.count(User.id))), 0)

    def test_cancel_and_close_buttons_reject_without_writing(self):
        for button_name in ("cancel_button", "close_button"):
            with self.subTest(button=button_name):
                dialog = AddUserDialog(session_factory=self.sessions)
                dialog.name_input.setText("Should not be saved")
                getattr(dialog, button_name).click()
                self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)

        with self.sessions() as session:
            self.assertEqual(session.scalar(select(func.count(User.id))), 0)

    def test_colour_picker_updates_swatch_and_cancel_preserves_it(self):
        dialog = AddUserDialog(session_factory=self.sessions)
        original = dialog.selected_color
        with patch(
            "ui.add_user.QColorDialog.getColor",
            return_value=QColor(),
        ):
            dialog.open_color_picker()
        self.assertEqual(dialog.selected_color, original)

        with patch(
            "ui.add_user.QColorDialog.getColor",
            return_value=QColor("#12ab34"),
        ):
            dialog.open_color_picker()
        self.assertEqual(dialog.selected_color.name(), "#12ab34")
        self.assertEqual(dialog.color_preview.toolTip(), "#12AB34")

    def test_dialog_is_modal_and_uses_compact_fixed_controls(self):
        dialog = AddUserDialog(session_factory=self.sessions)
        dialog.show()
        self.app.processEvents()

        self.assertTrue(dialog.isModal())
        self.assertTrue(
            dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
        )
        self.assertEqual(dialog.name_input.height(), 40)
        self.assertEqual(dialog.color_button.height(), 40)
        self.assertEqual(dialog.cancel_button.height(), 40)
        self.assertEqual(dialog.add_user_button.height(), 40)
        dialog.close()


if __name__ == "__main__":
    unittest.main()
