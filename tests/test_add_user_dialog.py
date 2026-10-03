import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QSizePolicy
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

    def test_palette_and_live_preview_track_name_and_colour(self):
        dialog = AddUserDialog(session_factory=self.sessions)
        dialog.name_input.setText("Alex")
        dialog.color_swatches[4].click()

        self.assertEqual(dialog.preview_name.fullText(), "Alex")
        self.assertEqual(dialog.selected_color.name(), "#ff8a34")
        self.assertEqual(dialog.color_preview.toolTip(), "#FF8A34")
        self.assertEqual(
            sum(bool(swatch.property("selected")) for swatch in dialog.color_swatches),
            1,
        )

    def test_group_layout_resizes_without_overlap_and_members_scroll(self):
        with self.sessions.begin() as session:
            session.add_all(
                User(
                    name=f"Member {index:02d}",
                    color="#3397f5",
                )
                for index in range(14)
            )

        dialog = AddUserDialog(session_factory=self.sessions)
        dialog.group_button.click()
        dialog.show()
        self.app.processEvents()

        self.assertGreaterEqual(dialog.height(), dialog.MINIMUM_HEIGHT)
        self.assertTrue(dialog.group_button.isChecked())
        self.assertFalse(dialog.user_button.isChecked())
        self.assertEqual(
            dialog.members_scroll.sizePolicy().verticalPolicy(),
            QSizePolicy.Policy.Expanding,
        )
        self.assertGreater(dialog.members_scroll.verticalScrollBar().maximum(), 0)

        dialog.resize(dialog.minimumSize())
        self.app.processEvents()
        content_bottom = (
            dialog.content_scroll.mapTo(dialog.card, QPoint(0, 0)).y()
            + dialog.content_scroll.height()
        )
        footer_top = dialog.footer.mapTo(dialog.card, QPoint(0, 0)).y()
        self.assertLessEqual(content_bottom, footer_top)

        compact_list_height = dialog.members_scroll.height()
        dialog.resize(
            dialog.width(),
            min(dialog.maximumHeight(), dialog.minimumHeight() + 100),
        )
        self.app.processEvents()
        self.assertGreaterEqual(dialog.members_scroll.height(), compact_list_height)
        self.assertEqual(dialog.user_button.width(), dialog.group_button.width())
        dialog.close()


if __name__ == "__main__":
    unittest.main()
